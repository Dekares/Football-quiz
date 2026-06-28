"""Günün Futbolcusu (LoLdle "Classic" tarzı) — ipuçsuz tahmin, özellik kıyası.

Gizli bir futbolcu var; oyuncu doğrudan isim yazar. Her tahminde tahmin edilen
oyuncunun özellikleri gizli oyuncununkilerle kıyaslanır: 🟩 aynı / 🟥 farklı,
sayısallarda (yaş, değer) ek olarak ↑↓ yön. Doğru oyuncuda biter.

Yalnız **aktif** (güncel market değeri olan) tanınmış oyuncular havuza girer.
Stateless: gizli oyuncu tarihten (TR saati) deterministik seçilir → herkese aynı.
Sunucuda durum yok; ilerleme/seri ve 8 tahmin hakkı istemcide (localStorage)
yönetilir. Cevap oyun sırasında sızmaz; oyun bitince /classic/reveal ile açılır.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query, Response

from ..db import query

router = APIRouter(prefix="/api", tags=["classic"])

_TZ = timezone(timedelta(hours=3))          # TR saati (UTC+3, DST yok)
_EPOCH = date(2024, 1, 1)

# GİZLİ oyuncu havuzu: aktif + tanınmış. Tanınırlık ölçütü ZİRVE değer
# (highest_market_value) — güncel değer yaşlı ünlüleri (Suárez/Isco/Modrić) kaçırır.
# Arama evreni daha geniştir (tüm aktif oyuncular; bkz. search.ACTIVE_PREDICATE).
_PEAK_THRESHOLD = 80_000_000
_POOL = (
    f"market_value IS NOT NULL AND market_value > 0 AND highest_market_value >= {_PEAK_THRESHOLD} "
    "AND is_legend = 0 "                # emekli efsaneler bayat bir güncel değer taşıyabilir → ele
    "AND position IN ('Attack', 'Midfield', 'Defender', 'Goalkeeper') "
    "AND country_of_citizenship IS NOT NULL AND country_of_citizenship != '' "
    "AND EXISTS (SELECT 1 FROM player_clubs pc WHERE pc.player_id = players.player_id)"
)

# "Kısmen" (🟨) eşleşmeleri için kıta / konfederasyon haritaları.
_CONTINENT = {
    "Austria": "EU", "Belgium": "EU", "Bosnia-Herzegovina": "EU", "Croatia": "EU",
    "Czech Republic": "EU", "Denmark": "EU", "England": "EU", "France": "EU",
    "Georgia": "EU", "Germany": "EU", "Greece": "EU", "Hungary": "EU", "Ireland": "EU",
    "Italy": "EU", "Montenegro": "EU", "Netherlands": "EU", "Norway": "EU", "Poland": "EU",
    "Portugal": "EU", "Scotland": "EU", "Serbia": "EU", "Slovakia": "EU", "Slovenia": "EU",
    "Spain": "EU", "Sweden": "EU", "Switzerland": "EU", "Türkiye": "EU", "Turkey": "EU",
    "Ukraine": "EU", "Wales": "EU",
    "Argentina": "SA", "Brazil": "SA", "Chile": "SA", "Colombia": "SA", "Ecuador": "SA",
    "Uruguay": "SA", "Paraguay": "SA", "Peru": "SA", "Venezuela": "SA", "Bolivia": "SA",
    "Canada": "NA", "Jamaica": "NA", "Mexico": "NA", "United States": "NA", "USA": "NA",
    "Algeria": "AF", "Burkina Faso": "AF", "Cameroon": "AF", "Cote d'Ivoire": "AF",
    "Ivory Coast": "AF", "DR Congo": "AF", "Egypt": "AF", "Gabon": "AF", "Ghana": "AF",
    "Guinea": "AF", "Morocco": "AF", "Nigeria": "AF", "Senegal": "AF", "The Gambia": "AF",
    "Mali": "AF", "Tunisia": "AF",
    "Japan": "AS", "Korea, South": "AS", "South Korea": "AS", "Australia": "AS",
    "Saudi Arabia": "AS", "Iran": "AS",
}
_LEAGUE_CONF = {
    "TR1": "EU", "UKR1": "EU", "IT1": "EU", "GB1": "EU", "FR1": "EU", "PO1": "EU",
    "RU1": "EU", "ES1": "EU", "L1": "EU", "GR1": "EU", "NL1": "EU", "BE1": "EU",
    "PL1": "EU", "DK1": "EU", "SE1": "EU", "RO1": "EU", "NO1": "EU", "SER1": "EU",
    "TS1": "EU", "SC1": "EU", "C1": "EU", "A1": "EU", "KR1": "EU",
    "ARG1": "SA", "BRA1": "SA", "COL1": "SA",
    "MLS1": "NA", "MEX1": "NA",
    "JAP1": "AS", "SA1": "AS", "RSK1": "AS", "AUS1": "AS",
}

_secret_cache: dict[int, dict[str, Any]] = {}


def _today() -> date:
    return datetime.now(_TZ).date()


def _day_number(d: date | None = None) -> int:
    return ((d or _today()) - _EPOCH).days


def _scatter(day: int, n: int) -> int:
    return (day * 2654435761) % n


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
        "position": p["position"],
        "age": _age(p["date_of_birth"]),
        "value": p["market_value"] or 0,
        "club_id": club["club_id"] if club else None,
        "club_name": club["name"] if club else None,
        "league": club["league"] if club else None,
    }


def _select_secret(conn: sqlite3.Connection, day: int) -> dict[str, Any] | None:
    ids = [r[0] for r in conn.execute(
        f"SELECT player_id FROM players WHERE {_POOL} ORDER BY player_id"
    )]
    if not ids:
        return None
    return _player_facts(conn, ids[_scatter(day, len(ids))])


async def _get_secret(day: int) -> dict[str, Any] | None:
    if day not in _secret_cache:
        secret = await query(lambda c: _select_secret(c, day))
        if not secret:
            return None
        _secret_cache[day] = secret
        for stale in [k for k in _secret_cache if k < day - 2]:
            del _secret_cache[stale]
    return _secret_cache[day]


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
        "nationality": _cat(
            gc, gc == sc,
            bool(_CONTINENT.get(gc)) and _CONTINENT.get(gc) == _CONTINENT.get(sc),
        ),
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
    day = _day_number()
    secret = await _get_secret(day)
    if not secret:
        return {"error": "unavailable"}
    return {"day": day, "date": _today().isoformat()}


@router.get("/classic/guess")
async def classic_guess(response: Response, player_id: int = Query(..., ge=1)) -> dict[str, Any]:
    """Bir tahminin özellik kıyası. Doğruysa correct=true (kazanan tahmin reveal'dır)."""
    response.headers["Cache-Control"] = _NO_STORE
    day = _day_number()
    secret = await _get_secret(day)
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
    day = _day_number()
    secret = await _get_secret(day)
    if not secret:
        return {"error": "unavailable"}
    return {
        "player": {
            "player_id": secret["player_id"],
            "name": secret["name"],
            "image_url": secret["image_url"],
            "country": secret["country"],
            "position": secret["position"],
            "club_name": secret["club_name"],
        }
    }
