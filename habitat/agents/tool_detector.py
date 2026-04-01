"""
tool_detector.py

Analyzes a user message and decides which tool(s) Nexarion should
invoke before generating its response.

Design principles:
- Fast: no LLM call for detection, pure pattern matching
- Conservative: only triggers when the need is clear
- Transparent: returns a list of (tool_name, param) tuples

The detector runs BEFORE the LLM call in api_chat. If tools are
detected, they execute, results are formatted, and the formatted
results are injected into the Nexarion prompt as context.

This means Nexarion gets real data and responds to it naturally —
it doesn't need to know it "used a tool", it just has better information.
"""

import re
from urllib.parse import urlparse


# =========================
# STOCK TICKER DETECTION
# =========================
# Common tickers that might appear in conversation
KNOWN_TICKERS = {
    # Major stocks
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
    "LYFT",
    "SNAP",
    "TWTR",
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
    "CVS",
    "XOM",
    "CVX",
    "BP",
    "SHEL",
    "COP",
    "BRK",
    "BRKB",
    "WMT",
    "TGT",
    "COST",
    "HD",
    "LOW",
    "DIS",
    "CMCSA",
    "T",
    "VZ",
    "TMUS",
    "BA",
    "LMT",
    "RTX",
    "GE",
    "CAT",
    "DE",
    "SPY",
    "QQQ",
    "DIA",
    "IWM",
    "VTI",
    "VOO",
    # Crypto
    "BTC",
    "ETH",
    "SOL",
    "ADA",
    "DOT",
    "LINK",
    "MATIC",
    "DOGE",
    "XRP",
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    # Indices (yfinance format)
    "^GSPC",
    "^DJI",
    "^IXIC",
    "^VIX",
}

# Market intent keywords
MARKET_KEYWORDS = [
    "stock",
    "price",
    "share",
    "ticker",
    "market",
    "trading",
    "invest",
    "portfolio",
    "nasdaq",
    "nyse",
    "s&p",
    "dow",
    "crypto",
    "bitcoin",
    "ethereum",
    "coin",
    "bull",
    "bear",
    "rally",
    "dip",
    "buy",
    "sell",
    "earnings",
    "dividend",
    "p/e",
    "market cap",
    "volume",
    "chart",
    "technical analysis",
    "fundamental",
    "valuation",
]

# Math/calculation keywords
MATH_KEYWORDS = [
    "calculate",
    "compute",
    "what is",
    "how much is",
    "solve",
    "sqrt",
    "square root",
    "percent",
    "percentage",
    "%",
    "multiply",
    "divide",
    "add up",
    "total",
    "average",
    "mean",
    "compound",
    "interest rate",
    "return on",
    "roi",
    "profit",
    "loss",
    "break even",
]

# Code execution keywords
CODE_KEYWORDS = [
    "run this",
    "execute",
    "run the code",
    "what does this code",
    "python",
    "script",
    "calculate with code",
    "simulate",
    "backtest",
    "analyze this data",
    "plot",
    "graph the",
]

# News keywords
NEWS_KEYWORDS = [
    "latest news",
    "recent news",
    "what happened with",
    "news about",
    "current events",
    "what's happening",
    "today's news",
    "breaking",
    "recently announced",
    "just released",
    "update on",
]

# URL pattern
URL_PATTERN = re.compile(
    r'https?://[^\s<>"{}|\\^`\[\]]+' r"|www\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}[^\s]*"
)


def _extract_ticker(text: str) -> str | None:
    """Try to extract a stock ticker from the message."""
    words = text.upper().split()

    # Direct ticker match
    for word in words:
        clean = re.sub(r"[^A-Z\-\^]", "", word)
        if clean in KNOWN_TICKERS:
            return clean

    # Pattern: $TICKER or ticker in parentheses
    ticker_pattern = re.findall(r"\$([A-Z]{1,5})", text.upper())
    if ticker_pattern:
        return ticker_pattern[0]

    parens_pattern = re.findall(r"\(([A-Z]{2,5})\)", text.upper())
    if parens_pattern:
        candidate = parens_pattern[0]
        if candidate in KNOWN_TICKERS or len(candidate) <= 4:
            return candidate

    return None


def _extract_url(text: str) -> str | None:
    """Extract a URL from the message if present."""
    urls = URL_PATTERN.findall(text)
    return urls[0] if urls else None


def _extract_math_expression(text: str) -> str | None:
    """Try to extract a mathematical expression."""
    # Look for explicit math expressions
    patterns = [
        r"(?:calculate|compute|what is|solve)\s+([0-9+\-*/().\s^%sqrtpilogcossinabs]+)",
        r"([0-9]+(?:\.[0-9]+)?\s*[\+\-\*\/\^]\s*[0-9]+(?:\.[0-9]+)?(?:\s*[\+\-\*\/\^]\s*[0-9]+(?:\.[0-9]+)?)*)",
    ]
    text_lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            expr = match.group(1).strip()
            if len(expr) > 2 and any(c.isdigit() for c in expr):
                return expr
    return None


def _extract_code_block(text: str) -> str | None:
    """Extract code from markdown code blocks."""
    # Look for ```python ... ``` or ``` ... ```
    code_block = re.search(r"```(?:python)?\s*\n?(.*?)```", text, re.DOTALL)
    if code_block:
        return code_block.group(1).strip()
    return None


def _extract_news_query(text: str) -> str | None:
    """Extract what topic to search news for."""
    text_lower = text.lower()
    patterns = [
        r"(?:latest|recent|current|today\'s|breaking)\s+news\s+(?:about|on|for)?\s+(.+?)(?:\?|$)",
        r"news\s+(?:about|on|for)\s+(.+?)(?:\?|$)",
        r"what(?:\'s| is)\s+happening\s+(?:with|to)?\s+(.+?)(?:\?|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            query = match.group(1).strip().rstrip("?.,!")
            if len(query) > 3:
                return query
    return None


# =========================
# MAIN DETECTOR
# =========================
def detect_tools(message: str) -> list[tuple[str, str]]:
    """
    Analyze a message and return list of (tool_name, param) to execute.
    Order matters — tools will execute in this order.

    Returns empty list if no tools needed (most messages).
    """
    tools = []
    msg = message.strip()
    msg_lower = msg.lower()

    # 1. URL fetch — highest priority if URL present
    url = _extract_url(msg)
    if url:
        tools.append(("web_fetch", url))
        return tools  # URL fetch is usually the whole intent

    # 2. Code execution — explicit code block
    code = _extract_code_block(msg)
    if code:
        tools.append(("python_exec", code))

    # 3. Market data — ticker or market keywords
    if any(kw in msg_lower for kw in MARKET_KEYWORDS):
        ticker = _extract_ticker(msg)
        if ticker:
            tools.append(("market_data", ticker))
        elif any(kw in msg_lower for kw in ["market", "s&p", "nasdaq", "dow"]):
            # Default to SPY if no specific ticker
            tools.append(("market_data", "SPY"))

    # 4. Calculator — math expressions
    if any(kw in msg_lower for kw in MATH_KEYWORDS) and not tools:
        expr = _extract_math_expression(msg)
        if expr:
            tools.append(("calculator", expr))

    # 5. News search — explicit news request
    if any(kw in msg_lower for kw in NEWS_KEYWORDS):
        query = _extract_news_query(msg)
        if query:
            tools.append(("news_search", query))

    # 6. Deep Wikipedia — "tell me everything about" / "deep dive"
    deep_signals = [
        "deep dive",
        "tell me everything",
        "full overview",
        "comprehensive",
        "in depth",
        "detailed explanation of",
    ]
    if any(sig in msg_lower for sig in deep_signals) and not tools:
        # Extract the subject — word after the signal
        for sig in deep_signals:
            if sig in msg_lower:
                after = msg_lower.split(sig)[-1].strip()
                # Take first meaningful noun phrase
                words = [w.strip("?.,!") for w in after.split() if len(w) > 3]
                if words:
                    topic = " ".join(words[:3])
                    tools.append(("wiki_deep", topic))
                    break

    return tools[:3]  # Cap at 3 tools per message


def format_tools_for_prompt(tool_results: list[dict]) -> str:
    """
    Format all tool results into a block for injection into the prompt.
    """
    from habitat.agents.tool_executor import format_tool_result

    if not tool_results:
        return ""

    lines = ["Real-time information retrieved for this response:"]
    for result in tool_results:
        lines.append(format_tool_result(result))
        lines.append("")

    return "\n".join(lines)
