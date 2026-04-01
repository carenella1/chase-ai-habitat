"""
tool_selector.py

LLM-driven tool selection — replaces the keyword-based tool_detector.

Instead of maintaining an ever-growing list of keywords and patterns,
this module asks the LLM itself which tool to use based on the user's
message. The LLM understands intent naturally, so it handles anything
the user might ask without requiring keyword maintenance.

The selection call uses a minimal prompt and short timeout so it
stays fast (target: under 10 seconds). It asks for JSON output only.

Architecture:
1. User message arrives at api_chat
2. select_tools_for_message() is called with the message
3. A fast LLM call returns {"tool": "market_data", "param": "CL=F"}
   or {"tool": "none"} if no tool is needed
4. Tool executes, result injected into Nexarion prompt
5. Nexarion responds with real data already in context

Adding a new tool: add it to TOOL_DESCRIPTIONS below.
The LLM will automatically know to use it — no other changes needed.
"""

import json
import re
import requests

# =========================
# TOOL DESCRIPTIONS
# Tell the LLM what each tool does so it can make good selections.
# Keep descriptions short and precise — this is what the LLM reads.
# =========================
TOOL_DESCRIPTIONS = {
    "market_data": "Get the live price and stats for any stock, ETF, cryptocurrency, or commodity. Use the correct yfinance symbol: stocks use ticker (AAPL, TSLA), crypto uses SYMBOL-USD (BTC-USD, ETH-USD), commodities use futures codes (CL=F for oil/crude, GC=F for gold, SI=F for silver, NG=F for natural gas, HG=F for copper, ZW=F for wheat, ZC=F for corn, BZ=F for Brent crude).",
    "web_fetch": "Fetch and read the full content of any URL. Use when the user provides a URL or asks to read/check a specific website.",
    "python_exec": "Execute Python code and return the output. Use when the user shares a code block (in backticks) or explicitly asks to run/execute code.",
    "calculator": "Evaluate a mathematical expression and return the result. Use for arithmetic, percentages, compound interest, unit conversions, or any numerical calculation.",
    "wiki_deep": "Fetch a full Wikipedia article on any topic. Use when the user asks for a deep dive, comprehensive overview, or detailed explanation of a concept.",
    "news_search": "Search for recent news articles on any topic. Use when the user asks about latest news, recent events, current developments, or what's happening with something.",
    "none": "No tool needed. Use for conversational questions, opinions, philosophical discussion, or anything that doesn't require real-time data or computation.",
}


# =========================
# SELECTION PROMPT
# =========================
def _build_selection_prompt(message: str) -> str:
    tool_list = "\n".join(
        f'- "{name}": {desc}' for name, desc in TOOL_DESCRIPTIONS.items()
    )

    return f"""You are a tool router. Given a user message, decide which tool to use.

Available tools:
{tool_list}

User message: "{message}"

Respond with ONLY a JSON object. No explanation. No markdown. Examples:
{{"tool": "market_data", "param": "CL=F"}}
{{"tool": "market_data", "param": "AAPL"}}
{{"tool": "calculator", "param": "10000 * (1 + 0.07) ** 20"}}
{{"tool": "news_search", "param": "artificial intelligence regulation"}}
{{"tool": "web_fetch", "param": "https://example.com"}}
{{"tool": "wiki_deep", "param": "quantum entanglement"}}
{{"tool": "none", "param": ""}}

JSON response:"""


# =========================
# MAIN SELECTOR
# =========================
def select_tools_for_message(message: str, call_llm_fn) -> list[tuple[str, str]]:
    """
    Ask the LLM which tool to use for this message.
    Returns list of (tool_name, param) tuples — same format as old detect_tools().
    Returns empty list if no tool needed or if selection fails.

    call_llm_fn: the existing call_llm function from run_ui.py
    """
    if not message or not message.strip():
        return []

    # Skip tool selection for very short conversational messages
    msg = message.strip()
    if len(msg) < 5:
        return []

    try:
        prompt = _build_selection_prompt(msg)

        # Short timeout — this is a fast routing call, not a reasoning call
        raw = call_llm_fn(prompt, timeout=20)

        if not raw or not raw.strip():
            print("⚠️ Tool selector: no response")
            return []

        # Strip think tags if DeepSeek adds them
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        # Extract JSON — handle cases where LLM adds surrounding text
        json_match = re.search(r"\{[^}]+\}", raw)
        if not json_match:
            print(f"⚠️ Tool selector: no JSON found in: {raw[:100]}")
            return []

        result = json.loads(json_match.group())
        tool = result.get("tool", "none").strip()
        param = result.get("param", "").strip()

        print(
            f"🔧 TOOL SELECTED: {tool}({param[:60]})"
            if tool != "none"
            else "🔧 NO TOOL NEEDED"
        )

        if tool == "none" or tool not in TOOL_DESCRIPTIONS:
            return []

        # Validate param exists for tools that need it
        if not param and tool != "none":
            print(f"⚠️ Tool selector: {tool} selected but no param provided")
            return []

        return [(tool, param)]

    except json.JSONDecodeError as e:
        print(
            f"⚠️ Tool selector JSON error: {e} — raw: {raw[:100] if 'raw' in dir() else 'N/A'}"
        )
        return []
    except Exception as e:
        print(f"⚠️ Tool selector error: {e}")
        return []


def format_tools_for_prompt(tool_results: list[dict]) -> str:
    """
    Format tool results for injection into the Nexarion prompt.
    Identical interface to the old tool_detector version.
    """
    from habitat.agents.tool_executor import format_tool_result

    if not tool_results:
        return ""

    lines = ["Real-time information retrieved for this response:"]
    for result in tool_results:
        lines.append(format_tool_result(result))
        lines.append("")

    return "\n".join(lines)
