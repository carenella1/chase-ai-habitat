# CLAUDE.md — Chase AI Habitat (NEX / Nexarion)

This file is read at the start of every Claude Code session. It tells you what this
project is, how it runs, and how the owner wants you to work. Read it fully before acting.

---

## Who you're working with

The owner is **not a software developer**. Explain your reasoning in plain English,
avoid unexplained jargon, and when you propose a change, say *what* it does and *why*
it helps in terms a non-coder can follow. The owner relies on you to fill the
engineering knowledge gap — be proactive about suggesting improvements they wouldn't
know to ask for, but always explain the tradeoffs.

## What this project is

Chase AI Habitat is a **local, multi-agent AI cognition system** — internally called
**NEX** (Nexarion). The long-term goal is to move NEX toward AGI-like behavior:
a system that researches, remembers, reasons across connected knowledge, and
increasingly improves itself.

A standing goal: **always be on the lookout for open-source libraries, techniques, and
upgrades that NEX could benefit from but couldn't discover on its own.** When you spot
one, surface it with pros and cons before changing anything.

## How it runs (Windows, local)

- **OS / environment:** Windows. Project root is `C:\Users\User\Desktop\Github\chase-ai-habitat`.
- **Language:** Python (3.11).
- **Virtual environment:** `habitat-env` (use its Python interpreter for running/testing).
- **Local LLM:** [Ollama](https://ollama.com) runs on `http://127.0.0.1:11434`. All model
  calls route through `llm_router.py` (`call_llm`, `call_llm_deep`, `get_llm_status`,
  `warmup_models`). NEX does **not** call a cloud API for its own cognition — it's local.
- **Web UI:** Flask app in `run_ui.py`, served at `http://127.0.0.1:5000`.
- **Launcher:** `launch_habitat.py` auto-starts Ollama, then launches the Flask UI in a
  desktop window. `launch_habitat_silent.pyw` is the no-console version used by the
  desktop shortcut.

To run the app for testing, use the launcher (which handles Ollama startup) rather than
starting Flask directly, unless you specifically need to isolate the UI.

## Key modules (project root)

- `run_ui.py` — Flask app + API endpoints; the central hub that wires everything together.
- `llm_router.py` — routes all LLM calls to Ollama.
- `self_optimizer.py` — `SelfOptimizer`: scores agent outputs and rewrites agent prompts
  to improve them over time. Changes are logged and reversible. **Never let it modify
  NEX's core identity/persona.**
- `knowledge_graph.py` — `NexKnowledgeGraph`: temporal entity/relationship graph over
  SQLite, enabling multi-hop reasoning.
- `structured_memory.py` — `NexMemory`: structured memory layer.
- `deep_research_trigger.py` — decides when to launch deeper research cycles.
- `nex_sandbox.py` — `NexSandbox`: isolated, safety-checked code execution for
  NEX-generated code (import whitelist, timeouts, no network, sandboxed working dir).
- `nex_docker_agent.py` — `NexDockerAgent` / `NexAutonomousEngine`: a Docker-based
  environment giving NEX broader agency, separate from the sandbox.
- `nex_trainer.py` — retrieval-augmented knowledge reinforcement (builds a local
  knowledge corpus injected into prompts; not weight-level training).

## Package structure

- `habitat/` — core package:
  - `habitat/agents/` — agent definitions (Researcher, Curator, Strategist, Archivist,
    curriculum, domain knowledge, etc.).
  - `habitat/knowledge/` — knowledge manager.
  - `habitat/memory/` — memory manager.
  - `habitat/voice/` — voice evolution/config.
- `data/` — SQLite databases: `memory.db`, `self_optimizer.db`, `knowledge_graph.db`,
  `sandbox_log.db`, plus JSON knowledge/cognition logs.
- `static/`, `templates/` — Flask front-end assets.

## How to make changes

- **Make surgical, minimal edits.** Change only what needs changing. (An older rule in
  `AI_DEV_RULES.md` asked for full-file replacements — that rule existed to work around a
  copy-paste workflow and is now obsolete. You edit files directly, so precise diffs are
  preferred.)
- **Preserve architecture and compatibility.** Don't introduce breaking changes without
  clearly explaining them first.
- **Test after editing** using the `habitat-env` interpreter, and report what you ran and
  what happened.
- **Explain before big moves.** For anything beyond a trivial fix, describe your plan and
  wait for approval.

## Safety and guardrails

- Keep `self_optimizer.py`'s protections intact: trust thresholds, change logging, revert
  ability, and the hard rule that it never edits NEX's identity/persona.
- Respect the sandbox restrictions in `nex_sandbox.py` (import whitelist, timeout,
  no network, no writing outside the sandbox folder). Don't weaken these without an
  explicit, explained reason.
- **Never hardcode secrets** (API keys, tokens) into source files. If you find any (e.g. a
  placeholder like `YOUR_API_KEY_HERE`), recommend moving them to environment variables or
  a local, git-ignored config file — and flag it, don't commit it.

## Git

This folder is a Git repo connected to the owner's remote. Use clear, descriptive commit
messages. Once a change the owner asked for (or agreed to) is complete and tested,
commit it automatically — no need to ask first. Group unrelated changes into separate
commits rather than one large one. Never commit secrets or credentials. Always confirm
with the owner before pushing to the remote, regardless of how the commit was made.
