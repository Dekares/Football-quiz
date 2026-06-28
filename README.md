# Futbol Quiz

Kulüp geçmişine bakarak gizemli futbolcuyu bul. Solo (kariyerden tahmin) ve
2-6 kişilik gerçek zamanlı çok-kişilik modu (Harman 1v1 düellosu 2 kişilik).
Ana sayfada **Günün Futbolcusu**
(LoLdle tarzı): ipucu yok; isim yaz, her tahminde milliyet/mevki/yaş/değer/kulüp/lig
özellikleri 🟩/🟨/🟥 + ↑↓ ile kıyaslanır (🟨 kısmen: aynı kıta/lig/yakın sayı; kulüp
hariç), daraltarak gizli oyuncuyu bul. Arama **tüm aktif** oyuncuları kapsar; gizli
oyuncu ise daha **tanınmış** (zirve değeri yüksek) bir aktif oyuncudur.

**Çok-kişilik modları:** `mc` (4 şıklı), `free` (serbest yazma), `duel` (oyuncular
sırayla birer takım seçer → herkes ortak oyuncuyu yarışır; ilk doğru +1, tur anında
biter, hedef puana ulaşan kazanır).

## Mimari

İki bağımsız ölçeklenen servis + paylaşılan **salt-okunur** SQLite:

| Servis | Sorumluluk | Ölçek | Durum |
|--------|-----------|-------|-------|
| **api** | HTTP: kulüp/oyuncu arama, quiz, günlük puzzle | Yatay (N replica) | Stateless |
| **realtime** | Socket.IO lobiler | Dikey (tek node) | In-memory lobi state |

- **Veri**: `data/football_quiz.db` her instance ile paketlenir; `mode=ro&immutable=1`
  ile açılır → DB sunucusu yok, sınırsız okuma ölçeği. Redis/Postgres gerekmez.
- **Arama**: FTS5 trigram (index'li substring); kısa sorgularda index'li LIKE fallback.
- **Quiz**: aday havuzu build anında `quiz_pool`'a hesaplanır → çalışma anı tek satır.
- **Günün Futbolcusu**: gizli oyuncu, tarihten (TR saati) deterministik seçilir → herkese
  aynı, sunucuda durum yok; seri/ilerleme istemcide `localStorage`'da. `/api/classic*` stateless.
- **Realtime**: tek async process binlerce eşzamanlı oyunu taşır. Mesaj kuyruğu yok.

## Dizin yapısı

```
backend/app/
  main.py            FastAPI fabrikası (api servisi entrypoint)
  config.py          ayarlar (APP_* env)
  text.py            isim normalizasyonu (API + build ortak)
  db.py              salt-okunur SQLite havuzu (run_in_executor)
  api/               health, search, quiz, classic (günün futbolcusu)
  realtime/
    server.py        socket.io AsyncServer + API'yi sarmalar (realtime entrypoint)
    handlers.py      event handler'ları
    lobby.py         Lobby/Player/Round + kurallar (saf)
    store.py         in-memory lobi kayıt defteri
    matchmaking.py   kulüp çifti seçimi
    questions.py     soru/çeldirici üretimi, cevap doğrulama
data/
  football_quiz.db   build çıktısı (commit'li, salt-okunur)
  build/             build_database.py, prune_obscure.py
  sources/           ham CSV + legends.json (CSV'ler gitignore)
frontend/static/     index.html, css, js (bağımlılıksız vanilla JS)
render.yaml          Render Blueprint (launch: tek servis, kök konum zorunlu)
deploy/              Dockerfile.api, Dockerfile.realtime, nginx.conf (ölçek)
```

## Çalıştırma (geliştirme)

```bash
pip install -r backend/requirements.txt
# Tek process: API + statik + socket.io (same-origin)
uvicorn backend.app.realtime.server:app --reload --port 8000
# http://127.0.0.1:8000
```

Sadece API (statiksiz): `uvicorn backend.app.main:app --port 8000`

## Veritabanını yeniden build etme

Ham CSV'ler `data/sources/` içinde olmalı (players, clubs, transfers, appearances + legends.json).

```bash
python data/build/build_database.py
```

CSV'lerden tam yeniden üretir (prune yok); FTS5 indekslerini ve `quiz_pool`'u
hesaplar. `data/build/prune_obscure.py` ise opsiyonel: alt lig/bilinmeyen
oyuncuları temizler (varsayılan akışta kullanılmaz).

### Kaggle'dan güncelleme (tek komut)

Kaynak set ([Kaggle: davidcariboo/player-scores](https://www.kaggle.com/datasets/davidcariboo/player-scores))
~haftalık güncellenir. `update.py` zinciri yürütür ve canlı DB'yi **yalnızca
doğrulama geçerse** atomik olarak takas eder (önce `.bak-update-*` yedeği alır):

```bash
python data/build/update.py                 # indir + build + doğrula + takas
python data/build/update.py --skip-download # elde mevcut CSV'lerle
python data/build/update.py --prune         # takas sonrası prune_obscure
python data/build/update.py --dry-run       # build + doğrula, takas yapma
```

Gereksinim: Kaggle CLI + `~/.kaggle/kaggle.json` token. Doğrulama oyuncu sayısı
tabanı, eskiye oran (%60), boş quiz havuzu ve `club_pair_stats`'i kontrol eder;
biri patlarsa canlı DB'ye dokunulmaz. `legends.json` elle bakımlıdır, Kaggle
setinde yoktur, indirme onu ezmez. Son 3 güncelleme yedeği tutulur.

Eksik kulüp boşlukları: build, transfers + appearances'a ek olarak
`players.csv`'deki `current_club`'ı da fallback stint olarak ekler (uydurmadan,
mevcut veriyi tam kullanarak) → "oynadığı kulüp gözükmüyor" durumlarını kapatır.

## Dağıtım

- **Launch (basit)**: `render.yaml` — tek servis her şeyi same-origin sunar.
- **Ölçek (1M/gün)**: `deploy/Dockerfile.api` (N replica, statik CDN) +
  `deploy/Dockerfile.realtime` (tek node) + `deploy/nginx.conf` (statik / `/api/` /
  `/socket.io/` yönlendirme).

### Çok-node realtime (Redis'siz)

Tek realtime node yetmezse, LB'de **lobi koduna göre consistent-hash routing**
uygulanır: her node kendi lobilerini in-memory sahiplenir, node'lar arası broadcast
gerekmez → mesaj kuyruğu (Redis) gerekmez. Restart dayanıklılığı için lobi state'i
periyodik olarak diske snapshot'lanabilir.

## Konfig (env, önek `APP_`)

| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `APP_DB_PATH` | `data/football_quiz.db` | Salt-okunur DB yolu |
| `APP_DB_POOL_SIZE` | `8` | SQLite thread havuzu |
| `APP_CORS_ORIGINS` | `["*"]` | İzinli origin'ler |
| `APP_SERVE_STATIC` | `true` | Statikleri Python'dan sun (prod: false) |
