"""Veritabanını Kaggle'dan tek komutla güncelle.

Kaggle 'davidcariboo/player-scores' seti ~haftalık güncellenir. Bu script
zinciri yürütür ve canlı DB'yi yalnızca doğrulama geçerse takas eder:

    indir (Kaggle API)  →  geçici DB'ye build  →  doğrula  →  yedekle + atomik takas

Kullanım:
    python data/build/update.py               # indir + build + doğrula + takas
    python data/build/update.py --skip-download   # elde mevcut CSV'lerle çalış
    python data/build/update.py --prune           # takas sonrası prune_obscure çalıştır
    python data/build/update.py --dry-run         # build + doğrula, takas YAPMA

Gereksinim: Kaggle CLI kurulu + ~/.kaggle/kaggle.json token mevcut.
Not: legends.json elle bakımlıdır ve Kaggle setinde yoktur; --unzip onu ezmez.
"""

import argparse
import glob
import os
import shutil
import sqlite3
import subprocess
import sys
import time

BUILD_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.dirname(BUILD_DIR)
SOURCES_DIR = os.path.join(DATA_ROOT, "sources")
LIVE_DB = os.path.join(DATA_ROOT, "football_quiz.db")
TMP_DB = LIVE_DB + ".new"
DATASET = "davidcariboo/player-scores"
REQUIRED_CSVS = ("players.csv", "clubs.csv", "transfers.csv", "appearances.csv")
KEEP_BACKUPS = 3                 # son N güncelleme yedeği tutulur
MIN_PLAYERS = 5000              # mutlak taban (altındaysa indirme bozuk demektir)
MIN_RATIO = 0.6                # yeni DB, eskinin en az %60'ı kadar oyuncu içermeli


def run(cmd, **kw):
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, **kw)


def db_counts(path):
    """Salt-okunur sayımlar; DB yoksa None döner."""
    if not os.path.exists(path):
        return None
    # immutable=1: salt-okunur sayım yan etki bırakmasın (-wal/-shm oluşturmaz)
    conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        g = lambda q, p=(): conn.execute(q, p).fetchone()[0]
        return {
            "players": g("SELECT COUNT(*) FROM players"),
            "clubs": g("SELECT COUNT(*) FROM clubs"),
            "stints": g("SELECT COUNT(*) FROM player_clubs"),
            "pairs": g("SELECT COUNT(*) FROM club_pair_stats"),
            "pool_easy": g("SELECT COUNT(*) FROM quiz_pool WHERE difficulty='easy'"),
            "pool_medium": g("SELECT COUNT(*) FROM quiz_pool WHERE difficulty='medium'"),
            "pool_hard": g("SELECT COUNT(*) FROM quiz_pool WHERE difficulty='hard'"),
        }
    finally:
        conn.close()


def download():
    print("\n[1/4] Kaggle'dan indiriliyor...")
    kaggle = shutil.which("kaggle")
    if not kaggle:
        sys.exit("HATA: 'kaggle' CLI bulunamadı. `pip install kaggle` + kaggle.json gerekli.")
    run([kaggle, "datasets", "download", "-d", DATASET,
         "-p", SOURCES_DIR, "--unzip", "--force"])
    for name in REQUIRED_CSVS:
        p = os.path.join(SOURCES_DIR, name)
        if not os.path.exists(p) or os.path.getsize(p) < 1024:
            sys.exit(f"HATA: indirme sonrası eksik/boş CSV: {name}")
    print("  CSV'ler indi.")


def build():
    print("\n[2/4] Geçici DB'ye build ediliyor...")
    if os.path.exists(TMP_DB):
        os.remove(TMP_DB)
    env = dict(os.environ, FOOTBALL_QUIZ_DB=TMP_DB,
               PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    run([sys.executable, os.path.join(BUILD_DIR, "build_database.py")], env=env)
    if not os.path.exists(TMP_DB):
        sys.exit("HATA: build çıktısı oluşmadı.")


def verify(old):
    print("\n[3/4] Doğrulama...")
    new = db_counts(TMP_DB)
    if new is None:
        sys.exit("HATA: geçici DB okunamadı.")
    for k, v in new.items():
        delta = "" if not old else f"  (eski: {old[k]:,})"
        print(f"  {k:14s} {v:>9,}{delta}")

    problems = []
    if new["players"] < MIN_PLAYERS:
        problems.append(f"oyuncu sayısı çok düşük: {new['players']}")
    if old and new["players"] < old["players"] * MIN_RATIO:
        problems.append(f"oyuncu sayısı eskinin %{int(MIN_RATIO*100)}'ından az "
                        f"({new['players']} < {old['players']})")
    for d in ("easy", "medium", "hard"):
        if new[f"pool_{d}"] == 0:
            problems.append(f"{d} quiz havuzu boş")
    if new["pairs"] == 0:
        problems.append("club_pair_stats boş (düello eşleşmesi bozulur)")

    if problems:
        os.remove(TMP_DB)
        sys.exit("DOĞRULAMA BAŞARISIZ → takas iptal, canlı DB'ye dokunulmadı:\n  - "
                 + "\n  - ".join(problems))
    print("  Doğrulama OK.")
    return new


def swap():
    print("\n[4/4] Yedekle + atomik takas...")
    if os.path.exists(LIVE_DB):
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup = f"{LIVE_DB}.bak-update-{ts}"
        shutil.copy2(LIVE_DB, backup)
        print(f"  yedek → {os.path.basename(backup)}")
    try:
        os.replace(TMP_DB, LIVE_DB)   # aynı klasör → atomik
    except PermissionError:
        # Windows: DB başka process tarafından açık (çalışan dev sunucu / SQLite
        # görüntüleyici). .new ve yedek korunur → süreçleri kapatıp tekrar dene.
        sys.exit(
            f"\nTAKAS ENGELLENDİ: '{LIVE_DB}' başka bir process tarafından açık tutuluyor.\n"
            f"Çalışan uvicorn dev sunucularını / SQLite görüntüleyicileri kapat, sonra:\n"
            f"    python data/build/update.py --skip-download\n"
            f"Yeni DB hazır: {TMP_DB}  (doğrulamadan geçti, silinmedi)."
        )
    print(f"  canlı DB güncellendi: {LIVE_DB}")

    backups = sorted(glob.glob(f"{LIVE_DB}.bak-update-*"))
    for old_bak in backups[:-KEEP_BACKUPS]:
        os.remove(old_bak)
        print(f"  eski yedek silindi: {os.path.basename(old_bak)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-download", action="store_true", help="Kaggle'dan indirme, mevcut CSV'leri kullan")
    ap.add_argument("--prune", action="store_true", help="Takas sonrası prune_obscure.py çalıştır")
    ap.add_argument("--dry-run", action="store_true", help="Build + doğrula, takas yapma")
    args = ap.parse_args()

    old = db_counts(LIVE_DB)
    t0 = time.time()

    if not args.skip_download:
        download()
    else:
        print("\n[1/4] İndirme atlandı (--skip-download).")

    build()
    verify(old)

    if args.dry_run:
        os.remove(TMP_DB)
        print("\n[dry-run] Doğrulama geçti; canlı DB değiştirilmedi.")
        return

    swap()

    if args.prune:
        print("\n[+] prune_obscure çalıştırılıyor...")
        run([sys.executable, os.path.join(BUILD_DIR, "prune_obscure.py")],
            env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"))

    print(f"\nBitti. Süre: {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
