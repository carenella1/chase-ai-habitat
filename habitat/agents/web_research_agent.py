# =============================================================
# CHASE AI HABITAT - WEB RESEARCH AGENT
# Save to: habitat/agents/web_research_agent.py
#
# Uses multiple search strategies with fallbacks:
#   1. DuckDuckGo Instant Answer JSON API (no bot blocking)
#   2. DuckDuckGo HTML with rotating user agents
#   3. Direct Wikipedia API
#
# Test: python habitat/agents/web_research_agent.py
# =============================================================

import requests
import time
import re
import random
from urllib.parse import quote_plus, quote, urlparse


# =============================================================
# CONFIGURATION
# =============================================================

# Rotate user agents to avoid detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
]

BLOCKED_DOMAINS = {
    "duckduckgo.com",
    "duck.com",
    "google.com",
    "google.co",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "snapchat.com",
    "linkedin.com",
    "youtube.com",
    "youtu.be",
    "amazon.com",
    "ebay.com",
    "ad.doubleclick.net",
    "googleadservices.com",
    "pinterest.com",
}

BLOCKED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".zip",
    ".rar",
    ".mp4",
    ".mp3",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".exe",
}

PREFERRED_DOMAINS = {
    "wikipedia.org",
    "britannica.com",
    "arxiv.org",
    "nature.com",
    "science.org",
    "mit.edu",
    "stanford.edu",
    "harvard.edu",
    "medium.com",
    "towardsdatascience.com",
    "wired.com",
    "technologyreview.com",
    "sciencedaily.com",
    "newscientist.com",
    "scientificamerican.com",
    "theatlantic.com",
    "plato.stanford.edu",
}


def get_headers():
    """Return headers with a random user agent each call."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "DNT": "1",
    }


# =============================================================
# SEARCH METHOD 1: DUCKDUCKGO JSON API
# This is DDG's official instant answer API — no HTML scraping,
# no bot detection. Returns structured JSON directly.
# Limitation: returns "abstract" and related topics, not a list
# of web URLs. But it gives us clean text content immediately.
# =============================================================


def search_duckduckgo_api(query, max_chars=2000):
    """
    Use DuckDuckGo's Instant Answer API.
    Returns clean text content directly — no page fetching needed.
    """
    if not query:
        return None

    encoded = quote_plus(query.strip()[:100])
    url = (
        f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
    )

    try:
        response = requests.get(url, headers=get_headers(), timeout=10)

        if response.status_code != 200:
            print(f"DDG API status: {response.status_code}")
            return None

        data = response.json()

        # Build result from available fields
        parts = []

        # Abstract (main summary)
        abstract = data.get("AbstractText", "")
        if abstract and len(abstract) > 100:
            parts.append(abstract)

        # Answer (direct factual answer)
        answer = data.get("Answer", "")
        if answer:
            parts.append(answer)

        # Definition
        definition = data.get("Definition", "")
        if definition:
            parts.append(definition)

        # Related topics text
        related = data.get("RelatedTopics", [])
        for topic in related[:3]:
            if isinstance(topic, dict):
                text = topic.get("Text", "")
                if text and len(text) > 50:
                    parts.append(text)

        if not parts:
            print(f"DDG API: no content for '{query}'")
            return None

        result = " ".join(parts)[:max_chars]
        print(f"DDG API: got {len(result)} chars for '{query}'")
        return result

    except Exception as e:
        print(f"DDG API error: {e}")
        return None


# =============================================================
# SEARCH METHOD 2: DUCKDUCKGO HTML WITH SESSION
# Uses a requests Session with cookies to appear more like a
# real browser, which bypasses most bot detection.
# =============================================================


def search_duckduckgo_html(query, max_results=5):
    """
    Search DuckDuckGo HTML using a persistent session with cookies.
    More reliable than single requests for getting result URLs.
    """
    if not query or len(query.strip()) < 3:
        return []

    session = requests.Session()

    # First visit the homepage to get cookies (acts like a real browser)
    try:
        session.get("https://duckduckgo.com/", headers=get_headers(), timeout=8)
        time.sleep(0.5)
    except Exception:
        pass

    encoded_query = quote_plus(query.strip()[:120])
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}&kl=us-en"

    try:
        response = session.get(url, headers=get_headers(), timeout=12)

        if response.status_code not in (200, 202):
            print(f"DDG HTML status: {response.status_code}")
            return []

        raw_html = response.text

        # Multiple patterns to catch different DDG HTML structures
        patterns = [
            r'<a[^>]+class="[^"]*result__url[^"]*"[^>]*href="([^"]+)"',
            r'<a[^>]+href="(https?://(?!duckduckgo)[^"]+)"[^>]*class="[^"]*result',
            r'href="(https?://[^"&]{20,})"',
        ]

        all_links = []
        for pattern in patterns:
            found = re.findall(pattern, raw_html, re.IGNORECASE)
            all_links.extend(found)

        clean_links = []
        preferred_links = []
        seen = set()

        for link in all_links:
            # Clean DDG redirect URLs
            if "duckduckgo.com/l/?uddg=" in link:
                try:
                    from urllib.parse import unquote

                    link = unquote(link.split("uddg=")[1].split("&")[0])
                except Exception:
                    continue

            try:
                parsed = urlparse(link)
                if not parsed.scheme in ("http", "https"):
                    continue

                domain = parsed.netloc.lower().replace("www.", "")

                if any(blocked in domain for blocked in BLOCKED_DOMAINS):
                    continue

                path_lower = parsed.path.lower()
                if any(path_lower.endswith(ext) for ext in BLOCKED_EXTENSIONS):
                    continue

                if link in seen:
                    continue

                seen.add(link)

                if any(pref in domain for pref in PREFERRED_DOMAINS):
                    preferred_links.append(link)
                else:
                    clean_links.append(link)

                if len(preferred_links) + len(clean_links) >= max_results * 2:
                    break

            except Exception:
                continue

        ranked = preferred_links + clean_links
        print(f"DDG HTML: {len(ranked)} results for '{query}'")
        return ranked[:max_results]

    except Exception as e:
        print(f"DDG HTML error: {e}")
        return []


# =============================================================
# SEARCH METHOD 3: WIKIPEDIA DIRECT SEARCH
# Always works, always returns clean knowledge content.
# Used as the most reliable fallback.
# =============================================================


def search_wikipedia_direct(query, max_chars=2000):
    """
    Search Wikipedia directly using their search API.
    Returns clean article text — no HTML parsing needed.
    """
    if not query:
        return None, None

    try:
        # Step 1: Find the best matching article title
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 3,
            "format": "json",
        }
        headers = {"User-Agent": "Chase-AI-Habitat/1.0 (research tool)"}

        search_resp = requests.get(
            search_url, params=search_params, headers=headers, timeout=8
        )
        search_data = search_resp.json()

        results = search_data.get("query", {}).get("search", [])
        if not results:
            return None, None

        # Get the top result title
        top_title = results[0]["title"]

        # Step 2: Get the article summary
        encoded_title = quote(top_title)
        summary_url = (
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"
        )

        summary_resp = requests.get(summary_url, headers=headers, timeout=8)
        if summary_resp.status_code != 200:
            return None, None

        summary_data = summary_resp.json()
        extract = summary_data.get("extract", "")
        page_url = (
            summary_data.get("content_urls", {}).get("desktop", {}).get("page", "")
        )

        if extract and len(extract) > 100:
            print(f"Wikipedia: found '{top_title}' ({len(extract)} chars)")
            return extract[:max_chars], page_url

        return None, None

    except Exception as e:
        print(f"Wikipedia search error: {e}")
        return None, None


# =============================================================
# PAGE FETCHER
# =============================================================


def fetch_page_content(url, max_chars=4000):
    """
    Fetch and clean content from a web page URL.
    """
    try:
        response = requests.get(
            url, headers=get_headers(), timeout=8, allow_redirects=True
        )

        if response.status_code != 200:
            return None

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return None

        raw_html = response.text

        clean = re.sub(
            r"<script[^>]*>.*?</script>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE
        )
        clean = re.sub(
            r"<style[^>]*>.*?</style>", " ", clean, flags=re.DOTALL | re.IGNORECASE
        )
        clean = re.sub(r"<!--.*?-->", " ", clean, flags=re.DOTALL)
        clean = re.sub(r"<[^>]+>", " ", clean)

        replacements = {
            "&amp;": "&",
            "&nbsp;": " ",
            "&lt;": "<",
            "&gt;": ">",
            "&quot;": '"',
            "&#39;": "'",
            "&mdash;": "-",
            "&ndash;": "-",
        }
        for entity, char in replacements.items():
            clean = clean.replace(entity, char)

        clean = re.sub(r"\s+", " ", clean).strip()

        if len(clean) < 200:
            return None

        return clean[:max_chars]

    except Exception as e:
        print(f"Page fetch error: {type(e).__name__} — {url[:60]}")
        return None


# =============================================================
# LLM SUMMARIZER
# =============================================================


def summarize_with_llm(content, topic, max_chars=600):
    """
    Use local Llama3 to extract key insights from content.
    """
    if not content or not topic:
        return ""

    prompt = f"""You are a research assistant for an AI cognitive system.

Topic: {topic}

Content:
{content[:2500]}

Extract the 2-3 most important, specific insights related to the topic.
Rules:
- Direct and factual only
- No preamble like "the article says" or "according to"
- Max 3 sentences total
- If completely unrelated to topic, reply only: SKIP"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "llama3:latest", "prompt": prompt, "stream": False},
            timeout=45,
        )
        result = response.json().get("response", "").strip()

        if result.upper().startswith("SKIP"):
            return ""

        return result[:max_chars]

    except Exception as e:
        print(f"LLM summarization error: {e}")
        return ""


# =============================================================
# MAIN PIPELINE
# =============================================================


def web_research(topic, max_results=4):
    """
    Main entry point. Tries multiple search strategies in order:
    1. DDG Instant Answer API  (fastest, no bot detection)
    2. DDG HTML with session   (real URLs, page fetching)
    3. Wikipedia direct search (most reliable fallback)

    Returns dict:
        summary    - extracted insight text
        source_url - URL used
        source     - 'web'
        domain     - domain of source
    """
    print(f"WEB RESEARCH: '{topic}'")

    result = {
        "summary": "",
        "source_url": "",
        "source": "web",
        "domain": "",
    }

    if not topic or len(topic.strip()) < 3:
        return result

    # -------------------------------------------------------
    # STRATEGY 1: DuckDuckGo Instant Answer API
    # -------------------------------------------------------
    print("Trying DDG Instant Answer API...")
    api_content = search_duckduckgo_api(topic)

    if api_content and len(api_content) > 150:
        summary = summarize_with_llm(api_content, topic)
        if not summary:
            summary = api_content[:500]

        result["summary"] = summary
        result["source_url"] = f"https://duckduckgo.com/?q={quote_plus(topic)}"
        result["domain"] = "duckduckgo.com"
        print(f"DDG API success: {len(summary)} chars")
        return result

    time.sleep(0.5)

    # -------------------------------------------------------
    # STRATEGY 2: DDG HTML search + page fetch
    # -------------------------------------------------------
    print("Trying DDG HTML search...")
    urls = search_duckduckgo_html(topic, max_results=max_results)

    if urls:
        for url in urls:
            print(f"Fetching: {url[:80]}...")
            content = fetch_page_content(url)

            if content and len(content) > 300:
                summary = summarize_with_llm(content, topic)
                if not summary:
                    summary = content[:500]

                parsed = urlparse(url)
                domain = parsed.netloc.replace("www.", "")

                result["summary"] = summary
                result["source_url"] = url
                result["domain"] = domain
                print(f"DDG HTML success: {domain} ({len(summary)} chars)")
                return result

            time.sleep(0.3)

    time.sleep(0.5)

    # -------------------------------------------------------
    # STRATEGY 3: Wikipedia direct search
    # -------------------------------------------------------
    print("Trying Wikipedia direct search...")
    wiki_content, wiki_url = search_wikipedia_direct(topic)

    if wiki_content:
        summary = summarize_with_llm(wiki_content, topic)
        if not summary:
            summary = wiki_content[:500]

        result["summary"] = summary
        result["source_url"] = (
            wiki_url or f"https://en.wikipedia.org/wiki/{quote(topic)}"
        )
        result["domain"] = "wikipedia.org"
        print(f"Wikipedia success: {len(summary)} chars")
        return result

    print(f"All strategies exhausted for '{topic}'")
    return result


# =============================================================
# STANDALONE TEST
# python habitat/agents/web_research_agent.py
# =============================================================

if __name__ == "__main__":
    test_topics = [
        "artificial intelligence emergent behavior",
        "quantum consciousness theories",
        "systems thinking complexity",
    ]

    for topic in test_topics:
        print("\n" + "=" * 60)
        result = web_research(topic)
        print(f"\nTopic:   {topic}")
        print(f"Source:  {result['domain']}")
        print(f"URL:     {result['source_url'][:80]}")
        print(f"Summary:\n{result['summary']}")
        print()
        time.sleep(1)
