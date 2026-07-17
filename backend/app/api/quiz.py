"""League-aware career quiz endpoints."""
from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..db import query


router = APIRouter(prefix="/api", tags=["quiz"])

VALID_RECOGNITIONS = {"known", "less_known", "obscure"}
DIFFICULTY_TO_RECOGNITION = {
    "easy": "known",
    "medium": "less_known",
    "hard": "obscure",
}
RETIREMENT_GAP_YEARS = 2
MAX_EXCLUDE = 100


def _parse_exclude(raw: str) -> list[int]:
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
            if len(out) >= MAX_EXCLUDE:
                break
    return out


def _pick_player_id(
    conn: sqlite3.Connection,
    league: str,
    recognition: str,
    exclude: list[int],
) -> int | None:
    if league == "ALL":
        table = "global_quiz_pool"
        league_sql = ""
        league_params: tuple[str, ...] = ()
    else:
        table = "quiz_pool"
        league_sql = "AND competition_id = ?"
        league_params = (league,)
    if exclude:
        placeholders = ",".join("?" * len(exclude))
        row = conn.execute(
            f"""
            SELECT DISTINCT player_id
            FROM {table}
            WHERE recognition = ? {league_sql}
              AND player_id NOT IN ({placeholders})
            ORDER BY RANDOM()
            LIMIT 1
            """,
            (recognition, *league_params, *exclude),
        ).fetchone()
        if row:
            return row["player_id"]
    row = conn.execute(
        f"""
        SELECT DISTINCT player_id
        FROM {table}
        WHERE recognition = ? {league_sql}
        ORDER BY RANDOM()
        LIMIT 1
        """,
        (recognition, *league_params),
    ).fetchone()
    return row["player_id"] if row else None


_CLUBS_SQL = """
    SELECT cl.name,
           cl.logo_url,
           pc.date_from,
           pc.date_to,
           CASE WHEN cl.name LIKE '%Retired%' THEN 1 ELSE 0 END AS is_retirement
    FROM player_clubs pc
    JOIN clubs cl ON cl.club_id = pc.club_id
    WHERE pc.player_id = ?
      AND cl.name NOT LIKE '%Without Club%'
      AND cl.name NOT LIKE '%Career break%'
      AND cl.name NOT LIKE '%Unknown%'
      AND cl.name IS NOT NULL AND cl.name != ''
    ORDER BY
        is_retirement,
        COALESCE(pc.date_from, pc.date_to, '9999'),
        pc.date_from NULLS FIRST,
        COALESCE(pc.date_to, '9999')
"""


def _load_quiz(
    conn: sqlite3.Connection,
    league: str,
    recognition: str,
    exclude: list[int],
) -> dict | None:
    player_id = _pick_player_id(conn, league, recognition, exclude)
    if player_id is None:
        return None
    player = conn.execute(
        """
        SELECT player_id, name, country_of_citizenship, position, sub_position,
               date_of_birth, image_url
        FROM players
        WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()
    if not player:
        return None
    clubs = [
        {
            "name": row["name"],
            "logo_url": row["logo_url"],
            "date_from": row["date_from"],
            "date_to": row["date_to"],
            "is_retirement": bool(row["is_retirement"]),
        }
        for row in conn.execute(_CLUBS_SQL, (player_id,)).fetchall()
    ]
    _append_synthetic_retirement(clubs)
    return {
        "player_id": player["player_id"],
        "name": player["name"],
        "country": player["country_of_citizenship"],
        "position": player["position"],
        "sub_position": player["sub_position"],
        "date_of_birth": player["date_of_birth"],
        "image_url": player["image_url"],
        "clubs": clubs,
        "league": league,
        "recognition": recognition,
    }


def _append_synthetic_retirement(clubs: list[dict]) -> None:
    if not clubs or any(item["is_retirement"] for item in clubs):
        return
    if any(item["date_to"] is None for item in clubs):
        return
    end_dates = [item["date_to"] for item in clubs if item["date_to"]]
    if not end_dates:
        return
    latest_end = max(end_dates)
    cutoff = date.today().replace(
        year=date.today().year - RETIREMENT_GAP_YEARS
    ).isoformat()
    if latest_end < cutoff:
        clubs.append({
            "name": "Retired",
            "logo_url": None,
            "date_from": latest_end,
            "date_to": None,
            "is_retirement": True,
        })


def _quiz_options(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        SELECT c.competition_id, c.name, c.country, c.season_id, c.sort_order,
               c.is_special, q.recognition, COUNT(*) AS player_count
        FROM competitions c
        JOIN quiz_pool q ON q.competition_id = c.competition_id
        GROUP BY c.competition_id, q.recognition
        ORDER BY c.sort_order
        """
    ).fetchall()
    competitions: dict[str, dict] = {}
    for row in rows:
        item = competitions.setdefault(row["competition_id"], {
            "id": row["competition_id"],
            "name": row["name"],
            "country": row["country"],
            "season": row["season_id"],
            "is_special": bool(row["is_special"]),
            "counts": {key: 0 for key in VALID_RECOGNITIONS},
        })
        item["counts"][row["recognition"]] = row["player_count"]
    ordered = list(competitions.values())
    all_counts = {key: 0 for key in VALID_RECOGNITIONS}
    for row in conn.execute(
        """
        SELECT recognition, COUNT(*) AS player_count
        FROM global_quiz_pool
        GROUP BY recognition
        """
    ):
        all_counts[row["recognition"]] = row["player_count"]
    return {
        "leagues": [{
            "id": "ALL",
            "name": "All Leagues",
            "country": "International",
            "season": None,
            "is_special": True,
            "counts": all_counts,
        }, *ordered],
        "recognitions": ["known", "less_known", "obscure"],
    }


@router.get("/quiz/options")
async def quiz_options() -> dict:
    return await query(_quiz_options)


@router.get("/quiz")
async def quiz(
    league: str = Query("ALL"),
    recognition: str | None = Query(None),
    difficulty: str | None = Query(None),
    exclude: str = Query(""),
) -> dict:
    if recognition not in VALID_RECOGNITIONS:
        recognition = DIFFICULTY_TO_RECOGNITION.get(difficulty or "", "known")
    league = league.upper()
    valid_league = await query(
        lambda conn: league == "ALL" or conn.execute(
            "SELECT 1 FROM competitions WHERE competition_id = ?",
            (league,),
        ).fetchone() is not None
    )
    if not valid_league:
        league = "ALL"
    result = await query(
        lambda conn: _load_quiz(
            conn,
            league,
            recognition,
            _parse_exclude(exclude),
        )
    )
    if not result:
        raise HTTPException(status_code=404, detail="Oyuncu bulunamadı")
    return result
