# Careerdle Proje Durumu

Son güncelleme: **21 Temmuz 2026**

Bu belge çalışma ağacındaki uygulama, pipeline ve yayın veritabanı incelenerek
hazırlanmıştır. Üretimde kullanılacak gerçek alan adı ve AdSense hesap işlemleri gibi
repo dışı adımlar ayrıca belirtilmiştir.

## 1. Mevcut durum

Careerdle, futbolcuyu kariyer ve transfer geçmişinden tahmin etmeye dayalı FastAPI ve
vanilla JavaScript uygulamasıdır. Yayındaki arayüz iki oyun sunar:

1. **Günün Futbolcusu:** Her tarihte herkes için aynı aktif ve global Bilindik
   havuzundan oyuncu. Sekiz tahminde milliyet, mevki, yaş, piyasa değeri, kulüp ve lig
   karşılaştırılır.
2. **Futbolcu Tahmin:** Lig ve bilinirlik havuzu seçilir; kronolojik kariyer yolundan
   oyuncu bulunur. Dünya Karması global sıralamayı, Kariyer Efsaneleri ise bilinirlik
   filtresi olmayan özel havuzu kullanır.

Realtime `mc`, `free` ve `duel` backend'i deneysel olarak korunur. Güncel frontend'de
çok oyunculu ekran yoktur; bu mod üretimde tamamlanmış özellik sayılmaz.

### Yayın veritabanı

Aktif artifact: `data/football_quiz_v2.db`

| Alan | Değer |
|---|---:|
| Build kimliği | `20260721-013929-06485908` |
| Oyuncu | 6.898 |
| Kulüp | 8.152 |
| Kariyer dönemi | 56.580 |
| Oyun havuzu | 13 |
| Kulüp çifti | 1.312 |
| Lig bazlı quiz kaydı | 6.162 |
| Global quiz kaydı | 5.960 |
| Global Bilindik | 477 |
| Global Az Bilindik | 1.609 |
| Global Bilinmedik | 3.874 |
| Günlük meydan okuma | 386 |

Günlük takvim `2026-07-01` ile `2027-07-21` arasını kapsar. Geçmiş ve bugünkü
cevaplar değişmez; gelecekteki cevaplar oyuncu global Bilindik havuzundan çıkarsa
yeniden planlanır.

Canonical kaynak `data/transfermarkt_source.db` içinde 6.900 oyuncu, 8.234 kulüp,
56.580 kariyer dönemi, 53.142 transfer, 109.280 piyasa değeri ve 21.522 ham snapshot
vardır. Kuyrukta bekleyen veya çalışan iş yoktur. Kaynak doğrulaması başarılıdır.

## 2. Tamamlanan özellikler

### Veri ve oyun mantığı

- 12 büyük lig: Premier League, Serie A, LaLiga, Bundesliga, Ligue 1, Liga Portugal,
  Eredivisie, Süper Lig, Belçika Pro League, Scottish Premiership, MLS ve Saudi Pro
  League.
- Split-year ve calendar-year liglerde güncel sezon keşfi ve API fallback'i.
- Kadro, profil, transfer ve piyasa değeri ingest'i; ham yanıt snapshot'ları.
- Kesintiden devam eden idempotent iş kuyruğu ve TTL tabanlı güncelleme.
- Transferlerden kronolojik kariyer dönemleri; dönüş transferleri ve emeklilik kaydı.
- Aynı oyuncudaki birden fazla açık dönemi tek güncel kulübe indiren veri onarımı.
- Gerçek Transfermarkt kimlikleri ve API verisiyle beslenen efsane havuzu.
- Lig bazlı ve global `known`, `less_known`, `obscure` sıralamaları.
- Kalıcı günlük takvim; yayınlanmış cevapları koruyan gelecek yeniden planlama kuralı.
- `<output>.new` üzerinde build, foreign key/kalite kontrolü ve atomik yayın.
- Eski istemciler için `easy`, `medium`, `hard` uyumluluk alanları.

### Backend ve güvenlik

- FastAPI HTTP API, Socket.IO realtime servisi ve salt okunur immutable SQLite.
- FTS5 trigram oyuncu/kulüp araması ve kısa sorgularda kontrollü fallback.
- Arama uzunluğu/kelime sınırı ve HTTP rate limiting.
- Same-origin CORS varsayılanı; açık wildcard kaldırıldı.
- `TrustedHostMiddleware`; doğrulanmamış `Host` ve forwarded header yansıması kapatıldı.
- CSP, HSTS, `nosniff`, frame engeli, referrer, permissions ve opener başlıkları.
- Dinamik görseller için yalnız güvenli HTTP(S) URL kabulü ve HTML escaping.
- Socket bağlantı/lobi oluşturma limitleri ve 1.000 aktif lobi tavanı.
- Realtime tur başlatma, seçim ve rövanş akışlarında yarış durumu koruması.
- Boş lobilerin bağlantı toleransı sonunda silinmesi.
- Merkezi futbol konfederasyonu ve bayrak kodu eşlemesi; aktif 136 ülke kapsanıyor.
- Non-root Docker kullanıcıları ve container healthcheck'leri.
- Sabitlenmiş runtime/dev bağımlılıkları ve `pip-audit` kontrolü.
- GitHub Actions: Python/JavaScript syntax, 31 test, DB smoke ve dependency audit.

### Arayüz, erişilebilirlik ve kullanıcı devamlılığı

- Koyu/açık tema ve temaya göre `logo.png` / `logo-koyu.png`.
- Tek kaynaktan enjekte edilen ortak header ve footer.
- Türkçe/İngilizce içerik; responsive masaüstü ve mobil düzen.
- Lig/havuz seçimi, aktif havuz özeti, can, ipucu, seri, rekor ve son tahminler.
- Son görülen 30 oyuncuyu dışlayarak yakın tekrarları azaltma.
- Sade doğru/atlandı/oyun bitti pencereleri ve kariyer özeti.
- Mobilde oyun akışını istatistiklerin önüne alan içerik sırası.
- Klavyeyle arama menüsü, combobox/listbox ARIA durumu, görünür focus ve modal focus
  trap/Escape/focus restore davranışı.
- Arama isteklerinde hata ve geç dönen eski cevap koruması.
- Tema başlangıç ve analytics kodunun ortak dosyalara ayrılması.
- Kişisel veri veya oyuncu adı taşımayan, Consent Mode'a bağlı olay ölçümü.
- About, Methodology, Contact, Privacy ve Terms sayfaları; canonical, sitemap,
  robots.txt, ads.txt, AdSense kimliği ve Consent Mode v2 başlangıcı.

### Kod temizliği

- Kullanılmayan eski çok oyunculu frontend CSS/çeviri/modal parçaları kaldırıldı.
- Çağrılmayan router ve modal yardımcıları kaldırıldı.
- Tekrarlanan ülke haritası merkezi backend verisine taşındı.
- Kullanılmayan `data/football_quiz.db`, `img/icon.png` ve `img/logo-text.png`
  kaldırıldı; yaklaşık 43 MB eski artifact artık repoda tutulmuyor.
- Frontend CSS ve JavaScript toplamında yüzlerce satır ölü kod temizlendi.
- Sunulmayan çok oyunculu özellik SEO ve tanıtım metinlerinden çıkarıldı.

## 3. Yarım kalan işler

### Üretim ve AdSense

- Coolify ortamında `APP_PUBLIC_BASE_URL=https://careerdle.com` ve
  `APP_TRUSTED_HOSTS=["careerdle.com","www.careerdle.com"]` korunmalı.
- AdSense tarafında alan adı ve `ads.txt` doğrulanmalı.
- EEA/UK/İsviçre için Google sertifikalı CMP mesajı Funding Choices üzerinden
  yayınlanmalı. Repo içindeki Consent Mode başlangıcı tek başına CMP değildir.
- Üretim hata izleme, latency, rate-limit ve Socket.IO metrikleri henüz yok.
- Pipeline zamanlanmış bir veri güncelleme workflow'una bağlanmadı; CI yalnız mevcut
  artifact'i doğruluyor.

### Ürün

- Realtime backend için yeni frontend ve iki gerçek istemciyle uçtan uca test yok.
- İstatistikler tarayıcı `localStorage` alanında; cihazlar arası senkronizasyon ve
  hesap sistemi yok.
- Anonim olaylar üretim analytics panelinde dönüşüm hunisi olarak yapılandırılmadı.
- Günlük paylaşım, geri dönüş ve havuz değiştirme olayları bir süre ölçülüp arayüz
  kararları gerçek kullanım verisiyle doğrulanmalı.

## 4. Bilinen hatalar ve riskler

1. Kaynak kuyrukta 10 `dead` iş vardır. Dört aktif oyuncunun transfer ve altı eski
   efsanenin profil endpoint'i yerel Transfermarkt API'den HTTP 500 döndürmektedir.
   Fallback verileri nedeniyle artifact doğrulaması ve oyun havuzu sağlamdır; altı
   oyuncu profil yenilemesi beklemektedir.
2. Realtime lobi durumu process belleğindedir. Process yeniden başlarsa aktif lobiler
   kaybolur; çok node için ortak Socket.IO manager ve state deposu gerekir.
3. Oyun DB'si `immutable=1` açılır. Yeni artifact yayınlandıktan sonra uygulama
   process'i yeniden başlatılmalıdır.
4. CSP, mevcut inline event handler'ları ve reklam entegrasyonu nedeniyle
   `script-src 'unsafe-inline'` içerir. Dinamik içerik escape edilir fakat uzun vadede
   handler'lar event delegation'a, üçüncü taraf scriptler nonce/hash modeline
   taşınmalıdır.
5. Bayrak ve oyuncu/kulüp görselleri üçüncü taraf HTTPS kaynaklarından gelir. Kaynak
   kapanırsa oyun çalışır, yalnız görsel fallback gösterilir.
6. AdSense onayı kodla garanti edilemez; içerik ve teknik sinyaller hazır olsa da son
   karar Google politika ve hesap incelemesidir.

## 5. Sonraki adımlar

1. Değişiklikleri gözden geçirip tek sürümlü commit olarak yayınla.
2. Coolify'da kök ve `www` domainlerini aynı servise bağla; Let's Encrypt sertifikası
   ile tercih edilen domaine yönlendirmeyi doğrula.
3. Google CMP, domain ve `ads.txt` doğrulamalarını tamamla.
4. Pipeline için zamanlanmış workflow ekle: `major-update -> validate -> publish ->
   smoke`; artifact değiştiğinde kontrollü deploy/restart uygula.
5. Üretim gözlemlenebilirliği ve alarm eşikleri ekle.
6. Realtime özelliğinin ürün kararını ver. Açılacaksa ortak state, frontend ve E2E;
   açılmayacaksa deneysel backend'i ayrı paket veya branch'e taşı.
7. CSP inline handler temizliğini ayrı, görsel regresyon testli bir çalışma olarak yap.
8. Kullanım verisi yeterli olduğunda günlük tamamlama, solo tur devamı ve ertesi gün
   geri dönüş oranlarına göre mevcut iki modu iyileştir.

## 6. Çalıştırma

### Kurulum

```powershell
cd "D:\projects\hazır veriseti"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

### Geliştirme sunucusu

Yerel Transfermarkt API `8000` kullanır. Careerdle için bu makinede ayrılmamış `9001`
portu kullanılır:

```powershell
$env:APP_DB_PATH = "data/football_quiz_v2.db"
$env:APP_SERVE_STATIC = "true"
$env:APP_ENABLE_DOCS = "true"

.\.venv\Scripts\python.exe -m uvicorn backend.app.realtime.server:app `
  --host 127.0.0.1 --port 9001 --workers 1
```

- Site: `http://127.0.0.1:9001`
- Sağlık: `http://127.0.0.1:9001/api/health`
- OpenAPI: `http://127.0.0.1:9001/api/docs`

## 7. Test ve build komutları

```powershell
# Python syntax
.\.venv\Scripts\python.exe -m compileall -q backend data tools tests

# Tüm JavaScript dosyaları
$js = rg --files frontend -g '*.js'
foreach ($file in $js) { node --check $file }

# 31 test
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Kaynak veri kalite kontrolü
.\.venv\Scripts\python.exe -m data.pipeline status
.\.venv\Scripts\python.exe -m data.pipeline validate

# Artifact kontratı
.\.venv\Scripts\python.exe -m tools.smoke_app --db data\football_quiz_v2.db

# Çalışan HTTP ve Socket.IO
.\.venv\Scripts\python.exe -m tools.smoke_app `
  --db data\football_quiz_v2.db `
  --base-url http://127.0.0.1:9001 `
  --socket-url http://127.0.0.1:9001

# Masaüstü/mobil görsel QA
.\.venv\Scripts\python.exe tools\visual_qa.py `
  --output-dir .tmp-visual-qa --port 9003 `
  --db data\football_quiz_v2.db

# Bağımlılık güvenliği
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe -m pip_audit -r requirements-dev.txt
```

Frontend vanilla HTML/CSS/JavaScript olduğu için npm build adımı yoktur.

### Veritabanını güncelle

Yerel Transfermarkt API `http://localhost:8000` üzerinde çalışırken:

```powershell
.\.venv\Scripts\python.exe -m data.pipeline major-update `
  --tiers 1,2 --with-market-values --concurrency 8 `
  --min-players 5400 --min-periods 50000
```

Komut discovery, ingest, repair, derive, legend sync, validate ve atomik publish
adımlarını çalıştırır. Normalde yalnız TTL'i dolan kayıtlar istenir. `--force` sadece
tam yenileme gerektiğinde kullanılmalıdır.

Kesilen işi sürdürmek için:

```powershell
.\.venv\Scripts\python.exe -m data.pipeline status
.\.venv\Scripts\python.exe -m data.pipeline work `
  --base-url http://localhost:8000 --concurrency 8
```

Ardından `major-update` tekrar çalıştırılır. Publish sonrası uygulama yeniden
başlatılır ve health build kimliği ile HTTP/Socket smoke kontrol edilir.

### Docker

```powershell
docker build -t careerdle .
docker run --rm -p 9001:8000 careerdle

docker build -f deploy\Dockerfile.api -t careerdle-api .
docker build -f deploy\Dockerfile.realtime -t careerdle-realtime .
```

## 8. Mimari kararlar ve genel akış

```text
Yerel Transfermarkt API (:8000)
        |
        v
transfermarkt_source.db
  crawl queue + raw snapshot + normalize kayıtlar + kalıcı günlük takvim
        |
        | repair + derive + legend sync + validate + publish
        v
football_quiz_v2.db
  read-only oyuncu/kulüp/kariyer + FTS + quiz havuzları + günlükler
        |
        v
FastAPI / Socket.IO
        |
        v
Vanilla HTML/CSS/JS arayüzü
```

- **Canonical/read model ayrımı:** Eksik bir crawl canlı oyun artifact'ini bozmaz.
- **Paketlenmiş SQLite:** Okuma yoğun, hesapsız oyun için basit ve hızlıdır. Online DB,
  sunucu tarafı kullanıcı ilerlemesi veya merkezi realtime state gerektiğinde anlamlıdır.
- **Build-time havuzlar:** Bilinirlik ve kulüp çiftleri istek sırasında hesaplanmaz.
- **Kalıcı günlük cevap:** Geçmiş cevaplar build'ler arasında değişmez.
- **Same-origin varsayımı:** Frontend, API ve Socket.IO aynı origin'de çalışır; CORS
  yalnız gerçekten ayrı bir istemci gerektiğinde açılır.
- **Tek shared shell:** Header/footer partial'ları FastAPI tarafından her HTML sayfasına
  enjekte edilir; gezinme ve marka değişikliği tek yerden yapılır.
- **Gizlilik:** Hesap yoktur; oyun istatistikleri yereldir. Analytics olayları yalnız
  sınırlı sayısal/kategorik alan taşır ve Consent Mode kararına tabidir.
