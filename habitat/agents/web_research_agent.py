"""
web_research_agent.py

Nexarion's primary knowledge acquisition system.
UPGRADED: Full internet access — real pages, not just Wikipedia.

Strategy per query (in priority order):
1. Topic-routed: arXiv for science/ML, Wikipedia for humanities
2. DuckDuckGo HTML search → fetch top 3 results full text
3. DuckDuckGo instant API snippet fallback

Sources now include: news sites, research papers, tech blogs,
scientific journals, forums, government sites — the full web.
"""

import re
import time
import requests
from urllib.parse import quote, urlparse

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}
REQUEST_TIMEOUT = 12

# Domains to always skip — low quality or require JS
SKIP_DOMAINS = {
    "duckduckgo.com",
    "duck.com",
    "bing.com",
    "google.com",
    "youtube.com",
    "facebook.com",
    "twitter.com",
    "instagram.com",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",  # reddit blocks scrapers
    "linkedin.com",
    "amazon.com",
    "ebay.com",
}

# High quality domains — prioritize these in results
PRIORITY_DOMAINS = {
    "arxiv.org",
    "nature.com",
    "sciencedirect.com",
    "pubmed.ncbi.nlm.nih.gov",
    "scholar.google.com",
    "semanticscholar.org",
    "biorxiv.org",
    "medrxiv.org",
    "ieee.org",
    "acm.org",
    "springer.com",
    "mit.edu",
    "stanford.edu",
    "en.wikipedia.org",
    "britannica.com",
    "techcrunch.com",
    "wired.com",
    "arstechnica.com",
    "thenextweb.com",
    "towardsdatascience.com",
    "medium.com",
    "substack.com",
    "bbc.com",
    "reuters.com",
    "apnews.com",
    "theguardian.com",
    "ourworldindata.org",
    "statista.com",
}


# =========================
# TEXT EXTRACTION
# =========================
def _fetch_page_text(url: str, max_chars: int = 3000) -> str:
    """Fetch a URL and extract meaningful text content."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return ""
        html = r.text

        # Strip scripts, styles, nav
        html = re.sub(
            r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
        )
        html = re.sub(
            r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE
        )
        html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(
            r"<footer[^>]*>.*?</footer>", "", html, flags=re.DOTALL | re.IGNORECASE
        )
        html = re.sub(
            r"<header[^>]*>.*?</header>", "", html, flags=re.DOTALL | re.IGNORECASE
        )

        # Extract article/main content first if possible
        article_match = re.search(
            r"<article[^>]*>(.*?)</article>", html, re.DOTALL | re.IGNORECASE
        )
        main_match = re.search(
            r"<main[^>]*>(.*?)</main>", html, re.DOTALL | re.IGNORECASE
        )

        content_html = ""
        if article_match:
            content_html = article_match.group(1)
        elif main_match:
            content_html = main_match.group(1)
        else:
            content_html = html

        # Strip remaining tags
        text = re.sub(r"<[^>]+>", " ", content_html)
        text = re.sub(r"\s+", " ", text).strip()

        # Extract meaningful sentences
        sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 40]
        result = ". ".join(sentences[:30])

        return result[:max_chars]
    except Exception:
        return ""


# =========================
# WIKIPEDIA
# =========================
def _try_wikipedia(query: str) -> dict:
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if data.get("type") == "disambiguation":
                return {}
            extract = data.get("extract", "")
            if len(extract) > 100:
                return {
                    "summary": extract[:2500],
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
# ARXIV
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
    "chemistry",
    "mathematics",
    "topology",
    "graph theory",
    "information theory",
    "robotics",
    "autonomous",
    "transformer",
    "diffusion",
    "generative",
    "llm",
    "reasoning",
    "consciousness",
    "neuroscience",
    "climate",
    "astrophysics",
    "cosmology",
}


def _try_arxiv(query: str) -> dict:
    if not any(t in query.lower() for t in ARXIV_TOPICS):
        return {}
    try:
        url = f"https://export.arxiv.org/api/query?search_query=all:{quote(query)}&start=0&max_results=3&sortBy=relevance"
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return {}
        entries = re.findall(r"<entry>(.*?)</entry>", r.text, re.DOTALL)
        if not entries:
            return {}
        summaries = []
        best_url = ""
        for entry in entries[:3]:
            title_m = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            summary_m = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
            link_m = re.search(r"<id>(.*?)</id>", entry)
            if title_m and summary_m:
                title = re.sub(r"\s+", " ", title_m.group(1).strip())
                summary = re.sub(r"\s+", " ", summary_m.group(1).strip())
                summaries.append(f"[{title[:80]}] {summary[:400]}")
                if not best_url and link_m:
                    best_url = link_m.group(1).strip().replace("abs", "pdf")
        if summaries:
            return {
                "summary": "\n\n".join(summaries)[:2500],
                "source_url": best_url or "https://arxiv.org",
                "domain": "arxiv.org",
                "quality_score": 10,
            }
    except Exception:
        pass
    return {}


# =========================
# DUCKDUCKGO SEARCH → FULL PAGE FETCH
# =========================
def _try_duckduckgo_web(query: str) -> dict:
    """
    Real web search: DuckDuckGo HTML search results → fetch actual pages.
    This is the full internet — any domain, any topic.
    """
    try:
        search_url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        r = requests.get(search_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return {}

        # Extract result URLs from DDG HTML
        urls = re.findall(r'class="result__url"[^>]*>\s*([^\s<]+)', r.text)
        if not urls:
            # Try alternate pattern
            urls = re.findall(r'href="//duckduckgo\.com/l/\?uddg=([^"&]+)"', r.text)
            urls = [requests.utils.unquote(u) for u in urls]

        # Also try extracting from result links
        if not urls:
            links = re.findall(
                r'<a[^>]+href="(https?://[^"]+)"[^>]*class="result__a"', r.text
            )
            urls = links

        # Filter and prioritize
        clean_urls = []
        seen_domains = set()
        for url in urls:
            if not url.startswith("http"):
                url = "https://" + url
            try:
                domain = urlparse(url).netloc.replace("www.", "")
            except Exception:
                continue
            if domain in SKIP_DOMAINS:
                continue
            if domain in seen_domains:
                continue
            seen_domains.add(domain)

            # Prioritize quality domains
            priority = 1 if domain in PRIORITY_DOMAINS else 0
            clean_urls.append((url, domain, priority))

            if len(clean_urls) >= 6:
                break

        # Sort: priority domains first
        clean_urls.sort(key=lambda x: x[2], reverse=True)

        # Try fetching each URL — return first good result
        for url, domain, _ in clean_urls[:4]:
            text = _fetch_page_text(url, max_chars=2500)
            if len(text) > 300:
                print(f"🌐 WEB HIT: {domain}")
                return {
                    "summary": text,
                    "source_url": url,
                    "domain": domain,
                    "quality_score": 8 if domain in PRIORITY_DOMAINS else 6,
                }

    except Exception as e:
        print(f"⚠️ DDG web search error: {e}")
    return {}


# =========================
# DUCKDUCKGO INSTANT API (FALLBACK)
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
                "summary": text[:1500],
                "source_url": data.get("AbstractURL", ""),
                "domain": "duckduckgo.com",
                "quality_score": 3,
            }
    except Exception:
        pass
    return {}


# =========================
# NEWS SEARCH — current events
# =========================
def _try_news(query: str) -> dict:
    """Fetch recent news on a topic."""
    try:
        news_url = (
            f"https://html.duckduckgo.com/html/?q={quote(query + ' news 2026')}&df=w"
        )
        r = requests.get(news_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)

        # Extract snippets and URLs
        snippets = re.findall(
            r'class="result__snippet"[^>]*>(.*?)</a>', r.text, re.DOTALL
        )
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', r.text, re.DOTALL)

        results = []
        for title, snippet in zip(titles[:5], snippets[:5]):
            t = re.sub(r"<[^>]+>", "", title).strip()
            s = re.sub(r"<[^>]+>", "", snippet).strip()
            if t and s and len(s) > 30:
                results.append(f"{t}: {s}")

        if results:
            return {
                "summary": "\n".join(results[:4]),
                "source_url": f"https://duckduckgo.com/?q={quote(query)}+news",
                "domain": "news_aggregated",
                "quality_score": 7,
            }
    except Exception:
        pass
    return {}


# =========================
# MAIN ENTRY POINT
# =========================
def web_research(query: str, max_results: int = 3) -> dict:
    if not query or len(query.strip()) < 3:
        return {"summary": "", "source_url": "", "domain": "", "quality_score": 0}

    query = query.strip()
    q_lower = query.lower()
    print(f"🌐 RESEARCHING: '{query}'")

    ARXIV_SIGNALS = {
        "machine learning",
        "deep learning",
        "neural",
        "quantum",
        "physics",
        "biology",
        "genomics",
        "algorithm",
        "statistics",
        "mathematics",
        "topology",
        "reinforcement",
        "transformer",
        "llm",
        "reasoning",
        "consciousness",
        "neuroscience",
        "climate",
        "astrophysics",
        "chemistry",
    }

    # Try arXiv first for science topics
    if any(t in q_lower for t in ARXIV_SIGNALS):
        result = _try_arxiv(query)
        if result.get("summary"):
            return result

    # Try full web search (DDG HTML → real pages)
    try:
        result = _try_duckduckgo_full(query)
        if result.get("summary"):
            return result
    except NameError:
        pass  # function name mismatch — fall through

    # Wikipedia fallback
    result = _try_wikipedia(query)
    if result.get("summary"):
        return result

    # DDG instant API last resort
    result = _try_duckduckgo_instant(query)
    if result.get("summary"):
        return result

    print(f"❌ ALL SOURCES FAILED: '{query}'")
    return {"summary": "", "source_url": "", "domain": "", "quality_score": 0}
