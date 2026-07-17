"""Connection, migration and persistent crawl queue helpers."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .schema import SCHEMA_SQL


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def initialize(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (SCHEMA_VERSION, utcnow()),
    )
    conn.commit()
    return conn


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def make_request_key(endpoint: str, entity_id: str, params: dict[str, Any] | None = None) -> str:
    raw = canonical_json({"endpoint": endpoint, "entity_id": str(entity_id), "params": params or {}})
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def enqueue_job(
    conn: sqlite3.Connection,
    endpoint: str,
    entity_type: str,
    entity_id: str | int,
    params: dict[str, Any] | None = None,
    priority: int = 100,
    refresh: bool = False,
) -> int:
    now = utcnow()
    params = params or {}
    request_key = make_request_key(endpoint, str(entity_id), params)
    conn.execute(
        """
        INSERT INTO crawl_jobs(
            request_key, endpoint, entity_type, entity_id, params_json,
            priority, available_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(request_key) DO UPDATE SET
            priority = MIN(crawl_jobs.priority, excluded.priority),
            status = CASE WHEN ? THEN 'pending' ELSE crawl_jobs.status END,
            attempts = CASE WHEN ? THEN 0 ELSE crawl_jobs.attempts END,
            available_at = CASE WHEN ? THEN excluded.available_at ELSE crawl_jobs.available_at END,
            completed_at = CASE WHEN ? THEN NULL ELSE crawl_jobs.completed_at END,
            last_error = CASE WHEN ? THEN NULL ELSE crawl_jobs.last_error END,
            updated_at = excluded.updated_at
        """,
        (
            request_key, endpoint, entity_type, str(entity_id), canonical_json(params),
            priority, now, now, now,
            int(refresh), int(refresh), int(refresh), int(refresh), int(refresh),
        ),
    )
    row = conn.execute("SELECT job_id FROM crawl_jobs WHERE request_key = ?", (request_key,)).fetchone()
    return int(row["job_id"])


def claim_job(conn: sqlite3.Connection) -> dict[str, Any] | None:
    now = utcnow()
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        """
        SELECT * FROM crawl_jobs
        WHERE status IN ('pending', 'retry') AND available_at <= ?
        ORDER BY priority, job_id
        LIMIT 1
        """,
        (now,),
    ).fetchone()
    if row is None:
        conn.commit()
        return None
    updated = conn.execute(
        """
        UPDATE crawl_jobs
        SET status = 'running', attempts = attempts + 1, leased_at = ?, updated_at = ?
        WHERE job_id = ? AND status IN ('pending', 'retry')
        """,
        (now, now, row["job_id"]),
    ).rowcount
    conn.commit()
    if not updated:
        return None
    claimed = dict(row)
    claimed["attempts"] = int(row["attempts"]) + 1
    claimed["params"] = json.loads(row["params_json"])
    return claimed


def complete_job(conn: sqlite3.Connection, job_id: int) -> None:
    now = utcnow()
    conn.execute(
        """
        UPDATE crawl_jobs
        SET status = 'completed', completed_at = ?, leased_at = NULL,
            last_error = NULL, updated_at = ?
        WHERE job_id = ?
        """,
        (now, now, job_id),
    )
    conn.commit()


def fail_job(conn: sqlite3.Connection, job: dict[str, Any], exc: Exception) -> None:
    now = utcnow()
    attempts = int(job["attempts"])
    is_dead = attempts >= int(job["max_attempts"])
    delay = min(3600, 2 ** min(attempts, 10))
    available = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(timespec="seconds")
    message = str(exc)[:2000]
    conn.execute(
        """
        INSERT INTO crawl_errors(job_id, request_key, error_type, message, occurred_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (job["job_id"], job["request_key"], type(exc).__name__, message, now),
    )
    conn.execute(
        """
        UPDATE crawl_jobs
        SET status = ?, available_at = ?, leased_at = NULL, last_error = ?, updated_at = ?
        WHERE job_id = ?
        """,
        ("dead" if is_dead else "retry", available, message, now, job["job_id"]),
    )
    conn.commit()


def reset_stale_jobs(conn: sqlite3.Connection, older_than_minutes: int = 30) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)).isoformat(timespec="seconds")
    now = utcnow()
    count = conn.execute(
        """
        UPDATE crawl_jobs
        SET status = 'retry', available_at = ?, leased_at = NULL,
            last_error = 'stale lease recovered', updated_at = ?
        WHERE status = 'running' AND leased_at < ?
        """,
        (now, now, cutoff),
    ).rowcount
    conn.commit()
    return count


def queue_counts(conn: sqlite3.Connection) -> dict[str, int]:
    result = {status: 0 for status in ("pending", "running", "retry", "completed", "dead")}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM crawl_jobs GROUP BY status"):
        result[row["status"]] = int(row["n"])
    return result
