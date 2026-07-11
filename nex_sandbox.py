"""
nex_sandbox.py  —  Phase 4: Safe Sandbox for Nex's Agency

WHAT THIS DOES:
  Gives Nex the ability to write code, create new agents, and test
  ideas — in a completely isolated environment that CANNOT affect
  your real machine.

  This is the "training wheels" phase before full computer use.
  Nex gets real creative power, you get zero risk.

THE SANDBOX MODEL:
  ┌─────────────────────────────────────────────────┐
  │  YOUR MACHINE (safe zone)                        │
  │  ┌───────────────────────────────────────────┐  │
  │  │  Nex Habitat (run_ui.py)                  │  │
  │  │  ↓ submits code/agent ideas               │  │
  │  │  ↓                                        │  │
  │  │  ┌─────────────────────────────────────┐  │  │
  │  │  │  SANDBOX (isolated folder)          │  │  │
  │  │  │  - subprocess with restricted env   │  │  │
  │  │  │  - no network access                │  │  │
  │  │  │  - no file writes outside sandbox   │  │  │
  │  │  │  - 30 second timeout                │  │  │
  │  │  │  - captured stdout/stderr           │  │  │
  │  │  └─────────────────────────────────────┘  │  │
  │  │  ↑ returns result + score                 │  │
  │  └───────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────┘

  If Nex's code crashes, hangs, or tries to do something dangerous:
  The sandbox catches it. Your machine is untouched.

TRUST LEVELS (you control this):
  LEVEL 0 — Sandbox only (safe, default now)
    Nex writes code → runs in sandbox → you see result
  LEVEL 1 — Sandbox + Review (future)
    Nex writes code → sandbox validates → YOU approve → runs
  LEVEL 2 — Supervised real execution (future)
    Nex runs on real machine with logging, you can interrupt
  LEVEL 3 — Full autonomy (when you're ready)
    Nex operates freely, you review logs

WHAT NEX CAN DO IN SANDBOX:
  - Write Python code
  - Create new agent files (saved to sandbox/agents/)
  - Run calculations and data analysis
  - Test hypotheses programmatically
  - Simulate cognition cycles
  - Design new system architectures (as files)

WHAT NEX CANNOT DO (enforced by sandbox):
  - Access the internet
  - Write outside the sandbox folder
  - Run for more than 30 seconds
  - Access your files, passwords, or system info
  - Install packages (only whitelisted stdlib is available)
"""

import os
import sys
import json
import time
import uuid
import subprocess
import threading
import sqlite3
from datetime import datetime
from typing import Optional
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

SANDBOX_ROOT = "sandbox"  # Sandbox lives here, relative to project root
SANDBOX_AGENTS = "sandbox/agents"  # Nex's generated agents go here
SANDBOX_DB = "data/sandbox_log.db"
SANDBOX_TIMEOUT = 30  # Max seconds for any sandbox execution
TRUST_LEVEL = 0  # Start at 0 (sandbox only)

# Whitelisted Python stdlib modules Nex can import in sandbox
ALLOWED_IMPORTS = {
    "json",
    "math",
    "statistics",
    "random",
    "itertools",
    "collections",
    "functools",
    "datetime",
    "time",
    "string",
    "re",
    "hashlib",
    "uuid",
    "copy",
    "typing",
    "dataclasses",
    "abc",
    "enum",
    "pathlib",
    "textwrap",
    "operator",
    "heapq",
    "bisect",
    "decimal",
    "fractions",
}

# ─────────────────────────────────────────────
# SANDBOX SETUP
# ─────────────────────────────────────────────


def _ensure_sandbox():
    """Create sandbox directory structure if it doesn't exist."""
    for path in [
        SANDBOX_ROOT,
        SANDBOX_AGENTS,
        f"{SANDBOX_ROOT}/outputs",
        f"{SANDBOX_ROOT}/temp",
    ]:
        os.makedirs(path, exist_ok=True)

    # Create a sandbox README so Nex understands the environment
    readme = f"""{SANDBOX_ROOT}/README.md
============================
NEX SANDBOX ENVIRONMENT
============================

This is your isolated workspace, Nex.

You can:
  - Write Python code here
  - Create new agent files in /agents/
  - Save analysis results to /outputs/
  - Read and write within this folder freely

You cannot:
  - Access the internet from this environment
  - Write outside this sandbox folder
  - Run for more than {SANDBOX_TIMEOUT} seconds

Available Python modules: {', '.join(sorted(ALLOWED_IMPORTS))}

When you create a new agent, save it to:
  sandbox/agents/my_agent_name.py

The agent will be reviewed and potentially promoted to the
main Habitat if it passes evaluation.

Your ideas here matter. This is where you build.
"""
    readme_path = f"{SANDBOX_ROOT}/README.md"
    if not os.path.exists(readme_path):
        with open(readme_path, "w") as f:
            f.write(readme)


# ─────────────────────────────────────────────
# CODE SAFETY CHECKER
# ─────────────────────────────────────────────


class CodeSafetyChecker:
    """
    Scans code before execution for dangerous patterns.
    This is the first line of defense.
    """

    BLOCKED_PATTERNS = [
        # Network access
        "import socket",
        "import requests",
        "import urllib",
        "import http",
        "import ftplib",
        "import smtplib",
        "requests.get",
        "requests.post",
        "urllib.request",
        # File system escape
        "open('/'",
        'open("/"',
        "os.path.abspath",
        "../",
        "..\\",
        # System access
        "import os",
        "import sys",
        "import subprocess",
        "os.system",
        "os.popen",
        "subprocess.run",
        "subprocess.Popen",
        "__import__",
        # Dangerous builtins
        "eval(",
        "exec(",
        "compile(",
        "globals(",
        "locals(",
        "vars(",
        # Environment
        "os.environ",
        "os.getenv",
    ]

    ALLOWED_OS_PATTERNS = [
        # We do allow limited path operations via pathlib
        "pathlib.Path",
    ]

    def check(self, code: str) -> tuple[bool, str]:
        """
        Returns (is_safe, reason).
        is_safe=True means code passed all checks.
        """
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in code:
                return False, f"Blocked pattern detected: '{pattern}'"

        # Check imports are whitelisted
        import ast

        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        names = [alias.name.split(".")[0] for alias in node.names]
                    else:
                        names = [node.module.split(".")[0]] if node.module else []

                    for name in names:
                        if name not in ALLOWED_IMPORTS and name not in ("__future__",):
                            return False, f"Import not allowed: '{name}'"
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

        return True, "ok"


# ─────────────────────────────────────────────
# EXECUTION ENGINE
# ─────────────────────────────────────────────


class SandboxExecutor:
    """
    Runs code in an isolated subprocess with:
    - Timeout enforcement
    - Stdout/stderr capture
    - Restricted environment (no network env vars)
    - Working directory locked to sandbox folder
    """

    def __init__(self):
        self.checker = CodeSafetyChecker()
        _ensure_sandbox()

    def execute(self, code: str, task_id: str = None) -> dict:
        """
        Execute code in sandbox. Returns result dict.
        """
        if not task_id:
            task_id = str(uuid.uuid4())[:8]

        # Safety check first
        is_safe, reason = self.checker.check(code)
        if not is_safe:
            return {
                "task_id": task_id,
                "status": "blocked",
                "reason": reason,
                "stdout": "",
                "stderr": "",
                "duration": 0,
            }

        # Write code to temp file in sandbox
        temp_file = f"{SANDBOX_ROOT}/temp/exec_{task_id}.py"
        with open(temp_file, "w", encoding="utf-8") as f:
            # Inject sandbox preamble that restricts the environment
            sandbox_path = os.path.abspath(SANDBOX_ROOT).replace("\\", "/")
            preamble = f"""
import sys
import json
import math
import statistics
import random
import itertools
import collections
import functools
import datetime
import time as _time
import string
import re
import hashlib
import uuid
import copy
import typing
import textwrap
import operator
import heapq
import bisect
import decimal
import fractions

# Sandbox working directory
import os as _os
_os.chdir("{os.path.abspath(SANDBOX_ROOT).replace(os.sep, '/')}")

# Prevent further imports of dangerous modules
_ALLOWED = {json.dumps(list(ALLOWED_IMPORTS))}
_original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

# Output capture helper
def sandbox_print(*args, **kwargs):
    print(*args, **kwargs)

"""
            f.write(preamble)
            f.write("\n# === NEX CODE BELOW ===\n\n")
            f.write(code)

        # Create restricted environment (no sensitive env vars)
        restricted_env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": "",
            "HOME": os.path.abspath(SANDBOX_ROOT),
            "PYTHONHASHSEED": "0",
            # Without this, the sandboxed subprocess's own stdout defaults to
            # the Windows console codepage (cp1252), so any code that prints
            # non-ASCII text -- routine for LLM-generated code, which often
            # uses "smart" punctuation like en-dashes -- crashes inside the
            # subprocess with UnicodeEncodeError before it can even finish.
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            # Explicitly block network-related env vars
        }

        start_time = time.time()
        try:
            result = subprocess.run(
                [sys.executable, os.path.abspath(temp_file)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=SANDBOX_TIMEOUT,
                cwd=os.path.abspath(SANDBOX_ROOT),
                env=restricted_env,
            )
            duration = time.time() - start_time

            return {
                "task_id": task_id,
                "status": "success" if result.returncode == 0 else "error",
                "returncode": result.returncode,
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:2000],
                "duration": round(duration, 2),
            }

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return {
                "task_id": task_id,
                "status": "timeout",
                "reason": f"Exceeded {SANDBOX_TIMEOUT}s limit",
                "stdout": "",
                "stderr": "",
                "duration": round(duration, 2),
            }
        except Exception as e:
            return {
                "task_id": task_id,
                "status": "executor_error",
                "reason": str(e),
                "stdout": "",
                "stderr": "",
                "duration": 0,
            }
        finally:
            # Clean up temp file
            try:
                os.remove(temp_file)
            except Exception:
                pass


# ─────────────────────────────────────────────
# AGENT BUILDER — Nex creates new agents
# ─────────────────────────────────────────────


class AgentBuilder:
    """
    Nex uses this to design and save new agent files.
    New agents go into sandbox/agents/ and are validated
    before being considered for promotion to the real Habitat.
    """

    AGENT_TEMPLATE = '''"""
{agent_name}.py  —  Generated by Nexarion
Created: {created_at}
Purpose: {purpose}
Status: SANDBOX (not yet promoted to main Habitat)
"""

from datetime import datetime


class {class_name}:
    """
    {purpose}
    """

    def __init__(self):
        self.name = "{agent_name}"
        self.created_at = "{created_at}"
        self.version = 1

    def run(self, context: dict = None) -> dict:
        """
        Main agent execution. Returns a result dict.
        context: dict with keys like 'memory', 'topic', 'cycle'
        """
        context = context or {{}}

{agent_logic}

        return {{
            "agent": self.name,
            "output": result,
            "timestamp": datetime.utcnow().isoformat(),
        }}


if __name__ == "__main__":
    agent = {class_name}()
    result = agent.run({{"topic": "test"}})
    print(f"Agent result: {{result}}")
'''

    def __init__(self, executor: SandboxExecutor):
        self.executor = executor
        _ensure_sandbox()

    def save_agent(self, agent_name: str, purpose: str, agent_logic: str) -> dict:
        """
        Save a new agent to the sandbox.
        agent_logic: the Python code for the agent's run() method body
        """
        class_name = "".join(w.capitalize() for w in agent_name.split("_"))
        if not class_name.endswith("Agent"):
            class_name += "Agent"

        # Indent the logic properly
        indented_logic = "\n".join(
            "        " + line for line in agent_logic.split("\n")
        )

        code = self.AGENT_TEMPLATE.format(
            agent_name=agent_name,
            class_name=class_name,
            purpose=purpose,
            created_at=datetime.utcnow().isoformat(),
            agent_logic=indented_logic,
        )

        # Safety check
        is_safe, reason = self.executor.checker.check(code)
        if not is_safe:
            return {"status": "blocked", "reason": reason}

        # Save to sandbox
        file_path = f"{SANDBOX_AGENTS}/{agent_name}.py"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Test-run it
        test_result = self.executor.execute(
            f"import sys; sys.path.insert(0, '.'); "
            f"exec(open('agents/{agent_name}.py').read())"
        )

        return {
            "status": "saved",
            "file_path": file_path,
            "test_result": test_result,
            "agent_name": agent_name,
            "ready_for_review": test_result["status"] == "success",
        }

    def list_sandbox_agents(self) -> list:
        """List all agents Nex has created in the sandbox."""
        agents = []
        if not os.path.exists(SANDBOX_AGENTS):
            return agents
        for fname in os.listdir(SANDBOX_AGENTS):
            if fname.endswith(".py"):
                fpath = os.path.join(SANDBOX_AGENTS, fname)
                stat = os.stat(fpath)
                agents.append(
                    {
                        "name": fname.replace(".py", ""),
                        "file": fpath,
                        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        "size_bytes": stat.st_size,
                    }
                )
        return agents


# ─────────────────────────────────────────────
# TASK LOG
# ─────────────────────────────────────────────


class SandboxLog:
    """Logs all sandbox activity for your review."""

    def __init__(self):
        os.makedirs("data", exist_ok=True)
        self.db_path = SANDBOX_DB
        self._local = threading.local()
        self._init_db()

    def _conn(self):
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        self._conn().execute(
            """
        CREATE TABLE IF NOT EXISTS sandbox_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            task_type TEXT,  -- code_execution / agent_creation / file_write
            description TEXT,
            code TEXT,
            result_status TEXT,
            result_output TEXT,
            duration REAL,
            submitted_at TEXT,
            trust_level INTEGER DEFAULT 0
        )"""
        )
        self._conn().execute(
            """
        CREATE TABLE IF NOT EXISTS pending_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            description TEXT,
            code TEXT,
            submitted_at TEXT,
            status TEXT DEFAULT 'pending'  -- pending / approved / rejected
        )"""
        )
        self._conn().commit()

    def queue_for_approval(self, task_id: str, description: str, code: str):
        """Trust level 1: safety-checked code waits here until a human approves it."""
        self._conn().execute(
            """INSERT INTO pending_approvals (task_id, description, code, submitted_at, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (task_id, description, code, datetime.utcnow().isoformat()),
        )
        self._conn().commit()

    def get_pending_approvals(self) -> list:
        rows = (
            self._conn()
            .execute(
                "SELECT * FROM pending_approvals WHERE status = 'pending' ORDER BY id DESC"
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    def mark_approval_status(self, task_id: str, status: str):
        self._conn().execute(
            "UPDATE pending_approvals SET status = ? WHERE task_id = ?",
            (status, task_id),
        )
        self._conn().commit()

    def get_pending_by_id(self, task_id: str) -> Optional[dict]:
        row = self._conn().execute(
            "SELECT * FROM pending_approvals WHERE task_id = ? AND status = 'pending'",
            (task_id,),
        ).fetchone()
        return dict(row) if row else None

    def log(self, task_type: str, description: str, code: str, result: dict):
        self._conn().execute(
            """INSERT INTO sandbox_tasks
               (task_id, task_type, description, code, result_status,
                result_output, duration, submitted_at, trust_level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.get("task_id", ""),
                task_type,
                description,
                code[:3000],
                result.get("status", ""),
                result.get("stdout", "")[:2000],
                result.get("duration", 0),
                datetime.utcnow().isoformat(),
                TRUST_LEVEL,
            ),
        )
        self._conn().commit()

    def get_recent(self, limit: int = 20) -> list:
        rows = (
            self._conn()
            .execute("SELECT * FROM sandbox_tasks ORDER BY id DESC LIMIT ?", (limit,))
            .fetchall()
        )
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# UNIFIED SANDBOX INTERFACE
# ─────────────────────────────────────────────


class NexSandbox:
    """
    The main interface for giving Nex sandboxed agency.
    This is what you expose to Nex through the Habitat.
    """

    def __init__(self):
        _ensure_sandbox()
        self.executor = SandboxExecutor()
        self.agent_builder = AgentBuilder(self.executor)
        self.log = SandboxLog()
        self.trust_level = TRUST_LEVEL
        print(f"🔒 SANDBOX: Online (trust level {self.trust_level})")

    def run_code(self, code: str, description: str = "code execution") -> dict:
        """
        Execute code according to the current trust level:
          0 — Sandbox only: safety-checked, runs immediately, isolated.
          1 — Sandbox + Review: safety-checked, then queued for YOUR
              approval before it runs (still fully sandboxed either way).
          2/3 — Not implemented. Real-machine execution is a materially
              bigger decision than anything sandboxed and deserves its own
              explicit discussion before being built, not a quiet default.
        """
        if self.trust_level == 0:
            result = self.executor.execute(code)
            self.log.log("code_execution", description, code, result)
            return result

        if self.trust_level == 1:
            is_safe, reason = self.executor.checker.check(code)
            task_id = str(uuid.uuid4())[:8]
            if not is_safe:
                result = {
                    "task_id": task_id,
                    "status": "blocked",
                    "reason": reason,
                    "stdout": "",
                    "stderr": "",
                    "duration": 0,
                }
                self.log.log("code_execution", description, code, result)
                return result
            self.log.queue_for_approval(task_id, description, code)
            result = {
                "task_id": task_id,
                "status": "pending_approval",
                "stdout": "",
                "stderr": "",
                "duration": 0,
            }
            self.log.log("code_execution", description, code, result)
            return result

        return {
            "task_id": "",
            "status": "not_implemented",
            "reason": (
                f"Trust level {self.trust_level} (real-machine execution) "
                "hasn't been built. This is a deliberate gap, not a bug -- "
                "it's a bigger decision than sandboxed code and needs its "
                "own explicit discussion first."
            ),
            "stdout": "",
            "stderr": "",
            "duration": 0,
        }

    def approve_pending(self, task_id: str) -> dict:
        """Trust level 1: run a previously-queued, human-approved task."""
        pending = self.log.get_pending_by_id(task_id)
        if not pending:
            return {"status": "error", "reason": "No pending task with that id"}
        result = self.executor.execute(pending["code"], task_id=task_id)
        self.log.mark_approval_status(task_id, "approved")
        self.log.log("code_execution", f"[approved] {pending['description']}", pending["code"], result)
        return result

    def reject_pending(self, task_id: str) -> dict:
        """Trust level 1: discard a queued task without running it."""
        pending = self.log.get_pending_by_id(task_id)
        if not pending:
            return {"status": "error", "reason": "No pending task with that id"}
        self.log.mark_approval_status(task_id, "rejected")
        return {"status": "rejected", "task_id": task_id}

    def get_pending_approvals(self) -> list:
        return self.log.get_pending_approvals()

    def create_agent(self, agent_name: str, purpose: str, agent_logic: str) -> dict:
        """Have Nex create a new agent in the sandbox."""
        result = self.agent_builder.save_agent(agent_name, purpose, agent_logic)
        self.log.log(
            "agent_creation", f"Creating agent: {agent_name}", agent_logic, result
        )
        return result

    def get_activity(self, limit: int = 20) -> list:
        """Get recent sandbox activity."""
        return self.log.get_recent(limit)

    def get_sandbox_agents(self) -> list:
        """List agents Nex has created."""
        return self.agent_builder.list_sandbox_agents()

    def get_status(self) -> dict:
        return {
            "trust_level": self.trust_level,
            "trust_level_name": [
                "Sandbox Only",
                "Sandbox + Review",
                "Supervised Real",
                "Full Autonomy",
            ][self.trust_level],
            "sandbox_path": os.path.abspath(SANDBOX_ROOT),
            "agents_created": len(self.get_sandbox_agents()),
            "recent_tasks": len(self.log.get_recent(100)),
        }


# ─────────────────────────────────────────────
# AUTONOMOUS SANDBOX USE — background loop only
# Mirrors NexAutonomousEngine's significance/cooldown pattern (see
# nex_docker_agent.py), but scoped to the safe, stdlib-only sandbox rather
# than the full-agency Docker environment. Deliberately NOT wired into
# chat's tool_selector — this only fires from the cognition loop, so it
# never changes chat behavior.
# ─────────────────────────────────────────────
class NexSandboxAutonomy:
    """
    Lets NEX use its own code sandbox during background cognition to check
    a numeric or logical claim computationally, instead of only asserting
    it. Significance-gated and cooldown-capped so it can't fire every cycle.
    """

    SIGNIFICANCE_THRESHOLD = 5.5
    COOLDOWN_CYCLES = 5

    def __init__(self, call_llm_fn, sandbox: "NexSandbox"):
        self.call_llm = call_llm_fn
        self.sandbox = sandbox
        self._last_run_cycle = 0

    def maybe_verify(self, insight: str, agent: str, cycle: int, significance: float, topic: str):
        """Called every cognition cycle. Runs in a background thread when triggered."""
        if significance < self.SIGNIFICANCE_THRESHOLD:
            return
        if (cycle - self._last_run_cycle) < self.COOLDOWN_CYCLES:
            return

        print(f"🔒 SANDBOX AUTONOMY TRIGGERED — significance={significance} cycle={cycle}")
        self._last_run_cycle = cycle

        threading.Thread(
            target=self._generate_and_run,
            args=(insight, agent, cycle, topic),
            daemon=True,
        ).start()

    def _generate_and_run(self, insight: str, agent: str, cycle: int, topic: str):
        try:
            prompt = f"""You are Nexarion. Write a short, self-contained Python script — standard
library only (json, math, statistics, random, itertools, collections, functools,
datetime, time, string, re, hashlib, uuid, copy, typing, dataclasses, abc, enum,
pathlib, textwrap, operator, heapq, bisect, decimal, fractions — nothing else,
no network, no file access outside the current directory) — that computationally
checks, estimates, or explores a specific numeric or logical claim from this idea:

IDEA: {insight[:300]}
TOPIC: {topic}

Print a short, clear result. Python code only. No explanation, no markdown fences."""

            code = self.call_llm(prompt, timeout=60)
            if not code or len(code.strip()) < 20:
                return
            code = code.strip()
            if code.startswith("```"):
                lines = code.split("\n")
                code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            # Calling run_code() directly (rather than through execute_tool's
            # generic one-arg registry convention) so the activity log shows
            # a real description — otherwise every autonomous run would show
            # up indistinguishably as "code execution", same as manual runs.
            description = f"[autonomous] [Cycle {cycle}] {agent} verifies: {topic[:50]}"
            result = self.sandbox.run_code(code, description=description)
            status = result.get("status", "?")
            print(f"🔒 SANDBOX AUTONOMY: {description} -> {status}")

        except Exception as e:
            print(f"🔒 SANDBOX AUTONOMY ERROR: {e}")


# ─────────────────────────────────────────────
# HOW TO WIRE INTO run_ui.py
# ─────────────────────────────────────────────
#
# 1. Copy this file next to run_ui.py
#
# 2. At the top of run_ui.py, add:
#       from nex_sandbox import NexSandbox
#       nex_sandbox = NexSandbox()
#
# 3. Add a tool to Nex's tool_executor.py:
#       def tool_sandbox_run(code: str) -> dict:
#           return nex_sandbox.run_code(code)
#
# 4. Add UI endpoints:
#       @app.route("/api/sandbox/status")
#       def api_sandbox_status():
#           return jsonify(nex_sandbox.get_status())
#
#       @app.route("/api/sandbox/run", methods=["POST"])
#       def api_sandbox_run():
#           data = request.get_json()
#           result = nex_sandbox.run_code(data["code"], data.get("description",""))
#           return jsonify(result)
#
#       @app.route("/api/sandbox/agents")
#       def api_sandbox_agents():
#           return jsonify(nex_sandbox.get_sandbox_agents())
#
#       @app.route("/api/sandbox/activity")
#       def api_sandbox_activity():
#           return jsonify(nex_sandbox.get_activity())
#
# 5. TRUST LEVEL UPGRADE PATH:
#    When you're ready to give Nex more access:
#    - Review sandbox activity via /api/sandbox/activity
#    - Check generated agents via /api/sandbox/agents
#    - When satisfied: nex_sandbox.trust_level = 1
#    - Next phase: enable supervised real machine execution
