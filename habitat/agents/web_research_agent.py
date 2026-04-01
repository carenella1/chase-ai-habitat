"""
web_research_agent.py

Nexarion's primary knowledge acquisition system.
Replaces the shallow DuckDuckGo instant API with real full-text fetching.

Strategy per query:
1. Try Wikipedia full article (best quality, structured)
2. Try arXiv for scientific/technical topics
3. Try DuckDuckGo HTML search → fetch top result full text
4. Fall back to DuckDuckGo instant API snippet

Each source returns a dict:
  {summary, source_url, domain, quality_score}
"""

import re
import time
import requests
from urllib.parse import quote, urlparse

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NexarionResearch/1.0; educational use)"
}
REQUEST_TIMEOUT = 8


# =========================
# WIKIPEDIA — full sections
# =========================
def _try_wikipedia(query: str) -> dict:
    try:
        # First try exact match
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if data.get("type") == "disambiguation":
                return {}
            extract = data.get("extract", "")
            if len(extract) > 100:
                return {
                    "summary": extract[:2000],
                    "source_url": data.get("content_urls", {})
                    .get("desktop", {})
                    .get("page", ""),
                    "domain": "en.wikipedia.org",
                    "quality_score": 9,
                }
    except Exception:
        pass
    return {}


# =========================
# ARXIV — research papers
# =========================
ARXIV_TOPICS = {
    "machine learning",
    "deep learning",
    "neural network",
    "reinforcement learning",
    "natural language",
    "computer vision",
    "quantum",
    "cryptography",
    "algorithm",
    "optimization",
    "statistics",
    "probability",
    "physics",
    "biology",
    "genomics",
    "economics",
    "finance",
    "trading",
    "market",
    "stock",
    "portfolio",
}


def _is_arxiv_topic(query: str) -> bool:
    q = query.lower()
    return any(t in q for t in ARXIV_TOPICS)


def _try_arxiv(query: str) -> dict:
    if not _is_arxiv_topic(query):
        return {}
    try:
        url = f"https://export.arxiv.org/api/query?search_query=all:{quote(query)}&start=0&max_results=3&sortBy=relevance"
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return {}
        # Parse atom XML minimally
        entries = re.findall(r"<entry>(.*?)</entry>", r.text, re.DOTALL)
        if not entries:
            return {}
        summaries = []
        best_url = ""
        for entry in entries[:2]:
            title_m = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            summary_m = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
            link_m = re.search(r"<id>(.*?)</id>", entry)
            if title_m and summary_m:
                title = title_m.group(1).strip()
                summary = re.sub(r"\s+", " ", summary_m.group(1).strip())
                summaries.append(f"{title}: {summary[:400]}")
            if link_m and not best_url:
                best_url = link_m.group(1).strip()
        if summaries:
            return {
                "summary": " | ".join(summaries)[:2000],
                "source_url": best_url,
                "domain": "arxiv.org",
                "quality_score": 8,
            }
    except Exception:
        pass
    return {}


# =========================
# FULL PAGE FETCH
# =========================
def _extract_text_from_html(html: str, max_chars: int = 2000) -> str:
    """Extract readable text from HTML. No BeautifulSoup dependency."""
    # Remove scripts, styles, nav
    html = re.sub(
        r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
    )
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(
        r"<header[^>]*>.*?</header>", "", html, flags=re.DOTALL | re.IGNORECASE
    )
    html = re.sub(
        r"<footer[^>]*>.*?</footer>", "", html, flags=re.DOTALL | re.IGNORECASE
    )
    # Convert paragraph tags to newlines
    html = re.sub(r"<p[^>]*>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<br[^>]*>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<h[1-6][^>]*>", "\n", html, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", html)
    # Clean whitespace
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 40]
    return " ".join(lines)[:max_chars]


def _fetch_page_text(url: str) -> str:
    """Fetch a URL and extract text content."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return ""
        content_type = r.headers.get("content-type", "")
        if "text/html" not in content_type:
            return ""
        return _extract_text_from_html(r.text)
    except Exception:
        return ""


# =========================
# DUCKDUCKGO HTML SEARCH
# =========================
def _try_duckduckgo_full(query: str) -> dict:
    """
    Search DuckDuckGo HTML (not the instant API), extract top result URLs,
    fetch the actual pages, return the best text found.
    """
    try:
        search_url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        r = requests.get(search_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return {}

        # Extract result URLs from DDG HTML
        urls = re.findall(r'href="(https?://[^"&]+)"', r.text)
        # Filter out DDG's own URLs and ad trackers
        SKIP_DOMAINS = {
            "duckduckgo.com",
            "duck.com",
            "bing.com",
            "google.com",
            "youtube.com",
            "facebook.com",
            "twitter.com",
            "instagram.com",
        }
        clean_urls = []
        seen = set()
        for url in urls:
            domain = urlparse(url).netloc.replace("www.", "")
            if domain in SKIP_DOMAINS:
                continue
            if url in seen:
                continue
            seen.add(url)
            clean_urls.append((url, domain))
            if len(clean_urls) >= 4:
                break

        # Try fetching each, return first good result
        for url, domain in clean_urls:
            text = _fetch_page_text(url)
            if len(text) > 200:
                return {
                    "summary": text[:2000],
                    "source_url": url,
                    "domain": domain,
                    "quality_score": 6,
                }
    except Exception:
        pass
    return {}


# =========================
# DUCKDUCKGO INSTANT API FALLBACK
# =========================
def _try_duckduckgo_instant(query: str) -> dict:
    try:
        url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json&no_redirect=1"
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        data = r.json()
        text = data.get("AbstractText") or ""
        if not text and data.get("RelatedTopics"):
            text = (
                data["RelatedTopics"][0].get("Text", "")
                if data["RelatedTopics"]
                else ""
            )
        if len(text) > 80:
            return {
                "summary": text[:1000],
                "source_url": data.get("AbstractURL", ""),
                "domain": "duckduckgo.com",
                "quality_score": 3,
            }
    except Exception:
        pass
    return {}


# =========================
# DOMAIN ROUTING
# =========================
# For certain topic types, route to the best source directly
DOMAIN_ROUTES = {
    # Finance / markets
    "stock": "arxiv",
    "trading": "arxiv",
    "portfolio": "arxiv",
    "market": "web",
    "investment": "web",
    "economy": "wikipedia",
    "inflation": "wikipedia",
    # Science
    "quantum": "arxiv",
    "machine learning": "arxiv",
    "deep learning": "arxiv",
    "neural": "arxiv",
    "protein": "arxiv",
    "genome": "arxiv",
    # Philosophy / humanities
    "philosophy": "wikipedia",
    "ethics": "wikipedia",
    "epistemology": "wikipedia",
    "consciousness": "wikipedia",
    "history": "wikipedia",
}


def _get_preferred_source(query: str) -> str:
    q = query.lower()
    for keyword, source in DOMAIN_ROUTES.items():
        if keyword in q:
            return source
    return "wikipedia"  # default


# =========================
# MAIN ENTRY POINT
# =========================
def web_research(query: str, max_results: int = 3) -> dict:
    """
    Primary knowledge acquisition function called by the brain loop.
    Tries sources in priority order based on topic type.
    Returns the highest-quality result found.

    Returns: {summary, source_url, domain, quality_score}
    """
    if not query or len(query.strip()) < 3:
        return {"summary": "", "source_url": "", "domain": "", "quality_score": 0}

    query = query.strip()
    preferred = _get_preferred_source(query)

    # Build attempt order based on preferred source
    if preferred == "arxiv":
        attempts = [
            _try_arxiv,
            _try_wikipedia,
            _try_duckduckgo_full,
            _try_duckduckgo_instant,
        ]
    elif preferred == "web":
        attempts = [
            _try_duckduckgo_full,
            _try_wikipedia,
            _try_arxiv,
            _try_duckduckgo_instant,
        ]
    else:  # wikipedia default
        attempts = [
            _try_wikipedia,
            _try_arxiv,
            _try_duckduckgo_full,
            _try_duckduckgo_instant,
        ]

    best = {"summary": "", "source_url": "", "domain": "", "quality_score": 0}

    for attempt_fn in attempts:
        try:
            result = attempt_fn(query)
            if result and result.get("quality_score", 0) > best.get("quality_score", 0):
                best = result
                # If we have a high-quality result, stop early
                if best["quality_score"] >= 8:
                    break
        except Exception as e:
            print(f"⚠️ Research attempt failed ({attempt_fn.__name__}): {e}")
            continue

    if best["summary"]:
        print(
            f"✅ RESEARCH: {best['domain']} (quality={best['quality_score']}) for '{query}'"
        )
    else:
        print(f"❌ RESEARCH: No result for '{query}'")

    return best
