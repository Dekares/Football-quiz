"""FastAPI uygulaması — stateless HTTP API (yatay ölçeklenen `api` servisi).

Entrypoint: `backend.app.main:app`
Realtime (socket.io) ayrı servistir; bkz. backend/app/realtime/server.py.
"""
from __future__ import annotations

from datetime import date
from html import escape as html_escape
import re
import secrets
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from .archive import get_entry, list_entries, render_archive_cards, render_archive_detail
from .api import classic, health, quiz, search
from .config import settings
from .daily import daily_today
from .db import query
from .ratelimit import RateLimiter


def _public_base_url(request: Request) -> str:
    """Canonical/OG/sitemap için site kökü (scheme + host), sondaki / olmadan.

    Ayar verilmişse onu kullanır; aksi halde TrustedHostMiddleware tarafından
    doğrulanmış istek URL'sini kullanır. Ham proxy başlıkları burada okunmaz.
    """
    candidate = settings.public_base_url or f"{request.url.scheme}://{request.url.netloc}"
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("APP_PUBLIC_BASE_URL must be an absolute HTTP(S) origin")
    if parsed.username or parsed.password or parsed.path not in {"", "/"} \
            or parsed.query or parsed.fragment:
        raise RuntimeError("APP_PUBLIC_BASE_URL must contain only scheme and host")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _is_public_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    if not settings.public_base_url:
        return False
    return urlsplit(settings.public_base_url).scheme == "https"

# Per-IP HTTP hız limiti. Asıl pahalı yol arama autocomplete'i (LIKE tarama);
# insan kullanımı için bol, tarayıcı/abuse için dar.
_api_limiter = RateLimiter(rate_per_sec=15, burst=30)
_STRICT_CSP_PATHS = {"/about", "/methodology", "/contact", "/privacy", "/terms"}


def _client_ip(request: Request) -> str:
    # Proxy header güveni Uvicorn --forwarded-allow-ips seviyesinde kurulmalıdır.
    # Uygulama doğrulanmamış X-Forwarded-For değerini asla yorumlamaz.
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

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET"],
            allow_headers=["Accept", "Content-Type"],
        )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        request.state.csp_nonce = secrets.token_urlsafe(18)
        if settings.public_base_url:
            public = urlsplit(_public_base_url(request))
            if (
                request.url.hostname == "www.careerdle.com"
                and public.hostname != "www.careerdle.com"
            ):
                target = f"{public.scheme}://{public.netloc}{request.url.path}"
                if request.url.query:
                    target += f"?{request.url.query}"
                return RedirectResponse(target, status_code=308)

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
        if (
            request.url.path in _STRICT_CSP_PATHS
            or request.url.path == "/archive"
            or request.url.path.startswith("/archive/")
        ):
            nonce = request.state.csp_nonce
            content_security_policy = (
                "default-src 'self'; base-uri 'none'; object-src 'none'; "
                "frame-ancestors 'none'; form-action 'self'; "
                f"script-src 'nonce-{nonce}' 'unsafe-inline' 'unsafe-eval' "
                "'strict-dynamic' https: http:; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com data:; "
                "img-src 'self' data: https:; connect-src 'self' https:; "
                "frame-src https:; media-src https:; worker-src blob: https:"
            )
        else:
            content_security_policy = (
                "default-src 'self'; base-uri 'self'; object-src 'none'; "
                "frame-ancestors 'none'; form-action 'self'; "
                "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com "
                "https://www.google-analytics.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com data:; "
                "img-src 'self' data: https:; "
                "connect-src 'self' https://www.google-analytics.com "
                "https://region1.google-analytics.com"
            )
        if _is_public_https(request):
            content_security_policy += "; upgrade-insecure-requests"
        response.headers.setdefault("Content-Security-Policy", content_security_policy)
        if settings.enable_hsts and _is_public_https(request):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

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

        def _render_page(
            request: Request,
            filename: str,
            replacements: dict[str, str] | None = None,
        ) -> str:
            html = (static_dir / filename).read_text(encoding="utf-8")
            header = (static_dir / "partials" / "site-header.html").read_text(encoding="utf-8")
            footer = (static_dir / "partials" / "site-footer.html").read_text(encoding="utf-8")
            rendered = (
                html.replace("{{SITE_HEADER}}", header)
                .replace("{{SITE_FOOTER}}", footer)
                .replace("{{BASE_URL}}", _public_base_url(request))
            )
            for placeholder, value in (replacements or {}).items():
                rendered = rendered.replace(placeholder, value)
            nonce = request.state.csp_nonce
            return re.sub(r"<script(?![^>]*\bnonce=)", f'<script nonce="{nonce}"', rendered)

        @app.get("/", include_in_schema=False)
        async def index(request: Request) -> HTMLResponse:
            # {{BASE_URL}} placeholder'ları canonical/OG/JSON-LD için mutlak URL'e
            # doldurulur. index.html asla cache'lenmemeli; aksi halde yeni
            # asset'ler görünmez.
            html = _render_page(request, "index.html")
            return HTMLResponse(
                html,
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

        def _serve_page(
            request: Request,
            filename: str,
            replacements: dict[str, str] | None = None,
        ) -> HTMLResponse:
            html = _render_page(request, filename, replacements)
            return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

        @app.get("/privacy", include_in_schema=False)
        async def privacy(request: Request) -> HTMLResponse:
            return _serve_page(request, "privacy.html")

        @app.get("/about", include_in_schema=False)
        async def about(request: Request) -> HTMLResponse:
            return _serve_page(request, "about.html")

        @app.get("/contact", include_in_schema=False)
        async def contact(request: Request) -> HTMLResponse:
            return _serve_page(request, "contact.html")

        @app.get("/methodology", include_in_schema=False)
        async def methodology(request: Request) -> HTMLResponse:
            return _serve_page(request, "methodology.html")

        @app.get("/terms", include_in_schema=False)
        async def terms(request: Request) -> HTMLResponse:
            return _serve_page(request, "terms.html")

        @app.get("/archive", include_in_schema=False)
        async def archive_index(request: Request) -> HTMLResponse:
            entries = await query(lambda conn: list_entries(conn, daily_today().isoformat()))
            return _serve_page(
                request,
                "archive.html",
                {
                    "{{ARCHIVE_CARDS_TR}}": render_archive_cards(entries, "tr"),
                    "{{ARCHIVE_CARDS_EN}}": render_archive_cards(entries, "en"),
                },
            )

        @app.get("/archive/{challenge_date}", include_in_schema=False)
        async def archive_detail(request: Request, challenge_date: str) -> HTMLResponse:
            try:
                date.fromisoformat(challenge_date)
            except ValueError as exc:
                raise HTTPException(status_code=404) from exc
            result = await query(
                lambda conn: get_entry(conn, challenge_date, daily_today().isoformat())
            )
            if not result:
                raise HTTPException(status_code=404)
            entry, periods = result
            title = html_escape(entry.name)
            description = html_escape(
                f"{entry.name}: {entry.challenge_date} Careerdle Günün Futbolcusu cevabı "
                "ve doğrulanmış kulüp kariyeri."
            )
            return _serve_page(
                request,
                "archive-detail.html",
                {
                    "{{ARCHIVE_TITLE}}": title,
                    "{{ARCHIVE_DESCRIPTION}}": description,
                    "{{ARCHIVE_DATE}}": entry.challenge_date,
                    "{{ARCHIVE_DAY}}": str(entry.day_number),
                    "{{ARCHIVE_DETAIL_TR}}": render_archive_detail(entry, periods, "tr"),
                    "{{ARCHIVE_DETAIL_EN}}": render_archive_detail(entry, periods, "en"),
                },
            )

        @app.get("/robots.txt", include_in_schema=False)
        async def robots(request: Request) -> PlainTextResponse:
            base = _public_base_url(request)
            body = (
                "User-agent: Mediapartners-Google\n"
                "Allow: /\n\n"
                "User-agent: Google-Display-Ads-Bot\n"
                "Allow: /\n\n"
                "User-agent: AdsBot-Google\n"
                "Allow: /\n\n"
                "User-agent: *\n"
                "Allow: /\n"
                "Disallow: /api/\n\n"
                f"Sitemap: {base}/sitemap.xml\n"
            )
            return PlainTextResponse(body, headers={"Cache-Control": "public, max-age=86400"})

        @app.get("/sitemap.xml", include_in_schema=False)
        async def sitemap(request: Request) -> Response:
            base = _public_base_url(request)
            archive_entries = await query(
                lambda conn: list_entries(conn, daily_today().isoformat())
            )
            archive_urls = "".join(
                f"  <url><loc>{base}/archive/{entry.challenge_date}</loc>"
                f"<lastmod>{entry.challenge_date}</lastmod><priority>0.6</priority></url>\n"
                for entry in archive_entries
            )
            xml = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                "  <url>\n"
                f"    <loc>{base}/</loc>\n"
                f"    <lastmod>{date.today().isoformat()}</lastmod>\n"
                "    <changefreq>daily</changefreq>\n"
                "    <priority>1.0</priority>\n"
                "  </url>\n"
                f"  <url><loc>{base}/about</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>\n"
                f"  <url><loc>{base}/methodology</loc><changefreq>weekly</changefreq><priority>0.7</priority></url>\n"
                f"  <url><loc>{base}/archive</loc><changefreq>daily</changefreq><priority>0.8</priority></url>\n"
                f"  <url><loc>{base}/contact</loc><changefreq>yearly</changefreq><priority>0.3</priority></url>\n"
                f"  <url><loc>{base}/privacy</loc><changefreq>yearly</changefreq><priority>0.3</priority></url>\n"
                f"  <url><loc>{base}/terms</loc><changefreq>yearly</changefreq><priority>0.3</priority></url>\n"
                f"{archive_urls}"
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
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "X-Content-Type-Options": "nosniff",
                },
            )

    return app


app = create_app()
