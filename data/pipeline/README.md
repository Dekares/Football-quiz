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
python -m data.pipeline import-legends
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

## Publication contract

Publishing performs these checks before replacing the target artifact:

- canonical and game foreign-key checks have no violations;
- no inverted player-club period exists;
- configured minimum player and period counts are met;
- every player belongs to one current competition and exactly one recognition
  bucket inside that competition;
- known, less-known and obscure pools are non-empty for every published league;
- every active league player belongs to exactly one independently ranked global
  recognition bucket used by the All Leagues option;
- the persistent daily schedule starts at `2026-07-01`, has valid sequential day
  numbers and covers at least the next 30 Türkiye-calendar days;
- production quiz pools and club-pair candidates are non-empty;
- no open canonical `error` issue remains.

The output is first built as `<output>.new`. If validation fails, the temporary
file is deleted and the existing output is untouched. Existing successful output
is backed up before the atomic replacement.

## Major-league updates

`major_leagues.json` defines a two-tier major-league scope, including MLS and the
Saudi Pro League. The updater derives split-year or calendar-year seasons,
accepts the actual season returned by the API when the source lags, and refreshes competition and
roster discovery daily, transfers daily, profiles every 30 days and market-value
history every 7 days.

```powershell
# Fast core update: profiles + transfers, then strict publish
python -m data.pipeline major-update --tiers 1,2 --concurrency 2

# Include full market-value history and enforce production-size gates
python -m data.pipeline major-update --tiers 1,2 --with-market-values `
  --min-players 5400 --min-periods 50000

# Discover competitions, clubs and roster IDs without player-detail calls
python -m data.pipeline major-update --tiers 1,2 --discovery-only
```

The core update still derives highest known values from transfer facts. Market
value history is an enrichment and can be scheduled separately. `--force` ignores
endpoint TTLs; normal scheduled runs only enqueue stale resources.
