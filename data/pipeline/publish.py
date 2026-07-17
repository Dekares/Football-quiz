"""Publish a validated, legacy-compatible, read-only game database artifact."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
import uuid
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

from backend.app.text import normalize_text

from .database import connect, utcnow
from .daily import build_daily_schedule
from .quiz_pools import build_quiz_pools, meaningful_club
from .validation import validate_game_db, validate_source

MAX_BACKUPS = 3
GAME_SCHEMA_SQL = r"""
CREATE TABLE players (
    player_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    country_of_citizenship TEXT,
    date_of_birth TEXT,
    position TEXT,
    image_url TEXT,
    market_value INTEGER,
    highest_market_value INTEGER,
    international_caps INTEGER,
    is_legend INTEGER NOT NULL DEFAULT 0,
    search_name TEXT NOT NULL,
    sub_position TEXT,
    foot TEXT,
    height_in_cm INTEGER,
    country_of_birth TEXT,
    city_of_birth TEXT,
    international_goals INTEGER
);

CREATE TABLE clubs (
    club_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    domestic_competition_id TEXT,
    logo_url TEXT,
    prestige_score INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE player_clubs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    club_id INTEGER NOT NULL REFERENCES clubs(club_id),
    date_from TEXT,
    date_to TEXT,
    UNIQUE(player_id, club_id, date_from, date_to)
);

CREATE TABLE club_aliases (
    alias TEXT NOT NULL,
    club_id INTEGER NOT NULL REFERENCES clubs(club_id),
    search_alias TEXT NOT NULL,
    UNIQUE(club_id, alias)
);

CREATE TABLE club_pair_stats (
    club_a_id INTEGER NOT NULL REFERENCES clubs(club_id),
    club_b_id INTEGER NOT NULL REFERENCES clubs(club_id),
    common_count INTEGER NOT NULL,
    min_prestige INTEGER NOT NULL,
    PRIMARY KEY (club_a_id, club_b_id)
);

CREATE TABLE competitions (
    competition_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT,
    season_id TEXT,
    sort_order INTEGER NOT NULL,
    is_special INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE quiz_pool (
    competition_id TEXT NOT NULL REFERENCES competitions(competition_id),
    recognition TEXT NOT NULL
        CHECK (recognition IN ('known', 'less_known', 'obscure')),
    difficulty TEXT NOT NULL,
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    recognition_score INTEGER NOT NULL,
    rank_in_league INTEGER NOT NULL,
    PRIMARY KEY (competition_id, recognition, player_id)
);

CREATE TABLE global_quiz_pool (
    recognition TEXT NOT NULL
        CHECK (recognition IN ('known', 'less_known', 'obscure')),
    difficulty TEXT NOT NULL,
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    recognition_score INTEGER NOT NULL,
    rank_global INTEGER NOT NULL,
    PRIMARY KEY (recognition, player_id)
);

CREATE TABLE daily_challenges (
    challenge_date TEXT PRIMARY KEY,
    day_number INTEGER NOT NULL UNIQUE CHECK (day_number >= 1),
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    recognition_score INTEGER NOT NULL,
    selection_version TEXT NOT NULL,
    scheduled_build_id TEXT NOT NULL,
    scheduled_at TEXT NOT NULL
);

CREATE TABLE build_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX idx_pc_club ON player_clubs(club_id);
CREATE INDEX idx_pc_player ON player_clubs(player_id);
CREATE INDEX idx_clubs_name ON clubs(name COLLATE NOCASE);
CREATE INDEX idx_alias ON club_aliases(alias COLLATE NOCASE);
CREATE INDEX idx_alias_search ON club_aliases(search_alias);
CREATE INDEX idx_players_search ON players(search_name);
CREATE INDEX idx_pair_difficulty ON club_pair_stats(min_prestige, common_count);
CREATE INDEX idx_quiz_pool_filter
    ON quiz_pool(competition_id, recognition, rank_in_league);
CREATE INDEX idx_quiz_pool_legacy
    ON quiz_pool(difficulty, player_id);
CREATE INDEX idx_global_quiz_pool_filter
    ON global_quiz_pool(recognition, rank_global);
CREATE INDEX idx_global_quiz_pool_legacy
    ON global_quiz_pool(difficulty, player_id);
CREATE INDEX idx_daily_challenges_player
    ON daily_challenges(player_id, challenge_date);
"""


def normalize_position(value: str | None) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    if "goalkeeper" in text or text == "keeper":
        return "Goalkeeper"
    if any(word in text for word in ("back", "defender", "sweeper")):
        return "Defender"
    if "midfield" in text or "midfielder" in text:
        return "Midfield"
    if any(word in text for word in ("winger", "forward", "striker", "attack", "second striker")):
        return "Attack"
    return None


def pair_eligible_club(name: str | None) -> bool:
    return meaningful_club(name)


def _insert_players(source: sqlite3.Connection, game: sqlite3.Connection) -> int:
    rows = source.execute(
        """
        SELECT p.*,
               (SELECT nationality FROM player_nationalities n
                WHERE n.player_id = p.player_id ORDER BY ordinal LIMIT 1) AS nationality
        FROM players p
        WHERE (p.profile_loaded = 1 OR p.is_legend = 1)
          AND p.name IS NOT NULL AND p.name != ''
          AND EXISTS (
              SELECT 1 FROM player_club_periods pc
              JOIN clubs c ON c.club_id = pc.club_id
              WHERE pc.player_id = p.player_id AND c.is_placeholder = 0
          )
        ORDER BY p.player_id
        """
    ).fetchall()
    values = []
    for row in rows:
        values.append((
            row["player_id"], row["name"], None, None, row["nationality"],
            row["date_of_birth"], normalize_position(row["position"]), row["image_url"],
            row["current_market_value"], row["highest_market_value"], None,
            row["is_legend"], normalize_text(row["name"]), row["sub_position"] or row["position"],
            row["foot"], row["height_in_cm"], row["country_of_birth"],
            row["city_of_birth"], None,
        ))
    game.executemany("INSERT INTO players VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
    return len(values)


def _insert_clubs(source: sqlite3.Connection, game: sqlite3.Connection) -> int:
    rows = source.execute(
        """
        SELECT c.club_id, c.name, c.logo_url,
               COALESCE(c.current_competition_id, (
                   SELECT cc.competition_id FROM competition_clubs cc
                   WHERE cc.club_id = c.club_id
                   ORDER BY cc.season_id DESC LIMIT 1
               )) AS competition_id
        FROM clubs c
        WHERE c.is_placeholder = 0 AND c.name IS NOT NULL AND c.name != ''
          AND EXISTS (
              SELECT 1 FROM player_club_periods pc
              JOIN players gp ON gp.player_id = pc.player_id
              WHERE pc.club_id = c.club_id
          )
        ORDER BY c.club_id
        """
    ).fetchall()
    game_player_ids = {row[0] for row in game.execute("SELECT player_id FROM players")}
    referenced = {
        row[0] for row in source.execute(
            "SELECT DISTINCT club_id, player_id FROM player_club_periods"
        ) if row[1] in game_player_ids
    }
    values = [
        (row["club_id"], row["name"], row["competition_id"], row["logo_url"], 0)
        for row in rows if row["club_id"] in referenced
    ]
    game.executemany("INSERT INTO clubs VALUES (?,?,?,?,?)", values)
    return len(values)


def _insert_periods(source: sqlite3.Connection, game: sqlite3.Connection) -> int:
    rows = source.execute(
        """
        SELECT DISTINCT player_id, club_id, date_from, date_to
        FROM player_club_periods
        ORDER BY player_id, COALESCE(date_from, date_to, ''), club_id
        """
    ).fetchall()
    player_ids = {row[0] for row in game.execute("SELECT player_id FROM players")}
    club_ids = {row[0] for row in game.execute("SELECT club_id FROM clubs")}
    values = [
        (row["player_id"], row["club_id"], row["date_from"], row["date_to"])
        for row in rows if row["player_id"] in player_ids and row["club_id"] in club_ids
    ]
    game.executemany(
        "INSERT OR IGNORE INTO player_clubs(player_id, club_id, date_from, date_to) VALUES (?,?,?,?)",
        values,
    )
    return int(game.execute("SELECT COUNT(*) FROM player_clubs").fetchone()[0])


def _insert_aliases(source: sqlite3.Connection, game: sqlite3.Connection) -> int:
    club_ids = {row[0] for row in game.execute("SELECT club_id FROM clubs")}
    aliases = {
        (row["club_id"], row["alias"], row["search_alias"])
        for row in source.execute("SELECT club_id, alias, search_alias FROM club_aliases")
        if row["club_id"] in club_ids and row["alias"] and row["search_alias"]
    }
    for row in game.execute("SELECT club_id, name FROM clubs"):
        aliases.add((row["club_id"], row["name"], normalize_text(row["name"])))
    game.executemany(
        "INSERT OR IGNORE INTO club_aliases(club_id, alias, search_alias) VALUES (?,?,?)",
        sorted(aliases),
    )
    return len(aliases)


def _build_derived_tables(
    source: sqlite3.Connection,
    game: sqlite3.Connection,
) -> dict[str, Any]:
    game.execute(
        """
        UPDATE clubs SET prestige_score = COALESCE((
            SELECT COUNT(DISTINCT pc.player_id)
            FROM player_clubs pc JOIN players p ON p.player_id = pc.player_id
            WHERE pc.club_id = clubs.club_id
              AND (p.highest_market_value >= 50000000 OR p.is_legend = 1)
        ), 0)
        """
    )
    prestige = {
        row[0]: row[2]
        for row in game.execute(
            """
            SELECT club_id, name, prestige_score FROM clubs
            WHERE prestige_score >= 3 AND domestic_competition_id IS NOT NULL
            """
        )
        if pair_eligible_club(row[1])
    }
    by_player: dict[int, set[int]] = defaultdict(set)
    for row in game.execute("SELECT player_id, club_id FROM player_clubs"):
        if row["club_id"] in prestige:
            by_player[row["player_id"]].add(row["club_id"])
    pair_counts: dict[tuple[int, int], int] = defaultdict(int)
    for clubs in by_player.values():
        for pair in combinations(sorted(clubs), 2):
            pair_counts[pair] += 1
    pair_rows = [
        (a, b, count, min(prestige[a], prestige[b]))
        for (a, b), count in pair_counts.items() if count >= 2
    ]
    game.executemany("INSERT INTO club_pair_stats VALUES (?,?,?,?)", pair_rows)

    pool_stats = build_quiz_pools(source, game)

    game.executescript(
        """
        CREATE VIRTUAL TABLE players_fts USING fts5(
            search_name, content='', tokenize='trigram'
        );
        INSERT INTO players_fts(rowid, search_name)
            SELECT player_id, search_name FROM players WHERE search_name != '';
        CREATE VIRTUAL TABLE club_aliases_fts USING fts5(
            club_id UNINDEXED, search_alias, tokenize='trigram'
        );
        INSERT INTO club_aliases_fts(club_id, search_alias)
            SELECT club_id, search_alias FROM club_aliases WHERE search_alias != '';
        """
    )
    return pool_stats


def publish_game_db(
    source_path: str | Path,
    output_path: str | Path,
    min_players: int = 1,
    min_periods: int = 1,
    strict: bool = True,
) -> dict[str, Any]:
    source_path = Path(source_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".new")
    if temp_path.exists():
        temp_path.unlink()
    build_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    source = connect(source_path)
    started_at = utcnow()
    source.execute(
        """
        INSERT INTO build_runs(build_id, status, source_db_path, output_path, started_at)
        VALUES (?, 'running', ?, ?, ?)
        """,
        (build_id, str(source_path.resolve()), str(output_path.resolve()), started_at),
    )
    source.commit()
    game: sqlite3.Connection | None = None
    try:
        source_validation = validate_source(source)
        if not source_validation["ok"]:
            raise RuntimeError("Source validation failed: " + ", ".join(source_validation["errors"]))
        game = sqlite3.connect(temp_path)
        game.row_factory = sqlite3.Row
        game.execute("PRAGMA foreign_keys = ON")
        game.executescript(GAME_SCHEMA_SQL)
        stats = {
            "players": _insert_players(source, game),
            "clubs": 0,
            "periods": 0,
            "aliases": 0,
        }
        stats["clubs"] = _insert_clubs(source, game)
        stats["periods"] = _insert_periods(source, game)
        stats["aliases"] = _insert_aliases(source, game)
        pool_stats = _build_derived_tables(source, game)
        stats["competitions"] = pool_stats["competitions"]
        stats["quiz_pool"] = pool_stats["pool_rows"]
        stats["global_quiz_pool"] = pool_stats["global_pool_rows"]
        stats["daily_challenges"] = build_daily_schedule(
            source,
            game,
            build_id,
        )
        stats["quiz_pool_counts"] = {
            competition_id: details["counts"]
            for competition_id, details in pool_stats["report"].items()
        }
        metadata = {
            "build_id": build_id,
            "built_at": utcnow(),
            "source_schema_version": "1",
            "source_db": source_path.name,
        }
        game.executemany("INSERT INTO build_metadata(key, value) VALUES (?, ?)", metadata.items())
        game.commit()
        validation = validate_game_db(game, min_players, min_periods, strict)
        if not validation["ok"]:
            raise RuntimeError("Game DB validation failed: " + ", ".join(validation["errors"]))
        game.execute("ANALYZE")
        game.commit()
        game.close()
        game = None
        if output_path.exists():
            backup = output_path.with_name(f"{output_path.name}.bak-pipeline-{time.strftime('%Y%m%d-%H%M%S')}")
            shutil.copy2(output_path, backup)
            backups = sorted(
                output_path.parent.glob(f"{output_path.name}.bak-pipeline-*"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            for stale_backup in backups[MAX_BACKUPS:]:
                stale_backup.unlink()
        os.replace(temp_path, output_path)
        source.execute(
            """
            UPDATE build_runs SET status = 'completed', stats_json = ?, validation_json = ?, completed_at = ?
            WHERE build_id = ?
            """,
            (json.dumps(stats), json.dumps(validation), utcnow(), build_id),
        )
        source.commit()
        return {"build_id": build_id, "output": str(output_path), "stats": stats, "validation": validation}
    except Exception as exc:
        if game is not None:
            game.close()
        if temp_path.exists():
            temp_path.unlink()
        source.rollback()
        source.execute(
            """
            UPDATE build_runs SET status = 'failed', validation_json = ?, completed_at = ?
            WHERE build_id = ?
            """,
            (json.dumps({"error": str(exc)}), utcnow(), build_id),
        )
        source.commit()
        raise
    finally:
        source.close()
