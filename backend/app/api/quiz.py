"""Tahmin oyunu: rastgele bir oyuncu + kronolojik kulüp geçmişi.

Aday havuzu build anında quiz_pool'a hesaplandığı için burada tek satır çekilir
(çalışma anı full scan yok).
"""
from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..db import query

router = APIRouter(prefix="/api", tags=["quiz"])

VALID_DIFFICULTIES = {"easy", "medium", "hard"}
RETIREMENT_GAP_YEARS = 2  # son kulüpten bu kadar yıl geçtiyse sentetik "Emeklilik"
MAX_EXCLUDE = 100         # client'tan gelen "son görülenler" listesi için üst sınır


def _parse_exclude(raw: str) -> list[int]:
    """`exclude=1,2,3` → [1,2,3]. Bozuk parçaları atar, üst sınırla kırpar."""
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
            if len(out) >= MAX_EXCLUDE:
                break
    return out


def _pick_player_id(c: sqlite3.Connection, difficulty: str, exclude: list[int]) -> int | None:
    """Havuzdan rastgele bir oyuncu seç; mümkünse son görülenleri dışla.

    Dışlananlar havuzu tüketirse (küçük havuz / çok oynanmış) dışlama yok sayılır
    → her zaman bir oyuncu döner, oyun asla boş ekranla kilitlenmez.
    """
    if exclude:
        placeholders = ",".join("?" * len(exclude))
        row = c.execute(
            f"SELECT player_id FROM quiz_pool WHERE difficulty = ? "
            f"AND player_id NOT IN ({placeholders}) ORDER BY RANDOM() LIMIT 1",
            (difficulty, *exclude),
        ).fetchone()
        if row:
            return row["player_id"]
    row = c.execute(
        "SELECT player_id FROM quiz_pool WHERE difficulty = ? ORDER BY RANDOM() LIMIT 1",
        (difficulty,),
    ).fetchone()
    return row["player_id"] if row else None

# Kulüp geçmişi: placeholder kulüpler gizlenir; "Retired" kaydı her zaman en sona.
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


def _load_quiz(c: sqlite3.Connection, difficulty: str, exclude: list[int]) -> dict | None:
    player_id = _pick_player_id(c, difficulty, exclude)
    if player_id is None:
        return None

    player = c.execute(
        "SELECT player_id, name, country_of_citizenship, position, image_url "
        "FROM players WHERE player_id = ?",
        (player_id,),
    ).fetchone()
    if not player:
        return None

    clubs = [
        {
            "name": r["name"],
            "logo_url": r["logo_url"],
            "date_from": r["date_from"],
            "date_to": r["date_to"],
            "is_retirement": bool(r["is_retirement"]),
        }
        for r in c.execute(_CLUBS_SQL, (player["player_id"],)).fetchall()
    ]
    _append_synthetic_retirement(clubs)

    return {
        "player_id": player["player_id"],
        "name": player["name"],
        "country": player["country_of_citizenship"],
        "position": player["position"],
        "image_url": player["image_url"],
        "clubs": clubs,
    }


def _append_synthetic_retirement(clubs: list[dict]) -> None:
    """DB'de Retired kaydı yoksa ama hiç aktif (date_to=NULL) kontrat yoksa ve son
    bitiş 2+ yıl önceyse, ipucu olarak sentetik bir 'Retired' satırı eklenir."""
    if not clubs or any(x["is_retirement"] for x in clubs):
        return
    if any(x["date_to"] is None for x in clubs):
        return  # aktif oyuncu
    end_dates = [x["date_to"] for x in clubs if x["date_to"]]
    if not end_dates:
        return
    latest_end = max(end_dates)
    cutoff = date.today().replace(year=date.today().year - RETIREMENT_GAP_YEARS).isoformat()
    if latest_end < cutoff:
        clubs.append({
            "name": "Retired", "logo_url": None,
            "date_from": latest_end, "date_to": None, "is_retirement": True,
        })


@router.get("/quiz")
async def quiz(difficulty: str = Query("easy"), exclude: str = Query("")) -> dict:
    if difficulty not in VALID_DIFFICULTIES:
        difficulty = "easy"
    ex = _parse_exclude(exclude)
    result = await query(lambda c: _load_quiz(c, difficulty, ex))
    if not result:
        raise HTTPException(status_code=404, detail="Oyuncu bulunamadı")
    return result
