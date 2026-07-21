from __future__ import annotations

import unittest
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.app.config import settings
from backend.app.daily import daily_today
from backend.app.main import _client_ip, create_app
from backend.app.country_data import country_data


class SecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_forwarded_host_is_not_reflected(self):
        response = self.client.get(
            "/",
            headers={"X-Forwarded-Host": '"><script>alert(1)</script>'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<script>alert(1)</script>", response.text)
        self.assertIn("http://testserver/", response.text)

    def test_untrusted_host_is_rejected(self):
        response = self.client.get("/", headers={"Host": "attacker.example"})
        self.assertEqual(response.status_code, 400)

    def test_production_hosts_are_trusted(self):
        for host in ("careerdle.com", "www.careerdle.com"):
            with self.subTest(host=host):
                response = self.client.get("/api/health", headers={"Host": host})
                self.assertEqual(response.status_code, 200)

    def test_security_headers_are_present(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertIn("camera=()", response.headers["permissions-policy"])

    def test_content_pages_use_nonce_based_adsense_csp(self):
        response = self.client.get("/about")
        self.assertEqual(response.status_code, 200)
        policy = response.headers["content-security-policy"]
        self.assertIn("'strict-dynamic'", policy)
        nonce = __import__("re").search(r"'nonce-([^']+)'", policy)
        self.assertIsNotNone(nonce)
        self.assertIn(f'nonce="{nonce.group(1)}"', response.text)

    def test_public_origin_forces_https_metadata_and_www_redirect(self):
        previous = settings.public_base_url
        settings.public_base_url = "https://careerdle.com"
        try:
            client = TestClient(create_app(), follow_redirects=False)
            response = client.get("/", headers={"Host": "careerdle.com"})
            self.assertEqual(response.status_code, 200)
            self.assertIn('href="https://careerdle.com/"', response.text)
            self.assertIn("max-age=31536000", response.headers["strict-transport-security"])
            redirect = client.get("/archive?from=test", headers={"Host": "www.careerdle.com"})
            self.assertEqual(redirect.status_code, 308)
            self.assertEqual(
                redirect.headers["location"],
                "https://careerdle.com/archive?from=test",
            )
        finally:
            settings.public_base_url = previous

    def test_archive_only_exposes_completed_challenges(self):
        index = self.client.get("/archive")
        self.assertEqual(index.status_code, 200)
        self.assertIn("Günlük futbol", index.text)
        with sqlite3.connect(settings.db_path) as connection:
            completed_date = connection.execute(
                "SELECT MAX(challenge_date) FROM daily_challenges WHERE challenge_date < ?",
                (daily_today().isoformat(),),
            ).fetchone()[0]
        self.assertIsNotNone(completed_date)
        completed = self.client.get(f"/archive/{completed_date}")
        self.assertEqual(completed.status_code, 200)
        self.assertIn("Kariyer zaman çizelgesi", completed.text)
        current = self.client.get(f"/archive/{daily_today().isoformat()}")
        self.assertEqual(current.status_code, 404)

    def test_client_ip_ignores_spoofed_forwarded_for(self):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", b"203.0.113.77")],
            "client": ("127.0.0.9", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
        self.assertEqual(_client_ip(Request(scope)), "127.0.0.9")

    def test_search_query_length_is_bounded(self):
        response = self.client.get("/api/search-player", params={"q": "a" * 81})
        self.assertEqual(response.status_code, 422)

    def test_dynamic_image_urls_are_sanitized_before_html_insertion(self):
        common = self._read("frontend/static/js/common.js")
        classic = self._read("frontend/static/js/classic.js")
        solo = self._read("frontend/static/js/solo.js")
        self.assertIn("function safeImageUrl", common)
        self.assertNotRegex(classic, r'src="\$\{[^}]*\.image_url\s*\|\|')
        self.assertNotRegex(solo, r'src="\$\{[^}]*\.(?:image_url|logo_url)\s*\|\|')

    def test_country_metadata_covers_active_dataset(self):
        database = Path(__file__).resolve().parents[1] / "data" / "football_quiz_v2.db"
        with sqlite3.connect(database) as connection:
            countries = {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT country_of_citizenship FROM players "
                    "WHERE market_value > 0 AND country_of_citizenship IS NOT NULL"
                )
            }
        missing = sorted(country for country in countries if country_data(country) is None)
        self.assertEqual(missing, [])

    @staticmethod
    def _read(relative_path: str) -> str:
        return (Path(__file__).resolve().parents[1] / relative_path).read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
