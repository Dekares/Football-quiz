import csv
import json
import sqlite3
import os
import re
import unicodedata
from collections import defaultdict
from itertools import combinations

# Yeni yerleşim: bu script data/build/ içinde; ham CSV'ler data/sources/ içinde,
# üretilen DB ise data/ kökünde (her API instance'ı ile paketlenen salt-okunur artifact).
BUILD_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.dirname(BUILD_DIR)              # .../data
DATA_DIR = os.path.join(DATA_ROOT, "sources")       # ham CSV + legends.json
# Çıktı yolu: varsayılan data/ kökü, ama FOOTBALL_QUIZ_DB ile geçici bir hedefe
# yönlendirilebilir (update.py önce temp DB'ye build edip doğrulama sonrası takas eder).
DB_PATH = os.environ.get("FOOTBALL_QUIZ_DB") or os.path.join(DATA_ROOT, "football_quiz.db")
LEGEND_ID_START = 9_000_001

# quiz_pool: zorluk başına uygun oyuncu havuzu (çalışma anı yerine build anında
# hesaplanır → /api/quiz tek satır LIMIT 1 ile çeker, full scan yok).
# Filtreler app.py'deki eski _quiz_impl mantığıyla birebir aynı.
RETIRED_EXISTS = (
    "EXISTS (SELECT 1 FROM player_clubs pcr JOIN clubs cr ON cr.club_id = pcr.club_id "
    "WHERE pcr.player_id = p.player_id AND cr.name LIKE '%Retired%')"
)
MULTI_CLUB = (
    "(SELECT COUNT(DISTINCT pc.club_id) FROM player_clubs pc "
    "WHERE pc.player_id = p.player_id) >= 2"
)
QUIZ_DIFFICULTY_FILTERS = {
    "easy": (
        "p.highest_market_value >= 60000000 OR p.is_legend = 1 "
        f"OR ({RETIRED_EXISTS} AND p.highest_market_value >= 20000000)"
    ),
    "medium": (
        "p.highest_market_value >= 20000000 "
        f"OR ({RETIRED_EXISTS} AND p.highest_market_value >= 10000000)"
    ),
    "hard": (
        "p.highest_market_value < 20000000 AND p.highest_market_value > 5000000 "
        "AND p.is_legend = 0"
    ),
}


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


# --- player_valuations isim çözücüsü için yardımcılar ---
# valuations.current_club_NAME tarihsel-doğru kulübü taşır; current_club_id ise
# bazı oyuncularda donmuş/yanlış. Bu yüzden kulübü İSİMDEN çözeriz: her isim için
# valuations'ın kendi çoğunluk-oyu id'sini al, sonra clubs.csv ismiyle ÇAPRAZ
# DOĞRULA → "Manisaspor→Gençlerbirliği" gibi oy hatalarını ele. (Geçmiş: id'ye
# körü körüne güvenmek gerçek kulüpleri youth sanıp sildirmişti.)
_VAL_YOUTH = re.compile(
    r'\bU[_-]?\d{1,2}\b|Youth|\bYth|Junior|Reserve|Amateur|Juvenil|'
    r'Primavera|Next Gen|\bsub-?\d|\bII$|\bIII$|\b[BC]$',
    re.IGNORECASE,
)
_CLUB_STOP = {
    "fc", "sc", "ac", "as", "cf", "sk", "if", "ss", "us", "afc", "cd", "ca",
    "club", "de", "spor", "kulubu", "football", "futbol", "calcio", "the",
    "sa", "spa", "asd", "jk", "ssc", "losc", "aj", "rc", "sv", "vfl", "vfb", "og",
}


def _val_is_youth(name: str) -> bool:
    return bool(name and _VAL_YOUTH.search(name))


def _club_tokens(s: str) -> set[str]:
    return set(normalize_text(s).split()) - _CLUB_STOP


def _names_similar(a: str, b: str) -> bool:
    """İki kulüp ismi aynı kulübü mü gösteriyor (kısa↔uzun varyant toleranslı)."""
    ta, tb = _club_tokens(a), _club_tokens(b)
    if not ta or not tb:
        return False
    if ta <= tb or tb <= ta:
        return True
    return len(ta & tb) / min(len(ta), len(tb)) >= 0.5


def to_int(val):
    if val and val.strip():
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None
    return None


def clean_image(url):
    """Transfermarkt'ın gri placeholder'ını (default.jpg) NULL'a çevir.

    Böylece frontend'in kendi onerror fallback'i devreye girer; çirkin silüet
    URL'i saklanmaz. Gerçek portre URL'leri olduğu gibi döner.
    """
    if not url or not url.strip() or "default" in url:
        return None
    return url


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
            search_name TEXT,
            -- Additive (backend okumaz; tools/inspect_player.py SELECT * ile gösterir)
            sub_position TEXT,
            foot TEXT,
            height_in_cm INTEGER,
            country_of_birth TEXT,
            city_of_birth TEXT,
            international_goals INTEGER
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

        -- Zorluk başına quiz aday havuzu (build anında hesaplanır)
        CREATE TABLE quiz_pool (
            difficulty TEXT NOT NULL,
            player_id INTEGER NOT NULL,
            PRIMARY KEY (difficulty, player_id)
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

    # 1) Players (current_club da topla → transfer/maç kaydı olmayan oyuncuların
    #    güncel kulübünü stint olarak ekleyebilmek için, bkz. adım 5.5)
    print("Loading players...")
    player_current_club = {}   # pid -> (club_id, club_name)
    with open(os.path.join(DATA_DIR, "players.csv"), encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            pid = int(r["player_id"])
            cc_id = to_int(r.get("current_club_id"))
            if cc_id:
                player_current_club[pid] = (cc_id, (r.get("current_club_name") or "").strip())
            rows.append((
                pid,
                r["name"],
                r["first_name"],
                r["last_name"],
                r["country_of_citizenship"],
                r["date_of_birth"],
                r["position"],
                clean_image(r["image_url"]),
                to_int(r.get("market_value_in_eur")),
                to_int(r.get("highest_market_value_in_eur")),
                to_int(r.get("international_caps")),
                0,
                normalize_text(r["name"]),
                (r.get("sub_position") or "").strip() or None,
                (r.get("foot") or "").strip() or None,
                to_int(r.get("height_in_cm")),
                (r.get("country_of_birth") or "").strip() or None,
                (r.get("city_of_birth") or "").strip() or None,
                to_int(r.get("international_goals")),
            ))
        c.executemany(
            "INSERT OR IGNORE INTO players VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )
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

    # 4) Stint kaynak zinciri: transfers → player_valuations → appearances →
    # game_lineups → current_club. Her kaynak, daha önce görülmemiş (pid,cid)
    # çiftini kendi tarihiyle ekler (existing_pairs dedup).
    print("Building player stints from transfers...")
    all_stints = []
    for pid, transfers in player_transfers.items():
        stints = build_stints(transfers, youth_club_ids)
        for s in stints:
            all_stints.append((pid, s["club_id"], s["date_from"], s["date_to"]))
    print(f"  {len(all_stints)} stints from transfers.")

    existing_pairs = set()
    for pid, cid, _, _ in all_stints:
        existing_pairs.add((pid, cid))

    # 4.5) player_valuations → İSİMDEN çözülen kariyer (transfers'ın kaçırdığı
    # kulüpler; özellikle eski/alt-lig dönemleri). current_club_name tarihsel-doğru;
    # kulübü isimden çoğunluk-oyu + clubs.csv çapraz doğrulamasıyla çözeriz.
    print("Adding stints from player_valuations (name-resolved)...")
    # kulüp id -> en iyi isim (clubs tablosu + transfers alias'ları)
    cname = {cid: nm for cid, nm in c.execute("SELECT club_id, name FROM clubs")}
    for cid, names in alias_map.items():
        best = pick_best_name(names)
        if best and (cid not in cname or len(best) > len(cname[cid])):
            cname[cid] = best
    # isim -> id oyları
    name_votes = defaultdict(lambda: defaultdict(int))   # name -> {cid: n}
    val_player_rows = defaultdict(list)                   # pid -> [(date, name)]
    with open(os.path.join(DATA_DIR, "player_valuations.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            nm = (r.get("current_club_name") or "").strip()
            cid_str = r.get("current_club_id")
            if not nm:
                continue
            if cid_str:
                try:
                    name_votes[nm][int(cid_str)] += 1
                except ValueError:
                    pass
            val_player_rows[int(r["player_id"])].append((r.get("date", ""), nm))
    # isim -> çözülmüş id (çoğunluk-oyu + çapraz doğrulama; youth isimleri elenir)
    val_resolved = {}
    for nm, votes in name_votes.items():
        if _val_is_youth(nm):
            continue
        mode_id = max(votes.items(), key=lambda kv: kv[1])[0]
        if mode_id in youth_club_ids:
            continue
        if mode_id in cname and _names_similar(nm, cname[mode_id]):
            val_resolved[nm] = mode_id
    # her oyuncu: tarihe göre sırala, ardışık aynı kulübü bloğa indirge, ekle
    val_added = 0
    for pid, rows in val_player_rows.items():
        rows.sort(key=lambda x: x[0])
        blocks = []   # [cid, from, to]
        for d, nm in rows:
            cid = val_resolved.get(nm)
            if cid is None:
                continue
            if blocks and blocks[-1][0] == cid:
                blocks[-1][2] = d
            else:
                blocks.append([cid, d, d])
        for cid, d_from, d_to in blocks:
            if (pid, cid) in existing_pairs or cid in youth_club_ids:
                continue
            all_stints.append((pid, cid, d_from or None, d_to or None))
            existing_pairs.add((pid, cid))
            alias_map.setdefault(cid, set()).add(cname.get(cid, ""))
            val_added += 1
    print(f"  {len(val_resolved)} club names resolved; {val_added} stints from valuations.")

    # 5) Appearances'dan eksik stint'leri ekle
    # Aynı taramada lig çıkarımı için kulüp başına domestic_league sayacı topla
    # (148MB'ı iki kez okumamak için piggyback). domestic_league kodları
    # competitions.csv'den (type='domestic_league') gelir.
    domestic_leagues = set()
    with open(os.path.join(DATA_DIR, "competitions.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("type") == "domestic_league":
                domestic_leagues.add(r["competition_id"])
    club_league_counts = defaultdict(lambda: defaultdict(int))  # cid -> {comp_id: n}

    print("Adding stints from appearances...")
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

            # Lig sayımı: youth/existing filtrelerinden ÖNCE (kulüp zaten stint'li
            # olsa da ligini çıkarabilmek için), domestic_league kayıtlarında.
            comp = r.get("competition_id")
            if comp and comp in domestic_leagues:
                club_league_counts[cid][comp] += 1

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
        existing_pairs.add((pid, cid))
        added += 1
    print(f"  {added} additional stints from appearances.")

    # 5.4) game_lineups'tan EŞİKLİ stint'ler: bir oyuncu bir kulübün kadrosunda
    # >=LINEUP_MIN kez yer aldıysa o kulübü kariyere ekle. Eşik, tek seferlik /
    # yanlış ilişkilendirmeleri eler (yedek/kısa kadro gürültüsü). transfers ve
    # appearances'ta hiç izi olmayan kulüpleri yakalar.
    LINEUP_MIN = 3
    print("Adding threshold stints from game_lineups...")
    lineup_agg = defaultdict(lambda: {"n": 0, "from": None, "to": None})
    with open(os.path.join(DATA_DIR, "game_lineups.csv"), encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cid_str = r.get("club_id")
            pid_str = r.get("player_id")
            if not cid_str or not pid_str:
                continue
            try:
                pid = int(pid_str)
                cid = int(cid_str)
            except ValueError:
                continue
            if cid in youth_club_ids or (pid, cid) in existing_pairs:
                continue
            cur = lineup_agg[(pid, cid)]
            cur["n"] += 1
            d = r.get("date", "")
            if d:
                if cur["from"] is None or d < cur["from"]:
                    cur["from"] = d
                if cur["to"] is None or d > cur["to"]:
                    cur["to"] = d

    lineup_added = 0
    for (pid, cid), agg in lineup_agg.items():
        if agg["n"] < LINEUP_MIN:
            continue
        all_stints.append((pid, cid, agg["from"], agg["to"]))
        existing_pairs.add((pid, cid))
        lineup_added += 1
    print(f"  {lineup_added} threshold stints from game_lineups (>= {LINEUP_MIN} apps).")

    # 5.5) current_club fallback: transfer VE maç kaydının ikisinde de izi olmayan
    # güncel kulüpleri ekle. Veriyi uydurmadan, players.csv'nin zaten taşıdığı
    # bilgiyi kullanır → "oynadığı kulüp gözükmüyor" boşluklarını kapatır.
    print("Adding fallback stints from current club...")
    cc_added = 0
    for pid, (cid, cname) in player_current_club.items():
        if cid in youth_club_ids or (pid, cid) in existing_pairs:
            continue
        if cname and is_youth_team(cname):
            youth_club_ids.add(cid)
            continue
        if cname:
            alias_map.setdefault(cid, set()).add(cname)
        # Tarih bilinmiyor; açık uçlu stint (date_to=None → "hâlâ orada").
        all_stints.append((pid, cid, None, None))
        existing_pairs.add((pid, cid))
        cc_added += 1
    print(f"  {cc_added} fallback stints from current club.")

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
                        clean_image(legend.get("image_url")),
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
                    clean_image(legend.get("image_url")),
                    None,
                    legend.get("highest_market_value"),
                    None,
                    1,
                    normalize_text(legend["name"]),
                    None, None, None, None, None, None,   # ek alanlar legends.json'da yok
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
            "INSERT OR IGNORE INTO players VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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

    # 6.7) Lig çıkarımı: domestic_competition_id'si boş kulüplere, appearances'ta
    # en sık görüldükleri first-tier ligi ata (sadece veri varsa; mevcutlar ezilmez).
    print("Inferring missing club leagues from appearances...")
    league_filled = 0
    for cid, counts in club_league_counts.items():
        if not counts:
            continue
        best_comp = max(counts.items(), key=lambda kv: kv[1])[0]
        cur = c.execute(
            "SELECT domestic_competition_id FROM clubs WHERE club_id = ?", (cid,)
        ).fetchone()
        if cur and (cur[0] is None or cur[0] == ""):
            c.execute(
                "UPDATE clubs SET domestic_competition_id = ? WHERE club_id = ?",
                (best_comp, cid),
            )
            league_filled += 1
    print(f"  {league_filled} clubs got an inferred league.")

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

    # Placeholder kulüpleri (Without Club / Retired / Unknown ...) kariyerden çıkar:
    # bunlar gerçek kulüp değil; kariyer geçmişinde "Without Club" gibi görünmesinler.
    # Kulüp satırı kalır (alias eşleşmesine zarar yok), sadece stint'leri silinir.
    print("Removing placeholder-club stints from careers...")
    c.execute("""
        DELETE FROM player_clubs WHERE club_id IN (
            SELECT club_id FROM clubs
            WHERE name LIKE '%Without Club%' OR name LIKE '%Retired%'
               OR name LIKE '%Unknown%' OR name LIKE '%Career Break%'
               OR name LIKE '%Suspended%' OR name IS NULL OR name = ''
        )
    """)
    print(f"  {c.rowcount} placeholder stints removed.")

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
    # Sahte/sistem kulüpleri prestiji 0'a zorla → pair_stats'tan otomatik düşer
    c.execute("""
        UPDATE clubs SET prestige_score = 0
        WHERE name LIKE '%Without Club%'
           OR name LIKE '%Retired%'
           OR name LIKE '%Unknown%'
           OR name LIKE '%Career Break%'
           OR name LIKE '%Suspended%'
           OR name IS NULL
           OR name = ''
    """)
    print(f"  {c.rowcount} system/placeholder clubs forced to prestige=0.")
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

    # 10) Quiz havuzları (zorluk başına uygun oyuncular — build anında hesaplanır)
    print("Building quiz_pool...")
    for difficulty, value_filter in QUIZ_DIFFICULTY_FILTERS.items():
        c.execute(f"""
            INSERT INTO quiz_pool (difficulty, player_id)
            SELECT ?, p.player_id
            FROM players p
            WHERE {MULTI_CLUB} AND ({value_filter})
        """, (difficulty,))
        n = c.execute("SELECT COUNT(*) FROM quiz_pool WHERE difficulty = ?", (difficulty,)).fetchone()[0]
        print(f"  {difficulty}: {n} players.")

    # 11) FTS5 arama indeksleri (trigram = index'li substring araması, LIKE '%..%' yerine)
    print("Building FTS5 search indexes...")
    c.executescript("""
        DROP TABLE IF EXISTS players_fts;
        CREATE VIRTUAL TABLE players_fts USING fts5(search_name, content='', tokenize='trigram');
        INSERT INTO players_fts(rowid, search_name)
            SELECT player_id, search_name FROM players
            WHERE search_name IS NOT NULL AND search_name != '';

        DROP TABLE IF EXISTS club_aliases_fts;
        CREATE VIRTUAL TABLE club_aliases_fts USING fts5(club_id UNINDEXED, search_alias, tokenize='trigram');
        INSERT INTO club_aliases_fts(club_id, search_alias)
            SELECT club_id, search_alias FROM club_aliases
            WHERE search_alias IS NOT NULL AND search_alias != '';
    """)

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

    # Veri kalite raporu — "eksik veri" sessiz kalmasın, her build'de ölçülür.
    print("\n=== VERİ KALİTE RAPORU ===")

    def pct(num, den):
        return f"%{100 * num / den:.1f}" if den else "%0.0"

    pf = lambda where: c.execute(
        f"SELECT COUNT(*) FROM players WHERE {where}").fetchone()[0]
    foto_yok = pf("image_url IS NULL")
    deger_yok = pf("market_value IS NULL OR market_value = 0")
    country_ok = pf("country_of_citizenship IS NOT NULL AND country_of_citizenship != ''")
    print(f"players: {p}")
    print(f"  foto dolu           {pct(pf('image_url IS NOT NULL'), p)}"
          f"   (placeholder NULL'a çevrildi: {foto_yok} oyuncu fotosuz)")
    print(f"  güncel değer dolu   {pct(pf('market_value IS NOT NULL AND market_value > 0'), p)}"
          f"   (gerçekten eksik: {deger_yok})")
    print(f"  ülke dolu           {pct(country_ok, p)}")
    print(f"  boy dolu            {pct(pf('height_in_cm IS NOT NULL'), p)}")
    print(f"  ayak dolu           {pct(pf('foot IS NOT NULL'), p)}")
    print(f"  alt-mevki dolu      {pct(pf('sub_position IS NOT NULL'), p)}")

    leagued = c.execute(
        "SELECT COUNT(*) FROM clubs WHERE domestic_competition_id IS NOT NULL "
        "AND domestic_competition_id != ''").fetchone()[0]
    print(f"clubs: {cl}")
    print(f"  lig dolu            {pct(leagued, cl)}   (build öncesi ~%7)")
    print(f"  logo dolu           %100 (deterministik türetilir)")

    # Oyuncunun GÜNCEL kulübünün ligi dolu mu (quiz 'lig' kıyası bunu kullanır)
    cur_league = c.execute("""
        WITH cur AS (
            SELECT pc.player_id, pc.club_id,
                   ROW_NUMBER() OVER (PARTITION BY pc.player_id
                       ORDER BY COALESCE(pc.date_from,'') DESC, pc.id DESC) rn
            FROM player_clubs pc
        )
        SELECT
          SUM(CASE WHEN cl.domestic_competition_id IS NOT NULL
                    AND cl.domestic_competition_id != '' THEN 1 ELSE 0 END),
          COUNT(*)
        FROM cur JOIN clubs cl ON cl.club_id = cur.club_id
        WHERE cur.rn = 1
    """).fetchone()
    print(f"  güncel-kulüp ligi dolu (oyuncu bazında) {pct(cur_league[0] or 0, cur_league[1])}")

    ph_stints = c.execute(
        "SELECT COUNT(*) FROM player_clubs pc JOIN clubs c ON c.club_id=pc.club_id "
        "WHERE c.name LIKE '%Without Club%' OR c.name LIKE '%Retired%'"
    ).fetchone()[0]
    print(f"\nstint özeti: toplam {pc} stint, "
          f"placeholder ('Without Club' vb.) stint: {ph_stints} (0 olmalı)")

    conn.close()
    print(f"\nDatabase saved to: {DB_PATH}")


if __name__ == "__main__":
    create_db()
