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
- file_search  — locate a file anywhere on disk by name/pattern
- file_read    — read a text file's contents by path
- own_code     — list or read Nexarion's own project source files
"""

import os
import re
import json
import time
import fnmatch
import traceback
import requests
from html import unescape as _html_unescape
from urllib.parse import quote, urlparse, unquote
from nex_sandbox import NexSandbox
from habitat.agents.web_safety import safe_get, wrap_untrusted_web_content

nex_sandbox = NexSandbox()

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NexarionTools/1.0)"}
REQUEST_TIMEOUT = 10

# habitat/agents/tool_executor.py -> project root is two levels up
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FILE_READ_MAX_BYTES = 200_000  # ~200KB cap so a huge file can't blow out the prompt
FILE_SEARCH_TIMEOUT = 8.0  # seconds — keeps the search inside run_ui.py's ~12s tool budget
FILE_SEARCH_MAX_RESULTS = 20

TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".csv", ".html",
    ".htm", ".css", ".yml", ".yaml", ".ini", ".cfg", ".conf", ".log", ".xml",
    ".sql", ".bat", ".ps1", ".sh", ".c", ".cpp", ".h", ".java", ".rs", ".go",
    ".rb", ".php", ".env", ".toml", ".rst", ".gitignore",
}


# =========================
# WEB FETCH
# =========================
def tool_web_fetch(url: str) -> dict:
    try:
        if not url.startswith("http"):
            url = "https://" + url
        r = safe_get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
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
        text = _html_unescape(re.sub(r"\s+", " ", html)).strip()
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


def tool_market_data(symbol: str) -> dict:
    symbol = symbol.upper().strip()


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
        print(f"⚠️ Yahoo API error for {symbol}: {e}")
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
        urls = [unquote(u) for u in re.findall(r'uddg=(https?[^&"]+)', r.text)]
        results = []
        for i, (title, snippet) in enumerate(zip(titles[:5], snippets[:5])):
            title_clean = _html_unescape(re.sub(r"<[^>]+>", "", title)).strip()
            snippet_clean = _html_unescape(re.sub(r"<[^>]+>", "", snippet)).strip()
            if title_clean and snippet_clean:
                results.append({
                    "title": title_clean,
                    "snippet": snippet_clean,
                    "url": urls[i] if i < len(urls) else "",
                })
        if not results:
            return {"error": "No news results found", "query": query, "results": []}
        return {
            "query": query,
            "results": results,
            "summary": " | ".join(f"{r['title']}: {r['snippet']}" for r in results[:3]),
        }
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
        urls = [unquote(u) for u in re.findall(r'uddg=(https?[^&"]+)', r.text)]
        results = []
        for i in range(min(4, len(titles), len(snippets))):
            title = _html_unescape(re.sub(r"<[^>]+>", "", titles[i])).strip()
            snippet = _html_unescape(re.sub(r"<[^>]+>", "", snippets[i])).strip()
            if title and snippet:
                results.append({
                    "title": title,
                    "snippet": snippet,
                    "url": urls[i] if i < len(urls) else "",
                })
        if not results:
            return {"error": "No search results found", "query": query, "results": []}

        # Fetch and synthesize the top few result pages, not just the first —
        # one page can be thin, wrong, or paywalled; a handful gives Nex
        # something to actually cross-reference.
        page_sections = []
        try:
            fetched_domains = set()
            for r_item in results:
                if len(page_sections) >= 3:
                    break
                top_url = r_item["url"]
                if not top_url:
                    continue
                domain = urlparse(top_url).netloc.replace("www.", "")
                if domain in fetched_domains:
                    continue
                try:
                    fetch_r = safe_get(top_url, headers=HEADERS, timeout=8)
                except ValueError:
                    continue  # blocked unsafe URL — skip, don't fail the whole search
                except Exception:
                    continue
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
                text = _html_unescape(re.sub(r"\s+", " ", html)).strip()
                sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 40]
                page_text = ". ".join(sentences[:6])
                if page_text:
                    fetched_domains.add(domain)
                    page_sections.append(f"[{domain}]({top_url}) {page_text}")
        except Exception:
            pass
        top_content = "\n\n".join(page_sections)
        return {
            "query": query,
            "results": results,
            "top_content": top_content[:2500] if top_content else "",
            "summary": " | ".join(f"{r['title']}: {r['snippet']}" for r in results[:3]),
        }
    except Exception as e:
        return {"error": str(e), "query": query, "results": []}


def tool_sandbox_run(code: str) -> dict:
    return nex_sandbox.run_code(code)


# =========================
# FILE SYSTEM ACCESS
# =========================
# Read-only. No write/delete/execute anywhere in this module. Scope is the
# whole local disk (per owner's explicit choice), time-boxed so a search
# that can't finish in the chat-response budget degrades gracefully instead
# of hanging the reply.
def _is_probably_text(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXTENSIONS:
        return True
    if ext == "":
        try:
            with open(path, "rb") as f:
                chunk = f.read(1024)
            return b"\x00" not in chunk
        except Exception:
            return False
    return False


def tool_file_read(path: str) -> dict:
    """Read a text file's contents by path, with a size cap."""
    path = (path or "").strip().strip("\"'")
    if not path:
        return {"error": "No path given", "content": ""}
    if not os.path.isfile(path):
        return {"error": f"No such file: {path}", "content": ""}

    try:
        size = os.path.getsize(path)
    except OSError as e:
        return {"error": str(e), "content": ""}

    if not _is_probably_text(path):
        return {
            "error": f"'{path}' doesn't look like a text file — binary content isn't readable this way",
            "content": "",
            "path": path,
            "size": size,
        }

    truncated = size > FILE_READ_MAX_BYTES
    try:
        with open(path, "rb") as f:
            raw = f.read(FILE_READ_MAX_BYTES)
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("latin-1", errors="replace")
    except Exception as e:
        return {"error": str(e), "content": "", "path": path}

    return {"path": path, "size": size, "content": content, "truncated": truncated}


def tool_file_search(query: str) -> dict:
    """Search the whole local disk for a file by name or wildcard pattern, time-boxed."""
    query = (query or "").strip().strip("\"'")
    if not query:
        return {"error": "No filename or pattern given", "matches": []}

    pattern = query if any(c in query for c in "*?") else f"*{query}*"
    pattern = pattern.lower()

    roots = []
    for d in "CDEFGHIJ":
        drive = f"{d}:\\"
        if os.path.exists(drive):
            roots.append(drive)

    skip_dirs = {"$recycle.bin", "system volume information", "winsxs"}
    matches = []
    start = time.time()
    timed_out = False

    for root in roots:
        if time.time() - start > FILE_SEARCH_TIMEOUT:
            timed_out = True
            break
        for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=lambda e: None):
            if time.time() - start > FILE_SEARCH_TIMEOUT:
                timed_out = True
                break
            dirnames[:] = [d for d in dirnames if d.lower() not in skip_dirs]
            for fname in filenames:
                if fnmatch.fnmatch(fname.lower(), pattern):
                    full = os.path.join(dirpath, fname)
                    try:
                        stat = os.stat(full)
                        matches.append({
                            "path": full,
                            "size": stat.st_size,
                            "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                        })
                    except OSError:
                        continue
                    if len(matches) >= FILE_SEARCH_MAX_RESULTS:
                        break
            if len(matches) >= FILE_SEARCH_MAX_RESULTS:
                break
        if len(matches) >= FILE_SEARCH_MAX_RESULTS:
            break

    result = {"query": query, "matches": matches, "timed_out": timed_out and len(matches) < FILE_SEARCH_MAX_RESULTS}

    # Auto-preview: if the search landed on a small number of hits and the
    # top one is readable text under the size cap, attach its content so
    # "find X" and "what's in X" resolve in one tool call.
    if 0 < len(matches) <= 3:
        top = matches[0]["path"]
        if _is_probably_text(top) and matches[0]["size"] <= FILE_READ_MAX_BYTES:
            read_result = tool_file_read(top)
            if not read_result.get("error"):
                result["preview_path"] = top
                result["preview_content"] = read_result["content"]
                result["preview_truncated"] = read_result["truncated"]

    return result


def tool_own_code(query: str) -> dict:
    """List or read Nexarion's own project source files (scoped to the project root, not the whole disk)."""
    query = (query or "").strip().strip("\"'")
    root = PROJECT_ROOT
    skip_dirs = {"habitat-env", ".git", "__pycache__", "node_modules", "data", "sandbox"}

    if not query or query.lower() in {"overview", "list", "structure"}:
        top_files = sorted(
            f for f in os.listdir(root)
            if f.endswith(".py") and os.path.isfile(os.path.join(root, f))
        )
        return {"root": root, "files": top_files[:40], "query": query}

    matches = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in filenames:
            if query.lower() in fname.lower():
                matches.append(os.path.join(dirpath, fname))
        if len(matches) >= FILE_SEARCH_MAX_RESULTS:
            break

    result = {"root": root, "query": query, "matches": matches[:FILE_SEARCH_MAX_RESULTS]}
    if len(matches) == 1 and _is_probably_text(matches[0]):
        r = tool_file_read(matches[0])
        if not r.get("error"):
            result["preview_path"] = matches[0]
            result["preview_content"] = r["content"]
            result["preview_truncated"] = r["truncated"]
    return result


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
    "sandbox_run": {
        "function": tool_sandbox_run,
        "description": (
            "Run Python in NEX's isolated, stdlib-only sandbox to verify a "
            "claim computationally. Not chat-selectable — only invoked "
            "autonomously from the background cognition loop."
        ),
        "param": "code",
        "example": "sandbox_run('print(sum(range(100)))')",
    },
    "file_search": {
        "function": tool_file_search,
        "description": "Search the whole local disk for a file by name or wildcard pattern",
        "param": "query",
        "example": "file_search('creative_engine.py')",
    },
    "file_read": {
        "function": tool_file_read,
        "description": "Read the text contents of a file at a specific path",
        "param": "path",
        "example": "file_read('C:/Users/User/Desktop/notes.txt')",
    },
    "own_code": {
        "function": tool_own_code,
        "description": "List or read Nexarion's own project source files",
        "param": "query",
        "example": "own_code('creative_engine')",
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


def _format_result_link(r: dict) -> str:
    """Render a search result dict as 'title: snippet', with a real markdown link when a URL is present."""
    title, snippet, url = r.get("title", ""), r.get("snippet", ""), r.get("url", "")
    if url:
        # Titles are scraped page text and can contain [ ] ( ) which would
        # otherwise break the markdown link syntax being built here.
        safe_title = title.replace("[", "(").replace("]", ")")
        return f"[{safe_title}]({url}) — {snippet}"
    return f"{title}: {snippet}"


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

    elif tool == "sandbox_run":
        status = result.get("status", "")
        if status == "success":
            return f"[Sandbox output]\n{result.get('stdout', '')}"
        if status == "blocked":
            return f"[Sandbox blocked] {result.get('reason', 'unsafe code')}"
        if status == "pending_approval":
            return "[Sandbox] Queued for human approval (trust level 1)."
        return f"[Sandbox error] {result.get('stderr') or result.get('reason', status)}"

    elif tool == "calculator":
        if result.get("result") is not None:
            return f"[Calculation] {result['formatted']}"
        return f"[Calculator error] {result.get('error', 'unknown')}"

    elif tool == "wiki_deep":
        content = result.get("summary", result.get("content", ""))
        topic = result.get("topic", "")
        sections = result.get("sections", [])
        lines = [f"[Wikipedia: {topic}]", wrap_untrusted_web_content(content[:1500], source="en.wikipedia.org")]
        if sections:
            lines.append(f"Article sections: {', '.join(sections[:5])}")
        return "\n".join(lines)

    elif tool == "web_fetch":
        content = result.get("content", "")
        domain = result.get("domain", "")
        return f"[Web content from {domain}]\n{wrap_untrusted_web_content(content[:2000], source=domain)}"

    elif tool == "news_search":
        results = result.get("results", [])
        query = result.get("query", "")
        if not results:
            return f"[News: {query}] No results found"
        lines = [f"[Recent news: {query}]"]
        body = "\n".join(f"• {_format_result_link(r)}" for r in results[:4])
        lines.append(wrap_untrusted_web_content(body, source="news search"))
        return "\n".join(lines)

    elif tool == "web_search":
        results = result.get("results", [])
        top = result.get("top_content", "")
        query = result.get("query", "")
        lines = [f"[Web search: {query}]"]
        if top:
            lines.append(wrap_untrusted_web_content(top[:1800], source="web search"))
        elif results:
            body = "\n".join(f"• {_format_result_link(r)}" for r in results[:4])
            lines.append(wrap_untrusted_web_content(body, source="web search"))
        return "\n".join(lines)

    elif tool == "file_search":
        matches = result.get("matches", [])
        query = result.get("query", "")
        if not matches:
            note = " (search timed out before finishing — try narrowing the name)" if result.get("timed_out") else ""
            return f"[File search: {query}] No matching files found{note}"
        lines = [f"[File search: {query}] Found {len(matches)} match(es):"]
        for m in matches[:10]:
            lines.append(f"  • {m['path']} ({m['size']} bytes, modified {m['modified']})")
        if result.get("preview_content"):
            trunc = " (truncated)" if result.get("preview_truncated") else ""
            lines.append(f"\nContents of {result['preview_path']}{trunc}:")
            lines.append(result["preview_content"][:4000])
        return "\n".join(lines)

    elif tool == "file_read":
        if result.get("content"):
            trunc = " (truncated)" if result.get("truncated") else ""
            return f"[File: {result.get('path')}]{trunc}\n{result['content'][:4000]}"
        return f"[File read error] {result.get('error', 'unknown')}"

    elif tool == "own_code":
        query = result.get("query", "")
        if result.get("files") is not None:
            files = result.get("files", [])
            return "[Nexarion's project files]\n" + "\n".join(f"  • {f}" for f in files)
        matches = result.get("matches", [])
        if not matches:
            return f"[Own code: {query}] No matching source file found"
        lines = [f"[Own code: {query}] Found {len(matches)} match(es):"]
        for m in matches[:10]:
            lines.append(f"  • {m}")
        if result.get("preview_content"):
            trunc = " (truncated)" if result.get("preview_truncated") else ""
            lines.append(f"\nContents of {result['preview_path']}{trunc}:")
            lines.append(result["preview_content"][:4000])
        return "\n".join(lines)

    content = result.get(
        "content", result.get("output", result.get("summary", str(result)))
    )
    return f"[{tool} result]\n{str(content)[:1500]}"
