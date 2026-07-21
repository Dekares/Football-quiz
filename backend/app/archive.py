"""Server-rendered archive for completed Daily Player challenges."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class ArchiveEntry:
    challenge_date: str
    day_number: int
    player_id: int
    name: str
    country: str
    position: str


@dataclass(frozen=True)
class CareerPeriod:
    club_name: str
    date_from: str | None
    date_to: str | None


def list_entries(conn: sqlite3.Connection, before_date: str) -> list[ArchiveEntry]:
    rows = conn.execute(
        """
        SELECT dc.challenge_date, dc.day_number, p.player_id, p.name,
               COALESCE(p.country_of_citizenship, '') AS country,
               COALESCE(p.position, '') AS position
        FROM daily_challenges dc
        JOIN players p ON p.player_id = dc.player_id
        WHERE dc.challenge_date < ?
        ORDER BY dc.challenge_date DESC
        """,
        (before_date,),
    ).fetchall()
    return [ArchiveEntry(*row) for row in rows]


def get_entry(
    conn: sqlite3.Connection,
    challenge_date: str,
    before_date: str,
) -> tuple[ArchiveEntry, list[CareerPeriod]] | None:
    row = conn.execute(
        """
        SELECT dc.challenge_date, dc.day_number, p.player_id, p.name,
               COALESCE(p.country_of_citizenship, '') AS country,
               COALESCE(p.position, '') AS position
        FROM daily_challenges dc
        JOIN players p ON p.player_id = dc.player_id
        WHERE dc.challenge_date = ? AND dc.challenge_date < ?
        """,
        (challenge_date, before_date),
    ).fetchone()
    if not row:
        return None
    entry = ArchiveEntry(*row)
    periods = [
        CareerPeriod(*period)
        for period in conn.execute(
            """
            SELECT c.name, pc.date_from, pc.date_to
            FROM player_clubs pc
            JOIN clubs c ON c.club_id = pc.club_id
            WHERE pc.player_id = ?
            ORDER BY COALESCE(pc.date_from, ''), pc.id
            """,
            (entry.player_id,),
        ).fetchall()
    ]
    return entry, periods


def _position(value: str, lang: str) -> str:
    if lang == "en":
        return {
            "Goalkeeper": "goalkeeper",
            "Defender": "defender",
            "Midfield": "midfielder",
            "Attack": "forward",
        }.get(value, "footballer")
    return {
        "Goalkeeper": "kaleci",
        "Defender": "savunma oyuncusu",
        "Midfield": "orta saha oyuncusu",
        "Attack": "hücum oyuncusu",
    }.get(value, "futbolcu")


def _period_label(period: CareerPeriod) -> str:
    start = period.date_from[:4] if period.date_from else "?"
    end = period.date_to[:4] if period.date_to else "?"
    return f"{escape(start)}–{escape(end)}"


def render_archive_cards(entries: list[ArchiveEntry], lang: str) -> str:
    if not entries:
        message = (
            "Henüz tamamlanmış günlük bulmaca yok."
            if lang == "tr"
            else "No completed daily puzzles yet."
        )
        return f'<p class="archive-empty">{message}</p>'
    cards = []
    for entry in entries:
        label = "Günün Futbolcusu" if lang == "tr" else "Daily Player"
        cards.append(
            '<article class="archive-card">'
            f'<p class="archive-date">{escape(entry.challenge_date)} · #{entry.day_number}</p>'
            f'<h2><a href="/archive/{escape(entry.challenge_date)}">{escape(entry.name)}</a></h2>'
            f'<p>{escape(entry.country or "—")} · {escape(_position(entry.position, lang))}</p>'
            f'<a class="archive-link" href="/archive/{escape(entry.challenge_date)}">{label} →</a>'
            '</article>'
        )
    return "".join(cards)


def render_archive_detail(entry: ArchiveEntry, periods: list[CareerPeriod], lang: str) -> str:
    unique_clubs = len({period.club_name for period in periods})
    if lang == "tr":
        intro = (
            f"{escape(entry.name)}, {escape(entry.country or 'bilinmeyen ülke')} futbolunun "
            f"{escape(_position(entry.position, lang))} olarak kaydedilmiş oyuncularından biridir. "
            f"{escape(entry.challenge_date)} tarihli Careerdle Günün Futbolcusu bulmacasının "
            f"cevabıydı. Bu arşiv kaydı, oyuncunun {unique_clubs} farklı kulübe yayılan doğrulanmış "
            "kariyer sırasını bulmaca tamamlandıktan sonra incelemek için saklar."
        )
        heading = "Kariyer zaman çizelgesi"
        note = (
            "Tarihler kaynak kayıtlardaki doğrulanabilen dönemleri gösterir; kiralık "
            "dönüşler ve aynı kulübe ikinci geçişler ayrı satır kalabilir. Bitiş yılı "
            "doğrulanamayan dönemler soru işaretiyle gösterilir."
        )
        back = "Tüm geçmiş bulmacalar"
        club_count = f"{unique_clubs} kulüp"
    else:
        intro = (
            f"{escape(entry.name)} is a {escape(_position(entry.position, lang))} associated with "
            f"{escape(entry.country or 'an unspecified country')}. This player was the Careerdle "
            f"Daily Player for {escape(entry.challenge_date)}. The completed-puzzle record preserves "
            f"a verified career sequence spanning {unique_clubs} clubs for review after the challenge."
        )
        heading = "Career timeline"
        note = (
            "Dates reflect periods that can be verified from the source records. Loan "
            "returns and later moves back to the same club can remain separate entries. "
            "A question mark denotes an unverified end year."
        )
        back = "All completed puzzles"
        club_count = f"{unique_clubs} clubs"

    timeline = "".join(
        '<li class="archive-period">'
        f'<span class="archive-period-years">{_period_label(period)}</span>'
        f'<strong>{escape(period.club_name)}</strong>'
        '</li>'
        for period in periods
    ) or '<li class="archive-period"><strong>—</strong></li>'
    return (
        f'<p class="doc-lead archive-intro">{intro}</p>'
        f'<div class="archive-facts"><span>#{entry.day_number}</span>'
        f'<span>{escape(entry.country or "—")}</span>'
        f'<span>{escape(_position(entry.position, lang))}</span><span>{club_count}</span></div>'
        f'<section class="archive-timeline"><h2>{heading}</h2><ol>{timeline}</ol><p>{note}</p></section>'
        f'<p><a class="doc-button" href="/archive">← {back}</a></p>'
    )
