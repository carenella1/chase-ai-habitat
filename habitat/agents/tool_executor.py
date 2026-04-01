"""
tool_executor.py

Nexarion's tool system — the bridge between knowledge and capability.

Current tools:
- web_fetch    — fetch and extract text from any URL
- python_exec  — execute Python code safely, return output
- market_data  — get live stock/crypto/commodity prices
- calculator   — evaluate mathematical expressions safely
- wiki_deep    — fetch full Wikipedia article
- news_search  — search for recent news on a topic
- web_search   — general web search (catch-all for current info)
"""

import re
import json
import time
import traceback
import requests
from urllib.parse import quote, urlparse, unquote

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NexarionTools/1.0)"}
REQUEST_TIMEOUT = 10


# =========================
# WEB FETCH
# =========================
def tool_web_fetch(url: str) -> dict:
    try:
        if not url.startswith("http"):
            url = "https://" + url
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}", "content": ""}
        html = r.text
        html = re.sub(
            r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
        )
        html = re.sub(
            r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE
        )
        html = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", html).strip()
        lines = [l.strip() for l in text.split(".") if len(l.strip()) > 40]
        content = ". ".join(lines[:30])
        domain = urlparse(url).netloc.replace("www.", "")
        return {
            "url": url,
            "domain": domain,
            "content": content[:3000],
            "length": len(content),
        }
    except Exception as e:
        return {"error": str(e), "content": ""}


# =========================
# PYTHON CODE EXECUTION
# =========================
def tool_python_exec(code: str) -> dict:
    import io, sys, math, statistics

    safe_builtins = {
        "print": print,
        "range": range,
        "len": len,
        "sum": sum,
        "min": min,
        "max": max,
        "abs": abs,
        "round": round,
        "sorted": sorted,
        "enumerate": enumerate,
        "zip": zip,
        "map": map,
        "filter": filter,
        "list": list,
        "dict": dict,
        "set": set,
        "tuple": tuple,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "type": type,
        "isinstance": isinstance,
        "True": True,
        "False": False,
        "None": None,
    }
    namespace = {"__builtins__": safe_builtins, "math": math, "statistics": statistics}
    try:
        import numpy as np

        namespace["np"] = np
        namespace["numpy"] = np
    except ImportError:
        pass
    try:
        import pandas as pd

        namespace["pd"] = pd
        namespace["pandas"] = pd
    except ImportError:
        pass
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    try:
        exec(compile(code, "<nexarion>", "exec"), namespace)
        output = buffer.getvalue()
        sys.stdout = old_stdout
        return {
            "output": output.strip()[:2000] if output.strip() else "(no output)",
            "error": None,
            "success": True,
        }
    except Exception as e:
        sys.stdout = old_stdout
        return {
            "output": "",
            "error": f"{type(e).__name__}: {str(e)}",
            "success": False,
        }


# =========================
# MARKET DATA
# =========================
def tool_market_data(symbol: str) -> dict:
    symbol = symbol.upper().strip()
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.info
        hist = ticker.history(period="5d")
        if not hist.empty:
            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
            change_pct = ((current - prev) / prev * 100) if prev else 0
            return {
                "symbol": symbol,
                "price": round(current, 4),
                "change_pct": round(change_pct, 2),
                "volume": int(hist["Volume"].iloc[-1]) if "Volume" in hist else None,
                "high_5d": round(float(hist["High"].max()), 4),
                "low_5d": round(float(hist["Low"].min()), 4),
                "name": info.get("longName", symbol),
                "sector": info.get("sector", ""),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "source": "yfinance",
            }
    except ImportError:
        pass
    except Exception as e:
        print(f"⚠️ yfinance error: {e}")
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?interval=1d&range=5d"
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if result:
            meta = result[0].get("meta", {})
            closes = (
                result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
            )
            closes = [c for c in closes if c is not None]
            current = closes[-1] if closes else meta.get("regularMarketPrice", 0)
            prev = closes[-2] if len(closes) > 1 else current
            change_pct = ((current - prev) / prev * 100) if prev else 0
            return {
                "symbol": symbol,
                "price": round(current, 4),
                "change_pct": round(change_pct, 2),
                "name": meta.get("longName", symbol),
                "source": "yahoo_api",
            }
    except Exception as e:
        return {"error": f"Market data unavailable: {e}", "symbol": symbol}
    return {"error": "No market data source available", "symbol": symbol}


# =========================
# CALCULATOR
# =========================
def tool_calculator(expression: str) -> dict:
    import math

    expr = expression.strip()
    if re.search(
        r"[^0-9+\-*/().,%^eE\s]",
        expr.replace("sqrt", "")
        .replace("sin", "")
        .replace("cos", "")
        .replace("log", "")
        .replace("pi", "")
        .replace("abs", ""),
    ):
        return {"error": "Expression contains unsafe characters", "result": None}
    safe_math = {
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "abs": abs,
        "pi": math.pi,
        "e": math.e,
        "pow": pow,
        "round": round,
    }
    try:
        result = eval(expr, {"__builtins__": {}}, safe_math)
        return {
            "expression": expression,
            "result": result,
            "formatted": f"{expression} = {result}",
        }
    except Exception as e:
        return {"error": str(e), "expression": expression, "result": None}


# =========================
# WIKIPEDIA DEEP FETCH
# =========================
def tool_wiki_deep(topic: str) -> dict:
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(topic)}"
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return {"error": f"Article not found: {topic}", "content": ""}
        data = r.json()
        if data.get("type") == "disambiguation":
            return {"error": f"'{topic}' is ambiguous", "content": ""}
        summary = data.get("extract", "")
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        section_names = []
        try:
            sections_url = f"https://en.wikipedia.org/w/api.php?action=parse&page={quote(topic)}&prop=sections&format=json"
            sr = requests.get(sections_url, headers=HEADERS, timeout=5)
            sd = sr.json()
            sections = sd.get("parse", {}).get("sections", [])
            section_names = [s["line"] for s in sections[:6] if s.get("line")]
        except Exception:
            pass
        return {
            "topic": data.get("title", topic),
            "summary": summary[:2000],
            "url": page_url,
            "sections": section_names,
            "content": summary,
        }
    except Exception as e:
        return {"error": str(e), "content": ""}


# =========================
# NEWS SEARCH
# =========================
def tool_news_search(query: str) -> dict:
    try:
        search_url = (
            f"https://html.duckduckgo.com/html/?q={quote(query + ' news')}&df=w"
        )
        r = requests.get(search_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        snippets = re.findall(
            r'class="result__snippet"[^>]*>(.*?)</a>', r.text, re.DOTALL
        )
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', r.text, re.DOTALL)
        results = []
        for i, (title, snippet) in enumerate(zip(titles[:5], snippets[:5])):
            title_clean = re.sub(r"<[^>]+>", "", title).strip()
            snippet_clean = re.sub(r"<[^>]+>", "", snippet).strip()
            if title_clean and snippet_clean:
                results.append(f"{title_clean}: {snippet_clean}")
        if not results:
            return {"error": "No news results found", "query": query, "results": []}
        return {"query": query, "results": results, "summary": " | ".join(results[:3])}
    except Exception as e:
        return {"error": str(e), "query": query, "results": []}


# =========================
# WEB SEARCH (GENERAL)
# =========================
def tool_web_search(query: str) -> dict:
    """General web search — catch-all for any current information request."""
    try:
        search_url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        r = requests.get(search_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        snippets = re.findall(
            r'class="result__snippet"[^>]*>(.*?)</a>', r.text, re.DOTALL
        )
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', r.text, re.DOTALL)
        results = []
        for i in range(min(4, len(titles), len(snippets))):
            title = re.sub(r"<[^>]+>", "", titles[i]).strip()
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            if title and snippet:
                results.append(f"{title}: {snippet}")
        if not results:
            return {"error": "No search results found", "query": query, "results": []}
        top_content = ""
        try:
            actual_urls = re.findall(r'uddg=(https?[^&"]+)', r.text)
            if actual_urls:
                top_url = unquote(actual_urls[0])
                fetch_r = requests.get(top_url, headers=HEADERS, timeout=8)
                html = fetch_r.text
                html = re.sub(
                    r"<script[^>]*>.*?</script>",
                    "",
                    html,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                html = re.sub(
                    r"<style[^>]*>.*?</style>",
                    "",
                    html,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                html = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"\s+", " ", html).strip()
                sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 40]
                top_content = ". ".join(sentences[:8])
        except Exception:
            pass
        return {
            "query": query,
            "results": results,
            "top_content": top_content[:1500] if top_content else "",
            "summary": " | ".join(results[:3]),
        }
    except Exception as e:
        return {"error": str(e), "query": query, "results": []}


# =========================
# TOOL REGISTRY
# =========================
TOOL_REGISTRY = {
    "web_fetch": {
        "function": tool_web_fetch,
        "description": "Fetch and read content from any URL",
        "param": "url",
        "example": "web_fetch('https://example.com')",
    },
    "python_exec": {
        "function": tool_python_exec,
        "description": "Execute Python code and return the output",
        "param": "code",
        "example": "python_exec('import math; print(math.pi)')",
    },
    "market_data": {
        "function": tool_market_data,
        "description": "Get live stock, crypto, or commodity market data",
        "param": "symbol",
        "example": "market_data('AAPL')",
    },
    "calculator": {
        "function": tool_calculator,
        "description": "Evaluate a mathematical expression",
        "param": "expression",
        "example": "calculator('sqrt(144) * pi')",
    },
    "wiki_deep": {
        "function": tool_wiki_deep,
        "description": "Fetch a full Wikipedia article with sections",
        "param": "topic",
        "example": "wiki_deep('quantum entanglement')",
    },
    "news_search": {
        "function": tool_news_search,
        "description": "Search for recent news on a topic",
        "param": "query",
        "example": "news_search('AI regulation 2026')",
    },
    "web_search": {
        "function": tool_web_search,
        "description": "General web search for any current information",
        "param": "query",
        "example": "web_search('number 1 movie Philippines 2026')",
    },
}


def execute_tool(tool_name: str, param: str) -> dict:
    """Execute a named tool with a parameter. Returns structured result."""
    if tool_name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {tool_name}"}
    tool = TOOL_REGISTRY[tool_name]
    try:
        print(f"🔧 TOOL EXECUTING: {tool_name}({param[:60]})")
        start = time.time()
        result = tool["function"](param)
        elapsed = round(time.time() - start, 2)
        result["_tool"] = tool_name
        result["_elapsed"] = elapsed
        print(f"🔧 TOOL COMPLETE: {tool_name} in {elapsed}s")
        return result
    except Exception as e:
        traceback.print_exc()
        return {"error": str(e), "_tool": tool_name}


def format_tool_result(result: dict) -> str:
    """Format a tool result for injection into the Nexarion prompt."""
    tool = result.get("_tool", "tool")
    error = result.get("error")

    if error:
        return f"[Tool: {tool}] Error: {error}"

    if tool == "market_data":
        symbol = result.get("symbol", "")
        price = result.get("price", "N/A")
        change = result.get("change_pct", 0)
        name = result.get("name", symbol)
        direction = "▲" if change >= 0 else "▼"
        lines = [f"Market data for {name} ({symbol}):"]
        lines.append(f"  Price: ${price} {direction} {abs(change):.2f}%")
        if result.get("high_5d"):
            lines.append(f"  5-day range: ${result['low_5d']} – ${result['high_5d']}")
        if result.get("pe_ratio"):
            lines.append(f"  P/E ratio: {result['pe_ratio']:.1f}")
        if result.get("sector"):
            lines.append(f"  Sector: {result['sector']}")
        return "\n".join(lines)

    elif tool == "python_exec":
        if result.get("success"):
            return f"[Python output]\n{result['output']}"
        return f"[Python error] {result['error']}"

    elif tool == "calculator":
        if result.get("result") is not None:
            return f"[Calculation] {result['formatted']}"
        return f"[Calculator error] {result.get('error', 'unknown')}"

    elif tool == "wiki_deep":
        content = result.get("summary", result.get("content", ""))
        topic = result.get("topic", "")
        sections = result.get("sections", [])
        lines = [f"[Wikipedia: {topic}]", content[:1500]]
        if sections:
            lines.append(f"Article sections: {', '.join(sections[:5])}")
        return "\n".join(lines)

    elif tool == "web_fetch":
        content = result.get("content", "")
        domain = result.get("domain", "")
        return f"[Web content from {domain}]\n{content[:2000]}"

    elif tool == "news_search":
        results = result.get("results", [])
        query = result.get("query", "")
        if not results:
            return f"[News: {query}] No results found"
        lines = [f"[Recent news: {query}]"]
        lines.extend(f"• {r}" for r in results[:4])
        return "\n".join(lines)

    elif tool == "web_search":
        results = result.get("results", [])
        top = result.get("top_content", "")
        query = result.get("query", "")
        lines = [f"[Web search: {query}]"]
        if top:
            lines.append(top[:1000])
        elif results:
            lines.extend(f"• {r}" for r in results[:4])
        return "\n".join(lines)

    content = result.get(
        "content", result.get("output", result.get("summary", str(result)))
    )
    return f"[{tool} result]\n{str(content)[:1500]}"
