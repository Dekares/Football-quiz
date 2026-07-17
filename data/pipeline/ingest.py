"""Endpoint handlers and persistent crawl worker."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from backend.app.text import normalize_text

from .client import ApiClient
from .database import (
    canonical_json,
    claim_job,
    complete_job,
    connect,
    enqueue_job,
    fail_job,
    initialize,
    reset_stale_jobs,
    utcnow,
)
from .derive import derive_player_periods

PARSER_VERSION = 1


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> str | None:
    if not value:
        return None
    raw = str(value)[:10]
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def _placeholder(name: str | None) -> int:
    value = normalize_text(name)
    return int(any(term in value for term in ("without club", "retired", "career break", "unknown")))


def _ensure_season(conn: sqlite3.Connection, season_id: str) -> None:
    now = utcnow()
    conn.execute(
        """
        INSERT INTO seasons(season_id, label, created_at, updated_at) VALUES (?, ?, ?, ?)
        ON CONFLICT(season_id) DO UPDATE SET label = excluded.label, updated_at = excluded.updated_at
        """,
        (season_id, season_id, now, now),
    )


def _upsert_competition(conn: sqlite3.Connection, competition_id: str, name: str | None = None) -> None:
    now = utcnow()
    conn.execute(
        """
        INSERT INTO competitions(competition_id, name, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(competition_id) DO UPDATE SET
            name = COALESCE(excluded.name, competitions.name), updated_at = excluded.updated_at
        """,
        (competition_id, name, now, now),
    )


def _upsert_club(
    conn: sqlite3.Connection,
    club_id: int | None,
    name: str | None,
    competition_id: str | None = None,
) -> None:
    if club_id is None:
        return
    now = utcnow()
    if competition_id:
        _upsert_competition(conn, competition_id)
    conn.execute(
        """
        INSERT INTO clubs(
            club_id, name, logo_url, current_competition_id, is_placeholder,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(club_id) DO UPDATE SET
            name = CASE
                WHEN clubs.name IS NULL OR LENGTH(excluded.name) > LENGTH(clubs.name)
                    THEN excluded.name ELSE clubs.name END,
            current_competition_id = COALESCE(excluded.current_competition_id, clubs.current_competition_id),
            is_placeholder = MAX(clubs.is_placeholder, excluded.is_placeholder),
            updated_at = excluded.updated_at
        """,
        (club_id, name, f"https://tmssl.akamaized.net/images/wappen/head/{club_id}.png",
         competition_id, _placeholder(name), now, now),
    )
    if name:
        conn.execute(
            """
            INSERT INTO club_aliases(club_id, alias, search_alias, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(club_id, alias) DO UPDATE SET last_seen_at = excluded.last_seen_at
            """,
            (club_id, name, normalize_text(name), now, now),
        )


def _upsert_player_stub(conn: sqlite3.Connection, player_id: int, name: str | None = None) -> None:
    now = utcnow()
    conn.execute(
        """
        INSERT INTO players(player_id, name, created_at, updated_at) VALUES (?, ?, ?, ?)
        ON CONFLICT(player_id) DO UPDATE SET
            name = COALESCE(excluded.name, players.name), updated_at = excluded.updated_at
        """,
        (player_id, name, now, now),
    )


def _replace_nationalities(conn: sqlite3.Connection, player_id: int, values: list[Any]) -> None:
    conn.execute("DELETE FROM player_nationalities WHERE player_id = ?", (player_id,))
    rows = [(player_id, str(value), i) for i, value in enumerate(values) if value]
    conn.executemany(
        "INSERT INTO player_nationalities(player_id, nationality, ordinal) VALUES (?, ?, ?)", rows
    )


def _issue(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: str | int,
    code: str,
    severity: str,
    details: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO data_issues(entity_type, entity_id, issue_code, severity, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (entity_type, str(entity_id), code, severity, canonical_json(details), utcnow()),
    )


def _resolve_issues(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: str | int,
    codes: tuple[str, ...],
) -> None:
    placeholders = ",".join("?" for _ in codes)
    conn.execute(
        f"""
        UPDATE data_issues SET resolved_at = ?
        WHERE entity_type = ? AND entity_id = ? AND resolved_at IS NULL
          AND issue_code IN ({placeholders})
        """,
        (utcnow(), entity_type, str(entity_id), *codes),
    )


def ingest_competition_clubs(
    conn: sqlite3.Connection, job: dict[str, Any], payload: dict[str, Any]
) -> None:
    competition_id = str(payload.get("id") or job["entity_id"])
    season_id = str(payload.get("seasonId") or job["params"].get("season_id") or "")
    if not season_id:
        raise ValueError("competition clubs response has no seasonId")
    now = utcnow()
    _upsert_competition(conn, competition_id, payload.get("name"))
    _ensure_season(conn, season_id)
    conn.execute(
        """
        INSERT OR REPLACE INTO competition_seasons(competition_id, season_id, discovered_at)
        VALUES (?, ?, ?)
        """,
        (competition_id, season_id, now),
    )
    _resolve_issues(conn, "competition", competition_id, ("club_missing_id",))
    conn.execute(
        "DELETE FROM competition_clubs WHERE competition_id = ? AND season_id = ?",
        (competition_id, season_id),
    )
    for club in payload.get("clubs") or []:
        club_id = _int(club.get("id"))
        if club_id is None:
            _issue(conn, "competition", competition_id, "club_missing_id", "warning", club)
            continue
        _upsert_club(conn, club_id, club.get("name"), competition_id)
        if club.get("name"):
            conn.execute(
                """
                UPDATE clubs SET name = ?, current_competition_id = ?, updated_at = ?
                WHERE club_id = ?
                """,
                (club["name"], competition_id, now, club_id),
            )
        conn.execute(
            """
            INSERT OR REPLACE INTO competition_clubs(competition_id, season_id, club_id, discovered_at)
            VALUES (?, ?, ?, ?)
            """,
            (competition_id, season_id, club_id, now),
        )
        enqueue_job(
            conn, "club_players", "club", club_id, {"season_id": season_id}, priority=20
        )


def ingest_club_players(conn: sqlite3.Connection, job: dict[str, Any], payload: dict[str, Any]) -> None:
    club_id = _int(payload.get("id") or job["entity_id"])
    season_id = str(job["params"].get("season_id") or "")
    if club_id is None or not season_id:
        raise ValueError("club roster job has invalid club or season")
    now = utcnow()
    _ensure_season(conn, season_id)
    _upsert_club(conn, club_id, None)
    _resolve_issues(conn, "club", club_id, ("roster_player_missing_id",))
    conn.execute(
        "DELETE FROM club_rosters WHERE club_id = ? AND season_id = ?", (club_id, season_id)
    )
    for raw in payload.get("players") or []:
        player_id = _int(raw.get("id"))
        if player_id is None:
            _issue(conn, "club", club_id, "roster_player_missing_id", "warning", raw)
            continue
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
            (_date(raw.get("dateOfBirth")), raw.get("position"), raw.get("foot"),
             _int(raw.get("height")), _int(raw.get("marketValue")), now, player_id),
        )
        nationalities = raw.get("nationality") or []
        if nationalities:
            _replace_nationalities(conn, player_id, nationalities)
        conn.execute(
            """
            INSERT OR REPLACE INTO club_rosters(
                club_id, season_id, player_id, position, joined_on,
                contract_until, market_value, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (club_id, season_id, player_id, raw.get("position"), _date(raw.get("joinedOn")),
             _date(raw.get("contract")), _int(raw.get("marketValue")), now),
        )
        enqueue_job(conn, "player_profile", "player", player_id, priority=30)
        enqueue_job(conn, "player_transfers", "player", player_id, priority=40)
        enqueue_job(conn, "player_market_value", "player", player_id, priority=50)


def ingest_player_profile(conn: sqlite3.Connection, job: dict[str, Any], payload: dict[str, Any]) -> None:
    player_id = _int(payload.get("id") or job["entity_id"])
    if player_id is None:
        raise ValueError("player profile response has no valid id")
    club = payload.get("club") or {}
    club_id = _int(club.get("id") or club.get("lastClubId"))
    club_name = club.get("name") or club.get("lastClubName")
    _upsert_club(conn, club_id, club_name)
    position = payload.get("position") or {}
    place = payload.get("placeOfBirth") or {}
    now = utcnow()
    _upsert_player_stub(conn, player_id, payload.get("name"))
    conn.execute(
        """
        UPDATE players SET
            name = COALESCE(?, name), full_name = COALESCE(?, full_name),
            date_of_birth = COALESCE(?, date_of_birth),
            country_of_birth = COALESCE(?, country_of_birth),
            city_of_birth = COALESCE(?, city_of_birth),
            position = COALESCE(?, position), sub_position = COALESCE(?, sub_position),
            foot = COALESCE(?, foot), height_in_cm = COALESCE(?, height_in_cm),
            image_url = COALESCE(?, image_url), current_club_id = COALESCE(?, current_club_id),
            current_market_value = COALESCE(?, current_market_value),
            is_retired = ?, retired_since = ?, profile_loaded = 1, updated_at = ?
        WHERE player_id = ?
        """,
        (payload.get("name"), payload.get("fullName"), _date(payload.get("dateOfBirth")),
         place.get("country"), place.get("city"), position.get("main"),
         ", ".join(position.get("other") or []) or None, payload.get("foot"),
         _int(payload.get("height")), payload.get("imageUrl"), club_id,
         _int(payload.get("marketValue")), int(bool(payload.get("isRetired"))),
         _date(payload.get("retiredSince")), now, player_id),
    )
    citizenship = payload.get("citizenship") or []
    if citizenship:
        _replace_nationalities(conn, player_id, citizenship)
    _resolve_issues(conn, "player", player_id, ("profile_missing_birth_date",))
    if not payload.get("dateOfBirth"):
        _issue(conn, "player", player_id, "profile_missing_birth_date", "warning", {})
    derive_player_periods(conn, player_id)


def ingest_player_transfers(
    conn: sqlite3.Connection, job: dict[str, Any], payload: dict[str, Any]
) -> None:
    player_id = _int(payload.get("id") or job["entity_id"])
    if player_id is None:
        raise ValueError("player transfers response has no valid id")
    _upsert_player_stub(conn, player_id)
    fetched_at = utcnow()
    observed_values: list[int] = []
    _resolve_issues(conn, "player", player_id, ("invalid_transfer",))
    conn.execute("DELETE FROM transfers WHERE player_id = ?", (player_id,))
    for raw in payload.get("transfers") or []:
        transfer_id = str(raw.get("id") or "")
        transfer_date = _date(raw.get("date"))
        if not transfer_id or not transfer_date:
            _issue(conn, "player", player_id, "invalid_transfer", "error", raw)
            continue
        from_club = raw.get("clubFrom") or {}
        to_club = raw.get("clubTo") or {}
        from_id = _int(from_club.get("id"))
        to_id = _int(to_club.get("id"))
        _upsert_club(conn, from_id, from_club.get("name"))
        _upsert_club(conn, to_id, to_club.get("name"))
        market_value = _int(raw.get("marketValue"))
        if market_value is not None:
            observed_values.append(market_value)
        conn.execute(
            """
            INSERT INTO transfers(
                transfer_id, player_id, from_club_id, to_club_id, transfer_date,
                season, transfer_type, market_value, fee, is_upcoming, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(transfer_id) DO UPDATE SET
                player_id = excluded.player_id, from_club_id = excluded.from_club_id,
                to_club_id = excluded.to_club_id, transfer_date = excluded.transfer_date,
                season = excluded.season, transfer_type = excluded.transfer_type,
                market_value = excluded.market_value, fee = excluded.fee,
                is_upcoming = excluded.is_upcoming, fetched_at = excluded.fetched_at
            """,
            (transfer_id, player_id, from_id, to_id, transfer_date, raw.get("season"),
             raw.get("type"), market_value, _int(raw.get("fee")),
             int(bool(raw.get("upcoming"))), fetched_at),
        )
    if observed_values:
        highest = max(observed_values)
        conn.execute(
            """
            UPDATE players SET
                highest_market_value = CASE
                    WHEN highest_market_value IS NULL THEN ?
                    ELSE MAX(highest_market_value, ?) END,
                updated_at = ?
            WHERE player_id = ?
            """,
            (highest, highest, fetched_at, player_id),
        )
    derive_player_periods(conn, player_id)


def ingest_player_market_value(
    conn: sqlite3.Connection, job: dict[str, Any], payload: dict[str, Any]
) -> None:
    player_id = _int(payload.get("id") or job["entity_id"])
    if player_id is None:
        raise ValueError("player market value response has no valid id")
    _upsert_player_stub(conn, player_id)
    fetched_at = utcnow()
    _resolve_issues(conn, "player", player_id, ("invalid_market_value_date",))
    conn.execute("DELETE FROM player_market_values WHERE player_id = ?", (player_id,))
    values: list[int] = []
    for raw in payload.get("marketValueHistory") or []:
        value_date = _date(raw.get("date"))
        if not value_date:
            _issue(conn, "player", player_id, "invalid_market_value_date", "warning", raw)
            continue
        club_id = _int(raw.get("clubId"))
        club_name = raw.get("clubName")
        _upsert_club(conn, club_id, club_name)
        value = _int(raw.get("marketValue"))
        if value is not None:
            values.append(value)
        source_key = str(club_id) if club_id is not None else normalize_text(club_name) or "unknown"
        conn.execute(
            """
            INSERT INTO player_market_values(
                player_id, value_date, club_id, club_name, market_value,
                age, source_key, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, value_date, source_key) DO UPDATE SET
                club_id = excluded.club_id, club_name = excluded.club_name,
                market_value = excluded.market_value, age = excluded.age,
                fetched_at = excluded.fetched_at
            """,
            (player_id, value_date, club_id, club_name, value, _int(raw.get("age")),
             source_key, fetched_at),
        )
    current = _int(payload.get("marketValue"))
    if current is not None:
        values.append(current)
    highest = max(values) if values else None
    conn.execute(
        """
        UPDATE players SET
            current_market_value = COALESCE(?, current_market_value),
            highest_market_value = CASE
                WHEN ? IS NULL THEN highest_market_value
                WHEN highest_market_value IS NULL THEN ?
                ELSE MAX(highest_market_value, ?) END,
            updated_at = ?
        WHERE player_id = ?
        """,
        (current, highest, highest, highest, fetched_at, player_id),
    )


HANDLERS: dict[str, Callable[[sqlite3.Connection, dict[str, Any], dict[str, Any]], None]] = {
    "competition_clubs": ingest_competition_clubs,
    "club_players": ingest_club_players,
    "player_profile": ingest_player_profile,
    "player_transfers": ingest_player_transfers,
    "player_market_value": ingest_player_market_value,
}


def _request_path(job: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    entity_id = quote(str(job["entity_id"]), safe="")
    params = job["params"]
    paths = {
        "competition_clubs": f"/competitions/{entity_id}/clubs",
        "club_players": f"/clubs/{entity_id}/players",
        "player_profile": f"/players/{entity_id}/profile",
        "player_transfers": f"/players/{entity_id}/transfers",
        "player_market_value": f"/players/{entity_id}/market_value",
    }
    if job["endpoint"] not in paths:
        raise ValueError(f"Unsupported endpoint: {job['endpoint']}")
    return paths[job["endpoint"]], params


def _store_snapshot(
    conn: sqlite3.Connection,
    job: dict[str, Any],
    request_url: str,
    status: int,
    payload: dict[str, Any],
) -> None:
    raw = canonical_json(payload)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    conn.execute(
        """
        INSERT INTO api_snapshots(
            job_id, request_key, endpoint, entity_type, entity_id, request_url,
            http_status, response_json, content_hash, parser_version, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (job["job_id"], job["request_key"], job["endpoint"], job["entity_type"],
         job["entity_id"], request_url, status, raw, digest, PARSER_VERSION, utcnow()),
    )
    conn.commit()


def process_job(db_path: str | Path, job: dict[str, Any], client: ApiClient) -> bool:
    conn = connect(db_path)
    try:
        path, params = _request_path(job)
        response = client.get(path, params)
        _store_snapshot(conn, job, response.url, response.status, response.payload)
        handler = HANDLERS[job["endpoint"]]
        handler(conn, job, response.payload)
        conn.commit()
        complete_job(conn, int(job["job_id"]))
        return True
    except Exception as exc:
        conn.rollback()
        fail_job(conn, job, exc)
        return False
    finally:
        conn.close()


def run_worker(
    db_path: str | Path,
    client: ApiClient,
    limit: int | None = None,
    concurrency: int = 2,
) -> dict[str, int]:
    concurrency = max(1, min(concurrency, 8))
    control = initialize(db_path)
    reset_stale_jobs(control)
    claimed = succeeded = failed = 0
    futures: dict[Future[bool], dict[str, Any]] = {}
    try:
        with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="transfer-api") as pool:
            while True:
                while len(futures) < concurrency and (limit is None or claimed < limit):
                    job = claim_job(control)
                    if job is None:
                        break
                    futures[pool.submit(process_job, db_path, job, client)] = job
                    claimed += 1
                if not futures:
                    break
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    futures.pop(future)
                    try:
                        if future.result():
                            succeeded += 1
                        else:
                            failed += 1
                    except Exception:
                        failed += 1
                if limit is not None and claimed >= limit and not futures:
                    break
    finally:
        control.close()
    return {"claimed": claimed, "succeeded": succeeded, "failed": failed}


def seed_competition_seasons(
    conn: sqlite3.Connection,
    competitions: list[str],
    seasons: list[str],
    refresh: bool = False,
) -> int:
    count = 0
    for competition_id in competitions:
        for season_id in seasons:
            _upsert_competition(conn, competition_id)
            _ensure_season(conn, season_id)
            enqueue_job(
                conn,
                "competition_clubs",
                "competition",
                competition_id,
                {"season_id": season_id},
                priority=10,
                refresh=refresh,
            )
            count += 1
    conn.commit()
    return count


def seed_players(conn: sqlite3.Connection, player_ids: list[int], refresh: bool = False) -> int:
    count = 0
    for player_id in player_ids:
        _upsert_player_stub(conn, player_id)
        enqueue_job(conn, "player_profile", "player", player_id, priority=30, refresh=refresh)
        enqueue_job(conn, "player_transfers", "player", player_id, priority=40, refresh=refresh)
        enqueue_job(conn, "player_market_value", "player", player_id, priority=50, refresh=refresh)
        count += 3
    conn.commit()
    return count
