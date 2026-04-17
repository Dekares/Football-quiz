"""Soru + çeldirici üretimi, cevap doğrulama."""
from __future__ import annotations

import random
import sqlite3
from typing import Any


def _get_common_players(
    conn: sqlite3.Connection, club_a: int, club_b: int
) -> list[dict[str, Any]]:
    c = conn.cursor()
    c.execute(
        """
        SELECT DISTINCT p.player_id, p.name, p.country_of_citizenship, p.position,
               p.image_url, p.highest_market_value, p.is_legend
        FROM player_clubs pc1
        JOIN player_clubs pc2 ON pc1.player_id = pc2.player_id
        JOIN players p ON p.player_id = pc1.player_id
        WHERE pc1.club_id = ? AND pc2.club_id = ?
        """,
        (club_a, club_b),
    )
    return [
        {
            "player_id": r[0],
            "name": r[1],
            "country": r[2],
            "position": r[3],
            "image_url": r[4],
            "highest_market_value": r[5] or 0,
            "is_legend": r[6] or 0,
        }
        for r in c.fetchall()
    ]


def _get_distractors(
    conn: sqlite3.Connection,
    club_a: int,
    club_b: int,
    correct: dict[str, Any],
    n: int = 3,
) -> list[dict[str, Any]]:
    """Doğru cevaba benzer 3 çeldirici:
    - Aynı mevki
    - club_a VEYA club_b'de oynamış AMA ikisinde de oynamamış
    - Doğru cevabın son stint dönemine ±5 yıl yakın
    """
    c = conn.cursor()
    c.execute(
        """
        SELECT MAX(COALESCE(date_to, date_from))
        FROM player_clubs
        WHERE player_id = ?
        """,
        (correct["player_id"],),
    )
    row = c.fetchone()
    anchor_year: int | None = None
    if row and row[0]:
        try:
            anchor_year = int(row[0][:4])
        except (ValueError, TypeError):
            anchor_year = None

    year_lo = (anchor_year - 5) if anchor_year else None
    year_hi = (anchor_year + 5) if anchor_year else None

    query = """
        SELECT DISTINCT p.player_id, p.name, p.country_of_citizenship, p.position, p.image_url
        FROM players p
        JOIN player_clubs pc ON pc.player_id = p.player_id
        WHERE pc.club_id IN (?, ?)
          AND p.player_id != ?
          AND p.position = ?
          AND p.player_id NOT IN (
              SELECT pc1.player_id
              FROM player_clubs pc1
              JOIN player_clubs pc2 ON pc1.player_id = pc2.player_id
              WHERE pc1.club_id = ? AND pc2.club_id = ?
          )
    """
    params: list[Any] = [club_a, club_b, correct["player_id"], correct["position"], club_a, club_b]

    if year_lo is not None and year_hi is not None:
        query += """
          AND EXISTS (
              SELECT 1 FROM player_clubs pcx
              WHERE pcx.player_id = p.player_id
                AND CAST(substr(COALESCE(pcx.date_to, pcx.date_from), 1, 4) AS INTEGER)
                    BETWEEN ? AND ?
          )
        """
        params.extend([year_lo, year_hi])

    query += " ORDER BY RANDOM() LIMIT 50"
    c.execute(query, params)
    pool = [
        {
            "player_id": r[0],
            "name": r[1],
            "country": r[2],
            "position": r[3],
            "image_url": r[4],
        }
        for r in c.fetchall()
    ]

    # Daha az filtreli fallback
    if len(pool) < n:
        c.execute(
            """
            SELECT DISTINCT p.player_id, p.name, p.country_of_citizenship, p.position, p.image_url
            FROM players p
            JOIN player_clubs pc ON pc.player_id = p.player_id
            WHERE pc.club_id IN (?, ?)
              AND p.player_id != ?
              AND p.player_id NOT IN (
                  SELECT pc1.player_id
                  FROM player_clubs pc1
                  JOIN player_clubs pc2 ON pc1.player_id = pc2.player_id
                  WHERE pc1.club_id = ? AND pc2.club_id = ?
              )
            ORDER BY RANDOM()
            LIMIT 50
            """,
            (club_a, club_b, correct["player_id"], club_a, club_b),
        )
        seen = {d["player_id"] for d in pool}
        for r in c.fetchall():
            if r[0] in seen:
                continue
            pool.append({
                "player_id": r[0], "name": r[1], "country": r[2],
                "position": r[3], "image_url": r[4],
            })

    random.shuffle(pool)
    return pool[:n]


def build_question(
    conn: sqlite3.Connection,
    club_a: dict[str, Any],
    club_b: dict[str, Any],
    mode: str,
) -> dict[str, Any] | None:
    """İki kulüpten bir tur sorusu üret.

    mode='mc'    -> 4 şıklı (doğru + 3 çeldirici, karıştırılmış)
    mode='free'  -> serbest yazma (şık yok)

    Döner: {correct_player, choices(mc ise)} veya None (ortak oyuncu yoksa).
    """
    commons = _get_common_players(conn, club_a["club_id"], club_b["club_id"])
    if not commons:
        return None

    # Tercihen yüksek değerli/efsane oyuncuyu seç (ama çeşitlilik için zaman zaman diğerleri)
    weighted = sorted(
        commons,
        key=lambda p: (p["is_legend"], p["highest_market_value"]),
        reverse=True,
    )
    # Üst %40 havuzundan rastgele
    top_n = max(1, len(weighted) * 2 // 5)
    correct = random.choice(weighted[:top_n])

    correct_public = {
        "player_id": correct["player_id"],
        "name": correct["name"],
        "country": correct["country"],
        "position": correct["position"],
        "image_url": correct["image_url"],
    }

    result: dict[str, Any] = {"correct_player": correct_public}

    if mode == "mc":
        distractors = _get_distractors(conn, club_a["club_id"], club_b["club_id"], correct, n=3)
        if len(distractors) < 3:
            # 4 şık oluşturamıyorsak bu pair'i atla (caller yeniden dener)
            return None
        choices = [correct_public] + distractors
        random.shuffle(choices)
        result["choices"] = choices

    return result


# ----- Cevap doğrulama (free mode) -----
def verify_free_answer(
    conn: sqlite3.Connection,
    text: str,
    club_a_id: int,
    club_b_id: int,
) -> int | None:
    """Yazılan metin iki kulüpte de oynamış bir oyuncuya eşleşiyorsa player_id döndür.

    normalize(text) ile players.search_name karşılaştırması yapar.
    Tam eşleşme öncelik, yoksa soyisim/tek kelime eşleşmesi.
    """
    if not text or not text.strip():
        return None

    c = conn.cursor()

    # Önce: tam normalize eşleşme
    c.execute(
        """
        SELECT p.player_id FROM players p
        WHERE p.search_name = normalize(?)
          AND EXISTS (SELECT 1 FROM player_clubs pc1 WHERE pc1.player_id = p.player_id AND pc1.club_id = ?)
          AND EXISTS (SELECT 1 FROM player_clubs pc2 WHERE pc2.player_id = p.player_id AND pc2.club_id = ?)
        LIMIT 1
        """,
        (text, club_a_id, club_b_id),
    )
    row = c.fetchone()
    if row:
        return row[0]

    # Sonra: her kelime search_name'de geçiyorsa
    norm = text.strip().lower()
    # normalize fonksiyonunu SQL tarafında zaten var; Python tarafında basit kelime listesi için aynı sonuç yeterli
    c.execute("SELECT normalize(?)", (text,))
    norm_result = c.fetchone()
    norm = norm_result[0] if norm_result else norm
    words = norm.split()
    if not words:
        return None

    where = " AND ".join(["p.search_name LIKE ?"] * len(words))
    params = [f"%{w}%" for w in words]
    c.execute(
        f"""
        SELECT p.player_id, p.search_name
        FROM players p
        WHERE {where}
          AND EXISTS (SELECT 1 FROM player_clubs pc1 WHERE pc1.player_id = p.player_id AND pc1.club_id = ?)
          AND EXISTS (SELECT 1 FROM player_clubs pc2 WHERE pc2.player_id = p.player_id AND pc2.club_id = ?)
        ORDER BY CASE WHEN p.search_name LIKE ? THEN 0 ELSE 1 END,
                 LENGTH(p.name)
        LIMIT 1
        """,
        params + [club_a_id, club_b_id, f"%{words[-1]}%"],
    )
    row = c.fetchone()
    return row[0] if row else None
