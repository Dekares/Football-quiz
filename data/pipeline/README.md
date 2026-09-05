# Transfermarkt canonical data pipeline

This pipeline keeps API acquisition, canonical football facts and the Careerdle
read model separate. It publishes `data/football_quiz_v2.db` only after
validation succeeds.

## Databases

- `data/transfermarkt_source.db`: mutable WAL database containing the persistent
  crawl queue, raw JSON snapshots, normalized entities, transfers, market values,
  derived club periods and quality reports.
- `data/football_quiz_v2.db`: immutable, legacy-compatible game artifact produced
  only after validation succeeds.

## Pilot run

The locally hosted Transfermarkt API must be available at `http://localhost:8000`.

```powershell
python -m data.pipeline init
python -m data.pipeline seed --competitions GB1 --seasons 2025
python -m data.pipeline work --limit 100 --concurrency 2
python -m data.pipeline status
python -m data.pipeline derive
python -m data.pipeline repair
python -m data.pipeline legend-update --base-url http://localhost:8000
python -m data.pipeline work --concurrency 2
python -m data.pipeline validate
python -m data.pipeline publish --allow-incomplete
```

For a small player-level smoke test without crawling a competition:

```powershell
python -m data.pipeline seed-player --players 28003
python -m data.pipeline work --limit 3 --concurrency 1
python -m data.pipeline derive
python -m data.pipeline publish --allow-incomplete
```

`--allow-incomplete` is only for small pilot datasets. A production publish omits
that option and therefore requires non-empty known/less-known/obscure solo pools
for every published competition, plus club-pair candidates.

Seed and worker execution can be combined:

```powershell
python -m data.pipeline crawl `
  --competitions GB1,ES1,IT1,L1,FR1 `
  --seasons 2025 `
  --concurrency 2
```

The queue is persistent and idempotent. Interrupted runs resume with `work`.
Completed discovery jobs are only repeated when `seed --refresh` is used.

## Legend identities

`data/sources/legend_candidates.txt` contains curated identity records, not
profiles, club histories, career dates or market values. The normal format is
`Name`; ambiguous names must use `Name|Transfermarkt ID`. `legend-update`
resolves those records through `/players/search`, requires exactly one matching
identity, and enqueues the standard profile, transfer and market-value jobs. An
unpinned name with multiple exact search results is rejected instead of trusting
search-result order. A sync is applied only when at least 80% of candidates
resolve, so a partial API outage cannot replace the working legend set. Use
`--refresh` to resolve identities again and `--refresh-details` when completed
detail jobs must also be requeued.

The Legends game option ignores recognition buckets and accepts one-club players.
World XI compares each active player's global and league recognition buckets and
uses the easier classification. A player is Obscure only when both rankings say
Obscure. The curated `world_xi_legend_pool` is then added to Known, and retired
legends never leak into Less Known or Obscure.

Every published player also receives a derived `career_status` on each build:

- `retired_legend`: a curated legend who is not in a current tracked squad;
- `active_legend`: an active player aged at least 32 with at least 12 career
  years, a recognition score of at least 75, and either eight elite-club years
  or a peak market value of at least EUR 100 million;
- `active_star`: any other active player with a recognition score of at least 65;
- `regular`: everyone else.

This field is derived rather than edited manually, so an aging star keeps the
weight of their historical career after moving to a weaker club or league. A
single expensive season cannot create an active legend. Realtime question
selection also prioritizes both active and retired legends before current stars.

## Recognition calibration

Recognition combines peak and current market value, merged career duration,
time spent at high-prestige clubs and a small club-breadth signal. A normal
one-club player is excluded from the career quiz, while a one-club player scoring
at least 65 remains eligible so globally recognizable players are not lost.

League Known pools combine a league-relative baseline with an absolute recognition
score. Tier-one leagues include at least the leading 18% and every player scoring
55 or more. Tier-two leagues include at least the leading 10% and every player
scoring 50 or more. The result is bounded to at most one third of the eligible
league pool and 160 players. World XI's active Known pool remains roughly the top
2.5%, capped at 150; every league's Known players and the curated iconic
retired-player pool are added separately.
Daily challenges use only the first 75 active players from that global ranking.
Published history and the current day remain fixed; future dates are rebuilt
chronologically on each publish so the same player cannot recur inside the
60-day window.

## Publication contract

Publishing performs these checks before replacing the target artifact:

- canonical and game foreign-key checks have no violations;
- no inverted player-club period exists;
- configured minimum player and period counts are met;
- every player belongs to one current competition and exactly one recognition
  bucket inside that competition;
- known, less-known and obscure pools are non-empty for every published league;
- every active league player belongs to exactly one independently ranked global
  recognition bucket used by the World XI option;
- active stars, active legends and retired legends are non-empty, retired
  legends stay out of the active global pool, the Legends option contains only
  `retired_legend` players, and World XI's curated legend pool contains no active
  or regular players;
- the persistent daily schedule starts at `2026-07-01`, has valid sequential day
  numbers, has no future repeat inside 60 days and covers at least the next 30
  Türkiye-calendar days;
- production quiz pools and club-pair candidates are non-empty;
- no open canonical `error` issue remains.

The output is first built as `<output>.new`. If validation fails, the temporary
file is deleted and the existing output is untouched. Existing successful output
is backed up before the atomic replacement.

## Major-league updates

`major_leagues.json` defines a two-tier major-league scope, including MLS and the
Saudi Pro League. The updater derives split-year or calendar-year seasons,
accepts the actual season returned by the API when the source lags, and refreshes competition and
roster discovery daily. A normal incremental run fetches profiles for newly
discovered players and transfer histories for new or newly transferred players.
Full player-detail refreshes remain available through `--force`.

```powershell
# Fast core update: profiles + transfers, then strict publish
python -m data.pipeline major-update --tiers 1,2 --concurrency 8 `
  --request-interval 5.5

# Enrich newly discovered players with market-value history
python -m data.pipeline major-update --tiers 1,2 --with-market-values `
  --request-interval 5.5 --min-players 5400 --min-periods 50000

# Planned full profile, transfer and market-value refresh
python -m data.pipeline major-update --tiers 1,2 --force --with-market-values `
  --request-interval 5.5 --min-players 5400 --min-periods 50000

# Discover competitions, clubs and roster IDs without player-detail calls
python -m data.pipeline major-update --tiers 1,2 --discovery-only
```

The core update still derives highest known values from transfer facts. Market
value history is an enrichment and can be scheduled separately. The request
interval is shared across worker threads and prevents the local API from
overloading Transfermarkt. `--force` ignores endpoint TTLs and performs a full
refresh; it should be reserved for planned maintenance windows.
