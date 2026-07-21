"""Kulüp ve oyuncu arama (autocomplete).

Sıcak yol: trigram FTS5 ile index'li substring araması. Trigram en az 3 harflik
terim ister; daha kısa sorgular için index'li LIKE'a düşülür. Sıralama bucket'ları
(tam eşleşme / kelime-prefix / orta eşleşme) korunur.

Kulüp araması düello modunda takım seçimi için kullanılır.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Query

from ..db import query
from ..country_data import flag_code_for
from ..text import normalize_text

router = APIRouter(prefix="/api", tags=["search"])

FTS_MIN_LEN = 3  # trigram tokenizer alt sınırı
QUERY_MAX_LEN = 80
QUERY_MAX_WORDS = 6

# "Günün Futbolcusu" tahmin evreni = TÜM aktif oyuncular (güncel market değeri olan).
# Gizli oyuncu havuzu daha dardır (classic.py); arama ise tüm aktifleri kapsar.
ACTIVE_PREDICATE = "(p.market_value IS NOT NULL AND p.market_value > 0)"


def _words(q: str) -> list[str]:
    return normalize_text(q[:QUERY_MAX_LEN]).split()[:QUERY_MAX_WORDS]


def _fts_match(words: list[str]) -> str | None:
    """Her kelimeyi substring olarak arayan FTS5 MATCH ifadesi; kısa kelime varsa None.

    Güvenlik invariantı: `words` her zaman normalize_text() çıktısıdır → yalnız
    [a-z0-9] içerir. Bu yüzden "..." ile sarmak FTS sözdizimi enjeksiyonuna kapalı
    ve sonuç bind edilir (MATCH :match). normalize_text gevşetilirse burası da
    gözden geçirilmeli.
    """
    if any(len(w) < FTS_MIN_LEN for w in words):
        return None
    return " AND ".join(f'"{w}"' for w in words)


def _bucket_params(words: list[str]) -> dict[str, str]:
    """Tam/prefix eşleşme sıralaması için ortak parametreler."""
    first, last = words[0], words[-1]
    return {
        "norm": " ".join(words),
        "fw": f"{first}%", "fw2": f"% {first}%",
        "lw": f"{last}%", "lw2": f"% {last}%",
    }


@router.get("/search-club")
async def search_club(q: str = Query("", min_length=0, max_length=QUERY_MAX_LEN)) -> list[dict]:
    words = _words(q.strip())
    if not words or len(q.strip()) < 2:
        return []

    bucket = "ca.search_alias"
    order = f"""
        ORDER BY
            CASE
                WHEN {bucket} = :norm THEN 0
                WHEN ({bucket} LIKE :fw OR {bucket} LIKE :fw2)
                 AND ({bucket} LIKE :lw OR {bucket} LIKE :lw2) THEN 1
                ELSE 2
            END,
            cl.prestige_score DESC,
            LENGTH(cl.name)
        LIMIT 60
    """
    params = _bucket_params(words)
    match = _fts_match(words)

    if match:
        params["match"] = match
        sql = f"""
            SELECT ca.club_id, cl.name, cl.logo_url, ca.search_alias
            FROM club_aliases_fts ca
            JOIN clubs cl ON cl.club_id = ca.club_id
            WHERE club_aliases_fts MATCH :match
            {order}
        """
    else:
        for i, w in enumerate(words):
            params[f"w{i}"] = f"%{w}%"
        where = " AND ".join(f"ca.search_alias LIKE :w{i}" for i in range(len(words)))
        sql = f"""
            SELECT ca.club_id, cl.name, cl.logo_url, ca.search_alias
            FROM club_aliases ca
            JOIN clubs cl ON cl.club_id = ca.club_id
            WHERE {where}
            {order}
        """

    rows = await query(lambda c: c.execute(sql, params).fetchall())
    return _dedupe_clubs(rows)


def _dedupe_clubs(rows: list[sqlite3.Row], limit: int = 20) -> list[dict]:
    seen: set[int] = set()
    out: list[dict] = []
    for r in rows:
        if r["club_id"] in seen:
            continue
        seen.add(r["club_id"])
        out.append({"club_id": r["club_id"], "name": r["name"], "logo_url": r["logo_url"]})
        if len(out) >= limit:
            break
    return out


@router.get("/search-player")
async def search_player(
    q: str = Query("", min_length=0, max_length=QUERY_MAX_LEN),
    active: int = Query(0),
) -> list[dict]:
    words = _words(q.strip())
    if not words or len(q.strip()) < 2:
        return []

    # active=1 → yalnız aktif oyuncular (Günün Futbolcusu autocomplete'i).
    active_clause = f" AND {ACTIVE_PREDICATE}" if active else ""

    # Contentless FTS'ten search_name dönmediği için bucket'ı players tablosundan al.
    bucket = "p.search_name"
    order = f"""
        ORDER BY
            CASE
                WHEN {bucket} = :norm THEN 0
                WHEN ({bucket} LIKE :fw OR {bucket} LIKE :fw2)
                 AND ({bucket} LIKE :lw OR {bucket} LIKE :lw2) THEN 1
                ELSE 2
            END,
            COALESCE(p.highest_market_value, p.market_value, 0) DESC,
            LENGTH(p.name)
        LIMIT 15
    """
    params = _bucket_params(words)
    match = _fts_match(words)

    if match:
        params["match"] = match
        sql = f"""
            SELECT p.player_id, p.name, p.country_of_citizenship, p.position, p.image_url
            FROM players_fts f
            JOIN players p ON p.player_id = f.rowid
            WHERE players_fts MATCH :match{active_clause}
            {order}
        """
    else:
        for i, w in enumerate(words):
            params[f"w{i}"] = f"%{w}%"
        where = " AND ".join(f"p.search_name LIKE :w{i}" for i in range(len(words)))
        sql = f"""
            SELECT p.player_id, p.name, p.country_of_citizenship, p.position, p.image_url
            FROM players p
            WHERE {where}{active_clause}
            {order}
        """

    rows = await query(lambda c: c.execute(sql, params).fetchall())
    return [
        {
            "player_id": r["player_id"],
            "name": r["name"],
            "country": r["country_of_citizenship"],
            "country_code": flag_code_for(r["country_of_citizenship"]),
            "position": r["position"],
            "image_url": r["image_url"],
        }
        for r in rows
    ]
