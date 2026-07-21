"""Günün Futbolcusu (LoLdle "Classic" tarzı) — ipuçsuz tahmin, özellik kıyası.

Gizli bir futbolcu var; oyuncu doğrudan isim yazar. Her tahminde tahmin edilen
oyuncunun özellikleri gizli oyuncununkilerle kıyaslanır: 🟩 aynı / 🟥 farklı,
sayısallarda (yaş, değer) ek olarak ↑↓ yön. Doğru oyuncuda biter.

Gizli oyuncu publish sırasında global "bilindik" havuzundan kalıcı takvime yazılır.
Bugünün kaydı Türkiye tarihine göre okunur → herkese aynı ve build'ler arasında sabit.
Sunucuda durum yok; ilerleme/seri ve 8 tahmin hakkı istemcide (localStorage)
yönetilir. Cevap oyun sırasında sızmaz; oyun bitince /classic/reveal ile açılır.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Query, Response

from ..daily import daily_number, daily_today
from ..db import query
from ..country_data import confederation_for, flag_code_for

router = APIRouter(prefix="/api", tags=["classic"])

_LEAGUE_CONF = {
    "TR1": "EU", "UKR1": "EU", "IT1": "EU", "GB1": "EU", "FR1": "EU", "PO1": "EU",
    "RU1": "EU", "ES1": "EU", "L1": "EU", "GR1": "EU", "NL1": "EU", "BE1": "EU",
    "PL1": "EU", "DK1": "EU", "SE1": "EU", "RO1": "EU", "NO1": "EU", "SER1": "EU",
    "TS1": "EU", "SC1": "EU", "C1": "EU", "A1": "EU", "KR1": "EU",
    "ARG1": "SA", "BRA1": "SA", "COL1": "SA",
    "MLS1": "NA", "MEX1": "NA",
    "JAP1": "AS", "SA1": "AS", "RSK1": "AS", "AUS1": "AS",
}

_secret_cache: dict[str, dict[str, Any]] = {}


def _today() -> date:
    return daily_today()


def _day_number(d: date | None = None) -> int:
    return daily_number(d or _today())


def _age(dob: str | None) -> int | None:
    if not dob:
        return None
    try:
        d = datetime.strptime(dob[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    t = _today()
    return t.year - d.year - ((t.month, t.day) < (d.month, d.day))


def _player_facts(conn: sqlite3.Connection, player_id: int) -> dict[str, Any] | None:
    """Bir oyuncunun kıyas vektörü: milliyet, mevki, yaş, güncel değer,
    güncel kulüp (en son katıldığı) ve o kulübün ligi."""
    p = conn.execute(
        "SELECT player_id, name, country_of_citizenship, date_of_birth, position, "
        "image_url, market_value FROM players WHERE player_id = ?",
        (player_id,),
    ).fetchone()
    if not p:
        return None

    # Güncel kulüp = en son katıldığı (en büyük date_from); ISO tarih string'i sıralanır.
    club, best_from = None, None
    for s in conn.execute(
        "SELECT pc.club_id, c.name, c.domestic_competition_id AS league, pc.date_from "
        "FROM player_clubs pc JOIN clubs c ON c.club_id = pc.club_id WHERE pc.player_id = ?",
        (player_id,),
    ):
        if not s["date_from"]:
            continue
        if best_from is None or s["date_from"] > best_from:
            best_from, club = s["date_from"], s

    return {
        "player_id": p["player_id"],
        "name": p["name"],
        "image_url": p["image_url"],
        "country": p["country_of_citizenship"],
        "country_code": flag_code_for(p["country_of_citizenship"]),
        "position": p["position"],
        "age": _age(p["date_of_birth"]),
        "value": p["market_value"] or 0,
        "club_id": club["club_id"] if club else None,
        "club_name": club["name"] if club else None,
        "league": club["league"] if club else None,
    }


def _select_secret(
    conn: sqlite3.Connection,
    challenge_date: str,
) -> dict[str, Any] | None:
    challenge = conn.execute(
        """
        SELECT challenge_date, day_number, player_id
        FROM daily_challenges
        WHERE challenge_date = ?
        """,
        (challenge_date,),
    ).fetchone()
    if not challenge:
        return None
    facts = _player_facts(conn, int(challenge["player_id"]))
    if not facts:
        return None
    facts["challenge_date"] = challenge["challenge_date"]
    facts["day_number"] = int(challenge["day_number"])
    return facts


async def _get_secret(challenge_date: str) -> dict[str, Any] | None:
    if challenge_date not in _secret_cache:
        secret = await query(lambda c: _select_secret(c, challenge_date))
        if not secret:
            return None
        _secret_cache[challenge_date] = secret
        for stale in sorted(_secret_cache)[:-3]:
            del _secret_cache[stale]
    return _secret_cache[challenge_date]


def _cat(value: Any, hit: bool, partial: bool = False) -> dict[str, Any]:
    return {"value": value, "status": "hit" if hit else ("partial" if partial else "miss")}


def _num(guess: int | None, secret: int | None, near: int) -> dict[str, Any]:
    """Sayısal: eşit 🟩, |fark|<=near 🟨, değilse 🟥; + yön (aranan büyük → up)."""
    if guess is None or secret is None:
        return {"value": guess, "status": "miss", "dir": None}
    if guess == secret:
        return {"value": guess, "status": "hit", "dir": None}
    status = "partial" if abs(guess - secret) <= near else "miss"
    return {"value": guess, "status": status, "dir": "up" if secret > guess else "down"}


def _num_value(guess: int, secret: int) -> dict[str, Any]:
    """Değer: eşit 🟩, %25 bandında 🟨, değilse 🟥; + yön."""
    if not guess or not secret:
        return {"value": guess, "status": "miss", "dir": None}
    if guess == secret:
        return {"value": guess, "status": "hit", "dir": None}
    status = "partial" if abs(guess - secret) <= 0.25 * secret else "miss"
    return {"value": guess, "status": status, "dir": "up" if secret > guess else "down"}


def _compare(secret: dict[str, Any], g: dict[str, Any]) -> dict[str, dict]:
    gc, sc = g["country"], secret["country"]
    gl, sl = g["league"], secret["league"]
    return {
        "nationality": {
            **_cat(
                gc, gc == sc,
                bool(confederation_for(gc))
                and confederation_for(gc) == confederation_for(sc),
            ),
            "code": g["country_code"],
        },
        "position": _cat(g["position"], g["position"] == secret["position"]),
        "age": _num(g["age"], secret["age"], near=2),
        "value": _num_value(g["value"], secret["value"]),
        # Kulüp: yalnız tam eşleşme (sarı yok — kullanıcı tercihi).
        "club": _cat(g["club_name"], bool(g["club_id"]) and g["club_id"] == secret["club_id"]),
        "league": _cat(
            gl, bool(gl) and gl == sl,
            bool(_LEAGUE_CONF.get(gl)) and _LEAGUE_CONF.get(gl) == _LEAGUE_CONF.get(sl),
        ),
    }


# Güne bağlı yanıtlar tarayıcıda cache'lenMEMELİ: gece yarısı (TR) gün değişince
# istemci bayat "day" alıp eski tahminleri göstermesin.
_NO_STORE = "no-store"


@router.get("/classic")
async def classic(response: Response) -> dict[str, Any]:
    """Bugünün meta'sı (gizli oyuncu GÖNDERİLMEZ)."""
    response.headers["Cache-Control"] = _NO_STORE
    secret = await _get_secret(_today().isoformat())
    if not secret:
        return {"error": "unavailable"}
    return {
        "day": secret["day_number"],
        "date": secret["challenge_date"],
    }


@router.get("/classic/guess")
async def classic_guess(response: Response, player_id: int = Query(..., ge=1)) -> dict[str, Any]:
    """Bir tahminin özellik kıyası. Doğruysa correct=true (kazanan tahmin reveal'dır)."""
    response.headers["Cache-Control"] = _NO_STORE
    secret = await _get_secret(_today().isoformat())
    if not secret:
        return {"error": "unavailable"}
    facts = await query(lambda c: _player_facts(c, player_id))
    if not facts:
        return {"error": "unknown_player"}
    return {
        "correct": facts["player_id"] == secret["player_id"],
        "guess": {
            "player_id": facts["player_id"],
            "name": facts["name"],
            "image_url": facts["image_url"],
        },
        "attrs": _compare(secret, facts),
    }


@router.get("/classic/reveal")
async def classic_reveal(response: Response) -> dict[str, Any]:
    """Bugünün gizli oyuncusunu açar — istemci yalnız oyun BİTİNCE çağırır."""
    response.headers["Cache-Control"] = _NO_STORE
    secret = await _get_secret(_today().isoformat())
    if not secret:
        return {"error": "unavailable"}
    return {
        "player": {
            "player_id": secret["player_id"],
            "name": secret["name"],
            "image_url": secret["image_url"],
            "country": secret["country"],
            "country_code": secret["country_code"],
            "position": secret["position"],
            "club_name": secret["club_name"],
        }
    }
