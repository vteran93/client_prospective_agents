"""
tools/scraper_tool.py — Web scraper with static (httpx+BS4) and JS (Playwright) modes.

Strategy:
  1. Fetch with httpx (fast, no JS).
  2. If response looks JS-heavy OR request fails, fall back to Playwright.
  3. Extract: emails, phones, WhatsApp links, social profiles, meta description.

Output: JSON ScrapedProfile dict.
"""

from __future__ import annotations

import json
import re

import httpx
from bs4 import BeautifulSoup
from pydantic import Field

try:
    from crewai.tools import BaseTool as _BaseTool
except ImportError:  # crewai not installed (e.g. unit tests)

    class _BaseTool:  # type: ignore[no-redef]
        """Minimal stub so extraction helpers are testable without crewai."""

        name: str = ""
        description: str = ""

        def _run(self, *args, **kwargs) -> str:  # noqa: ANN001
            return ""


# ──────────────────────────────────────────────────────────────────
# Regex patterns
# ──────────────────────────────────────────────────────────────────
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+57|57)?[\s\-]?"
    r"(?:3\d{2}[\s\-]?\d{3}[\s\-]?\d{4}"  # mobile
    r"|[1-9]\d{6,7})"  # landline
)
_WHATSAPP_RE = re.compile(r"wa\.me/(\d+)|whatsapp\.com/send\?phone=(\d+)", re.I)
_SOCIAL_RE = {
    "facebook": re.compile(r"facebook\.com/(?!sharer)[^\"'\s/]+"),
    "instagram": re.compile(r"instagram\.com/(?!p/)[^\"'\s/]+"),
    "twitter": re.compile(r"(?:twitter|x)\.com/(?!intent)[^\"'\s/]+"),
    "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[^\"'\s/]+"),
    "tiktok": re.compile(r"tiktok\.com/@[^\"'\s/]+"),
    "youtube": re.compile(r"youtube\.com/(?:channel|@|user)/[^\"'\s/]+"),
}
_JS_SIGNALS = re.compile(
    r"<div id=['\"]root['\"]|__NEXT_DATA__|window\.__nuxt__|ng-app=", re.I
)


class WebScraperTool(_BaseTool):
    name: str = "web_scraper"
    description: str = (
        "Scrape a business website to extract contact data. "
        "Input: a URL string. "
        "Output: JSON ScrapedProfile with emails, phones, has_whatsapp, "
        "whatsapp_number, social_links, description, technology_stack."
    )
    timeout: int = Field(default=15)
    max_html_size: int = Field(default=500_000)  # 500 KB

    def _run(self, url: str) -> str:  # type: ignore[override]
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Step 1 — try static fetch
        html, used_playwright = _fetch_static(url, self.timeout)

        # Step 2 — fall back to Playwright if JS-heavy or fetch failed
        if html is None or (html and _JS_SIGNALS.search(html[:4_000])):
            pw_html = _fetch_playwright(url, self.timeout)
            if pw_html:
                html = pw_html
                used_playwright = True

        if not html:
            return json.dumps(
                {"error": f"Could not fetch {url}", "emails": [], "phones": []}
            )

        profile = _extract_profile(html, url)
        profile["scraper_mode"] = "playwright" if used_playwright else "static"
        return json.dumps(profile, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────────
# Fetch helpers
# ──────────────────────────────────────────────────────────────────


def _fetch_static(url: str, timeout: int) -> tuple[str | None, bool]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; GrowthGuardBot/1.0; +https://growthguard.co)"
        ),
        "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    }
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
        if resp.status_code in (200, 203):
            return resp.text[:500_000], False
        return None, False
    except Exception:  # noqa: BLE001
        return None, False


def _fetch_playwright(url: str, timeout: int) -> str | None:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    locale="es-CO",
                )
                page = ctx.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1_000)
                return page.content()[:500_000]
            finally:
                browser.close()
    except Exception:  # noqa: BLE001
        return None


# ──────────────────────────────────────────────────────────────────
# Extraction
# ──────────────────────────────────────────────────────────────────


def _extract_profile(html: str, base_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)

    emails = list({m.group() for m in _EMAIL_RE.finditer(text)})
    phones = list({_normalise_phone(m.group()) for m in _PHONE_RE.finditer(text)})
    phones = [p for p in phones if len(p) >= 7]

    # WhatsApp
    wa_links = _WHATSAPP_RE.findall(html)
    wa_number = ""
    has_whatsapp = bool(wa_links)
    if wa_links:
        wa_number = wa_links[0][0] or wa_links[0][1]

    # Social links
    social_links: dict[str, str] = {}
    for network, pattern in _SOCIAL_RE.items():
        m = pattern.search(html)
        if m:
            social_links[network] = "https://" + m.group()

    # Meta description
    meta = soup.find("meta", attrs={"name": re.compile("description", re.I)})
    description = meta.get("content", "").strip() if meta else ""  # type: ignore[union-attr]
    if not description:
        og = soup.find("meta", attrs={"property": "og:description"})
        if og:
            description = og.get("content", "").strip()  # type: ignore[union-attr]

    # Technology stack (simple heuristics)
    tech = _detect_tech(html)

    return {
        "emails": emails,
        "phones": phones,
        "has_whatsapp": has_whatsapp,
        "whatsapp_number": wa_number,
        "social_links": social_links,
        "description": description[:500],
        "technology_stack": tech,
    }


def _normalise_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("57") and len(digits) == 12:
        digits = digits[2:]
    return digits


def _detect_tech(html: str) -> list[str]:
    tech: list[str] = []
    checks = {
        "WordPress": "wp-content",
        "Wix": "wix.com",
        "Shopify": "cdn.shopify.com",
        "Webflow": "webflow.com",
        "React": "react",
        "Next.js": "__NEXT_DATA__",
        "Angular": "ng-app",
        "Vue.js": "__vue_app__",
        "Bootstrap": "bootstrap",
    }
    html_lower = html.lower()
    for name, marker in checks.items():
        if marker.lower() in html_lower:
            tech.append(name)
    return tech
