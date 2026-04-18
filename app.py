from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO
import sqlite3
import os
import random
import re
import unicodedata

from game.sockets import register_socket_handlers

app = Flask(__name__, static_folder="static")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
DB_PATH = os.path.join(os.path.dirname(__file__), "football_quiz.db")


def normalize_text(s):
    """İsimleri aksansız, küçük harfli, alfanümerik + boşluk forma çevirir.

    Örn: 'Özil' -> 'ozil', "N'Golo Kanté" -> 'ngolo kante',
         'Fenerbahçe' -> 'fenerbahce', 'Müller' -> 'muller'.
    """
    if not s:
        return ""
    s = s.replace('ı', 'i').replace('İ', 'i')
    s = s.replace('ø', 'o').replace('Ø', 'o')
    s = s.replace('ł', 'l').replace('Ł', 'l')
    s = s.replace('đ', 'd').replace('Đ', 'd')
    s = s.replace('ß', 'ss')
    s = s.replace('æ', 'ae').replace('Æ', 'ae')
    s = s.replace('œ', 'oe').replace('Œ', 'oe')
    s = s.replace('þ', 'th').replace('Þ', 'th')
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return ' '.join(s.split())


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.create_function("normalize", 1, normalize_text)
    return conn


def ensure_search_columns():
    """Eski veritabanına normalize edilmiş arama sütunları ekle (idempotent)."""
    conn = get_db()
    c = conn.cursor()

    player_cols = {r[1] for r in c.execute("PRAGMA table_info(players)")}
    if "search_name" not in player_cols:
        print("Migrating: players.search_name ekleniyor...")
        c.execute("ALTER TABLE players ADD COLUMN search_name TEXT")
        c.execute("UPDATE players SET search_name = normalize(name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_players_search ON players(search_name)")

    alias_cols = {r[1] for r in c.execute("PRAGMA table_info(club_aliases)")}
    if "search_alias" not in alias_cols:
        print("Migrating: club_aliases.search_alias ekleniyor...")
        c.execute("ALTER TABLE club_aliases ADD COLUMN search_alias TEXT")
        c.execute("UPDATE club_aliases SET search_alias = normalize(alias)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_alias_search ON club_aliases(search_alias)")

    conn.commit()
    conn.close()


ensure_search_columns()

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")
register_socket_handlers(socketio, get_db)


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/health")
def health():
    # Render cold-start'ı sıcak tutmak için hafif endpoint.
    return jsonify({"ok": True})


@app.route("/api/search-club")
def search_club():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])

    norm_q = normalize_text(q)
    words = norm_q.split()
    if not words:
        return jsonify([])

    conn = get_db()
    c = conn.cursor()

    # %w% sayesinde her kelime alias'ın herhangi bir yerinde geçebilir
    # (isim/soyisim/alias'ın ortasından başlayan aramalar çalışır).
    where = " AND ".join(["ca.search_alias LIKE ?"] * len(words))
    params = [f"%{w}%" for w in words]

    first_word = words[0]
    last_word = words[-1]

    # Sıralama bucket'ları:
    #   0 -> alias tam eşleşme
    #   1 -> ilk VE son sorgu kelimesi, alias'taki bir kelimenin baştan eşleşmesi
    #   2 -> sadece ortadan eşleşme
    # Aynı bucket içinde prestij skoru yüksek kulüpler önce gelir.
    c.execute(f"""
        SELECT ca.club_id, cl.name, cl.logo_url
        FROM club_aliases ca
        JOIN clubs cl ON cl.club_id = ca.club_id
        WHERE {where}
        ORDER BY
            CASE
                WHEN ca.search_alias = ? THEN 0
                WHEN (ca.search_alias LIKE ? OR ca.search_alias LIKE ?)
                 AND (ca.search_alias LIKE ? OR ca.search_alias LIKE ?) THEN 1
                ELSE 2
            END,
            cl.prestige_score DESC,
            LENGTH(cl.name)
        LIMIT 60
    """, params + [
        norm_q,
        f"{first_word}%", f"% {first_word}%",
        f"{last_word}%",  f"% {last_word}%",
    ])

    results = [{"club_id": r[0], "name": r[1], "logo_url": r[2]} for r in c.fetchall()]

    # Deduplicate by club_id (keep first/best match)
    seen = set()
    unique = []
    for r in results:
        if r["club_id"] not in seen:
            seen.add(r["club_id"])
            unique.append(r)
        if len(unique) >= 20:
            break

    conn.close()
    return jsonify(unique)


@app.route("/api/common-players")
def common_players():
    club1 = request.args.get("club1", type=int)
    club2 = request.args.get("club2", type=int)
    if not club1 or not club2:
        return jsonify({"error": "İki kulüp ID gerekli"}), 400

    conn = get_db()
    c = conn.cursor()

    # Get club info
    c.execute("SELECT club_id, name, logo_url FROM clubs WHERE club_id IN (?, ?)", (club1, club2))
    clubs = {r[0]: {"name": r[1], "logo_url": r[2]} for r in c.fetchall()}

    # Common players
    c.execute("""
        SELECT DISTINCT p.player_id, p.name, p.country_of_citizenship, p.position, p.image_url
        FROM player_clubs pc1
        JOIN player_clubs pc2 ON pc1.player_id = pc2.player_id
        JOIN players p ON p.player_id = pc1.player_id
        WHERE pc1.club_id = ? AND pc2.club_id = ?
        ORDER BY p.name
    """, (club1, club2))

    players = [{
        "player_id": r[0],
        "name": r[1],
        "country": r[2],
        "position": r[3],
        "image_url": r[4],
    } for r in c.fetchall()]

    conn.close()
    return jsonify({"clubs": clubs, "players": players, "count": len(players)})


@app.route("/api/quiz")
def quiz():
    difficulty = request.args.get("difficulty", "easy")
    conn = get_db()
    c = conn.cursor()

    # Zorluk seviyesine göre piyasa değeri filtresi
    if difficulty == "easy":
        # Efsaneler kolay modda her zaman seçilebilir
        value_filter = "AND (p.highest_market_value >= 60000000 OR p.is_legend = 1)"
    elif difficulty == "medium":
        value_filter = "AND p.highest_market_value >= 20000000"
    else:
        value_filter = "AND (p.highest_market_value < 20000000 AND p.highest_market_value > 5000000) AND p.is_legend = 0"

    c.execute(f"""
        SELECT p.player_id, p.name, p.country_of_citizenship, p.position, p.image_url
        FROM players p
        WHERE (
            SELECT COUNT(DISTINCT pc.club_id)
            FROM player_clubs pc
            WHERE pc.player_id = p.player_id
        ) >= 2
        {value_filter}
    """)

    candidates = c.fetchall()
    if not candidates:
        conn.close()
        return jsonify({"error": "Oyuncu bulunamadı"}), 404

    player = random.choice(candidates)

    # Get club history with dates, chronological order
    # "Without Club" ve "Retired" gibi kayıtları hariç tut
    c.execute("""
        SELECT COALESCE(cl.name, ca_sub.alias, CAST(pc.club_id AS TEXT)),
               cl.logo_url,
               pc.date_from,
               pc.date_to
        FROM player_clubs pc
        LEFT JOIN clubs cl ON cl.club_id = pc.club_id
        LEFT JOIN (
            SELECT club_id, MIN(alias) as alias FROM club_aliases GROUP BY club_id
        ) ca_sub ON ca_sub.club_id = pc.club_id
        WHERE pc.player_id = ?
          AND COALESCE(cl.name, '') NOT LIKE '%Without Club%'
          AND COALESCE(cl.name, '') NOT LIKE '%Retired%'
          AND COALESCE(cl.name, '') NOT LIKE '%Unknown%'
          AND cl.name IS NOT NULL
          AND cl.name != ''
        ORDER BY
            COALESCE(pc.date_from, pc.date_to, '9999'),
            pc.date_from NULLS FIRST,
            COALESCE(pc.date_to, '9999')
    """, (player[0],))

    clubs = [{
        "name": r[0],
        "logo_url": r[1],
        "date_from": r[2],
        "date_to": r[3],
    } for r in c.fetchall()]

    conn.close()
    return jsonify({
        "player_id": player[0],
        "name": player[1],
        "country": player[2],
        "position": player[3],
        "image_url": player[4],
        "clubs": clubs,
    })


@app.route("/api/search-player")
def search_player():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])

    norm_q = normalize_text(q)
    words = norm_q.split()
    if not words:
        return jsonify([])

    conn = get_db()
    c = conn.cursor()

    # Her kelime normalize edilmiş isimde geçmeli (ad/soyad/parça eşleşmesi).
    # %w% sayesinde ismin veya soyismin ortasından başlayan aramalar da çalışır.
    where = " AND ".join(["search_name LIKE ?"] * len(words))
    params = [f"%{w}%" for w in words]

    first_word = words[0]
    last_word = words[-1]

    # Sıralama bucket'ları:
    #   0 -> tam isim eşleşmesi
    #   1 -> ilk VE son sorgu kelimesi, isimdeki bir kelimenin başından eşleşiyor
    #        (ad ya da soyad prefix'i — tek kelime sorguda: herhangi bir kelime baştan)
    #   2 -> sadece ortadan eşleşme (kelimenin içinde geçiyor)
    # Aynı bucket içinde piyasa değeri yüksek oyuncular önce gelir.
    c.execute(f"""
        SELECT player_id, name, country_of_citizenship, position, image_url
        FROM players
        WHERE {where}
        ORDER BY
            CASE
                WHEN search_name = ? THEN 0
                WHEN (search_name LIKE ? OR search_name LIKE ?)
                 AND (search_name LIKE ? OR search_name LIKE ?) THEN 1
                ELSE 2
            END,
            COALESCE(highest_market_value, market_value, 0) DESC,
            LENGTH(name)
        LIMIT 15
    """, params + [
        norm_q,
        f"{first_word}%", f"% {first_word}%",
        f"{last_word}%",  f"% {last_word}%",
    ])

    results = [{
        "player_id": r[0],
        "name": r[1],
        "country": r[2],
        "position": r[3],
        "image_url": r[4],
    } for r in c.fetchall()]

    conn.close()
    return jsonify(results)


if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000)
