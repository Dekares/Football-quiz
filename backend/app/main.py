"""FastAPI uygulaması — stateless HTTP API (yatay ölçeklenen `api` servisi).

Entrypoint: `backend.app.main:app`
Realtime (socket.io) ayrı servistir; bkz. backend/app/realtime/server.py.
"""
from __future__ import annotations

from datetime import date

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from .api import classic, health, quiz, search
from .config import settings
from .ratelimit import RateLimiter


def _public_base_url(request: Request) -> str:
    """Canonical/OG/sitemap için site kökü (scheme + host), sondaki / olmadan.

    Ayar verilmişse onu kullanır; aksi halde isteği reverse-proxy başlıklarından
    türetir (Render TLS'i proxy'de sonlandırır → X-Forwarded-Proto=https).
    """
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    )
    return f"{proto}://{host}"

# Per-IP HTTP hız limiti. Asıl pahalı yol arama autocomplete'i (LIKE tarama);
# insan kullanımı için bol, tarayıcı/abuse için dar.
_api_limiter = RateLimiter(rate_per_sec=15, burst=30)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RevalidateStaticFiles(StaticFiles):
    """Statikleri her zaman doğrulatır (ETag/Last-Modified ile 304).

    İçerik-hash'li URL kullanmadığımız için ``no-cache`` ile tarayıcının her
    yüklemede yeniden doğrulamasını sağlıyoruz → deploy sonrası bayat JS/CSS
    sorunu olmaz; değişmeyen dosyalar yine 304 döner (ucuz). Production'da
    statikler CDN'e taşınınca bu yol kullanılmaz (APP_SERVE_STATIC=false).
    """

    def file_response(self, *args, **kwargs) -> Response:
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


def create_app() -> FastAPI:
    app = FastAPI(
        title="Careerdle API",
        docs_url="/api/docs" if settings.enable_docs else None,
        openapi_url="/api/openapi.json" if settings.enable_docs else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _rate_limit(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path != "/api/health":
            if not _api_limiter.allow(_client_ip(request)):
                return JSONResponse({"detail": "rate_limited"}, status_code=429)
        return await call_next(request)

    for module in (health, search, quiz, classic):
        app.include_router(module.router)

    if settings.serve_static:
        static_dir = settings.static_dir
        app.mount("/static", RevalidateStaticFiles(directory=static_dir), name="static")

        @app.get("/", include_in_schema=False)
        async def index(request: Request) -> HTMLResponse:
            # {{BASE_URL}} placeholder'ları canonical/OG/JSON-LD için mutlak URL'e
            # doldurulur. index.html asla cache'lenmemeli; aksi halde yeni
            # asset'ler görünmez.
            html = (static_dir / "index.html").read_text(encoding="utf-8")
            html = html.replace("{{BASE_URL}}", _public_base_url(request))
            return HTMLResponse(
                html,
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

        @app.get("/robots.txt", include_in_schema=False)
        async def robots(request: Request) -> PlainTextResponse:
            base = _public_base_url(request)
            body = (
                "User-agent: *\n"
                "Allow: /\n"
                "Disallow: /api/\n\n"
                f"Sitemap: {base}/sitemap.xml\n"
            )
            return PlainTextResponse(body, headers={"Cache-Control": "public, max-age=86400"})

        @app.get("/sitemap.xml", include_in_schema=False)
        async def sitemap(request: Request) -> Response:
            base = _public_base_url(request)
            xml = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                "  <url>\n"
                f"    <loc>{base}/</loc>\n"
                f"    <lastmod>{date.today().isoformat()}</lastmod>\n"
                "    <changefreq>daily</changefreq>\n"
                "    <priority>1.0</priority>\n"
                "  </url>\n"
                "</urlset>\n"
            )
            return Response(
                xml,
                media_type="application/xml",
                headers={"Cache-Control": "public, max-age=3600"},
            )

        @app.get("/ads.txt", include_in_schema=False)
        async def ads_txt() -> PlainTextResponse:
            # Google AdSense yetkili satıcı doğrulaması (publisher ca-pub-5823826038472901).
            return PlainTextResponse(
                "google.com, pub-5823826038472901, DIRECT, f08c47fec0942fa0\n",
                headers={"Cache-Control": "public, max-age=86400"},
            )

    return app


app = create_app()
