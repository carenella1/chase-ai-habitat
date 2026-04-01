"""
tool_selector.py

Fast intent-based tool selection — no LLM call required.
"""

import re


# =========================
# COMMODITY MAP
# =========================
COMMODITY_MAP = {
    "oil": "CL=F",
    "crude": "CL=F",
    "barrel": "CL=F",
    "wti": "CL=F",
    "brent": "BZ=F",
    "petroleum": "CL=F",
    "gold": "GC=F",
    "silver": "SI=F",
    "natural gas": "NG=F",
    "gas futures": "NG=F",
    "copper": "HG=F",
    "wheat": "ZW=F",
    "corn": "ZC=F",
    "soybean": "ZS=F",
    "coffee": "KC=F",
    "cotton": "CT=F",
    "platinum": "PL=F",
    "palladium": "PA=F",
}

KNOWN_TICKERS = {
    "AAPL",
    "MSFT",
    "GOOGL",
    "GOOG",
    "AMZN",
    "META",
    "TSLA",
    "NVDA",
    "AMD",
    "NFLX",
    "UBER",
    "SNAP",
    "SPOT",
    "SHOP",
    "PLTR",
    "COIN",
    "JPM",
    "BAC",
    "GS",
    "MS",
    "WFC",
    "C",
    "V",
    "MA",
    "PYPL",
    "JNJ",
    "PFE",
    "MRNA",
    "ABBV",
    "UNH",
    "XOM",
    "CVX",
    "COP",
    "WMT",
    "TGT",
    "COST",
    "HD",
    "DIS",
    "T",
    "VZ",
    "BA",
    "LMT",
    "GE",
    "CAT",
    "SPY",
    "QQQ",
    "DIA",
    "IWM",
    "VTI",
    "VOO",
    "BTC",
    "ETH",
    "SOL",
    "ADA",
    "DOGE",
    "XRP",
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "CL=F",
    "BZ=F",
    "GC=F",
    "SI=F",
    "NG=F",
    "HG=F",
    "ZW=F",
    "ZC=F",
}


# =========================
# PARAM EXTRACTORS
# =========================
def _extract_market_param(msg):
    msg_lower = msg.lower()
    for phrase in sorted(COMMODITY_MAP.keys(), key=len, reverse=True):
        if phrase in msg_lower:
            return COMMODITY_MAP[phrase]
    dollar = re.findall(r"\$([A-Z]{1,5})", msg.upper())
    if dollar and dollar[0] in KNOWN_TICKERS:
        return dollar[0]
    words = re.findall(r"\b([A-Z]{2,5})\b", msg.upper())
    for word in words:
        if word in KNOWN_TICKERS:
            return word
    return "SPY"


def _extract_calc_param(msg):
    expr = re.search(r"[\d]+(?:\.\d+)?(?:\s*[\+\-\*\/\^]\s*[\d]+(?:\.\d+)?)+", msg)
    if expr:
        return expr.group().strip()
    ci = re.search(
        r"\$?([\d,]+)\s*(?:at|@)\s*([\d.]+)%.*?(\d+)\s*year", msg, re.IGNORECASE
    )
    if ci:
        principal = ci.group(1).replace(",", "")
        rate = ci.group(2)
        years = ci.group(3)
        return f"{principal} * (1 + {rate}/100) ** {years}"
    return None


def _extract_url_param(msg):
    url = re.search(r'https?://[^\s<>"{}|\\^`\[\]]+', msg)
    if url:
        return url.group()
    www = re.search(r"www\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}[^\s]*", msg)
    if www:
        return "https://" + www.group()
    return None


def _extract_code_param(msg):
    block = re.search(r"```(?:python)?\s*\n?(.*?)```", msg, re.DOTALL)
    if block:
        return block.group(1).strip()
    inline = re.search(r"`([^`]*print\([^`]*)`", msg)
    if inline:
        return inline.group(1).strip()
    return None


def _extract_news_param(msg):
    msg_lower = msg.lower()
    patterns = [
        r"(?:latest|recent|current|breaking|today\'s)\s+news\s+(?:about|on|for|regarding)?\s*(.+?)(?:\?|$)",
        r"news\s+(?:about|on|for|regarding)\s+(.+?)(?:\?|$)",
        r"what(?:\'s| is)\s+(?:happening|going on)\s+(?:with|in)?\s*(.+?)(?:\?|$)",
        r"(?:update|updates)\s+(?:on|about)\s+(.+?)(?:\?|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, msg_lower)
        if match:
            query = match.group(1).strip().rstrip("?.,!")
            if len(query) > 2:
                return query
    clean = re.sub(
        r"\b(latest|recent|current|news|update|today)\b", "", msg_lower
    ).strip()
    if clean and len(clean) > 3:
        return clean.rstrip("?.,!")
    return None


def _extract_wiki_param(msg):
    patterns = [
        r"(?:deep dive|tell me everything|full overview|detailed explanation)\s+(?:on|about|of|into)?\s*(.+?)(?:\?|$)",
        r"(?:explain|describe|what is|what are)\s+(.+?)\s+(?:in depth|comprehensively|thoroughly|fully)(?:\?|$)",
    ]
    msg_lower = msg.lower()
    for pattern in patterns:
        match = re.search(pattern, msg_lower)
        if match:
            topic = match.group(1).strip().rstrip("?.,!")
            if len(topic) > 2:
                return topic
    return None


def _extract_search_param(msg):
    """Extract search query — catch-all for any current information request."""
    query = re.sub(
        r"\b(tell me|find me|get me|show me|what is|what are|who is|who are|"
        r"where is|when is|how is|can you|please|right now|currently|today|"
        r"the latest|latest|current|now)\b",
        "",
        msg,
        flags=re.IGNORECASE,
    ).strip()
    query = re.sub(r"\s+", " ", query).strip().rstrip("?.,!")
    return query if len(query) > 2 else msg.strip().rstrip("?.,!")


# =========================
# TOOL INTENT DEFINITIONS
# =========================
TOOL_INTENTS = [
    {
        "tool": "web_fetch",
        "signals": [
            "http://",
            "https://",
            "www.",
            "fetch ",
            "read this url",
            "check this link",
            "visit this page",
        ],
        "negative": [],
        "extractor": _extract_url_param,
        "priority": 10,
    },
    {
        "tool": "python_exec",
        "signals": [
            "```python",
            "```\n",
            "run this code",
            "execute this",
            "run the following",
            "print(",
            "import numpy",
            "import pandas",
            "def ",
            "for i in range",
        ],
        "negative": [],
        "extractor": _extract_code_param,
        "priority": 9,
    },
    {
        "tool": "news_search",
        "signals": [
            "latest news",
            "recent news",
            "news about",
            "news on",
            "what's happening",
            "what is happening",
            "current events",
            "breaking news",
            "today's news",
            "updates on",
            "update on",
            "recently announced",
            "just released",
            "what happened with",
        ],
        "negative": [],
        "extractor": _extract_news_param,
        "priority": 8,
    },
    {
        "tool": "market_data",
        "signals": [
            "price of",
            "current price",
            "stock price",
            "share price",
            "trading at",
            "market price",
            "how much is",
            "what's the price",
            "what is the price",
            "cost of",
            "oil",
            "crude",
            "barrel",
            "barrels",
            "brent",
            "wti",
            "gold price",
            "silver price",
            "natural gas",
            "copper price",
            "commodity",
            "commodities",
            "futures",
            "stock",
            "ticker",
            "nasdaq",
            "crypto",
            "bitcoin",
            "ethereum",
            "find me the",
            "get me the",
            "show me the",
        ],
        "negative": ["news", "latest news", "recent news"],
        "extractor": _extract_market_param,
        "priority": 7,
    },
    {
        "tool": "wiki_deep",
        "signals": [
            "deep dive",
            "tell me everything",
            "full overview",
            "comprehensive",
            "in depth",
            "explain in detail",
            "detailed explanation",
            "thoroughly explain",
        ],
        "negative": [],
        "extractor": _extract_wiki_param,
        "priority": 6,
    },
    {
        "tool": "calculator",
        "signals": [
            "calculate",
            "compute",
            "what is",
            "how much is",
            "solve",
            "percent of",
            "% of",
            "compound interest",
            "divided by",
            "multiplied by",
            "times",
            "square root",
            "sqrt",
        ],
        "negative": ["news", "price of", "stock", "crypto", "oil", "gold"],
        "extractor": _extract_calc_param,
        "priority": 5,
    },
    {
        "tool": "web_search",
        "signals": [
            # Current info
            "right now",
            "currently",
            "today",
            "at the moment",
            "this week",
            "this year",
            "in 2025",
            "in 2026",
            # Entertainment
            "number 1 movie",
            "top movie",
            "box office",
            "now showing",
            "playing now",
            "what movie",
            "best movie",
            "top show",
            "number one",
            "#1",
            # Sports
            "score",
            "standings",
            "who won",
            "game today",
            "match result",
            "tournament",
            "championship",
            "league",
            # People / places / events
            "who is the",
            "who are the",
            "where is",
            "what happened to",
            # Generic lookups
            "tell me about",
            "find me",
            "look up",
            "search for",
            "what is the",
            "who is",
            "where can i",
        ],
        "negative": [
            "price of",
            "stock price",
            "oil",
            "gold",
            "crypto",
            "calculate",
            "latest news",
            "news about",
            "http",
            "www.",
            "```",
        ],
        "extractor": _extract_search_param,
        "priority": 3,  # Lowest — catch-all fires only when nothing else matches
    },
]


# =========================
# MAIN SELECTOR
# =========================
def select_tools_for_message(message, call_llm_fn=None):
    """
    Analyze message and return list of (tool_name, param) to execute.
    call_llm_fn accepted for API compatibility but intentionally unused.
    """
    if not message or len(message.strip()) < 3:
        return []

    msg = message.strip()
    msg_lower = msg.lower()

    best_tool = None
    best_priority = -1
    best_param = None

    for intent in TOOL_INTENTS:
        if any(neg in msg_lower for neg in intent["negative"]):
            continue
        signal_hits = sum(1 for sig in intent["signals"] if sig in msg_lower)
        if signal_hits == 0:
            continue
        effective_priority = intent["priority"] + signal_hits
        if effective_priority > best_priority:
            param = intent["extractor"](msg)
            if param:
                best_tool = intent["tool"]
                best_priority = effective_priority
                best_param = param

    if best_tool and best_param:
        print(f"🔧 TOOL SELECTED: {best_tool}({best_param[:60]})")
        return [(best_tool, best_param)]

    print("🔧 NO TOOL NEEDED")
    return []


def format_tools_for_prompt(tool_results):
    """Format tool results for injection into the Nexarion prompt."""
    from habitat.agents.tool_executor import format_tool_result

    if not tool_results:
        return ""

    lines = ["Real-time information retrieved for this response:"]
    for result in tool_results:
        lines.append(format_tool_result(result))
        lines.append("")

    return "\n".join(lines)
