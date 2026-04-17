"""Zorluğa göre kulüp çifti seçimi.

Pre-compute edilmiş `club_pair_stats` tablosundan rastgele pair çeker.
Son 10 turun pair'leri cache'te tutulur ve filtrelenir.
"""
from __future__ import annotations

import sqlite3
from typing import Any

DIFFICULTY_FILTERS = {
    "easy":   "min_prestige >= 20 AND common_count >= 5",
    "medium": "min_prestige BETWEEN 8 AND 25 AND common_count BETWEEN 3 AND 8",
    "hard":   "min_prestige BETWEEN 3 AND 10 AND common_count BETWEEN 2 AND 4",
}

# Zorluk bucket'ı küçükse (ör: Easy=89) aynı pair'lerin tekrar gelmemesi için
# son N tur cache tutuyoruz.
RECENT_PAIRS_WINDOW = 10


def pick_club_pair(
    conn: sqlite3.Connection,
    difficulty: str,
    recent_pairs: list[tuple[int, int]],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Zorluğa göre bir kulüp çifti seç.

    `recent_pairs`: [(club_a_id, club_b_id), ...] son 10 turdan, yeni pair listeye eklenir.
    Döner: ({club_id,name,logo_url}, {club_id,name,logo_url}) veya None (bulunamazsa).
    """
    filt = DIFFICULTY_FILTERS.get(difficulty, DIFFICULTY_FILTERS["medium"])
    c = conn.cursor()

    # Aday havuzu: zorluk kriterini karşılayan tüm pair'ler, son N'i hariç
    exclusion_clause = ""
    params: list[Any] = []
    if recent_pairs:
        placeholders = ",".join(["(?,?)"] * len(recent_pairs))
        exclusion_clause = f" AND (club_a_id, club_b_id) NOT IN ({placeholders})"
        for a, b in recent_pairs:
            params.extend([a, b])

    query = f"""
        SELECT club_a_id, club_b_id
        FROM club_pair_stats
        WHERE {filt}{exclusion_clause}
        ORDER BY RANDOM()
        LIMIT 1
    """
    c.execute(query, params)
    row = c.fetchone()

    # Cache yüzünden boş kalırsa, exclusion'ı kaldır
    if not row and recent_pairs:
        c.execute(f"SELECT club_a_id, club_b_id FROM club_pair_stats WHERE {filt} ORDER BY RANDOM() LIMIT 1")
        row = c.fetchone()

    # Zorluk filtresi hiç eşleşmezse None
    if not row:
        return None

    a, b = row
    c.execute("SELECT club_id, name, logo_url FROM clubs WHERE club_id IN (?, ?)", (a, b))
    clubs = {r[0]: {"club_id": r[0], "name": r[1], "logo_url": r[2]} for r in c.fetchall()}
    if a not in clubs or b not in clubs:
        return None

    recent_pairs.append((a, b))
    if len(recent_pairs) > RECENT_PAIRS_WINDOW:
        recent_pairs.pop(0)

    return clubs[a], clubs[b]
