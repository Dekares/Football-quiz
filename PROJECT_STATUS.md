# Careerdle Proje Durumu

Son güncelleme: **17 Temmuz 2026**

Bu belge, mevcut çalışma ağacındaki kod ve veritabanı esas alınarak hazırlanmıştır.
README'den farklı bir bilgi varsa, bu belgedeki "Mevcut durum" ve "Yarım kalan
işler" bölümleri güncel uygulama davranışını ifade eder.

## 1. Projenin mevcut durumu

Careerdle, futbolcuyu kariyer geçmişinden tahmin etmeye dayalı, FastAPI ve vanilla
JavaScript ile geliştirilmiş bir futbol oyunudur. Kullanıcıya açık ve aktif iki oyun
akışı vardır:

1. **Günün Futbolcusu:** Her gün herkes için aynı aktif oyuncu seçilir. Tahminler
   milliyet, mevki, yaş, değer, kulüp ve lig bilgileriyle karşılaştırılır.
2. **Futbolcu Tahmin / Solo:** Lig ve bilinirlik havuzu seçilir; oyuncu kariyerindeki
   kulüp sırasından tahmin edilir.

Realtime çok oyunculu backend kodu mevcuttur; ancak güncel frontend router'da çok
oyunculu ekran veya rota yoktur. Bu nedenle çok oyunculu mod şu anda kullanıcıya açık
tamamlanmış bir özellik olarak kabul edilmemelidir.

### Güncel veri durumu

Aktif oyun artifact'i: `data/football_quiz_v2.db`

| Alan | Mevcut değer |
|---|---:|
| Build kimliği | `20260716-172641-e1b57aa7` |
| Oyuncu | 6.737 |
| Kulüp | 8.004 |
| Kariyer dönemi | 54.672 |
| Oyun ligi/havuzu | 13 |
| Kulüp çifti | 979 |
| Günlük meydan okuma | 381 |
| Lig bazlı quiz havuzu | 6.005 |
| Global quiz havuzu | 5.961 |

13 oyun havuzu, yapılandırılmış 12 lig ile özel `Kariyer Efsaneleri` havuzundan
oluşur. Kullanıcı arayüzündeki `Tüm Ligler`, bu 13 sayısına eklenen sanal bir seçimdir
ve bağımsız `global_quiz_pool` tablosunu kullanır.

Kaynak veritabanı `data/transfermarkt_source.db` içinde 6.737 oyuncu, 8.017 kulüp,
50.983 transfer, 105.465 piyasa değeri kaydı ve 20.324 ham API snapshot'ı vardır.
Kaynak kalite doğrulaması başarılıdır; açık `error` seviyesinde veri sorunu yoktur.

### Son doğrulama durumu

- SQLite `quick_check`: başarılı.
- Foreign key kontrolü: başarılı.
- Pipeline'ın yeniden ürettiği artifact ile mevcut artifact arasında şema farkı: 0.
- Oyuncu, kulüp, kariyer, havuz, alias ve eşleşme satır farkı: 0.
- Birim ve uyumluluk testleri: **19/19 başarılı**.
- Veritabanı ve HTTP smoke testi: başarılı.
- Masaüstü/mobil görsel regresyon testi: başarılı.

## 2. Tamamlanan özellikler

### Oyunlar

- Günün Futbolcusu için kalıcı, tarih bazlı günlük oyuncu seçimi.
- Günlük takvimin `2026-07-01` tarihinden başlaması.
- Yayınlanmış günlük cevapların sonraki DB build'lerinde değişmeden korunması.
- Günlük oyuncunun global `Bilindik` havuzundan seçilmesi.
- Günlük tahminlerde milliyet, mevki, yaş, piyasa değeri, kulüp ve lig karşılaştırması.
- Solo oyunda lig seçimi.
- Solo oyunda `Bilindik`, `Az Bilindik`, `Bilinmedik` oyuncu havuzları.
- `Tüm Ligler` için lig yüzdeliklerinden bağımsız global bilinirlik havuzu.
- Kariyer Efsaneleri seçeneği ve elle bakımlı emekli oyuncular.
- Kariyer yolunun kronolojik takım listesi olarak gösterilmesi.
- Tekrarlanan kulüp dönemlerinin ve dönüş transferlerinin korunması.
- Emeklilik durumunun kariyer sonunda sentetik veya gerçek kayıt olarak gösterilmesi.
- Doğru cevap ve atlama sonuç pencerelerinin sade, tema uyumlu hale getirilmesi.
- Solo seri, rekor, toplam doğru ve son oyuncuların `localStorage` ile saklanması.
- Günlük oyun ilerlemesi ve serisinin `localStorage` ile saklanması.

### Ligler ve veri kapsamı

- Premier League, Serie A, LaLiga, Bundesliga ve Ligue 1.
- Liga Portugal, Eredivisie, Süper Lig, Jupiler Pro League ve Scottish Premiership.
- Major League Soccer.
- Saudi Pro League.
- Güncel sezonun split-year ve calendar-year ligler için otomatik hesaplanması.
- API istenen sezonu döndürmezse keşfedilen en güncel sezona geri düşülmesi.
- Oyuncu profilleri, kadrolar, transferler ve piyasa değeri geçmişlerinin alınması.
- Transferlerden normalize kariyer dönemlerinin türetilmesi.
- Ham API cevaplarının snapshot olarak saklanması.
- Kesintiden sonra devam edebilen kalıcı ve idempotent iş kuyruğu.

### Veritabanı pipeline'ı

- Mutable canonical kaynak DB ile immutable oyun DB'sinin ayrılması.
- Kaynak DB: `data/transfermarkt_source.db`.
- Yayın artifact'i: `data/football_quiz_v2.db`.
- TTL tabanlı güncelleme:
  - Kulüp ve kadro keşfi: 1 gün.
  - Transferler: 1 gün.
  - Oyuncu profilleri: 30 gün.
  - Piyasa değerleri: 7 gün.
- Kaynak ve çıktı foreign key kontrolleri.
- Minimum oyuncu ve kariyer dönemi eşikleri.
- Her lig için birbirini dışlayan üç bilinirlik havuzu.
- Global bilinirlik havuzunun ayrı sıralanması.
- Realtime oyun için kulüp çifti adaylarının build sırasında üretilmesi.
- `<output>.new` üzerinde build ve doğrulama sonrası atomik yayın.
- Başarılı eski artifact'ler için en fazla üç otomatik yedek.
- Güncel backend formatıyla pipeline uyumluluğu doğrulandı.

### Backend ve platform

- FastAPI HTTP API.
- Socket.IO realtime backend ve in-memory lobi kayıt defteri.
- SQLite'ın `mode=ro&immutable=1` ile salt okunur açılması.
- Bloklayıcı SQLite sorgularının sabit thread pool üzerinde çalıştırılması.
- FTS5 trigram oyuncu ve kulüp araması; kısa sorgular için LIKE fallback.
- HTTP API rate limiting.
- Tek process geliştirme/launch modeli: API + statik dosyalar + Socket.IO.
- Ayrı ölçekleme için API ve realtime Dockerfile'ları ile nginx örneği.
- Render ve Docker dağıtım yapılandırmaları.
- Sağlık kontrolü ve build kimliği endpoint'i.
- İsteğe bağlı OpenAPI dokümantasyonu (`/api/docs`).

### Arayüz ve içerik

- Koyu ve açık tema.
- Koyu temada `logo.png`, açık temada `logo-koyu.png` kullanımı.
- Tüm sayfalarda ortak üst ve alt bar.
- Ortak kabuk dosyaları:
  - `frontend/static/partials/site-header.html`
  - `frontend/static/partials/site-footer.html`
- Header/footer'ın FastAPI tarafından tüm HTML sayfalarına enjekte edilmesi.
- Türkçe ve İngilizce arayüz/içerik desteği.
- Mobil navigasyon ve responsive sayfa düzenleri.
- About, Data Methodology, Contact, Privacy ve Terms of Use sayfaları.
- Logo, favicon, Open Graph ve Twitter görselleri.
- `robots.txt`, `sitemap.xml` ve `ads.txt` endpoint'leri.
- AdSense publisher meta etiketleri ve Auto Ads script'i.
- Consent Mode v2 varsayılanlarının reddedilmiş olarak başlatılması.
- AdSense/SEO/site uyumluluğu için otomatik statik kontroller.

## 3. Yarım kalan işler

### Çok oyunculu frontend

Realtime backend; lobi oluşturma, katılma, yeniden bağlanma, ayar değiştirme, oyun
başlatma, cevap gönderme, kulüp seçme, oyuncu atma ve rövanş event'lerini içerir.
Ancak eski `frontend/static/js/multi.js` kaldırılmış ve güncel router'da yalnızca
`#/` ile `#/solo` rotaları kalmıştır.

Tamamlanması için:

- Çok oyunculu ekranın yeni temaya göre yeniden tasarlanması.
- Socket.IO istemcisinin yeniden bağlanması.
- MC, serbest yazma ve düello akışlarının uçtan uca test edilmesi.
- Mobil lobi ve bağlantı kopması senaryolarının test edilmesi.
- Özellik açılana kadar SEO metinlerindeki “canlı düello / 2-6 kişi” ifadelerinin
  kaldırılması veya “yakında” olarak değiştirilmesi.

### AdSense operasyonu

Teknik site hazırlıkları tamamlanmıştır; ancak AdSense onayı kodla garanti edilemez.
Google tarafında aşağıdaki işler ayrıca tamamlanmalıdır:

- Alan adının AdSense hesabında doğrulanması.
- `ads.txt` durumunun Google panelinde doğrulanması.
- EEA/UK/İsviçre için Google sertifikalı CMP mesajının Funding Choices üzerinden
  yayınlanması.
- Site sahipliği, politika ve içerik incelemesinin Google tarafından onaylanması.
- Gerçek alan adı belli olduğunda `APP_PUBLIC_BASE_URL` değerinin sabitlenmesi.

### Operasyon ve dağıtım

- Online veritabanına geçiş henüz yapılmadı. Mevcut mimari paketlenmiş salt-okunur
  SQLite kullanıyor ve şu an için bilinçli tercih budur.
- Pipeline güncellemeleri zamanlanmış CI/cron göreviyle otomatik çalışmıyor.
- GitHub Actions veya eşdeğer CI yapılandırması yok.
- Realtime lobi state'i restart sonrası kaybolur; kalıcı snapshot uygulanmadı.
- Çok node realtime için belgelenen lobi koduna göre consistent-hash routing henüz
  üretim ortamında uygulanmadı.
- Çalışma ağacındaki kapsamlı değişiklikler henüz temiz bir commit/release halinde
  paketlenmedi; kritik yeni pipeline, test ve DB dosyaları Git tarafından untracked
  görünüyor.

## 4. Bilinen hatalar ve riskler

1. **Dört dead pipeline işi:** Transfermarkt API dört oyuncunun transfer endpoint'inde
   HTTP 500 döndürdü. Oyuncu kimlikleri: `308279`, `989995`, `707802`, `468264`.
   Kaynak validasyonu yine de başarılıdır ve açık veri hatası yoktur. Sonraki
   `major-update` bu dead işleri tekrar kuyruğa alır.
2. **Çok oyunculu tanıtım tutarsızlığı:** Bazı README, SEO ve sayfa metinleri canlı
   çok oyunculu modu mevcutmuş gibi anlatıyor; güncel frontend bu modu sunmuyor.
3. **Immutable DB nedeniyle restart gereksinimi:** Uygulama çalışan thread'lerde DB'yi
   immutable bağlantıyla açık tuttuğu için yeni artifact yayınlandıktan sonra uygulama
   process'i yeniden başlatılmalıdır.
4. **Realtime state kaybı:** Tek realtime process yeniden başlarsa aktif lobiler ve
   maçlar kaybolur.
5. **AdSense dış bağımlılığı:** Teknik dosyalar doğru olsa bile Google hesabı, CMP ve
   politika onayı tamamlanmadan reklam gösterimi başlamaz.

## 5. Sonraki yapılması gereken adımlar

Önerilen öncelik sırası:

1. Çalışma ağacını gözden geçir, üretilmiş/geçici dosyaları ayır ve mevcut çalışan
   durumu tek bir sürümlü commit olarak güvenceye al.
2. Çok oyunculu modun ürün kapsamına karar ver:
   - Yeniden açılacaksa frontend ve E2E testlerini tamamla.
   - Yakın vadede açılmayacaksa SEO, README ve tanıtım metinlerinden çıkar.
3. Gerçek üretim alan adını belirle ve `APP_PUBLIC_BASE_URL`, CORS ve AdSense site
   doğrulamasını üretim değerleriyle yapılandır.
4. Google sertifikalı CMP mesajını yayınla ve AdSense panelindeki `ads.txt` durumunu
   doğrula.
5. Pipeline'ı günlük veya haftalık zamanlanmış bir iş haline getir; yayın öncesi
   `validate`, yayın sonrası `smoke_app` zorunlu olsun.
6. Dört dead transfer işinin yerel Transfermarkt API tarafındaki HTTP 500 nedenini
   incele.
7. CI ekle: unittest, JavaScript syntax, pipeline smoke ve Docker build.
8. Üretim gözlemlenebilirliği ekle: hata logları, sağlık kontrolü, latency ve Socket.IO
   bağlantı metrikleri.
9. Trafik gerçekten gerektirirse API/statik/realtime ayrık dağıtımına geç; online DB'ye
   yalnızca yazma veya çoklu bölge gereksinimi oluştuğunda karar ver.

## 6. Projeyi çalıştırma

### Gereksinimler

- Python 3.11 veya 3.12.
- PowerShell komutları için Windows.
- Veritabanı güncellemesi yapılacaksa çalışan yerel Transfermarkt API.
- Görsel QA için Google Chrome.

### Bağımlılık kurulumu

```powershell
cd "D:\projects\hazır veriseti"

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

### Careerdle geliştirme sunucusu

Transfermarkt API `8000` portunda çalışıyorsa Careerdle için `8011` kullan:

```powershell
cd "D:\projects\hazır veriseti"

$env:APP_DB_PATH = "data/football_quiz_v2.db"
$env:APP_SERVE_STATIC = "true"
$env:APP_ENABLE_DOCS = "true"

.\.venv\Scripts\python.exe -m uvicorn backend.app.realtime.server:app `
  --host 127.0.0.1 `
  --port 8011 `
  --workers 1
```

- Site: `http://127.0.0.1:8011`
- Sağlık: `http://127.0.0.1:8011/api/health`
- OpenAPI: `http://127.0.0.1:8011/api/docs`

Sadece stateless HTTP API çalıştırmak için:

```powershell
$env:APP_SERVE_STATIC = "false"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app `
  --host 127.0.0.1 --port 8011
```

## 7. Test komutları

### Birim ve uyumluluk testleri

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Beklenen güncel sonuç: `Ran 19 tests ... OK`.

### Python ve JavaScript syntax kontrolleri

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend data\pipeline tools

node --check frontend\static\js\common.js
node --check frontend\static\js\classic.js
node --check frontend\static\js\solo.js
node --check frontend\static\js\router.js
node --check frontend\static\js\doc-page.js
node --check frontend\static\js\privacy-consent.js
```

### Kaynak DB kontrolü

```powershell
.\.venv\Scripts\python.exe -m data.pipeline status
.\.venv\Scripts\python.exe -m data.pipeline validate
```

### Artifact smoke testi

Sunucu olmadan yalnızca DB kontratını test etmek için:

```powershell
.\.venv\Scripts\python.exe -m tools.smoke_app `
  --db data\football_quiz_v2.db
```

Çalışan siteyle HTTP ve Socket.IO dahil test etmek için:

```powershell
.\.venv\Scripts\python.exe -m tools.smoke_app `
  --db data\football_quiz_v2.db `
  --base-url http://127.0.0.1:8011 `
  --socket-url http://127.0.0.1:8011
```

### Görsel regresyon testi

Araç kendi geçici sunucusunu başlatır ve masaüstü/mobil ekran görüntüleri üretir:

```powershell
.\.venv\Scripts\python.exe tools\visual_qa.py `
  --output-dir .tmp-visual-qa `
  --port 8013 `
  --db data\football_quiz_v2.db
```

Tek bir görsel işi çalıştırmak için örnek:

```powershell
.\.venv\Scripts\python.exe tools\visual_qa.py `
  --only result-skipped-mobile
```

## 8. Veritabanı güncelleme ve build komutları

Veritabanı build'i sırasında yerel Transfermarkt API'nin
`http://localhost:8000` adresinde çalışması gerekir.

### Üretim kapsamındaki tüm büyük ligleri güncelle

```powershell
.\.venv\Scripts\python.exe -m data.pipeline major-update `
  --tiers 1,2 `
  --with-market-values `
  --concurrency 8 `
  --min-players 5400 `
  --min-periods 50000
```

Bu komut keşif, ingest, repair, kariyer türetme, efsane importu, kaynak doğrulama ve
sıkı artifact publish adımlarını birlikte çalıştırır. Normal çalışmada yalnızca TTL'i
dolan kaynaklar yeniden istenir.

TTL'i yok sayarak her şeyi tekrar istemek için yalnızca gerektiğinde `--force` ekle.

### Kesilen işi devam ettir

```powershell
.\.venv\Scripts\python.exe -m data.pipeline status
.\.venv\Scripts\python.exe -m data.pipeline work `
  --base-url http://localhost:8000 `
  --concurrency 8
```

Worker bittikten sonra `major-update` komutunu yeniden çalıştırarak kalan aşamaları ve
publish'i tamamla.

### Manuel aşamalar

```powershell
.\.venv\Scripts\python.exe -m data.pipeline repair
.\.venv\Scripts\python.exe -m data.pipeline derive
.\.venv\Scripts\python.exe -m data.pipeline import-legends
.\.venv\Scripts\python.exe -m data.pipeline validate
.\.venv\Scripts\python.exe -m data.pipeline publish `
  --min-players 5400 `
  --min-periods 50000
```

`--allow-incomplete` yalnızca küçük pilot datasetlerde kullanılmalıdır; üretim
artifact'i için kullanılmamalıdır.

### Yayın sonrası

1. Careerdle process'ini yeniden başlat.
2. `/api/health` içindeki build kimliğinin değiştiğini doğrula.
3. DB + HTTP smoke testini çalıştır.
4. Günlük oyuncu ve Solo akışını tarayıcıdan kontrol et.

### Frontend build

Frontend vanilla HTML/CSS/JavaScript'tir; npm tabanlı compile veya bundle aşaması
yoktur. Statik dosyalar doğrudan `frontend/static/` altından sunulur.

## 9. Docker ve dağıtım komutları

### Tek servis Docker build

```powershell
docker build -t careerdle .
docker run --rm -p 8000:8000 careerdle
```

### Ayrık servis build'leri

```powershell
docker build -f deploy\Dockerfile.api -t careerdle-api .
docker build -f deploy\Dockerfile.realtime -t careerdle-realtime .
```

Basit üretim dağıtımı için kökteki `render.yaml`, tek process API + statik + Socket.IO
modelini kullanır. Ayrık yüksek trafik modeli için `deploy/nginx.conf` örneği vardır.

## 10. Önemli mimari kararlar

### Canonical DB ve read model ayrımı

Pipeline doğrudan oyun DB'sine yazmaz. Veri akışı:

```text
Yerel Transfermarkt API (:8000)
        |
        v
transfermarkt_source.db
  - crawl queue
  - raw snapshots
  - normalize oyuncu/kulüp/transfer/değer verisi
  - kalıcı günlük takvim
        |
        | derive + repair + validate + publish
        v
football_quiz_v2.db
  - salt-okunur oyun artifact'i
  - FTS indexleri
  - quiz/global havuzlar
  - kulüp çiftleri
  - günlük meydan okumalar
        |
        v
FastAPI / Socket.IO -> vanilla frontend
```

Bu ayrım, yarım kalan veya hatalı bir crawl'ın canlı oyunu bozmasını engeller.

### SQLite'ın paketlenmiş ve immutable kullanılması

Oyun DB'si runtime'da yazılmaz. Bunun sonuçları:

- API replica'ları ortak DB sunucusuna ihtiyaç duymaz.
- Okuma sorguları kilitsiz ve hızlıdır.
- Artifact Docker image veya deploy paketiyle birlikte dağıtılabilir.
- Yeni DB yayınlandıktan sonra process restart gerekir.
- Kullanıcı istatistikleri şimdilik sunucuda değil tarayıcıda tutulur.

Online DB'ye geçiş ancak kullanıcı hesabı, sunucu tarafı ilerleme, canlı yazma,
çoklu bölge güncelleme veya merkezi realtime state gereksinimi oluştuğunda anlamlıdır.

### Bilinirlik modeli

Lig havuzları ve global havuz build sırasında hesaplanır. Runtime her istekte pahalı
sıralama yapmaz. `known`, `less_known`, `obscure` değerleri birbirini dışlar. Legacy
istemciler için `easy`, `medium`, `hard` alanları da artifact'te korunur.

### Günlük oyuncu kararlılığı

Günlük cevaplar kaynak DB'de kalıcıdır. Bir oyuncunun sonraki build'de bilinirlik
puanı değişse bile yayınlanmış günün cevabı değiştirilmez. Takvim global Bilindik
havuzundan deterministik olarak ileri uzatılır.

### Realtime ölçekleme

Lobiler process belleğindedir. Bu nedenle realtime servisi tek worker çalışır. HTTP API
stateless olduğu için yatay ölçeklenebilir. Çok realtime node gerektiğinde sticky veya
lobi koduna göre consistent-hash routing gerekir; Redis şu an mimarinin zorunlu parçası
değildir.

### Ortak site kabuğu

HTML sayfaları header ve footer kopyası taşımaz. `{{SITE_HEADER}}` ve
`{{SITE_FOOTER}}` işaretçileri FastAPI tarafından ortak partial dosyalarıyla değiştirilir.
Bu nedenle topbar veya footer değişikliği tek yerden yapılır. Sayfaları doğrudan diskten
`file://` ile açmak yerine uygulama sunucusu üzerinden çalıştırmak gerekir.

## 11. Temel dosyalar

| Dosya/dizin | Sorumluluk |
|---|---|
| `backend/app/main.py` | FastAPI fabrikası, statik sayfalar, ortak partial render, SEO endpoint'leri |
| `backend/app/db.py` | Salt-okunur SQLite bağlantı/thread havuzu |
| `backend/app/api/` | Health, arama, solo quiz ve günlük oyuncu API'leri |
| `backend/app/realtime/` | Socket.IO lobi ve oyun motoru |
| `data/pipeline/` | Ingest, normalize, repair, derive, validate ve publish |
| `data/pipeline/major_leagues.json` | Güncellenen lig kapsamı ve TTL ayarları |
| `data/sources/legends.json` | Elle bakımlı emekli/efsane oyuncular |
| `frontend/static/index.html` | Günlük ve Solo ana uygulama yüzeyi |
| `frontend/static/partials/` | Ortak header ve footer |
| `frontend/static/js/classic.js` | Günlük oyun istemcisi |
| `frontend/static/js/solo.js` | Solo oyun istemcisi |
| `tests/test_pipeline.py` | Pipeline, havuz, günlük takvim ve API kontrat testleri |
| `tests/test_site_compliance.py` | Sayfa, tema, AdSense ve ortak kabuk kontrolleri |
| `tools/smoke_app.py` | DB, HTTP ve Socket.IO smoke testi |
| `tools/visual_qa.py` | Chrome masaüstü/mobil görsel regresyon testi |
