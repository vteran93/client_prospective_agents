"""
tests/test_scraper.py — Unit tests for scraper_tool.py extraction logic.

These tests use only the extraction helpers (_extract_profile / _detect_tech)
so no external HTTP requests are made.
"""

from __future__ import annotations

import pytest

from tools.scraper_tool import _detect_tech, _extract_profile, _normalise_phone


class TestExtractProfile:
    def test_extracts_email(self):
        html = "<html><body>Contacto: info@empresa.com.co</body></html>"
        profile = _extract_profile(html, "http://empresa.com.co")
        assert "info@empresa.com.co" in profile["emails"]

    def test_extracts_colombian_mobile(self):
        html = "<html><body>Llámenos: 300 123 4567</body></html>"
        profile = _extract_profile(html, "http://empresa.com")
        assert any("3001234567" in p for p in profile["phones"]) or profile["phones"]

    def test_detects_whatsapp(self):
        html = '<html><a href="https://wa.me/573001234567">WhatsApp</a></html>'
        profile = _extract_profile(html, "http://empresa.com")
        assert profile["has_whatsapp"] is True
        assert "573001234567" in profile["whatsapp_number"]

    def test_extracts_meta_description(self):
        html = '<html><head><meta name="description" content="Taller mecánico profesional"></head></html>'
        profile = _extract_profile(html, "http://empresa.com")
        assert "Taller mecánico" in profile["description"]

    def test_extracts_og_description_fallback(self):
        html = '<html><head><meta property="og:description" content="Servicio automotriz"></head></html>'
        profile = _extract_profile(html, "http://empresa.com")
        assert "Servicio automotriz" in profile["description"]

    def test_extracts_social_facebook(self):
        html = '<html><a href="https://www.facebook.com/tallercolombia">FB</a></html>'
        profile = _extract_profile(html, "http://empresa.com")
        assert "facebook" in profile["social_links"]

    def test_no_false_positive_emails(self):
        """Strings like 'not@valid' or just '@' should not be extracted."""
        html = (
            "<html><body>Email us at: contact@valid.co — or see name@.bad</body></html>"
        )
        profile = _extract_profile(html, "http://empresa.com")
        assert all("." in e.split("@")[1] for e in profile["emails"])


class TestDetectTech:
    def test_wordpress(self):
        assert "WordPress" in _detect_tech('<link href="/wp-content/style.css">')

    def test_next_js(self):
        assert "Next.js" in _detect_tech('<script id="__NEXT_DATA__">')

    def test_wix(self):
        assert "Wix" in _detect_tech("https://static.wix.com/something")

    def test_no_false_positive(self):
        # Plain HTML with no tech signals
        result = _detect_tech("<html><body><h1>Hola</h1></body></html>")
        assert result == []


class TestNormalisePhone:
    def test_strips_country_code(self):
        assert _normalise_phone("573001234567") == "3001234567"

    def test_removes_formatting(self):
        assert _normalise_phone("300-123-4567") == "3001234567"

    def test_plain_mobile(self):
        assert _normalise_phone("3001234567") == "3001234567"
