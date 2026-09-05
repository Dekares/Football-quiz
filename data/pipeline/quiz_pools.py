"""League-aware solo quiz pool generation."""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).with_name("major_leagues.json")
RECOGNITIONS = ("known", "less_known", "obscure")
LEAGUE_BUCKET_RATIOS = (0.06, 0.30)
GLOBAL_BUCKET_RATIOS = (0.025, 0.25)
LEAGUE_KNOWN_RATIO_BY_TIER = {1: 0.18, 2: 0.10}
LEAGUE_KNOWN_CAP = 160
GLOBAL_KNOWN_CAP = 150
ONE_CLUB_STAR_SCORE = 65
ACTIVE_STAR_SCORE = 65
ACTIVE_LEGEND_MIN_AGE = 32
ACTIVE_LEGEND_MIN_CAREER_YEARS = 12
ACTIVE_LEGEND_MIN_SCORE = 75
ACTIVE_LEGEND_MIN_ELITE_YEARS = 8
ACTIVE_LEGEND_HIGH_PEAK_VALUE = 100_000_000
WORLD_XI_LEGEND_MIN_SCORE = 75
HISTORIC_WORLD_XI_LEGEND_IDS = {
    206, 1527, 3187, 3465, 3516, 3521, 3624, 4153, 4168, 5758,
    5775, 5803, 5937, 7942, 8021, 8023, 8024, 8542, 12000, 17121,
    22256, 35604, 42049, 70667, 72347, 74471, 80568, 101045,
    117619, 117633, 229662,
}
LEGACY_DIFFICULTY = {
    "known": "easy",
    "less_known": "medium",
    "obscure": "hard",
}
YOUTH_CLUB_PATTERN = re.compile(
    r"\b(?:u1[5-9]|u2[0-3]|under 1[5-9]|under 2[0-3]|youth|yth|academy|"
    r"reserves?|primavera|castilla|juvenil|b team)\b"
)


def meaningful_club(name: str | None) -> bool:
    if not name:
        return False
    normalized = name.casefold().replace("-", " ")
    return not YOUTH_CLUB_PATTERN.search(normalized)


def recognition_score(
    highest_market_value: int | None,
    max_club_prestige: int,
    meaningful_clubs: int,
    is_legend: bool,
    *,
    current_market_value: int | None = None,
    elite_club_years: float = 0.0,
    career_years: float = 0.0,
) -> int:
    """Return a deterministic 0-100 recognition score.

    Peak value remains a useful signal, but exposure and longevity prevent a
    newly expensive player from automatically outranking an established star.
    """
    peak_value = highest_market_value or 0
    peak_points = 1
    for threshold, points in (
        (150_000_000, 50),
        (100_000_000, 47),
        (80_000_000, 43),
        (60_000_000, 38),
        (50_000_000, 34),
        (40_000_000, 30),
        (30_000_000, 25),
        (20_000_000, 19),
        (12_000_000, 13),
        (7_000_000, 8),
        (3_000_000, 4),
    ):
        if peak_value >= threshold:
            peak_points = points
            break

    current_value = current_market_value or 0
    if current_value >= 100_000_000:
        current_points = 8
    elif current_value >= 60_000_000:
        current_points = 6
    elif current_value >= 35_000_000:
        current_points = 4
    elif current_value >= 15_000_000:
        current_points = 2
    else:
        current_points = 0

    if max_club_prestige >= 40:
        prestige_points = 10
    elif max_club_prestige >= 20:
        prestige_points = 8
    elif max_club_prestige >= 10:
        prestige_points = 5
    elif max_club_prestige >= 5:
        prestige_points = 3
    else:
        prestige_points = 1

    if elite_club_years >= 8:
        exposure_points = 15
    elif elite_club_years >= 5:
        exposure_points = 12
    elif elite_club_years >= 3:
        exposure_points = 9
    elif elite_club_years >= 1:
        exposure_points = 5
    elif elite_club_years > 0:
        exposure_points = 2
    else:
        exposure_points = 0

    if career_years >= 12:
        longevity_points = 7
    elif career_years >= 8:
        longevity_points = 5
    elif career_years >= 5:
        longevity_points = 3
    elif career_years >= 2:
        longevity_points = 1
    else:
        longevity_points = 0

    if meaningful_clubs >= 7:
        breadth_points = 3
    elif meaningful_clubs >= 4:
        breadth_points = 2
    elif meaningful_clubs >= 3:
        breadth_points = 1
    else:
        breadth_points = 0

    return min(
        100,
        peak_points
        + current_points
        + prestige_points
        + exposure_points
        + longevity_points
        + breadth_points
        + (20 if is_legend else 0),
    )


def _league_config() -> list[dict[str, Any]]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return list(config["leagues"])


def _current_assignments(
    source: sqlite3.Connection,
    competition_ids: list[str],
) -> dict[int, str]:
    """Choose one current competition per player from the latest roster snapshots."""
    candidates: dict[int, list[tuple[int, str, int, str]]] = defaultdict(list)
    order = {competition_id: index for index, competition_id in enumerate(competition_ids)}
    for competition_id in competition_ids:
        season = source.execute(
            """
            SELECT season_id
            FROM competition_seasons
            WHERE competition_id = ?
            ORDER BY discovered_at DESC, season_id DESC
            LIMIT 1
            """,
            (competition_id,),
        ).fetchone()
        if not season:
            continue
        season_id = season["season_id"]
        rows = source.execute(
            """
            SELECT r.player_id, r.club_id, r.discovered_at, p.current_club_id
            FROM club_rosters r
            JOIN competition_clubs cc
              ON cc.club_id = r.club_id AND cc.season_id = r.season_id
            JOIN players p ON p.player_id = r.player_id
            WHERE cc.competition_id = ? AND r.season_id = ?
            """,
            (competition_id, season_id),
        ).fetchall()
        for row in rows:
            candidates[row["player_id"]].append((
                1 if row["current_club_id"] == row["club_id"] else 0,
                row["discovered_at"] or "",
                -order[competition_id],
                competition_id,
            ))
    return {
        player_id: max(player_candidates)[3]
        for player_id, player_candidates in candidates.items()
    }


def _covered_years(intervals: list[tuple[date, date]]) -> float:
    if not intervals:
        return 0.0
    merged: list[list[date]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        elif end > merged[-1][1]:
            merged[-1][1] = end
    return sum((end - start).days for start, end in merged) / 365.25


def _age(date_of_birth: str | None, today: date | None = None) -> int | None:
    if not date_of_birth:
        return None
    try:
        born = date.fromisoformat(date_of_birth[:10])
    except ValueError:
        return None
    today = today or date.today()
    return today.year - born.year - (
        (today.month, today.day) < (born.month, born.day)
    )


def classify_career_status(
    metrics: dict[str, Any],
    *,
    is_active: bool,
    today: date | None = None,
) -> str:
    """Separate current stars, active career legends and retired legends.

    The active-legend rule deliberately requires several sustained-career
    signals. A single high transfer value or one good season is insufficient.
    """
    if not is_active:
        return "retired_legend" if metrics["is_legend"] else "regular"
    if metrics["is_legend"]:
        return "active_legend"

    age = _age(metrics.get("date_of_birth"), today)
    sustained_elite_career = bool(
        age is not None
        and age >= ACTIVE_LEGEND_MIN_AGE
        and metrics["career_years"] >= ACTIVE_LEGEND_MIN_CAREER_YEARS
        and metrics["score"] >= ACTIVE_LEGEND_MIN_SCORE
        and (
            metrics["elite_club_years"] >= ACTIVE_LEGEND_MIN_ELITE_YEARS
            or metrics["highest_market_value"] >= ACTIVE_LEGEND_HIGH_PEAK_VALUE
        )
    )
    if sustained_elite_career:
        return "active_legend"
    if metrics["score"] >= ACTIVE_STAR_SCORE:
        return "active_star"
    return "regular"


def _player_metrics(game: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    players = {
        row["player_id"]: {
            "player_id": row["player_id"],
            "name": row["name"],
            "current_market_value": row["market_value"] or 0,
            "highest_market_value": row["highest_market_value"] or 0,
            "is_legend": bool(row["is_legend"]),
            "position": row["position"],
            "country": row["country_of_citizenship"],
            "date_of_birth": row["date_of_birth"],
            "meaningful_clubs": 0,
            "max_prestige": 0,
            "elite_club_years": 0.0,
            "career_years": 0.0,
        }
        for row in game.execute(
            """
            SELECT player_id, name, market_value, highest_market_value, is_legend, position,
                   country_of_citizenship, date_of_birth
            FROM players
            """
        )
    }
    seen_clubs: dict[int, set[int]] = defaultdict(set)
    career_intervals: dict[int, list[tuple[date, date]]] = defaultdict(list)
    elite_intervals: dict[int, list[tuple[date, date]]] = defaultdict(list)
    today = date.today()
    for row in game.execute(
        """
        SELECT pc.player_id, pc.date_from, pc.date_to,
               c.club_id, c.name, c.prestige_score
        FROM player_clubs pc JOIN clubs c ON c.club_id = pc.club_id
        """
    ):
        metrics = players.get(row["player_id"])
        if not metrics or not meaningful_club(row["name"]):
            continue
        seen_clubs[row["player_id"]].add(row["club_id"])
        metrics["max_prestige"] = max(metrics["max_prestige"], row["prestige_score"])
        if not row["date_from"]:
            continue
        try:
            start = date.fromisoformat(row["date_from"][:10])
            end = date.fromisoformat(row["date_to"][:10]) if row["date_to"] else today
        except ValueError:
            continue
        if end <= start:
            continue
        career_intervals[row["player_id"]].append((start, end))
        if row["prestige_score"] >= 20:
            elite_intervals[row["player_id"]].append((start, end))
    for player_id, club_ids in seen_clubs.items():
        players[player_id]["meaningful_clubs"] = len(club_ids)
        players[player_id]["career_years"] = _covered_years(career_intervals[player_id])
        players[player_id]["elite_club_years"] = _covered_years(elite_intervals[player_id])
    for metrics in players.values():
        metrics["score"] = recognition_score(
            metrics["highest_market_value"],
            metrics["max_prestige"],
            metrics["meaningful_clubs"],
            metrics["is_legend"],
            current_market_value=metrics["current_market_value"],
            elite_club_years=metrics["elite_club_years"],
            career_years=metrics["career_years"],
        )
    return players


def _eligible(metrics: dict[str, Any], *, legend: bool = False) -> bool:
    if not metrics["position"] or not metrics["country"]:
        return False
    if legend:
        return metrics["meaningful_clubs"] >= 1
    return bool(
        metrics["meaningful_clubs"] >= 2
        or (
            metrics["meaningful_clubs"] == 1
            and metrics["score"] >= ONE_CLUB_STAR_SCORE
        )
    )


def _ranked_buckets(
    players: list[dict[str, Any]],
    ratios: tuple[float, float] = LEAGUE_BUCKET_RATIOS,
    known_cap: int | None = LEAGUE_KNOWN_CAP,
    known_min_score: int | None = None,
    known_min_count: int = 1,
) -> dict[str, list[dict[str, Any]]]:
    ranked = sorted(
        players,
        key=lambda item: (
            -item["score"],
            -item["highest_market_value"],
            item["name"].casefold(),
            item["player_id"],
        ),
    )
    total = len(ranked)
    if total < 3:
        return {"known": ranked, "less_known": [], "obscure": []}
    known_count = max(1, round(total * ratios[0]))
    if known_min_score is not None:
        qualified = sum(item["score"] >= known_min_score for item in ranked)
        known_count = max(known_count, known_min_count, qualified)
    if known_cap is not None:
        known_count = min(known_count, known_cap)
    known_count = min(known_count, max(1, total // 3), total - 2)
    less_count = max(1, round(total * ratios[1]))
    if known_count + less_count >= total:
        less_count = max(1, total - known_count - 1)
    return {
        "known": ranked[:known_count],
        "less_known": ranked[known_count:known_count + less_count],
        "obscure": ranked[known_count + less_count:],
    }


def build_quiz_pools(
    source: sqlite3.Connection,
    game: sqlite3.Connection,
) -> dict[str, Any]:
    """Populate competitions and mutually-exclusive league/recognition pools."""
    config = _league_config()
    config_ids = [item["competition_id"] for item in config]
    assignments = _current_assignments(source, config_ids)
    metrics = _player_metrics(game)

    source_competitions = {
        row["competition_id"]: row
        for row in source.execute(
            "SELECT competition_id, name, country FROM competitions"
        )
    }
    seasons = {}
    for item in config:
        competition_id = item["competition_id"]
        row = source.execute(
            """
            SELECT season_id FROM competition_seasons
            WHERE competition_id = ?
            ORDER BY discovered_at DESC, season_id DESC LIMIT 1
            """,
            (competition_id,),
        ).fetchone()
        seasons[competition_id] = row["season_id"] if row else None

    competition_rows = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for player_id, competition_id in assignments.items():
        player = metrics.get(player_id)
        if player and _eligible(player):
            grouped[competition_id].append(player)

    active_ids = set(assignments)
    status_rows = []
    for player_id, player in metrics.items():
        player["career_status"] = classify_career_status(
            player,
            is_active=player_id in active_ids,
        )
        status_rows.append((player["career_status"], player_id))
    game.executemany(
        "UPDATE players SET career_status = ? WHERE player_id = ?",
        status_rows,
    )
    legends = [
        player for player_id, player in metrics.items()
        if player["is_legend"] and player_id not in active_ids and _eligible(player, legend=True)
    ]
    if legends:
        grouped["LEGENDS"] = legends

    world_xi_legends = sorted(
        (
            player for player in legends
            if player["score"] >= WORLD_XI_LEGEND_MIN_SCORE
            or player["player_id"] in HISTORIC_WORLD_XI_LEGEND_IDS
        ),
        key=lambda player: (
            -player["score"],
            -player["highest_market_value"],
            player["name"].casefold(),
            player["player_id"],
        ),
    )
    game.executemany(
        "INSERT INTO world_xi_legend_pool VALUES (?,?,?)",
        (
            (player["player_id"], player["score"], rank)
            for rank, player in enumerate(world_xi_legends, 1)
        ),
    )

    for index, item in enumerate(config):
        competition_id = item["competition_id"]
        if not grouped.get(competition_id):
            continue
        source_item = source_competitions.get(competition_id)
        competition_rows.append((
            competition_id,
            (source_item["name"] if source_item and source_item["name"] else item["name"]),
            (source_item["country"] if source_item and source_item["country"] else item["country"]),
            seasons[competition_id],
            index,
            0,
        ))
    if legends:
        competition_rows.append((
            "LEGENDS", "Career Legends", "International", None, len(config), 1,
        ))
    game.executemany(
        "INSERT INTO competitions VALUES (?,?,?,?,?,?)",
        competition_rows,
    )

    pool_rows = []
    report: dict[str, Any] = {}
    league_config = {item["competition_id"]: item for item in config}
    for competition_id, league_players in grouped.items():
        item = league_config.get(competition_id)
        if item is None:
            buckets = _ranked_buckets(league_players)
        else:
            tier = int(item["tier"])
            tier_one = tier == 1
            buckets = _ranked_buckets(
                league_players,
                ratios=(LEAGUE_KNOWN_RATIO_BY_TIER[tier], LEAGUE_BUCKET_RATIOS[1]),
                known_min_score=55 if tier_one else 50,
                known_min_count=30 if tier_one else 5,
            )
        report[competition_id] = {"total": len(league_players), "counts": {}}
        for recognition in RECOGNITIONS:
            bucket = buckets[recognition]
            report[competition_id]["counts"][recognition] = len(bucket)
            report[competition_id][recognition] = {
                "highest": [item["name"] for item in bucket[:3]],
                "lowest": [item["name"] for item in bucket[-3:]],
            }
            for rank, player in enumerate(bucket, 1):
                pool_rows.append((
                    competition_id,
                    recognition,
                    LEGACY_DIFFICULTY[recognition],
                    player["player_id"],
                    player["score"],
                    rank,
                ))
    game.executemany(
        "INSERT INTO quiz_pool VALUES (?,?,?,?,?,?)",
        pool_rows,
    )

    global_players = [
        metrics[player_id]
        for player_id in assignments
        if player_id in metrics and _eligible(metrics[player_id])
    ]
    global_buckets = _ranked_buckets(
        global_players,
        GLOBAL_BUCKET_RATIOS,
        GLOBAL_KNOWN_CAP,
    )
    global_rows = []
    global_report = {"total": len(global_players), "counts": {}}
    for recognition in RECOGNITIONS:
        bucket = global_buckets[recognition]
        global_report["counts"][recognition] = len(bucket)
        global_report[recognition] = {
            "highest": [item["name"] for item in bucket[:3]],
            "lowest": [item["name"] for item in bucket[-3:]],
        }
        for rank, player in enumerate(bucket, 1):
            global_rows.append((
                recognition,
                LEGACY_DIFFICULTY[recognition],
                player["player_id"],
                player["score"],
                rank,
            ))
    game.executemany(
        "INSERT INTO global_quiz_pool VALUES (?,?,?,?,?)",
        global_rows,
    )
    report["ALL"] = global_report
    return {
        "competitions": len(competition_rows),
        "pool_rows": len(pool_rows),
        "global_pool_rows": len(global_rows),
        "world_xi_legends": len(world_xi_legends),
        "report": report,
    }
