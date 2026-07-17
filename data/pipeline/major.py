"""Config-driven, resumable updater for the configured major leagues."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .client import ApiClient
from .database import enqueue_job, initialize, make_request_key, utcnow
from .derive import derive_all_periods
from .ingest import run_worker
from .maintenance import repair_snapshots, sync_legends
from .publish import publish_game_db
from .validation import validate_source

DEFAULT_CONFIG = Path(__file__).with_name("major_leagues.json")
DEFAULT_LEGENDS = Path(__file__).resolve().parents[1] / "sources" / "legend_candidates.txt"


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        config = json.load(handle)
    if not config.get("leagues"):
        raise ValueError("Major league config has no leagues")
    return config


def current_season(mode: str, today: date | None = None) -> str:
    today = today or date.today()
    if mode == "calendar_year":
        return str(today.year)
    if mode == "split_year":
        return str(today.year if today.month >= 7 else today.year - 1)
    raise ValueError(f"Unknown season mode: {mode}")


def selected_leagues(
    config: dict[str, Any], tiers: set[int], season_override: str | None = None
) -> list[dict[str, Any]]:
    selected = []
    for league in config["leagues"]:
        if int(league["tier"]) not in tiers:
            continue
        item = dict(league)
        item["season_id"] = season_override or current_season(item["season_mode"])
        selected.append(item)
    if not selected:
        raise ValueError("No major leagues matched the selected tiers")
    return selected


def _is_stale(timestamp: str | None, max_age_days: int) -> bool:
    if not timestamp:
        return True
    parsed = datetime.fromisoformat(timestamp)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed < datetime.now(timezone.utc) - timedelta(days=max_age_days)


def enqueue_if_stale(
    conn: sqlite3.Connection,
    endpoint: str,
    entity_type: str,
    entity_id: str | int,
    params: dict[str, Any],
    priority: int,
    max_age_days: int,
    force: bool = False,
) -> bool:
    request_key = make_request_key(endpoint, str(entity_id), params)
    row = conn.execute(
        """
        SELECT j.status, MAX(s.fetched_at) AS fetched_at
        FROM crawl_jobs j
        LEFT JOIN api_snapshots s ON s.request_key = j.request_key
        WHERE j.request_key = ?
        GROUP BY j.job_id
        """,
        (request_key,),
    ).fetchone()
    if row is None:
        enqueue_job(conn, endpoint, entity_type, entity_id, params, priority)
        return True
    if row["status"] in {"pending", "running", "retry"}:
        return True
    refresh = force or row["status"] == "dead" or _is_stale(row["fetched_at"], max_age_days)
    if refresh:
        enqueue_job(conn, endpoint, entity_type, entity_id, params, priority, refresh=True)
    return refresh


def prepare_competitions(
    conn: sqlite3.Connection,
    leagues: list[dict[str, Any]],
    refresh_days: dict[str, int],
    force: bool,
) -> int:
    count = 0
    now = utcnow()
    for league in leagues:
        conn.execute(
            """
            INSERT INTO competitions(competition_id,name,country,created_at,updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(competition_id) DO UPDATE SET
                name=excluded.name,country=excluded.country,updated_at=excluded.updated_at
            """,
            (league["competition_id"], league["name"], league["country"], now, now),
        )
        count += int(enqueue_if_stale(
            conn, "competition_clubs", "competition", league["competition_id"],
            {"season_id": league["season_id"]}, 10,
            int(refresh_days["competition_clubs"]), force,
        ))
    conn.commit()
    return count


def prepare_rosters(
    conn: sqlite3.Connection,
    leagues: list[dict[str, Any]],
    refresh_days: dict[str, int],
    force: bool,
) -> int:
    count = 0
    for league in leagues:
        clubs = conn.execute(
            """
            SELECT club_id FROM competition_clubs
            WHERE competition_id = ? AND season_id = ?
            """,
            (league["competition_id"], league["season_id"]),
        ).fetchall()
        for club in clubs:
            count += int(enqueue_if_stale(
                conn, "club_players", "club", club["club_id"],
                {"season_id": league["season_id"]}, 20,
                int(refresh_days["club_players"]), force,
            ))
    conn.commit()
    return count


def resolve_discovered_seasons(
    conn: sqlite3.Connection, leagues: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Use the season actually returned by the API when it differs from the request."""
    resolved: list[dict[str, Any]] = []
    for league in leagues:
        item = dict(league)
        requested = item["season_id"]
        exact = conn.execute(
            """
            SELECT season_id FROM competition_seasons
            WHERE competition_id = ? AND season_id = ?
            """,
            (item["competition_id"], requested),
        ).fetchone()
        if exact is None:
            latest = conn.execute(
                """
                SELECT season_id FROM competition_seasons
                WHERE competition_id = ?
                ORDER BY discovered_at DESC, season_id DESC LIMIT 1
                """,
                (item["competition_id"],),
            ).fetchone()
            if latest is not None:
                item["season_id"] = str(latest["season_id"])
        resolved.append(item)
    return resolved


def current_player_ids(conn: sqlite3.Connection, leagues: list[dict[str, Any]]) -> list[int]:
    pairs = [(league["competition_id"], league["season_id"]) for league in leagues]
    conditions = " OR ".join("(cc.competition_id=? AND cc.season_id=?)" for _ in pairs)
    params = [value for pair in pairs for value in pair]
    rows = conn.execute(
        f"""
        SELECT DISTINCT cr.player_id
        FROM competition_clubs cc
        JOIN club_rosters cr ON cr.club_id=cc.club_id AND cr.season_id=cc.season_id
        WHERE {conditions}
        ORDER BY cr.player_id
        """,
        params,
    ).fetchall()
    return [int(row["player_id"]) for row in rows]


def prepare_players(
    conn: sqlite3.Connection,
    player_ids: list[int],
    refresh_days: dict[str, int],
    force: bool,
    include_market_values: bool,
) -> dict[str, int]:
    endpoints = [
        ("player_profile", 30),
        ("player_transfers", 40),
    ]
    if include_market_values:
        endpoints.append(("player_market_value", 50))
    counts = {endpoint: 0 for endpoint, _ in endpoints}
    for player_id in player_ids:
        for endpoint, priority in endpoints:
            counts[endpoint] += int(enqueue_if_stale(
                conn, endpoint, "player", player_id, {}, priority,
                int(refresh_days[endpoint]), force,
            ))
    conn.commit()
    return counts


def update_major_leagues(
    db_path: str | Path,
    client: ApiClient,
    config_path: str | Path = DEFAULT_CONFIG,
    tiers: set[int] | None = None,
    season_override: str | None = None,
    concurrency: int = 2,
    force: bool = False,
    include_market_values: bool = False,
    discovery_only: bool = False,
    publish_output: str | Path | None = None,
    min_players: int = 1,
    min_periods: int = 1,
) -> dict[str, Any]:
    config = load_config(config_path)
    leagues = selected_leagues(config, tiers or {1, 2}, season_override)
    refresh_days = config["refresh_days"]
    conn = initialize(db_path)
    result: dict[str, Any] = {
        "scope": [{"competition_id": x["competition_id"], "season_id": x["season_id"]} for x in leagues]
    }
    try:
        competition_jobs = prepare_competitions(conn, leagues, refresh_days, force)
        result["competition_jobs"] = run_worker(
            db_path, client, competition_jobs, concurrency
        ) if competition_jobs else {"claimed": 0, "succeeded": 0, "failed": 0}

        leagues = resolve_discovered_seasons(conn, leagues)
        result["resolved_scope"] = [
            {"competition_id": x["competition_id"], "season_id": x["season_id"]}
            for x in leagues
        ]

        roster_jobs = prepare_rosters(conn, leagues, refresh_days, force)
        result["roster_jobs"] = run_worker(
            db_path, client, roster_jobs, concurrency
        ) if roster_jobs else {"claimed": 0, "succeeded": 0, "failed": 0}

        player_ids = current_player_ids(conn, leagues)
        result["current_players"] = len(player_ids)
        if discovery_only:
            result["validation"] = validate_source(conn)
            return result

        if DEFAULT_LEGENDS.exists():
            result["legends"] = sync_legends(
                conn,
                client,
                DEFAULT_LEGENDS,
                refresh=force,
                enqueue_details=False,
            )
            legend_ids = [
                int(row["player_id"])
                for row in conn.execute(
                    "SELECT player_id FROM players WHERE is_legend=1 ORDER BY player_id"
                )
            ]
            player_ids = sorted(set(player_ids) | set(legend_ids))

        detail_jobs = prepare_players(
            conn, player_ids, refresh_days, force, include_market_values
        )
        result["detail_jobs_prepared"] = detail_jobs
        detail_total = sum(detail_jobs.values())
        result["detail_jobs"] = run_worker(
            db_path, client, detail_total, concurrency
        ) if detail_total else {"claimed": 0, "succeeded": 0, "failed": 0}
        result["repair"] = repair_snapshots(conn)
        result["derived"] = derive_all_periods(conn)
        result["validation"] = validate_source(conn)
        if publish_output is not None:
            result["publish"] = publish_game_db(
                db_path, publish_output, min_players, min_periods, strict=True
            )
        return result
    finally:
        conn.close()
