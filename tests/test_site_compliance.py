from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "frontend" / "static"
PUBLISHER = "ca-pub-5823826038472901"
PAGES = {
    "index.html": "/",
    "about.html": "/about",
    "contact.html": "/contact",
    "privacy.html": "/privacy",
    "methodology.html": "/methodology",
    "terms.html": "/terms",
}


def read(name: str) -> str:
    raw = (STATIC / name).read_text(encoding="utf-8")
    if name.endswith(".html"):
        header = (STATIC / "partials" / "site-header.html").read_text(encoding="utf-8")
        footer = (STATIC / "partials" / "site-footer.html").read_text(encoding="utf-8")
        raw = raw.replace("{{SITE_HEADER}}", header).replace("{{SITE_FOOTER}}", footer)
    return raw


def words(raw: str) -> int:
    text = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


class SiteComplianceTests(unittest.TestCase):
    def test_public_pages_have_publisher_privacy_and_canonical_signals(self):
        for filename, route in PAGES.items():
            with self.subTest(filename=filename):
                raw = read(filename)
                self.assertIn(
                    f'<meta name="google-adsense-account" content="{PUBLISHER}">',
                    raw,
                )
                self.assertIn('<meta name="referrer" content="strict-origin-when-cross-origin">', raw)
                self.assertIn('<script src="/static/js/privacy-consent.js"></script>', raw)
                self.assertIn(f'href="{{{{BASE_URL}}}}{route}"', raw)
                self.assertIn('href="/privacy"', raw)
                self.assertIn('href="/terms"', raw)
                self.assertIn('href="/methodology"', raw)

    def test_consent_defaults_precede_adsense(self):
        index = read("index.html")
        self.assertLess(
            index.index("/static/js/privacy-consent.js"),
            index.index("pagead2.googlesyndication.com"),
        )
        consent = read("js/privacy-consent.js")
        for key in (
            "ad_storage",
            "analytics_storage",
            "ad_user_data",
            "ad_personalization",
        ):
            self.assertRegex(consent, rf"{key}:\s*'denied'")
        self.assertIn("googlefc.showRevocationMessage", consent)

    def test_site_has_substantial_visible_publisher_content(self):
        self.assertIn('class="editorial-content"', read("index.html"))
        self.assertGreater(words(read("index.html")), 850)
        self.assertGreater(words(read("about.html")), 600)
        self.assertGreater(words(read("methodology.html")), 900)
        self.assertGreater(words(read("terms.html")), 650)
        self.assertGreater(words(read("privacy.html")), 1000)

    def test_adsense_identity_is_consistent(self):
        index = read("index.html")
        self.assertIn(f"client={PUBLISHER}", index)
        main = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("google.com, pub-5823826038472901, DIRECT, f08c47fec0942fa0", main)
        self.assertIn('"/methodology"', main)
        self.assertIn('"/terms"', main)

    def test_decorative_orbs_are_not_in_markup(self):
        self.assertNotIn('class="orb ', read("index.html"))

    def test_solo_has_league_and_recognition_selection(self):
        index = read("index.html")
        solo = read("js/solo.js")
        for marker in (
            'id="solo-league-select"',
            'data-recognition="known"',
            'data-recognition="less_known"',
            'data-recognition="obscure"',
            'id="solo-start-btn"',
        ):
            self.assertIn(marker, index)
        self.assertIn("/api/quiz/options", solo)
        self.assertIn("recognition=", solo)
        self.assertIn("league=", solo)
        self.assertIn("effectiveRecognition", solo)
        self.assertIn("uses_recognition", solo)
        self.assertIn("Dünya Karması", read("js/common.js"))
        for marker in (
            "solo-result-modal",
            "rm-quick-facts",
            "rm-pool-line",
            "closeQuizModalAndChangeSelection",
        ):
            self.assertIn(marker, solo)

    def test_brand_logo_and_career_path_are_consistent(self):
        logo = STATIC / "img" / "logo.png"
        light_logo = STATIC / "img" / "logo-koyu.png"
        self.assertTrue(logo.is_file())
        self.assertTrue(light_logo.is_file())
        self.assertGreater(logo.stat().st_size, 10_000)
        self.assertGreater(light_logo.stat().st_size, 10_000)
        for filename in PAGES:
            with self.subTest(filename=filename):
                raw = read(filename)
                self.assertIn("/static/img/logo.png", raw)
                self.assertNotIn("/static/img/icon.png", raw)
                self.assertNotIn('<span class="brand-mark">C</span>', raw)
        css = read("css/app.css")
        self.assertIn(".quiz-timeline::before", css)
        self.assertIn("border: 2px solid #fff;", css)
        self.assertIn("background: var(--vermilion);", css)

    def test_public_pages_use_one_shared_header_and_footer(self):
        header = read("partials/site-header.html")
        footer = read("partials/site-footer.html")
        self.assertIn('class="site-nav"', header)
        self.assertIn('class="site-footer"', footer)
        for filename in PAGES:
            with self.subTest(filename=filename):
                raw = (STATIC / filename).read_text(encoding="utf-8")
                self.assertEqual(raw.count("{{SITE_HEADER}}"), 1)
                self.assertEqual(raw.count("{{SITE_FOOTER}}"), 1)
                self.assertNotIn('class="site-nav"', raw)
                self.assertNotIn('class="site-footer"', raw)


if __name__ == "__main__":
    unittest.main()
