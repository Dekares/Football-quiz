"""League-aware solo quiz pool generation."""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).with_name("major_leagues.json")
RECOGNITIONS = ("known", "less_known", "obscure")
LEAGUE_BUCKET_RATIOS = (0.18, 0.32)
GLOBAL_BUCKET_RATIOS = (0.08, 0.27)
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
) -> int:
    """Return a deterministic 0-100 prominence score.

    The score orders players both inside competitions and in the independent
    global pool. Each scope applies its own rank ratios.
    """
    value = highest_market_value or 0
    value_points = 2
    for threshold, points in (
        (80_000_000, 50),
        (60_000_000, 45),
        (40_000_000, 38),
        (25_000_000, 30),
        (15_000_000, 23),
        (8_000_000, 16),
        (3_000_000, 10),
        (1_000_000, 6),
    ):
        if value >= threshold:
            value_points = points
            break

    if max_club_prestige >= 20:
        prestige_points = 25
    elif max_club_prestige >= 10:
        prestige_points = 18
    elif max_club_prestige >= 5:
        prestige_points = 12
    elif max_club_prestige >= 2:
        prestige_points = 6
    else:
        prestige_points = 2

    if meaningful_clubs >= 7:
        breadth_points = 10
    elif meaningful_clubs >= 5:
        breadth_points = 7
    elif meaningful_clubs >= 3:
        breadth_points = 4
    else:
        breadth_points = 2

    return min(
        100,
        value_points
        + prestige_points
        + breadth_points
        + (25 if is_legend else 0),
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


def _player_metrics(game: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    players = {
        row["player_id"]: {
            "player_id": row["player_id"],
            "name": row["name"],
            "highest_market_value": row["highest_market_value"] or 0,
            "is_legend": bool(row["is_legend"]),
            "position": row["position"],
            "country": row["country_of_citizenship"],
            "meaningful_clubs": 0,
            "max_prestige": 0,
        }
        for row in game.execute(
            """
            SELECT player_id, name, highest_market_value, is_legend, position,
                   country_of_citizenship
            FROM players
            """
        )
    }
    seen_clubs: dict[int, set[int]] = defaultdict(set)
    for row in game.execute(
        """
        SELECT pc.player_id, c.club_id, c.name, c.prestige_score
        FROM player_clubs pc JOIN clubs c ON c.club_id = pc.club_id
        """
    ):
        metrics = players.get(row["player_id"])
        if not metrics or not meaningful_club(row["name"]):
            continue
        seen_clubs[row["player_id"]].add(row["club_id"])
        metrics["max_prestige"] = max(metrics["max_prestige"], row["prestige_score"])
    for player_id, club_ids in seen_clubs.items():
        players[player_id]["meaningful_clubs"] = len(club_ids)
    for metrics in players.values():
        metrics["score"] = recognition_score(
            metrics["highest_market_value"],
            metrics["max_prestige"],
            metrics["meaningful_clubs"],
            metrics["is_legend"],
        )
    return players


def _eligible(metrics: dict[str, Any]) -> bool:
    return bool(
        metrics["position"]
        and metrics["country"]
        and metrics["meaningful_clubs"] >= 2
    )


def _ranked_buckets(
    players: list[dict[str, Any]],
    ratios: tuple[float, float] = LEAGUE_BUCKET_RATIOS,
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
    legends = [
        player for player_id, player in metrics.items()
        if player["is_legend"] and player_id not in active_ids and _eligible(player)
    ]
    if legends:
        grouped["LEGENDS"] = legends

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
    for competition_id, league_players in grouped.items():
        buckets = _ranked_buckets(league_players)
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
    global_buckets = _ranked_buckets(global_players, GLOBAL_BUCKET_RATIOS)
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
        "report": report,
    }
