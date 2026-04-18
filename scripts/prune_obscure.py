"""Alt lig / bilinmeyen oyuncu + orphan kulüp temizliği.

Idempotent, tek transaction. Kullanım:
    python scripts/prune_obscure.py --dry-run   # sadece istatistik
    python scripts/prune_obscure.py             # gerçek silme + backup + VACUUM

Korunan oyuncular: is_legend=1 VEYA international_caps>0 VEYA
highest_market_value >= T_PLAYER_MV. Kalanı silinir. Orphan kulüpler
(hiç player_clubs kaydı kalmayan) cascade ile temizlenir. Sonra
prestige_score ve club_pair_stats baştan hesaplanır.
"""

import argparse
import os
import shutil
import sqlite3
import sys
import time
from collections import defaultdict
from itertools import combinations

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "football_quiz.db")
T_PLAYER_MV = 1_000_000

KEEP_CONDITION = (
    "is_legend = 1 "
    "OR (international_caps IS NOT NULL AND international_caps > 0) "
    f"OR (highest_market_value IS NOT NULL AND highest_market_value >= {T_PLAYER_MV})"
)
DROP_CONDITION = (
    "is_legend = 0 "
    "AND (international_caps IS NULL OR international_caps = 0) "
    f"AND (highest_market_value IS NULL OR highest_market_value < {T_PLAYER_MV})"
)


def table_counts(c):
    out = {}
    for t in ("players", "clubs", "player_clubs", "club_aliases", "club_pair_stats"):
        c.execute(f"SELECT COUNT(*) FROM {t}")
        out[t] = c.fetchone()[0]
    return out


def print_stats(label, stats):
    print(f"\n=== {label} ===")
    for k, v in stats.items():
        print(f"  {k:18s} {v:>10,}")


def rebuild_prestige_and_pairs(c):
    print("\nRecomputing prestige_score...")
    c.execute("""
        UPDATE clubs SET prestige_score = COALESCE((
            SELECT COUNT(DISTINCT pc.player_id)
            FROM player_clubs pc
            JOIN players p ON p.player_id = pc.player_id
            WHERE pc.club_id = clubs.club_id
              AND (p.highest_market_value >= 50000000 OR p.is_legend = 1)
        ), 0)
    """)
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
    c.execute("SELECT COUNT(*) FROM clubs WHERE prestige_score >= 3")
    print(f"  clubs with prestige_score >= 3: {c.fetchone()[0]}")

    print("Rebuilding club_pair_stats...")
    c.execute("DELETE FROM club_pair_stats")
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

    rows = []
    for (a, b), cnt in pair_common.items():
        if cnt < 2:
            continue
        min_p = min(prestige_score_map.get(a, 0), prestige_score_map.get(b, 0))
        rows.append((a, b, cnt, min_p))

    c.executemany(
        "INSERT INTO club_pair_stats (club_a_id, club_b_id, common_count, min_prestige) VALUES (?,?,?,?)",
        rows,
    )
    print(f"  {len(rows):,} club pairs stored.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Sadece istatistikleri yazdır, DB'yi değiştirme")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    before = table_counts(c)
    print_stats("BEFORE", before)

    c.execute(f"SELECT COUNT(*) FROM players WHERE {DROP_CONDITION}")
    players_to_delete = c.fetchone()[0]

    c.execute(f"""
        SELECT COUNT(*) FROM clubs
        WHERE club_id NOT IN (
            SELECT DISTINCT pc.club_id
            FROM player_clubs pc
            JOIN players p ON p.player_id = pc.player_id
            WHERE p.is_legend = 1
               OR (p.international_caps IS NOT NULL AND p.international_caps > 0)
               OR (p.highest_market_value IS NOT NULL AND p.highest_market_value >= {T_PLAYER_MV})
        )
    """)
    clubs_to_delete = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM players WHERE is_legend = 1")
    legend_count = c.fetchone()[0]

    print("\n=== PLAN ===")
    print(f"  players to delete : {players_to_delete:>10,}")
    print(f"  orphan clubs      : {clubs_to_delete:>10,}")
    print(f"  legends preserved : {legend_count:>10,}")
    print(f"  MV threshold      : {T_PLAYER_MV:>10,}")

    if args.dry_run:
        print("\n[dry-run] DB değiştirilmedi.")
        conn.close()
        return

    # Backup
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_path = f"{DB_PATH}.bak-prune-{ts}"
    conn.close()
    print(f"\nBacking up → {backup_path}")
    shutil.copy2(DB_PATH, backup_path)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("BEGIN")

        print("\nDeleting player_clubs rows for obscure players...")
        c.execute(f"""
            DELETE FROM player_clubs WHERE player_id IN (
                SELECT player_id FROM players WHERE {DROP_CONDITION}
            )
        """)
        print(f"  player_clubs removed: {c.rowcount:,}")

        print("Deleting obscure players...")
        c.execute(f"DELETE FROM players WHERE {DROP_CONDITION}")
        print(f"  players removed: {c.rowcount:,}")

        print("Finding orphan clubs...")
        orphan_ids = [r[0] for r in c.execute("""
            SELECT club_id FROM clubs
            WHERE club_id NOT IN (SELECT DISTINCT club_id FROM player_clubs)
        """)]
        print(f"  orphan clubs: {len(orphan_ids):,}")

        if orphan_ids:
            # Chunk delete (SQLite expression tree limit ~999 params)
            CHUNK = 500
            for i in range(0, len(orphan_ids), CHUNK):
                chunk = orphan_ids[i:i + CHUNK]
                placeholders = ",".join("?" * len(chunk))
                c.execute(f"DELETE FROM club_aliases WHERE club_id IN ({placeholders})", chunk)
                c.execute(f"DELETE FROM clubs       WHERE club_id IN ({placeholders})", chunk)
            print(f"  orphan clubs + aliases removed.")

        rebuild_prestige_and_pairs(c)

        conn.commit()
        print("\nCOMMIT OK.")
    except Exception as e:
        conn.rollback()
        print(f"\nERROR → rollback: {e}")
        conn.close()
        sys.exit(1)

    # VACUUM (transaction dışında)
    print("\nVACUUM...")
    c.execute("VACUUM")
    conn.close()

    # Son istatistikler
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    after = table_counts(c)
    print_stats("AFTER", after)

    c.execute("SELECT COUNT(*) FROM players WHERE is_legend = 1")
    post_legend = c.fetchone()[0]
    size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    backup_mb = os.path.getsize(backup_path) / (1024 * 1024)
    print(f"\nLegend sanity: {post_legend} (before: {legend_count}) {'OK' if post_legend == legend_count else 'MISMATCH!'}")
    print(f"DB size: {size_mb:.1f} MB  (backup: {backup_mb:.1f} MB)")
    print(f"Backup kept at: {backup_path}")
    conn.close()


if __name__ == "__main__":
    main()
