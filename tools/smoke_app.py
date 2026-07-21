"""Smoke-test a published Careerdle database and an optional running HTTP API."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.app.realtime.matchmaking import pick_club_pair
from backend.app.realtime.questions import build_question
from backend.app.daily import DAILY_START_DATE, daily_number, daily_today
from backend.app.text import normalize_text


def _scalar(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[object, ...] = (),
) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def check_database(path: Path) -> dict[str, object]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.create_function("normalize", 1, normalize_text, deterministic=True)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        counts = {
            "players": _scalar(conn, "SELECT COUNT(*) FROM players"),
            "clubs": _scalar(conn, "SELECT COUNT(*) FROM clubs"),
            "periods": _scalar(conn, "SELECT COUNT(*) FROM player_clubs"),
            "pairs": _scalar(conn, "SELECT COUNT(*) FROM club_pair_stats"),
            "competitions": _scalar(conn, "SELECT COUNT(*) FROM competitions"),
            "daily_challenges": _scalar(conn, "SELECT COUNT(*) FROM daily_challenges"),
        }
        assert all(counts.values())
        quiz_counts: dict[str, int] = {}
        realtime: dict[str, dict[str, object]] = {}
        for difficulty in ("easy", "medium", "hard"):
            quiz_counts[difficulty] = _scalar(
                conn,
                f"SELECT COUNT(*) FROM quiz_pool WHERE difficulty = '{difficulty}'",
            )
            assert quiz_counts[difficulty] > 0
            recent: list[tuple[int, int]] = []
            question = None
            pair = None
            for _ in range(30):
                pair = pick_club_pair(conn, difficulty, recent)
                if pair:
                    question = build_question(conn, pair[0], pair[1], "mc")
                if question:
                    break
            assert pair and question and len(question["choices"]) == 4
            realtime[difficulty] = {
                "clubs": [pair[0]["name"], pair[1]["name"]],
                "answer": question["correct_player"]["name"],
            }
        recognition_counts = {}
        global_recognition_counts = {}
        for recognition in ("known", "less_known", "obscure"):
            recognition_counts[recognition] = _scalar(
                conn,
                "SELECT COUNT(*) FROM quiz_pool WHERE recognition = ?",
                (recognition,),
            )
            assert recognition_counts[recognition] > 0
            global_recognition_counts[recognition] = _scalar(
                conn,
                "SELECT COUNT(*) FROM global_quiz_pool WHERE recognition = ?",
                (recognition,),
            )
            assert global_recognition_counts[recognition] > 0
        overlap = _scalar(
            conn,
            """
            SELECT COUNT(*) FROM (
                SELECT competition_id, player_id FROM quiz_pool
                GROUP BY competition_id, player_id
                HAVING COUNT(DISTINCT recognition) != 1
            )
            """,
        )
        assert overlap == 0
        today = daily_today().isoformat()
        daily = conn.execute(
            """
            SELECT challenge_date,day_number,player_id
            FROM daily_challenges
            WHERE challenge_date=?
            """,
            (today,),
        ).fetchone()
        assert daily is not None
        assert daily["day_number"] == daily_number(date.fromisoformat(today))
        invalid_future_daily = _scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM daily_challenges d
            LEFT JOIN global_quiz_pool g
              ON g.player_id = d.player_id AND g.recognition = 'known'
            WHERE d.challenge_date > ? AND g.player_id IS NULL
            """,
            (today,),
        )
        assert invalid_future_daily == 0
        first_daily = conn.execute(
            """
            SELECT challenge_date,day_number FROM daily_challenges
            ORDER BY challenge_date LIMIT 1
            """
        ).fetchone()
        assert tuple(first_daily) == (DAILY_START_DATE.isoformat(), 1)
        global_overlap = _scalar(
            conn,
            """
            SELECT COUNT(*) FROM (
                SELECT player_id FROM global_quiz_pool
                GROUP BY player_id
                HAVING COUNT(DISTINCT recognition) != 1
            )
            """,
        )
        assert global_overlap == 0
        return {
            "counts": counts,
            "quiz_pool": quiz_counts,
            "recognition_pool": recognition_counts,
            "global_recognition_pool": global_recognition_counts,
            "invalid_future_daily": invalid_future_daily,
            "realtime": realtime,
        }
    finally:
        conn.close()


def _get(base_url: str, path: str, params: dict[str, object] | None = None):
    url = f"{base_url.rstrip('/')}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    with urlopen(url, timeout=10) as response:
        assert response.status == 200
        return json.loads(response.read().decode("utf-8"))


def _get_text(base_url: str, path: str) -> tuple[int, str, str]:
    with urlopen(f"{base_url.rstrip('/')}{path}", timeout=10) as response:
        return (
            response.status,
            response.headers.get("Content-Type", ""),
            response.read().decode("utf-8"),
        )


def check_http(base_url: str) -> dict[str, object]:
    health = _get(base_url, "/api/health")
    assert health.get("ok") is True
    players = _get(base_url, "/api/search-player", {"q": "saka"})
    clubs = _get(base_url, "/api/search-club", {"q": "arsenal"})
    assert players and clubs
    options = _get(base_url, "/api/quiz/options")
    assert len(options.get("leagues") or []) >= 13
    all_leagues = next(item for item in options["leagues"] if item["id"] == "ALL")
    premier = next(item for item in options["leagues"] if item["id"] == "GB1")
    assert all(all_leagues["counts"][key] > 0 for key in ("known", "less_known", "obscure"))
    assert all(premier["counts"][key] > 0 for key in ("known", "less_known", "obscure"))
    quizzes = {}
    global_quizzes = {}
    for recognition in ("known", "less_known", "obscure"):
        global_quiz = _get(
            base_url,
            "/api/quiz",
            {"league": "ALL", "recognition": recognition},
        )
        assert global_quiz.get("player_id") and len(global_quiz.get("clubs") or []) >= 2
        assert global_quiz["league"] == "ALL"
        assert global_quiz["recognition"] == recognition
        global_quizzes[recognition] = global_quiz["name"]
        quiz = _get(
            base_url,
            "/api/quiz",
            {"league": "GB1", "recognition": recognition},
        )
        assert quiz.get("player_id") and len(quiz.get("clubs") or []) >= 2
        assert quiz["league"] == "GB1" and quiz["recognition"] == recognition
        quizzes[recognition] = quiz["name"]
    legacy_quiz = _get(base_url, "/api/quiz", {"difficulty": "easy"})
    assert legacy_quiz["recognition"] == "known"
    classic = _get(base_url, "/api/classic")
    assert classic["day"] == daily_number(date.fromisoformat(classic["date"]))
    reveal = _get(base_url, "/api/classic/reveal")
    assert classic.get("day") is not None and reveal.get("player", {}).get("player_id")
    guess = _get(
        base_url,
        "/api/classic/guess",
        {"player_id": reveal["player"]["player_id"]},
    )
    assert guess.get("correct") is True
    public_pages = ("/", "/about", "/contact", "/privacy", "/methodology", "/terms")
    for page in public_pages:
        status, _, html = _get_text(base_url, page)
        assert status == 200
        assert 'name="google-adsense-account"' in html
        assert 'href="/privacy"' in html
        assert 'href="/terms"' in html
        assert 'href="/methodology"' in html
    ads_status, ads_type, ads_body = _get_text(base_url, "/ads.txt")
    assert ads_status == 200 and ads_type.startswith("text/plain")
    assert ads_body.strip() == "google.com, pub-5823826038472901, DIRECT, f08c47fec0942fa0"
    _, _, robots = _get_text(base_url, "/robots.txt")
    _, _, sitemap = _get_text(base_url, "/sitemap.xml")
    assert "Mediapartners-Google" in robots
    assert all(path in sitemap for path in ("/about", "/methodology", "/privacy", "/terms"))
    return {
        "search_players": len(players),
        "search_clubs": len(clubs),
        "quiz": quizzes,
        "global_quiz": global_quizzes,
        "quiz_leagues": len(options["leagues"]),
        "classic": reveal["player"]["name"],
        "public_pages": len(public_pages),
        "ads_txt": "authorized",
    }


def check_socket(base_url: str) -> dict[str, object]:
    endpoint = f"{base_url.rstrip('/')}/socket.io/?EIO=4&transport=polling"
    with urlopen(endpoint, timeout=10) as response:
        opening = response.read().decode("utf-8")
    assert opening.startswith("0")
    metadata = json.loads(opening[1:])
    sid = metadata["sid"]
    session_url = f"{endpoint}&sid={sid}"
    connect = Request(
        session_url,
        data=b"40",
        headers={"Content-Type": "text/plain;charset=UTF-8"},
        method="POST",
    )
    with urlopen(connect, timeout=10) as response:
        assert response.status == 200
    with urlopen(session_url, timeout=10) as response:
        acknowledgement = response.read().decode("utf-8")
    assert acknowledgement.startswith("40")
    close = Request(
        session_url,
        data=b"1",
        headers={"Content-Type": "text/plain;charset=UTF-8"},
        method="POST",
    )
    with urlopen(close, timeout=10):
        pass
    return {"connected": True, "transport": "polling"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--socket-url")
    args = parser.parse_args()
    result: dict[str, object] = {"database": check_database(args.db)}
    if args.base_url:
        result["http"] = check_http(args.base_url)
    if args.socket_url:
        result["socket"] = check_socket(args.socket_url)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
