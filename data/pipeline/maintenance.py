"""Offline repairs and curated-data imports for the canonical database."""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from backend.app.text import normalize_text

from .client import ApiClient, ApiError
from .database import utcnow
from .ingest import (
    _date,
    _int,
    _placeholder,
    _replace_nationalities,
    _upsert_club,
    _upsert_player_stub,
    seed_players,
)


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


def repair_placeholder_flags(conn: sqlite3.Connection) -> dict[str, int]:
    """Recompute sticky placeholder flags after legacy club-ID collisions."""
    changed = 0
    now = utcnow()
    for row in conn.execute("SELECT club_id,name,is_placeholder FROM clubs"):
        expected = _placeholder(row["name"])
        if expected == int(row["is_placeholder"]):
            continue
        changed += conn.execute(
            "UPDATE clubs SET is_placeholder=?,updated_at=? WHERE club_id=?",
            (expected, now, row["club_id"]),
        ).rowcount
    conn.commit()
    return {"clubs_changed": changed}


def repair_snapshots(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    return {
        "competitions": repair_competition_snapshots(conn),
        "rosters": repair_roster_snapshots(conn),
        "placeholders": repair_placeholder_flags(conn),
    }


@dataclass(frozen=True)
class LegendCandidate:
    name: str
    player_id: int | None = None


def load_legend_candidates(source_path: str | Path) -> list[LegendCandidate]:
    """Read ``name`` or ``name|Transfermarkt ID`` identity records."""
    candidates: list[LegendCandidate] = []
    seen: set[str] = set()
    seen_ids: set[int] = set()
    for raw in Path(source_path).read_text(encoding="utf-8").splitlines():
        record = raw.split("#", 1)[0].strip()
        if not record:
            continue
        parts = [part.strip() for part in record.split("|")]
        if len(parts) > 2 or not parts[0]:
            raise ValueError(f"Invalid legend identity record: {raw!r}")
        name = parts[0]
        player_id = None
        if len(parts) == 2 and parts[1]:
            if not parts[1].isdigit():
                raise ValueError(f"Invalid Transfermarkt player ID for {name!r}")
            player_id = int(parts[1])
        key = normalize_text(name)
        if key in seen:
            raise ValueError(f"Duplicate legend candidate: {name!r}")
        if player_id is not None and player_id in seen_ids:
            raise ValueError(f"Duplicate legend player ID: {player_id}")
        candidates.append(LegendCandidate(name, player_id))
        seen.add(key)
        if player_id is not None:
            seen_ids.add(player_id)
    if not candidates:
        raise ValueError("Legend candidate list is empty")
    return candidates


def _search_position(value: str | None) -> str | None:
    code = normalize_text(value).upper()
    if code == "GK":
        return "Goalkeeper"
    if code in {"CB", "SW", "LB", "RB", "DEFENDER", "DEFENCE"}:
        return "Defender"
    if code in {"DM", "CM", "AM", "LM", "RM", "MIDFIELD", "MIDFIELDER"}:
        return "Midfield"
    if code in {"LW", "RW", "SS", "CF", "ATTACK", "FORWARD", "STRIKER"}:
        return "Attack"
    return value or None


def _resolved_search_player(
    name: str,
    results: list[dict],
    expected_player_id: int | None = None,
) -> tuple[int, str, str | None, list[str]] | None:
    wanted = normalize_text(name)
    matches = [item for item in results if normalize_text(item.get("name")) == wanted]
    if expected_player_id is not None:
        matches = [
            item for item in matches
            if str(item.get("id") or "") == str(expected_player_id)
        ]
    # An unpinned ambiguous name is unsafe: never trust search-result order.
    if len(matches) != 1:
        return None
    player_id = matches[0].get("id")
    if player_id is None or not str(player_id).isdigit():
        return None
    return (
        int(player_id),
        str(matches[0].get("name") or name),
        _search_position(matches[0].get("position")),
        [str(value) for value in matches[0].get("nationalities") or [] if value],
    )


def _remove_legacy_manual_legends(
    conn: sqlite3.Connection,
    resolved_ids: set[int],
    stale_registry_ids: set[int] | None = None,
) -> dict[str, int]:
    """Remove obsolete legend identities that are not used by live game data."""
    rows = conn.execute(
        """
        SELECT player_id FROM players
        WHERE is_legend = 1 AND player_id BETWEEN 9000000 AND 9999999
        """
    ).fetchall()
    candidates = {
        int(row["player_id"])
        for row in rows
        if row["player_id"] not in resolved_ids
    }
    candidates.update((stale_registry_ids or set()) - resolved_ids)
    removed = blocked = 0
    for player_id in sorted(candidates):
        referenced = conn.execute(
            """
            SELECT
              EXISTS(SELECT 1 FROM club_rosters WHERE player_id=?) OR
              EXISTS(SELECT 1 FROM daily_challenges WHERE player_id=?)
            """,
            (player_id, player_id),
        ).fetchone()[0]
        if referenced:
            blocked += 1
            continue
        # Transfer rows fetched through a bad identity are derived data, not a
        # reason to keep that identity alive. Other player-owned rows cascade.
        conn.execute("DELETE FROM transfers WHERE player_id = ?", (player_id,))
        conn.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
        removed += 1
    return {"legacy_removed": removed, "legacy_blocked": blocked}


def sync_legends(
    conn: sqlite3.Connection,
    client: ApiClient,
    source_path: str | Path,
    refresh: bool = False,
    refresh_details: bool = False,
    enqueue_details: bool = True,
    minimum_resolution_ratio: float = 0.80,
) -> dict[str, object]:
    """Resolve curated names to real Transfermarkt IDs and enqueue API enrichment."""
    candidates = load_legend_candidates(source_path)
    names = [candidate.name for candidate in candidates]
    now = utcnow()
    previous_registry_ids = {
        int(row["player_id"])
        for row in conn.execute(
            "SELECT player_id FROM legend_registry WHERE player_id IS NOT NULL"
        )
    }
    resolved: dict[str, tuple[int, str, str | None, list[str]]] = {}
    unresolved: list[str] = []

    for candidate in candidates:
        name = candidate.name
        cached = conn.execute(
            """
            SELECT player_id, resolved_name FROM legend_registry
            WHERE candidate_name = ? AND status = 'resolved'
            """,
            (name,),
        ).fetchone()
        cached_match = (
            (
                int(cached["player_id"]), cached["resolved_name"] or name, None, []
            )
            if cached and cached["player_id"] is not None
            else None
        )
        cached_matches_pin = bool(
            cached_match
            and (
                candidate.player_id is None
                or cached_match[0] == candidate.player_id
            )
        )
        if (
            cached_matches_pin
            and not refresh
        ):
            assert cached_match is not None
            resolved[name] = cached_match
            continue
        try:
            response = client.get(f"/players/search/{quote(name, safe='')}")
        except ApiError:
            if cached_matches_pin:
                assert cached_match is not None
                resolved[name] = cached_match
            else:
                unresolved.append(name)
            continue
        match = _resolved_search_player(
            name,
            list(response.payload.get("results") or []),
            candidate.player_id,
        )
        if match is None:
            unresolved.append(name)
            conn.execute(
                """
                INSERT INTO legend_registry(candidate_name,status,last_checked_at)
                VALUES (?, 'not_found', ?)
                ON CONFLICT(candidate_name) DO UPDATE SET
                    player_id=NULL,resolved_name=NULL,status='not_found',
                    last_checked_at=excluded.last_checked_at
                """,
                (name, now),
            )
            continue
        resolved[name] = match
        _upsert_player_stub(conn, match[0], match[1])
        conn.execute(
            "UPDATE players SET position=COALESCE(position, ?), updated_at=? WHERE player_id=?",
            (match[2], now, match[0]),
        )
        has_nationality = conn.execute(
            "SELECT 1 FROM player_nationalities WHERE player_id=? LIMIT 1", (match[0],)
        ).fetchone()
        if match[3] and not has_nationality:
            _replace_nationalities(conn, match[0], match[3])
        conn.execute(
            """
            INSERT INTO legend_registry(
                candidate_name,player_id,resolved_name,status,last_checked_at
            ) VALUES (?, ?, ?, 'resolved', ?)
            ON CONFLICT(candidate_name) DO UPDATE SET
                player_id=excluded.player_id,resolved_name=excluded.resolved_name,
                status='resolved',last_checked_at=excluded.last_checked_at
            """,
            (name, match[0], match[1], now),
        )

    required = max(1, math.ceil(len(names) * minimum_resolution_ratio))
    if len(resolved) < required:
        conn.rollback()
        raise ValueError(
            f"Legend sync resolved {len(resolved)}/{len(names)}; required at least {required}"
        )

    resolved_ids = {item[0] for item in resolved.values()}
    name_placeholders = ",".join("?" for _ in names)
    conn.execute(
        f"DELETE FROM legend_registry WHERE candidate_name NOT IN ({name_placeholders})",
        names,
    )
    cleanup = _remove_legacy_manual_legends(
        conn,
        resolved_ids,
        previous_registry_ids - resolved_ids,
    )
    conn.execute("UPDATE players SET is_legend = 0 WHERE is_legend = 1")
    for player_id, resolved_name, _position, _nationalities in resolved.values():
        _upsert_player_stub(conn, player_id, resolved_name)
    placeholders = ",".join("?" for _ in resolved_ids)
    conn.execute(
        f"UPDATE players SET is_legend = 1, updated_at = ? WHERE player_id IN ({placeholders})",
        (now, *sorted(resolved_ids)),
    )
    pending_before = int(conn.execute(
        "SELECT COUNT(*) FROM crawl_jobs WHERE status IN ('pending','retry')"
    ).fetchone()[0])
    if enqueue_details:
        seed_players(conn, sorted(resolved_ids), refresh=refresh_details)
    pending_after = int(conn.execute(
        "SELECT COUNT(*) FROM crawl_jobs WHERE status IN ('pending','retry')"
    ).fetchone()[0])
    conn.commit()
    return {
        "candidates": len(names),
        "resolved": len(resolved),
        "unresolved": unresolved,
        "queued_jobs": max(0, pending_after - pending_before),
        **cleanup,
    }
