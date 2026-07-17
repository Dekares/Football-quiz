"""Derive deterministic player-club periods from transfer facts."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any

from .database import utcnow


def _merge_same_club_periods(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for club_id in sorted({period["club_id"] for period in periods}):
        club_periods = sorted(
            (period for period in periods if period["club_id"] == club_id),
            key=lambda period: (
                period["date_from"] is not None,
                period["date_from"] or "",
                period["date_to"] or "9999-12-31",
            ),
        )
        for period in club_periods:
            if period["date_from"] and period["date_from"] == period["date_to"]:
                continue
            if not merged or merged[-1]["club_id"] != club_id:
                merged.append(dict(period))
                continue
            previous = merged[-1]
            overlaps = (
                previous["date_to"] is None
                or period["date_from"] is None
                or previous["date_to"] >= period["date_from"]
            )
            if not overlaps:
                merged.append(dict(period))
                continue
            starts = [
                value for value in (previous["date_from"], period["date_from"])
                if value is not None
            ]
            previous["date_from"] = min(starts) if starts else None
            if previous["date_to"] is None or period["date_to"] is None:
                previous["date_to"] = None
            else:
                previous["date_to"] = max(previous["date_to"], period["date_to"])
            if period["source"] == "roster":
                previous["source"] = "roster"
                previous["confidence"] = "inferred"
            elif previous["confidence"] != "inferred":
                previous["confidence"] = (
                    "exact"
                    if previous["confidence"] == period["confidence"] == "exact"
                    else "bounded"
                )
    return sorted(
        merged,
        key=lambda period: (
            period["date_from"] or period["date_to"] or "",
            period["club_id"],
        ),
    )


def _normalize_open_periods(
    periods: list[dict[str, Any]],
    current_club_id: int | None,
    current_joined_on: str | None,
    is_retired: bool,
    retired_since: str | None,
) -> list[dict[str, Any]]:
    """Guarantee at most one authoritative open career period."""
    starts = sorted({
        period["date_from"] for period in periods if period["date_from"] is not None
    })
    normalized: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for period in periods:
        item = dict(period)
        if item["date_to"] is not None:
            normalized.append(item)
            continue
        start = item["date_from"]
        next_start = next(
            (candidate for candidate in starts if start and candidate > start),
            None,
        )
        if next_start:
            item["date_to"] = next_start
            item["confidence"] = "bounded"
            normalized.append(item)
        else:
            unresolved.append(item)

    if is_retired:
        for item in unresolved:
            start = item["date_from"]
            if retired_since and (start is None or retired_since > start):
                item["date_to"] = retired_since
                item["confidence"] = "bounded"
                normalized.append(item)
    elif current_club_id is not None:
        normalized.append({
            "club_id": current_club_id,
            "date_from": current_joined_on,
            "date_to": None,
            "source": "roster",
            "confidence": "inferred",
        })
    elif unresolved:
        winner = max(
            unresolved,
            key=lambda item: item["date_from"] or "",
        )
        normalized.append(winner)

    return _merge_same_club_periods(normalized)


def derive_player_periods(conn: sqlite3.Connection, player_id: int) -> int:
    transfers = conn.execute(
        """
        SELECT transfer_id, from_club_id, to_club_id, transfer_date
        FROM transfers
        WHERE player_id = ? AND is_upcoming = 0
        ORDER BY transfer_date, transfer_id
        """,
        (player_id,),
    ).fetchall()
    conn.execute(
        "DELETE FROM player_club_periods WHERE player_id = ? AND source IN ('transfer', 'roster')",
        (player_id,),
    )
    periods: list[dict[str, Any]] = []
    open_periods: dict[int, list[int]] = defaultdict(list)

    def usable(club_id: int | None) -> bool:
        if club_id is None:
            return False
        row = conn.execute("SELECT is_placeholder FROM clubs WHERE club_id = ?", (club_id,)).fetchone()
        return bool(row) and not bool(row["is_placeholder"])

    for transfer in transfers:
        transfer_date = transfer["transfer_date"]
        from_id = transfer["from_club_id"]
        to_id = transfer["to_club_id"]
        if usable(from_id):
            if open_periods[from_id]:
                index = open_periods[from_id].pop()
                periods[index]["date_to"] = transfer_date
                periods[index]["confidence"] = "exact"
            else:
                periods.append({
                    "club_id": from_id, "date_from": None, "date_to": transfer_date,
                    "source": "transfer", "confidence": "bounded",
                })
        if usable(to_id):
            periods.append({
                "club_id": to_id, "date_from": transfer_date, "date_to": None,
                "source": "transfer", "confidence": "bounded",
            })
            open_periods[to_id].append(len(periods) - 1)

    current = conn.execute(
        """
        SELECT current_club_id, is_retired, retired_since
        FROM players WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()
    current_club_id = current["current_club_id"] if current else None
    if not usable(current_club_id):
        current_club_id = None
    roster = conn.execute(
        """
        SELECT joined_on
        FROM club_rosters
        WHERE player_id = ? AND club_id = ?
        ORDER BY discovered_at DESC, season_id DESC
        LIMIT 1
        """,
        (player_id, current_club_id),
    ).fetchone() if current_club_id is not None else None
    joined_candidates = [
        roster["joined_on"] if roster else None,
    ]
    if current_club_id is not None:
        joined_candidates.extend(
            transfer["transfer_date"] for transfer in transfers
            if transfer["to_club_id"] == current_club_id
        )
    current_joined_on = max(
        (value for value in joined_candidates if value is not None),
        default=None,
    )
    periods = _normalize_open_periods(
        periods,
        current_club_id,
        current_joined_on,
        bool(current and current["is_retired"]),
        current["retired_since"] if current else None,
    )

    now = utcnow()
    rows = []
    seen: set[tuple[Any, ...]] = set()
    for period in periods:
        key = (period["club_id"], period["date_from"], period["date_to"])
        if key in seen:
            continue
        seen.add(key)
        rows.append((player_id, *key, period["source"], period["confidence"], now))
    conn.executemany(
        """
        INSERT INTO player_club_periods(
            player_id, club_id, date_from, date_to, source, confidence, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def derive_all_periods(conn: sqlite3.Connection) -> dict[str, int]:
    player_ids = [
        int(row["player_id"])
        for row in conn.execute(
            "SELECT player_id FROM players WHERE profile_loaded = 1 OR player_id IN "
            "(SELECT DISTINCT player_id FROM transfers) ORDER BY player_id"
        )
    ]
    periods = 0
    for player_id in player_ids:
        periods += derive_player_periods(conn, player_id)
    conn.commit()
    return {"players": len(player_ids), "periods": periods}
