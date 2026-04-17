import csv
import json
import sqlite3
import os
import re
import unicodedata
from collections import defaultdict
from itertools import combinations

DB_PATH = os.path.join(os.path.dirname(__file__), "football_quiz.db")
DATA_DIR = os.path.dirname(__file__)
LEGEND_ID_START = 9_000_001


def normalize_text(s):
    """İsimleri aksansız, küçük harfli, alfanümerik + boşluk forma çevirir."""
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

# Genç/yedek takım pattern'leri
YOUTH_PATTERNS = re.compile(
    r'\bU[_-]?\d{2}\b|'
    r'\bYouth\b|\bYth\.?\b|\bJunior[s]?\b|\bReserve[s]?\b|'
    r'\bJV$|\bAmateur[es]*\b|\bJuvenil\b|'
    r'\bRes\.$',
    re.IGNORECASE,
)

RESERVE_SUFFIX = re.compile(r'\s[BC]$|\s(?:II|III)$')


def is_youth_team(name: str) -> bool:
    if YOUTH_PATTERNS.search(name):
        return True
    if RESERVE_SUFFIX.search(name):
        return True
    return False


def pick_best_name(names: set[str]) -> str:
    if not names:
        return ""
    clean = [n for n in names if not is_youth_team(n)]
    if not clean:
        clean = list(names)
    return max(clean, key=len)


def to_int(val):
    if val and val.strip():
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None
    return None


def build_stints(transfers_for_player, youth_club_ids):
    """Bir oyuncunun transfer listesinden stint'ler oluştur.

    Her transfer: oyuncu from_club'dan ayrılıp to_club'a katılıyor.
    Aynı kulübe birden fazla dönüş olabilir → ayrı stint'ler.
    """
    # Transferleri tarihe göre sırala
    sorted_transfers = sorted(transfers_for_player, key=lambda t: t["date"] or "")

    # Her stint: {club_id, date_from, date_to}
    # Açık stint'leri takip et: club_id -> list of open stint indices
    stints = []
    open_stints = defaultdict(list)  # club_id -> [stint_index, ...]

    for t in sorted_transfers:
        date = t["date"]
        from_cid = t["from_club_id"]
        to_cid = t["to_club_id"]

        # from_club stint'ini kapat
        if from_cid and from_cid not in youth_club_ids:
            if open_stints[from_cid]:
                idx = open_stints[from_cid].pop()
                stints[idx]["date_to"] = date
            else:
                # Önceden açık stint yoksa, sadece bitiş tarihi olan bir stint oluştur
                stints.append({"club_id": from_cid, "date_from": None, "date_to": date})

        # to_club'da yeni stint aç
        if to_cid and to_cid not in youth_club_ids:
            idx = len(stints)
            stints.append({"club_id": to_cid, "date_from": date, "date_to": None})
            open_stints[to_cid].append(idx)

    return stints


def create_db():
    conn = sqlite3.connect(DB_PATH)
    conn.create_function("normalize", 1, normalize_text)
    c = conn.cursor()

    c.executescript("""
        DROP TABLE IF EXISTS players;
        DROP TABLE IF EXISTS clubs;
        DROP TABLE IF EXISTS player_clubs;
        DROP TABLE IF EXISTS club_aliases;
        DROP TABLE IF EXISTS club_pair_stats;

        CREATE TABLE players (
            player_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            country_of_citizenship TEXT,
            date_of_birth TEXT,
            position TEXT,
            image_url TEXT,
            market_value INTEGER,
            highest_market_value INTEGER,
            international_caps INTEGER,
            is_legend INTEGER NOT NULL DEFAULT 0,
            search_name TEXT
        );

        CREATE TABLE clubs (
            club_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            domestic_competition_id TEXT,
            logo_url TEXT,
            prestige_score INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE club_pair_stats (
            club_a_id INTEGER NOT NULL,
            club_b_id INTEGER NOT NULL,
            common_count INTEGER NOT NULL,
            min_prestige INTEGER NOT NULL,
            PRIMARY KEY (club_a_id, club_b_id)
        );

        -- Her stint ayrı satır (aynı kulübe dönüşler ayrı kayıt)
        CREATE TABLE player_clubs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            club_id INTEGER NOT NULL,
            date_from TEXT,
            date_to TEXT,
            FOREIGN KEY (player_id) REFERENCES players(player_id),
            FOREIGN KEY (club_id) REFERENCES clubs(club_id)
        );

        CREATE TABLE club_aliases (
            alias TEXT NOT NULL,
            club_id INTEGER NOT NULL,
            search_alias TEXT,
            FOREIGN KEY (club_id) REFERENCES clubs(club_id)
        );

        CREATE INDEX idx_pc_club ON player_clubs(club_id);
        CREATE INDEX idx_pc_player ON player_clubs(player_id);
        CREATE INDEX idx_pc_unique ON player_clubs(player_id, club_id, date_from);
        CREATE INDEX idx_clubs_name ON clubs(name COLLATE NOCASE);
        CREATE INDEX idx_alias ON club_aliases(alias COLLATE NOCASE);
        CREATE INDEX idx_alias_search ON club_aliases(search_alias);
        CREATE INDEX idx_players_search ON players(search_name);
        CREATE INDEX idx_pair_difficulty ON club_pair_stats(min_prestige, common_count);
    """)

    # 1) Players
    print("Loading players...")
    with open(os.path.join(DATA_DIR, "players.csv"), encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            rows.append((
                int(r["player_id"]),
                r["name"],
                r["first_name"],
                r["last_name"],
                r["country_of_citizenship"],
                r["date_of_birth"],
                r["position"],
                r["image_url"],
                to_int(r.get("market_value_in_eur")),
                to_int(r.get("highest_market_value_in_eur")),
                to_int(r.get("international_caps")),
                0,
                normalize_text(r["name"]),
            ))
        c.executemany("INSERT OR IGNORE INTO players VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    print(f"  {len(rows)} players loaded.")

    # 2) Clubs (genç takımları atla)
    print("Loading clubs...")
    with open(os.path.join(DATA_DIR, "clubs.csv"), encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        skipped_youth = 0
        for r in reader:
            if is_youth_team(r["name"]):
                skipped_youth += 1
                continue
            cid = int(r["club_id"])
            logo_url = f"https://tmssl.akamaized.net/images/wappen/head/{cid}.png"
            rows.append((cid, r["name"], r["domestic_competition_id"], logo_url))
        c.executemany("INSERT OR IGNORE INTO clubs (club_id, name, domestic_competition_id, logo_url) VALUES (?,?,?,?)", rows)
    print(f"  {len(rows)} clubs loaded, {skipped_youth} youth teams skipped.")

    # 3) Transferleri oyuncu bazında topla
    print("Collecting transfers per player...")
    alias_map = {}
    youth_club_ids = set()
    player_transfers = defaultdict(list)

    with open(os.path.join(DATA_DIR, "transfers.csv"), encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            pid = int(r["player_id"])
            tdate = r["transfer_date"] or ""

            from_cid = None
            to_cid = None

            for side in ("from", "to"):
                cid_str = r[f"{side}_club_id"]
                cname = r[f"{side}_club_name"]
                if not cid_str:
                    continue
                try:
                    cid = int(cid_str)
                except ValueError:
                    continue

                if cname and is_youth_team(cname):
                    youth_club_ids.add(cid)
                    continue

                if cname:
                    alias_map.setdefault(cid, set()).add(cname)

                if side == "from":
                    from_cid = cid
                else:
                    to_cid = cid

            player_transfers[pid].append({
                "date": tdate,
                "from_club_id": from_cid,
                "to_club_id": to_cid,
            })

    print(f"  {sum(len(v) for v in player_transfers.values())} transfers for {len(player_transfers)} players.")
    print(f"  {len(youth_club_ids)} youth club IDs excluded.")

    # 4) Stint'leri oluştur
    print("Building player stints from transfers...")
    all_stints = []
    for pid, transfers in player_transfers.items():
        stints = build_stints(transfers, youth_club_ids)
        for s in stints:
            all_stints.append((pid, s["club_id"], s["date_from"], s["date_to"]))

    print(f"  {len(all_stints)} stints from transfers.")

    # 5) Appearances'dan eksik stint'leri ekle
    print("Adding stints from appearances...")
    # Hangi (pid, cid) çiftleri zaten var?
    existing_pairs = set()
    for pid, cid, _, _ in all_stints:
        existing_pairs.add((pid, cid))

    appearance_stints = defaultdict(lambda: {"from": None, "to": None})
    with open(os.path.join(DATA_DIR, "appearances.csv"), encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            pid = int(r["player_id"])
            cid_str = r["player_club_id"]
            if not cid_str:
                continue
            try:
                cid = int(cid_str)
            except ValueError:
                continue

            if cid in youth_club_ids:
                continue
            if (pid, cid) in existing_pairs:
                continue

            key = (pid, cid)
            match_date = r.get("date", "")
            if match_date:
                cur = appearance_stints[key]
                if cur["from"] is None or match_date < cur["from"]:
                    cur["from"] = match_date
                if cur["to"] is None or match_date > cur["to"]:
                    cur["to"] = match_date

    added = 0
    for (pid, cid), dates in appearance_stints.items():
        all_stints.append((pid, cid, dates["from"], dates["to"]))
        added += 1
    print(f"  {added} additional stints from appearances.")

    c.executemany(
        "INSERT INTO player_clubs (player_id, club_id, date_from, date_to) VALUES (?,?,?,?)",
        all_stints,
    )

    # 6) Eksik kulüpleri ekle + isim normalizasyonu
    print("Adding missing clubs & normalizing names...")
    existing_club_ids = {row[0] for row in c.execute("SELECT club_id FROM clubs").fetchall()}
    missing_clubs = []
    for cid, names in alias_map.items():
        if cid in youth_club_ids:
            continue
        best_name = pick_best_name(names)
        if cid not in existing_club_ids:
            logo_url = f"https://tmssl.akamaized.net/images/wappen/head/{cid}.png"
            missing_clubs.append((cid, best_name, None, logo_url))
        else:
            c.execute("SELECT name FROM clubs WHERE club_id = ?", (cid,))
            current_name = c.fetchone()[0]
            names.add(current_name)
            best_name = pick_best_name(names)
            if best_name != current_name:
                c.execute("UPDATE clubs SET name = ? WHERE club_id = ?", (best_name, cid))

    c.executemany("INSERT OR IGNORE INTO clubs (club_id, name, domestic_competition_id, logo_url) VALUES (?,?,?,?)", missing_clubs)
    print(f"  {len(missing_clubs)} missing clubs added.")

    # 6.5) Legends (efsane futbolcular) — legends.json'dan
    legends_path = os.path.join(DATA_DIR, "legends.json")
    if os.path.exists(legends_path):
        print("Loading legends...")
        with open(legends_path, encoding="utf-8") as f:
            legends = json.load(f)

        existing_club_ids = {row[0] for row in c.execute("SELECT club_id FROM clubs").fetchall()}
        existing_player_ids = {row[0] for row in c.execute("SELECT player_id FROM players").fetchall()}

        legend_new_player_rows = []
        legend_stint_rows = []
        legend_new_clubs = []
        merged_count = 0
        new_legend_count = 0

        for idx, legend in enumerate(legends):
            # Mevcut DB'de aynı isimli oyuncu var mı?
            c.execute(
                "SELECT player_id FROM players WHERE name = ? COLLATE NOCASE LIMIT 1",
                (legend["name"],),
            )
            match = c.fetchone()

            if match:
                pid = match[0]
                # Mevcut satırı legend bilgileriyle güncelle
                c.execute(
                    """
                    UPDATE players SET
                        name = ?,
                        first_name = ?,
                        last_name = ?,
                        country_of_citizenship = ?,
                        date_of_birth = ?,
                        position = ?,
                        image_url = ?,
                        highest_market_value = COALESCE(?, highest_market_value),
                        is_legend = 1,
                        search_name = ?
                    WHERE player_id = ?
                    """,
                    (
                        legend["name"],
                        legend.get("first_name"),
                        legend.get("last_name"),
                        legend.get("country"),
                        legend.get("date_of_birth"),
                        legend.get("position"),
                        legend.get("image_url") or None,
                        legend.get("highest_market_value"),
                        normalize_text(legend["name"]),
                        pid,
                    ),
                )
                # Eski stint'leri sil, legend'ın kulüpleriyle değiştir
                c.execute("DELETE FROM player_clubs WHERE player_id = ?", (pid,))
                merged_count += 1
            else:
                pid = LEGEND_ID_START + idx
                while pid in existing_player_ids:
                    pid += 1
                existing_player_ids.add(pid)

                legend_new_player_rows.append((
                    pid,
                    legend["name"],
                    legend.get("first_name"),
                    legend.get("last_name"),
                    legend.get("country"),
                    legend.get("date_of_birth"),
                    legend.get("position"),
                    legend.get("image_url") or None,
                    None,
                    legend.get("highest_market_value"),
                    None,
                    1,
                    normalize_text(legend["name"]),
                ))
                new_legend_count += 1

            for club in legend.get("clubs", []):
                cid = club["club_id"]
                cname = club["name"]
                if cid not in existing_club_ids:
                    logo_url = f"https://tmssl.akamaized.net/images/wappen/head/{cid}.png"
                    legend_new_clubs.append((cid, cname, None, logo_url))
                    existing_club_ids.add(cid)
                alias_map.setdefault(cid, set()).add(cname)
                legend_stint_rows.append((pid, cid, club.get("from"), club.get("to")))

        c.executemany("INSERT OR IGNORE INTO clubs (club_id, name, domestic_competition_id, logo_url) VALUES (?,?,?,?)", legend_new_clubs)
        c.executemany(
            "INSERT OR IGNORE INTO players VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            legend_new_player_rows,
        )
        c.executemany(
            "INSERT INTO player_clubs (player_id, club_id, date_from, date_to) VALUES (?,?,?,?)",
            legend_stint_rows,
        )
        print(
            f"  {new_legend_count} new legends, {merged_count} merged into existing players, "
            f"{len(legend_stint_rows)} stints, {len(legend_new_clubs)} new clubs."
        )

    # Genç takımları temizle
    print("Cleaning youth references...")
    if youth_club_ids:
        placeholders = ",".join(["?"] * len(youth_club_ids))
        c.execute(f"DELETE FROM player_clubs WHERE club_id IN ({placeholders})", list(youth_club_ids))
        print(f"  {c.rowcount} youth player_clubs records removed.")
        c.execute(f"DELETE FROM clubs WHERE club_id IN ({placeholders})", list(youth_club_ids))

    # 7) Club aliases
    print("Building club aliases...")
    c.execute("SELECT club_id, name FROM clubs")
    for cid, name in c.fetchall():
        alias_map.setdefault(cid, set()).add(name)

    alias_rows = []
    for cid, names in alias_map.items():
        if cid in youth_club_ids:
            continue
        for name in names:
            if not is_youth_team(name):
                alias_rows.append((name, cid, normalize_text(name)))
    c.executemany("INSERT INTO club_aliases (alias, club_id, search_alias) VALUES (?,?,?)", alias_rows)
    print(f"  {len(alias_rows)} aliases.")

    # Orphan oyuncuları temizle
    c.execute("""
        DELETE FROM players WHERE player_id NOT IN (
            SELECT DISTINCT player_id FROM player_clubs
        )
    """)
    print(f"  {c.rowcount} orphan players removed.")

    # 8) Prestige score: her kulüpte kaç "50M+ VEYA efsane" oyuncu oynamış
    print("Computing club prestige scores...")
    c.execute("""
        UPDATE clubs SET prestige_score = COALESCE((
            SELECT COUNT(DISTINCT pc.player_id)
            FROM player_clubs pc
            JOIN players p ON p.player_id = pc.player_id
            WHERE pc.club_id = clubs.club_id
              AND (p.highest_market_value >= 50000000 OR p.is_legend = 1)
        ), 0)
    """)
    c.execute("SELECT COUNT(*) FROM clubs WHERE prestige_score >= 3")
    print(f"  {c.fetchone()[0]} clubs with prestige_score >= 3.")

    # 9) Kulüp çifti istatistikleri (matchmaking için)
    print("Building club_pair_stats...")
    prestige_clubs = {r[0] for r in c.execute("SELECT club_id FROM clubs WHERE prestige_score >= 3")}
    prestige_score_map = {r[0]: r[1] for r in c.execute("SELECT club_id, prestige_score FROM clubs")}

    player_clubs_map = defaultdict(set)
    for pid, cid in c.execute("SELECT player_id, club_id FROM player_clubs"):
        if cid in prestige_clubs:
            player_clubs_map[pid].add(cid)

    pair_common = defaultdict(int)
    for club_set in player_clubs_map.values():
        if len(club_set) < 2:
            continue
        for a, b in combinations(sorted(club_set), 2):
            pair_common[(a, b)] += 1

    pair_rows = []
    for (a, b), cnt in pair_common.items():
        if cnt < 2:
            continue
        min_p = min(prestige_score_map.get(a, 0), prestige_score_map.get(b, 0))
        pair_rows.append((a, b, cnt, min_p))

    c.executemany(
        "INSERT INTO club_pair_stats (club_a_id, club_b_id, common_count, min_prestige) VALUES (?,?,?,?)",
        pair_rows,
    )
    print(f"  {len(pair_rows)} club pairs stored.")

    conn.commit()

    # Stats
    c.execute("SELECT COUNT(*) FROM players")
    p = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM clubs")
    cl = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM player_clubs")
    pc = c.fetchone()[0]
    print(f"\nDatabase ready: {p} players, {cl} clubs, {pc} stints")

    c.execute("""
        SELECT COUNT(*) FROM (
            SELECT player_id FROM player_clubs GROUP BY player_id HAVING COUNT(*) >= 2
        )
    """)
    print(f"2+ stint'li oyuncu: {c.fetchone()[0]}")

    # Pogba testi
    c.execute("""
        SELECT cl.name, pc.date_from, pc.date_to
        FROM player_clubs pc
        LEFT JOIN clubs cl ON cl.club_id = pc.club_id
        WHERE pc.player_id = 122153
        ORDER BY COALESCE(pc.date_from, pc.date_to, '9999')
    """)
    print("\nPogba stint kontrol:")
    for r in c.fetchall():
        print(f"  {r[1] or '?'} - {r[2] or '?'} : {r[0]}")

    conn.close()
    print(f"\nDatabase saved to: {DB_PATH}")


if __name__ == "__main__":
    create_db()
