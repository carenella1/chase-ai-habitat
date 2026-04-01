"""
domain_knowledge.py

On-demand domain expertise for Nexarion.
When Chase asks Nexarion to work on a specific domain (trading, medicine,
law, engineering, etc.), this module rapidly acquires and consolidates
real knowledge from multiple sources into a structured briefing.

This is the bridge between "Nexarion has been thinking about things"
and "Nexarion can actually help with this specific problem."

Usage in run_ui.py (chat route):
    from habitat.agents.domain_knowledge import get_domain_briefing
    briefing = get_domain_briefing("stock market trading", depth=3)
"""

import re
import time
import requests
from urllib.parse import quote

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NexarionResearch/1.0)"}

# =========================
# DOMAIN DETECTION
# =========================
DOMAIN_MAP = {
    # Finance
    "stock": "stock market trading and financial markets",
    "trading": "algorithmic trading and market microstructure",
    "crypto": "cryptocurrency and blockchain technology",
    "invest": "investment analysis and portfolio theory",
    "hedge": "hedge funds and alternative investments",
    "option": "options trading and derivatives",
    "forex": "foreign exchange markets",
    # Technology
    "machine learning": "machine learning and artificial intelligence",
    "deep learning": "deep neural networks",
    "cybersecurity": "cybersecurity and information security",
    "blockchain": "blockchain technology and distributed systems",
    "quantum": "quantum computing",
    # Medicine / Biology
    "cancer": "oncology and cancer treatment",
    "drug": "pharmacology and drug development",
    "genome": "genomics and genetic engineering",
    "neuroscience": "neuroscience and brain function",
    "clinical": "clinical medicine and evidence-based practice",
    # Law
    "contract": "contract law and legal agreements",
    "patent": "intellectual property and patent law",
    "regulation": "regulatory compliance and law",
    # Engineering
    "civil": "civil engineering and infrastructure",
    "electrical": "electrical engineering",
    "mechanical": "mechanical engineering",
    # Social sciences
    "psychology": "psychology and human behavior",
    "economics": "economics and macroeconomic theory",
    "sociology": "sociology and social systems",
    "politics": "political science and governance",
}


def detect_domain(query: str) -> str:
    """Map a user query to the most relevant domain description."""
    q = query.lower()
    for keyword, domain in DOMAIN_MAP.items():
        if keyword in q:
            return domain
    return query  # use query directly if no mapping


# =========================
# MULTI-SOURCE ACQUISITION
# =========================
def _fetch_wikipedia_sections(topic: str) -> list:
    """Get multiple Wikipedia sections for depth."""
    results = []
    # Get the summary
    try:
        r = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(topic)}",
            headers=HEADERS,
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("type") != "disambiguation" and data.get("extract"):
                results.append(
                    {
                        "source": "Wikipedia",
                        "url": data.get("content_urls", {})
                        .get("desktop", {})
                        .get("page", ""),
                        "content": data["extract"][:1500],
                    }
                )
    except Exception:
        pass

    # Get related topics
    subtopics = _generate_subtopics(topic)
    for subtopic in subtopics[:3]:
        try:
            time.sleep(0.3)  # be polite
            r = requests.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(subtopic)}",
                headers=HEADERS,
                timeout=6,
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("type") != "disambiguation" and data.get("extract", ""):
                    extract = data["extract"]
                    if len(extract) > 100:
                        results.append(
                            {
                                "source": f"Wikipedia ({subtopic})",
                                "url": data.get("content_urls", {})
                                .get("desktop", {})
                                .get("page", ""),
                                "content": extract[:800],
                            }
                        )
        except Exception:
            continue

    return results


def _generate_subtopics(topic: str) -> list:
    """Generate related subtopics for deeper coverage."""
    # Static subtopic expansions for key domains
    SUBTOPIC_EXPANSIONS = {
        "stock market trading": [
            "technical analysis",
            "fundamental analysis",
            "market sentiment",
            "risk management trading",
        ],
        "algorithmic trading": [
            "high frequency trading",
            "quantitative finance",
            "backtesting",
            "market making",
        ],
        "machine learning": [
            "gradient descent",
            "neural network",
            "overfitting",
            "cross-validation",
        ],
        "quantum computing": [
            "quantum entanglement",
            "qubit",
            "quantum algorithm",
            "superposition",
        ],
        "blockchain": [
            "consensus mechanism",
            "smart contract",
            "distributed ledger",
            "cryptographic hash",
        ],
        "psychology": [
            "cognitive bias",
            "behavioral economics",
            "decision making",
            "motivation",
        ],
        "neuroscience": [
            "synaptic plasticity",
            "neuroplasticity",
            "prefrontal cortex",
            "dopamine",
        ],
        "economics": [
            "supply and demand",
            "monetary policy",
            "game theory",
            "behavioral economics",
        ],
    }
    topic_lower = topic.lower()
    for key, subtopics in SUBTOPIC_EXPANSIONS.items():
        if key in topic_lower or topic_lower in key:
            return subtopics
    # Generic expansion
    words = topic.split()
    return (
        [f"{words[0]} theory", f"{words[0]} applications", f"{topic} research"]
        if words
        else []
    )


def _fetch_arxiv_papers(topic: str) -> list:
    """Get recent research paper abstracts from arXiv."""
    results = []
    try:
        url = f"https://export.arxiv.org/api/query?search_query=all:{quote(topic)}&start=0&max_results=5&sortBy=relevance"
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return results
        entries = re.findall(r"<entry>(.*?)</entry>", r.text, re.DOTALL)
        for entry in entries[:3]:
            title_m = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            summary_m = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
            link_m = re.search(r'href="(https://arxiv[^"]+)"', entry)
            if title_m and summary_m:
                title = re.sub(r"\s+", " ", title_m.group(1).strip())
                summary = re.sub(r"\s+", " ", summary_m.group(1).strip())
                results.append(
                    {
                        "source": f"arXiv: {title[:60]}",
                        "url": link_m.group(1) if link_m else "https://arxiv.org",
                        "content": summary[:600],
                    }
                )
    except Exception:
        pass
    return results


# =========================
# BRIEFING COMPILER
# =========================
def get_domain_briefing(query: str, depth: int = 3) -> str:
    """
    Compile a structured knowledge briefing on a domain.

    depth=1: Wikipedia summary only (fast, ~5s)
    depth=2: Wikipedia + subtopics (~15s)
    depth=3: Wikipedia + subtopics + arXiv papers (~25s)

    Returns a formatted string ready to inject into a prompt.
    """
    domain = detect_domain(query)
    print(f"📚 DOMAIN BRIEFING: '{domain}' (depth={depth})")

    all_knowledge = []

    # Layer 1: Wikipedia
    wiki_results = _fetch_wikipedia_sections(domain)
    all_knowledge.extend(wiki_results)

    # Layer 3: arXiv (only for technical/scientific queries)
    if depth >= 3:
        arxiv_results = _fetch_arxiv_papers(domain)
        all_knowledge.extend(arxiv_results)

    if not all_knowledge:
        return ""

    # Compile into a structured briefing
    lines = [f"Domain knowledge on: {domain}"]
    lines.append("=" * 50)

    for i, item in enumerate(all_knowledge[:6]):
        lines.append(f"\n[{item['source']}]")
        lines.append(item["content"])

    briefing = "\n".join(lines)
    print(f"📚 BRIEFING COMPILED: {len(all_knowledge)} sources, {len(briefing)} chars")
    return briefing[:4000]  # cap at 4000 chars to stay within prompt budget


# =========================
# DOMAIN DETECTION FROM CHAT
# =========================
TASK_SIGNALS = [
    "help me",
    "help with",
    "i need",
    "can you",
    "analyze",
    "research",
    "explain",
    "tell me about",
    "how do i",
    "what is",
    "strategy for",
    "build",
    "create",
    "solve",
    "figure out",
    "understand",
    "learn about",
]


def detect_task_domain(message: str) -> str:
    """
    Detect if a chat message is asking Nexarion to work on a specific domain.
    Returns domain string if detected, empty string if it's just conversation.
    """
    msg = message.lower().strip()

    # Check for task signals
    has_task_signal = any(signal in msg for signal in TASK_SIGNALS)
    if not has_task_signal:
        return ""

    # Check for domain keywords
    for keyword, domain in DOMAIN_MAP.items():
        if keyword in msg:
            return domain

    return ""
