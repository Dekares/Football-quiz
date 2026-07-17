"""Offline repairs and curated-data imports for the canonical database."""
from __future__ import annotations

import json
import sqlite3
import zlib
from pathlib import Path
from typing import Any

from backend.app.text import normalize_text

from .database import utcnow
from .ingest import _date, _int, _replace_nationalities, _upsert_club, _upsert_player_stub


def repair_roster_snapshots(conn: sqlite3.Connection) -> dict[str, int]:
    """Restore richer roster fields that sparse profile responses may have erased."""
    rows = conn.execute(
        """
        SELECT response_json
        FROM api_snapshots snapshot
        WHERE endpoint = 'club_players' AND http_status = 200
          AND snapshot_id = (
              SELECT MAX(latest.snapshot_id)
              FROM api_snapshots latest
              WHERE latest.request_key = snapshot.request_key
                AND latest.endpoint = 'club_players' AND latest.http_status = 200
          )
        ORDER BY snapshot_id
        """
    ).fetchall()
    before = int(conn.execute(
        "SELECT COUNT(*) FROM players WHERE date_of_birth IS NOT NULL"
    ).fetchone()[0])
    players_seen: set[int] = set()
    now = utcnow()
    for row in rows:
        payload = json.loads(row["response_json"])
        for raw in payload.get("players") or []:
            player_id = _int(raw.get("id"))
            if player_id is None:
                continue
            players_seen.add(player_id)
            _upsert_player_stub(conn, player_id, raw.get("name"))
            conn.execute(
                """
                UPDATE players SET
                    date_of_birth = COALESCE(date_of_birth, ?),
                    position = COALESCE(position, ?),
                    foot = COALESCE(foot, ?),
                    height_in_cm = COALESCE(height_in_cm, ?),
                    current_market_value = COALESCE(current_market_value, ?),
                    updated_at = ?
                WHERE player_id = ?
                """,
                (
                    _date(raw.get("dateOfBirth")), raw.get("position"), raw.get("foot"),
                    _int(raw.get("height")), _int(raw.get("marketValue")), now, player_id,
                ),
            )
            nationalities = raw.get("nationality") or []
            if nationalities:
                for ordinal, nationality in enumerate(nationalities):
                    if nationality:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO player_nationalities(
                                player_id, nationality, ordinal
                            ) VALUES (?, ?, ?)
                            """,
                            (player_id, str(nationality), ordinal),
                        )
    conn.commit()
    after = int(conn.execute(
        "SELECT COUNT(*) FROM players WHERE date_of_birth IS NOT NULL"
    ).fetchone()[0])
    return {
        "snapshots": len(rows),
        "players_seen": len(players_seen),
        "birth_dates_restored": after - before,
        "players_with_birth_date": after,
    }


def repair_competition_snapshots(conn: sqlite3.Connection) -> dict[str, int]:
    """Restore authoritative current-club names from competition discovery."""
    rows = conn.execute(
        """
        SELECT response_json
        FROM api_snapshots snapshot
        WHERE endpoint = 'competition_clubs' AND http_status = 200
          AND snapshot_id = (
              SELECT MAX(latest.snapshot_id)
              FROM api_snapshots latest
              WHERE latest.request_key = snapshot.request_key
                AND latest.endpoint = 'competition_clubs' AND latest.http_status = 200
          )
        ORDER BY snapshot_id
        """
    ).fetchall()
    updated = 0
    now = utcnow()
    for row in rows:
        payload = json.loads(row["response_json"])
        competition_id = str(payload.get("id") or "")
        for club in payload.get("clubs") or []:
            club_id = _int(club.get("id"))
            name = club.get("name")
            if club_id is None or not name:
                continue
            _upsert_club(conn, club_id, name, competition_id or None)
            updated += conn.execute(
                """
                UPDATE clubs SET name = ?, current_competition_id = COALESCE(?, current_competition_id),
                    updated_at = ? WHERE club_id = ?
                """,
                (name, competition_id or None, now, club_id),
            ).rowcount
    conn.commit()
    return {"snapshots": len(rows), "clubs_updated": updated}


def repair_snapshots(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    return {
        "competitions": repair_competition_snapshots(conn),
        "rosters": repair_roster_snapshots(conn),
    }


def _resolve_player_id(conn: sqlite3.Connection, item: dict[str, Any], ordinal: int) -> int:
    wanted_name = normalize_text(item.get("name"))
    wanted_birth = _date(item.get("date_of_birth"))
    matches = [
        row for row in conn.execute("SELECT player_id, name, date_of_birth FROM players")
        if normalize_text(row["name"]) == wanted_name
    ]
    if wanted_birth:
        exact = [row for row in matches if row["date_of_birth"] == wanted_birth]
        if exact:
            return int(exact[0]["player_id"])
    if len(matches) == 1:
        return int(matches[0]["player_id"])
    candidate = 9_000_001 + ordinal
    while conn.execute("SELECT 1 FROM players WHERE player_id = ?", (candidate,)).fetchone():
        candidate += 100
    return candidate


def _resolve_club_id(conn: sqlite3.Connection, desired_id: int, name: str) -> int:
    wanted = normalize_text(name)
    for row in conn.execute("SELECT club_id, name FROM clubs"):
        if normalize_text(row["name"]) == wanted:
            return int(row["club_id"])
    existing = conn.execute("SELECT name FROM clubs WHERE club_id = ?", (desired_id,)).fetchone()
    if existing is None or normalize_text(existing["name"]) == wanted:
        return desired_id
    candidate = 90_000_000 + zlib.crc32(wanted.encode("utf-8")) % 9_000_000
    while True:
        row = conn.execute("SELECT name FROM clubs WHERE club_id = ?", (candidate,)).fetchone()
        if row is None or normalize_text(row["name"]) == wanted:
            return candidate
        candidate += 1


def import_legends(conn: sqlite3.Connection, source_path: str | Path) -> dict[str, int]:
    """Upsert curated legends and exact manual career periods."""
    path = Path(source_path)
    items = json.loads(path.read_text(encoding="utf-8"))
    now = utcnow()
    periods = 0
    matched = 0
    created = 0
    for ordinal, item in enumerate(items):
        player_id = _resolve_player_id(conn, item, ordinal)
        exists = conn.execute("SELECT 1 FROM players WHERE player_id = ?", (player_id,)).fetchone()
        matched += int(exists is not None)
        created += int(exists is None)
        _upsert_player_stub(conn, player_id, item.get("name"))
        conn.execute(
            """
            UPDATE players SET
                name = COALESCE(?, name),
                full_name = COALESCE(full_name, ?),
                date_of_birth = COALESCE(date_of_birth, ?),
                country_of_birth = COALESCE(country_of_birth, ?),
                position = COALESCE(position, ?),
                image_url = COALESCE(image_url, ?),
                highest_market_value = CASE
                    WHEN ? IS NULL THEN highest_market_value
                    WHEN highest_market_value IS NULL THEN ?
                    ELSE MAX(highest_market_value, ?) END,
                is_retired = 1, is_legend = 1, profile_loaded = 1, updated_at = ?
            WHERE player_id = ?
            """,
            (
                item.get("name"), " ".join(filter(None, (
                    item.get("first_name"), item.get("last_name")
                ))) or None,
                _date(item.get("date_of_birth")), item.get("country"), item.get("position"),
                item.get("image_url"), _int(item.get("highest_market_value")),
                _int(item.get("highest_market_value")), _int(item.get("highest_market_value")),
                now, player_id,
            ),
        )
        if item.get("country"):
            _replace_nationalities(conn, player_id, [item["country"]])
        conn.execute(
            "DELETE FROM player_club_periods WHERE player_id = ? AND source = 'manual'",
            (player_id,),
        )
        for club in item.get("clubs") or []:
            club_id = _resolve_club_id(conn, int(club["club_id"]), str(club["name"]))
            _upsert_club(conn, club_id, club.get("name"))
            conn.execute(
                """
                INSERT INTO player_club_periods(
                    player_id, club_id, date_from, date_to, source, confidence, created_at
                ) VALUES (?, ?, ?, ?, 'manual', 'exact', ?)
                """,
                (player_id, club_id, _date(club.get("from")), _date(club.get("to")), now),
            )
            periods += 1
    conn.commit()
    return {
        "legends": len(items),
        "matched_existing_players": matched,
        "created_players": created,
        "manual_periods": periods,
    }
