"""Persistent daily challenge scheduling from the global known-player pool."""
from __future__ import annotations

import hashlib
import sqlite3
from collections import Counter
from datetime import date, timedelta
from typing import Any

from backend.app.daily import (
    DAILY_SELECTION_VERSION,
    DAILY_START_DATE,
    daily_number,
    daily_today,
)

from .database import utcnow


SCHEDULE_AHEAD_DAYS = 365
RECENT_PLAYER_WINDOW = 60


def _date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _selection_key(challenge_date: str, player_id: int) -> tuple[bytes, int]:
    payload = f"{DAILY_SELECTION_VERSION}:{challenge_date}:{player_id}".encode("ascii")
    return hashlib.sha256(payload).digest(), player_id


def build_daily_schedule(
    source: sqlite3.Connection,
    game: sqlite3.Connection,
    build_id: str,
    today: date | None = None,
) -> dict[str, Any]:
    """Keep existing dates stable and schedule missing dates from global known players."""
    today = today or daily_today()
    schedule_end = today + timedelta(days=SCHEDULE_AHEAD_DAYS)
    known_players = {
        int(row["player_id"]): int(row["recognition_score"])
        for row in game.execute(
            """
            SELECT player_id, recognition_score
            FROM global_quiz_pool
            WHERE recognition = 'known'
            """
        )
    }
    if not known_players:
        raise RuntimeError("Cannot build daily schedule without global known players")

    existing = {
        row["challenge_date"]: dict(row)
        for row in source.execute(
            """
            SELECT challenge_date, day_number, player_id, recognition_score,
                   selection_version, scheduled_build_id, scheduled_at
            FROM daily_challenges
            WHERE challenge_date >= ?
            ORDER BY challenge_date
            """,
            (DAILY_START_DATE.isoformat(),),
        )
    }
    usage = Counter(
        int(row["player_id"])
        for row in existing.values()
        if int(row["player_id"]) in known_players
    )
    scheduled_at = utcnow()
    inserted = 0

    for challenge_date in _date_range(DAILY_START_DATE, schedule_end):
        date_text = challenge_date.isoformat()
        expected_day = daily_number(challenge_date)
        current = existing.get(date_text)
        if current:
            if int(current["day_number"]) != expected_day:
                raise RuntimeError(
                    f"Daily challenge numbering mismatch for {date_text}: "
                    f"{current['day_number']} != {expected_day}"
                )
            continue

        recent_ids = {
            int(existing[previous.isoformat()]["player_id"])
            for offset in range(1, RECENT_PLAYER_WINDOW + 1)
            if (previous := challenge_date - timedelta(days=offset)).isoformat() in existing
        }
        candidates = [
            player_id for player_id in known_players
            if player_id not in recent_ids
        ] or list(known_players)
        minimum_usage = min(usage[player_id] for player_id in candidates)
        least_used = [
            player_id for player_id in candidates
            if usage[player_id] == minimum_usage
        ]
        player_id = min(
            least_used,
            key=lambda candidate: _selection_key(date_text, candidate),
        )
        row = {
            "challenge_date": date_text,
            "day_number": expected_day,
            "player_id": player_id,
            "recognition_score": known_players[player_id],
            "selection_version": DAILY_SELECTION_VERSION,
            "scheduled_build_id": build_id,
            "scheduled_at": scheduled_at,
        }
        source.execute(
            """
            INSERT INTO daily_challenges(
                challenge_date, day_number, player_id, recognition_score,
                selection_version, scheduled_build_id, scheduled_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            tuple(row.values()),
        )
        existing[date_text] = row
        usage[player_id] += 1
        inserted += 1

    game_player_ids = {
        int(row["player_id"]) for row in game.execute("SELECT player_id FROM players")
    }
    missing_players = sorted({
        int(row["player_id"]) for row in existing.values()
        if int(row["player_id"]) not in game_player_ids
    })
    if missing_players:
        raise RuntimeError(
            "Scheduled daily players missing from game database: "
            + ",".join(map(str, missing_players[:10]))
        )

    rows = [
        (
            row["challenge_date"],
            row["day_number"],
            row["player_id"],
            row["recognition_score"],
            row["selection_version"],
            row["scheduled_build_id"],
            row["scheduled_at"],
        )
        for row in sorted(existing.values(), key=lambda item: item["challenge_date"])
    ]
    game.executemany(
        "INSERT INTO daily_challenges VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    return {
        "start": DAILY_START_DATE.isoformat(),
        "end": max(existing) if existing else None,
        "scheduled": len(rows),
        "inserted": inserted,
        "known_pool": len(known_players),
    }
