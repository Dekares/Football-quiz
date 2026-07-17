# Careerdle

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

- **Veri**: `data/football_quiz_v2.db` her instance ile paketlenir; `mode=ro&immutable=1`
  ile açılır → DB sunucusu yok, sınırsız okuma ölçeği. Redis/Postgres gerekmez.
- **Arama**: FTS5 trigram (index'li substring); kısa sorgularda index'li LIKE fallback.
- **Kariyer Quiz**: oyuncular son kadro snapshot'ına göre 12 ligden birine bağlanır.
  Her ligde bilinirlik puanına göre birbirini dışlayan **Bilindik / Az Bilindik /
  Bilinmedik** havuzları build anında `quiz_pool`'a yazılır. Emekli editoryal
  oyuncular ayrı `Kariyer Efsaneleri` havuzunda tutulur. **Tüm Ligler** seçimi,
  lig yüzdeliklerini birleştirmek yerine daha seçici oranlarla üretilen bağımsız
  `global_quiz_pool` tablosunu kullanır.
- **Günün Futbolcusu**: `01.07.2026` tarihinden başlayan kalıcı takvim kaynak DB'de
  saklanır. Eksik günler global **Bilindik** havuzundan planlanır; yayınlanmış cevaplar
  sonraki build'lerde korunur. Seri/ilerleme istemcide `localStorage`'da tutulur.
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
  football_quiz_v2.db  doğrulanmış oyun artifact'i (salt-okunur)
  transfermarkt_source.db canonical kaynak, snapshot ve kalıcı iş kuyruğu (gitignore)
  pipeline/           API ingest, normalize, validate ve atomik publish
  sources/legends.json elle bakımlı efsane oyuncu kaynağı
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

## Veritabanını güncelleme

Yerel Transfermarkt API `http://localhost:8000` adresinde çalışırken canonical
veri, ham JSON snapshot'lar ve kalıcı iş kuyruğu
`data/transfermarkt_source.db` içinde tutulur. Büyük liglerin güncel sezonu
otomatik hesaplanır; başarısız işler tekrar denenebilir ve tamamlanan istekler
TTL dolmadan yeniden çağrılmaz.

```powershell
python -m data.pipeline major-update --tiers 1,2 --with-market-values `
  --concurrency 8 --min-players 5400 --min-periods 50000
python -m data.pipeline repair
python -m data.pipeline import-legends
python -m data.pipeline validate
python -m tools.smoke_app --db data/football_quiz_v2.db
```

Publish önce `<output>.new` oluşturur; FK, veri eşiği, quiz havuzları ve kulüp
çiftleri doğrulanırsa mevcut artifact'i atomik olarak değiştirir. Ayrıntılı
komutlar ve zamanlama modeli için `data/pipeline/README.md` kullanılır.

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
| `APP_DB_PATH` | `data/football_quiz_v2.db` | Salt-okunur DB yolu |
| `APP_DB_POOL_SIZE` | `8` | SQLite thread havuzu |
| `APP_CORS_ORIGINS` | `["*"]` | İzinli origin'ler |
| `APP_SERVE_STATIC` | `true` | Statikleri Python'dan sun (prod: false) |
