"""
deep_research.py

Nexarion's Deep Research Engine.

When Chase asks a hard question, this module runs a structured
multi-stage investigation rather than a single LLM call.

Pipeline:
1. DECOMPOSE  — Break the question into 4-6 focused sub-questions
2. INVESTIGATE — Research each sub-question using available tools
3. SYNTHESIZE  — Build a coherent picture from all findings
4. CRITIQUE    — Identify gaps, uncertainties, and strongest conclusions
5. REPORT      — Return a structured research report

This is how real research works. Each stage builds on the last.
The final report has actual sources, actual data, actual reasoning.

Usage:
    from habitat.agents.deep_research import DeepResearcher
    researcher = DeepResearcher(call_llm_fn)
    report = researcher.investigate("What are the most promising
                                     mechanisms for defeating glioblastoma?")
"""

import time
import json
import os
import re
from datetime import datetime


RESEARCH_LOG_FILE = "data/research_sessions.jsonl"


class DeepResearcher:

    def __init__(self, call_llm_fn):
        self.call_llm = call_llm_fn
        self.tools_available = self._check_tools()

    def _check_tools(self) -> dict:
        """Verify which tools are available."""
        try:
            from habitat.agents.tool_executor import TOOL_REGISTRY

            return {name: True for name in TOOL_REGISTRY}
        except Exception:
            return {}

    def _run_tool(self, tool_name: str, param: str) -> str:
        """Run a tool and return formatted result."""
        try:
            from habitat.agents.tool_executor import execute_tool, format_tool_result

            result = execute_tool(tool_name, param)
            return format_tool_result(result)
        except Exception as e:
            return f"[Tool error: {e}]"

    # =========================
    # STAGE 1: DECOMPOSE
    # =========================
    def _decompose(self, question: str) -> list[str]:
        """Break a complex question into focused sub-questions."""
        prompt = f"""You are a research director. Break this complex question into exactly 5 focused sub-questions that together would fully answer it.

Question: {question}

Rules:
- Each sub-question must be specific and researchable
- Cover different aspects: mechanisms, evidence, current state, challenges, future directions
- Order from foundational to advanced
- Each sub-question on its own line starting with a number and period

Sub-questions:"""

        raw = self.call_llm(prompt, timeout=45)
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        sub_questions = []
        for line in raw.split("\n"):
            line = line.strip()
            if re.match(r"^\d+[\.\)]\s+", line):
                q = re.sub(r"^\d+[\.\)]\s+", "", line).strip()
                if len(q) > 15:
                    sub_questions.append(q)

        # Fallback if parsing fails
        if len(sub_questions) < 3:
            sub_questions = [
                f"What is the current scientific understanding of {question}?",
                f"What are the main mechanisms or processes involved in {question}?",
                f"What evidence exists for the most promising approaches to {question}?",
                f"What are the key challenges and open problems in {question}?",
                f"What are the most recent breakthroughs related to {question}?",
            ]

        print(f"🔬 DECOMPOSED INTO {len(sub_questions)} SUB-QUESTIONS")
        return sub_questions[:6]

    # =========================
    # STAGE 2: INVESTIGATE
    # =========================
    def _investigate_subquestion(self, sub_question: str, context: str) -> dict:
        """Research a single sub-question using available tools."""

        # Determine best tool for this sub-question
        sq_lower = sub_question.lower()
        tool_results = []

        # Always do a web search for current information
        tool_result = self._run_tool("web_search", sub_question)
        if tool_result and "Error" not in tool_result:
            tool_results.append(tool_result)

        # Also search for news if question is about recent developments
        if any(
            w in sq_lower
            for w in ["recent", "latest", "current", "new", "2024", "2025", "2026"]
        ):
            news_result = self._run_tool("news_search", sub_question)
            if news_result and "No results" not in news_result:
                tool_results.append(news_result)

        # Deep Wikipedia if it's a foundational concept question
        if any(
            w in sq_lower
            for w in ["what is", "mechanism", "process", "how does", "explain"]
        ):
            # Extract key concept for wiki lookup
            concept_prompt = f"Extract the main scientific concept from this question in 2-4 words: {sub_question}\nConcept:"
            concept = self.call_llm(concept_prompt, timeout=15)
            concept = re.sub(
                r"<think>.*?</think>", "", concept, flags=re.DOTALL
            ).strip()
            concept = concept.split("\n")[0].strip()[:50]
            if concept and len(concept) > 3:
                wiki_result = self._run_tool("wiki_deep", concept)
                if wiki_result and "Error" not in wiki_result:
                    tool_results.append(wiki_result)

        # Synthesize findings for this sub-question
        tool_data = (
            "\n\n".join(tool_results) if tool_results else "No tool data retrieved."
        )

        analysis_prompt = f"""You are a research analyst synthesizing findings.

Research Question: {sub_question}

Context from prior research:
{context[:500] if context else "None yet."}

Data retrieved:
{tool_data[:2000]}

Write a focused 3-5 sentence analysis that:
1. Directly answers the sub-question based on the data
2. Notes the strongest evidence
3. Identifies any key uncertainties
4. Connects to the broader research question

Analysis:"""

        analysis = self.call_llm(analysis_prompt, timeout=60)
        analysis = re.sub(r"<think>.*?</think>", "", analysis, flags=re.DOTALL).strip()

        return {
            "sub_question": sub_question,
            "tool_data": tool_data[:1500],
            "analysis": analysis[:800],
            "sources_used": len(tool_results),
        }

    # =========================
    # STAGE 3: SYNTHESIZE
    # =========================
    def _synthesize(self, question: str, findings: list[dict]) -> str:
        """Build a coherent synthesis from all sub-question findings."""

        findings_text = "\n\n".join(
            [
                f"Finding {i+1} ({f['sub_question'][:80]}):\n{f['analysis']}"
                for i, f in enumerate(findings)
            ]
        )

        prompt = f"""You are synthesizing a research report.

Original Question: {question}

Individual Findings:
{findings_text}

Write a comprehensive synthesis (6-8 paragraphs) that:
1. Opens with the most important conclusion
2. Explains the key mechanisms or processes
3. Summarizes the strongest evidence
4. Identifies cross-cutting themes across findings
5. Highlights what is well-established vs uncertain
6. Notes the most promising directions
7. Closes with implications

Write with precision and intellectual honesty. Cite specific evidence from the findings.

Synthesis:"""

        synthesis = self.call_llm(prompt, timeout=90)
        synthesis = re.sub(
            r"<think>.*?</think>", "", synthesis, flags=re.DOTALL
        ).strip()
        return synthesis

    # =========================
    # STAGE 4: CRITIQUE
    # =========================
    def _critique(self, question: str, synthesis: str) -> dict:
        """Identify gaps, confidence levels, and key conclusions."""

        prompt = f"""Critically evaluate this research synthesis.

Question: {question}

Synthesis:
{synthesis[:1500]}

Provide:
1. TOP 3 CONCLUSIONS (most well-supported findings, one per line starting with ✓)
2. KEY UNCERTAINTIES (what we don't know well, one per line starting with ?)
3. CONFIDENCE LEVEL (overall: High / Medium / Low and why in one sentence)
4. NEXT RESEARCH STEPS (what would strengthen this research, 2-3 steps)

Format exactly as shown with the symbols."""

        critique_raw = self.call_llm(prompt, timeout=45)
        critique_raw = re.sub(
            r"<think>.*?</think>", "", critique_raw, flags=re.DOTALL
        ).strip()

        return {"critique": critique_raw}

    # =========================
    # MAIN ENTRY POINT
    # =========================
    def investigate(self, question: str, depth: str = "standard") -> dict:
        """
        Run a full deep research investigation on a question.

        depth: "quick" (3 sub-questions), "standard" (5), "deep" (6+web fetch)

        Returns a structured report dict with all findings.
        """
        start_time = time.time()
        print(f"\n🔬 DEEP RESEARCH STARTING: {question[:80]}")
        print(f"🔬 Available tools: {list(self.tools_available.keys())}")

        report = {
            "question": question,
            "started_at": datetime.now().isoformat(),
            "depth": depth,
            "sub_questions": [],
            "findings": [],
            "synthesis": "",
            "critique": {},
            "elapsed_seconds": 0,
            "sources_consulted": 0,
        }

        # Stage 1: Decompose
        print("🔬 STAGE 1: Decomposing question...")
        sub_questions = self._decompose(question)
        report["sub_questions"] = sub_questions

        if depth == "quick":
            sub_questions = sub_questions[:3]

        # Stage 2: Investigate each sub-question
        findings = []
        context_so_far = ""
        total_sources = 0

        for i, sq in enumerate(sub_questions):
            print(f"🔬 STAGE 2.{i+1}: Investigating: {sq[:60]}...")
            finding = self._investigate_subquestion(sq, context_so_far)
            findings.append(finding)
            context_so_far += f"\n{finding['analysis']}"
            total_sources += finding["sources_used"]
            # Small pause to avoid rate limits
            time.sleep(1)

        report["findings"] = findings
        report["sources_consulted"] = total_sources

        # Stage 3: Synthesize
        print("🔬 STAGE 3: Synthesizing findings...")
        synthesis = self._synthesize(question, findings)
        report["synthesis"] = synthesis

        # Stage 4: Critique
        print("🔬 STAGE 4: Critical evaluation...")
        critique = self._critique(question, synthesis)
        report["critique"] = critique

        report["elapsed_seconds"] = round(time.time() - start_time, 1)
        print(f"🔬 DEEP RESEARCH COMPLETE in {report['elapsed_seconds']}s")
        print(f"🔬 Sources consulted: {total_sources}")

        # Log the session
        self._log_session(report)

        return report

    def _log_session(self, report: dict):
        """Persist research session to disk."""
        try:
            os.makedirs("data", exist_ok=True)
            entry = {
                "timestamp": int(time.time()),
                "question": report["question"],
                "synthesis_preview": report["synthesis"][:300],
                "sources": report["sources_consulted"],
                "elapsed": report["elapsed_seconds"],
            }
            with open(RESEARCH_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"⚠️ Research log error: {e}")

    def format_report(self, report: dict) -> str:
        """Format a research report for display in chat."""
        lines = []
        lines.append(f"## Research Report: {report['question']}")
        lines.append(
            f"*{report['sources_consulted']} sources · {report['elapsed_seconds']}s · {report['depth']} depth*\n"
        )

        lines.append("### Synthesis")
        lines.append(report.get("synthesis", "No synthesis generated."))

        if report.get("critique", {}).get("critique"):
            lines.append("\n### Critical Assessment")
            lines.append(report["critique"]["critique"])

        lines.append(f"\n*Research completed: {report['started_at'][:19]}*")
        return "\n\n".join(lines)
