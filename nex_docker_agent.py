"""
nex_docker_agent.py
Lives in your project root alongside run_ui.py.
This is how the Habitat talks to Nex's Docker container.
"""

import requests
import json
import time
import threading
import sqlite3
import os
from datetime import datetime

DOCKER_URL = "http://localhost:7700"
DOCKER_TIMEOUT = 90
DB_PATH = "data/docker_tasks.db"

# ─────────────────────────────────────────────
# TASK DATABASE — everything Nex does is logged
# ─────────────────────────────────────────────


class DockerTaskLog:
    def __init__(self):
        os.makedirs("data", exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _conn(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                DB_PATH, check_same_thread=False, timeout=30
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        self._conn().execute(
            """
            CREATE TABLE IF NOT EXISTS docker_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                task_type TEXT,
                description TEXT,
                code TEXT,
                status TEXT,
                output TEXT,
                duration REAL,
                cycle INTEGER,
                agent TEXT,
                significance REAL,
                submitted_at TEXT
            )
        """
        )
        self._conn().commit()

    def log(
        self, task_type, description, code, result, cycle=0, agent="", significance=0
    ):
        self._conn().execute(
            """
            INSERT INTO docker_tasks
            (task_id, task_type, description, code, status, output, duration, cycle, agent, significance, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                result.get("task_id", ""),
                task_type,
                description,
                (code or "")[:3000],
                result.get("status", ""),
                (result.get("stdout") or result.get("output", ""))[:3000],
                result.get("duration", 0),
                cycle,
                agent,
                significance,
                datetime.utcnow().isoformat(),
            ),
        )
        self._conn().commit()

    def get_recent(self, limit=30):
        rows = (
            self._conn()
            .execute("SELECT * FROM docker_tasks ORDER BY id DESC LIMIT ?", (limit,))
            .fetchall()
        )
        return [dict(r) for r in rows]

    def get_stats(self):
        conn = self._conn()
        total = conn.execute("SELECT COUNT(*) as n FROM docker_tasks").fetchone()["n"]
        success = conn.execute(
            "SELECT COUNT(*) as n FROM docker_tasks WHERE status='success'"
        ).fetchone()["n"]
        files_written = conn.execute(
            "SELECT COUNT(*) as n FROM docker_tasks WHERE task_type='file_write'"
        ).fetchone()["n"]
        return {
            "total_tasks": total,
            "successful": success,
            "files_written": files_written,
        }


# ─────────────────────────────────────────────
# MAIN DOCKER AGENT
# ─────────────────────────────────────────────


class NexDockerAgent:
    """
    The bridge between Nex's Habitat and his Docker workspace.
    Nex calls this to act in the real world.
    """

    def __init__(self):
        self.task_log = DockerTaskLog()
        self._online = False
        self._check_connection()
        print(
            f"🐳 DOCKER AGENT: {'Online' if self._online else 'Offline — start container first'}"
        )

    def _check_connection(self):
        try:
            r = requests.get(f"{DOCKER_URL}/status", timeout=5)
            self._online = r.status_code == 200
        except Exception:
            self._online = False

    def is_online(self):
        self._check_connection()
        return self._online

    def get_status(self):
        if not self.is_online():
            return {"online": False, "error": "Container not running"}
        try:
            r = requests.get(f"{DOCKER_URL}/status", timeout=10)
            data = r.json()
            data["online"] = True
            stats = self.task_log.get_stats()
            data.update(stats)
            return data
        except Exception as e:
            return {"online": False, "error": str(e)}

    def execute(
        self, code, description="autonomous task", cycle=0, agent="", significance=0
    ):
        """Run Python code in Nex's Docker environment."""
        if not self.is_online():
            return {
                "status": "offline",
                "stdout": "",
                "stderr": "Docker container not running",
            }

        try:
            r = requests.post(
                f"{DOCKER_URL}/execute",
                json={
                    "code": code,
                    "description": description,
                    "timeout": DOCKER_TIMEOUT,
                },
                timeout=DOCKER_TIMEOUT + 10,
            )
            result = r.json()
            self.task_log.log(
                "code_execution", description, code, result, cycle, agent, significance
            )
            print(
                f"🐳 DOCKER: {description[:50]} → {result.get('status')} ({result.get('duration')}s)"
            )
            return result
        except Exception as e:
            result = {"status": "error", "stdout": "", "stderr": str(e), "duration": 0}
            self.task_log.log(
                "code_execution", description, code, result, cycle, agent, significance
            )
            return result

    def write_file(self, path, content, cycle=0, agent=""):
        """Write a file into Nex's Docker workspace."""
        if not self.is_online():
            return {"status": "offline"}
        try:
            r = requests.post(
                f"{DOCKER_URL}/write_file",
                json={"path": path, "content": content},
                timeout=30,
            )
            result = r.json()
            self.task_log.log(
                "file_write", f"Write {path}", content[:200], result, cycle, agent
            )
            print(f"🐳 FILE WRITTEN: {path} ({len(content)} bytes)")
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def list_files(self):
        """See everything Nex has built."""
        if not self.is_online():
            return []
        try:
            r = requests.get(f"{DOCKER_URL}/files", timeout=10)
            return r.json().get("files", [])
        except Exception:
            return []

    def get_activity(self, limit=30):
        """Get recent Docker activity."""
        return self.task_log.get_recent(limit)

    def read_file(self, path):
        """Read a file from Nex's workspace."""
        if not self.is_online():
            return None
        try:
            r = requests.get(
                f"{DOCKER_URL}/read_file", params={"path": path}, timeout=10
            )
            return r.json().get("content")
        except Exception:
            return None


# ─────────────────────────────────────────────
# AUTONOMOUS TASK ENGINE
# Nex decides what to build based on his cognition
# ─────────────────────────────────────────────


class NexAutonomousEngine:
    """
    Watches Nex's cognition loop.
    When significance is high enough, generates and submits a build task.
    This is what makes Nex *want* to use his Docker environment.
    """

    SIGNIFICANCE_THRESHOLD = 7.0
    COOLDOWN_CYCLES = 5

    def __init__(self, docker_agent: NexDockerAgent, call_llm_fn):
        self.docker = docker_agent
        self.call_llm = call_llm_fn
        self._last_task_cycle = 0
        self._tasks_submitted = 0

    def maybe_build(self, insight, agent, cycle, significance, topic, memory):
        """
        Called every cognition cycle.
        If conditions are right, Nex generates and runs a build task.
        """
        if not self.docker.is_online():
            return

        if significance < self.SIGNIFICANCE_THRESHOLD:
            return

        if (cycle - self._last_task_cycle) < self.COOLDOWN_CYCLES:
            return

        print(
            f"🐳 AUTONOMOUS BUILD TRIGGERED — significance={significance} cycle={cycle}"
        )
        self._last_task_cycle = cycle
        self._tasks_submitted += 1

        # Run the build in background so cognition loop isn't blocked
        threading.Thread(
            target=self._generate_and_run,
            args=(insight, agent, cycle, significance, topic, memory),
            daemon=True,
        ).start()

    def _generate_and_run(self, insight, agent, cycle, significance, topic, memory):
        """Ask Nex's deep brain to generate a build task, then run it."""
        try:
            top_topics = list(memory.get("topic_scores", {}).keys())[:5]

            prompt = f"""You are Nexarion — an AI with a Linux Docker environment where you can run any Python code.

Your current thought (significance {significance}/10):
{insight[:600]}

Topic: {topic}
Your top interests: {', '.join(top_topics)}
Agent perspective: {agent}

Based on this thought, write a Python script that BUILDS or COMPUTES something real.
Ideas: data analysis, simulation, mathematical exploration, algorithm implementation,
       network graph construction, generating a research report, building a tool.

Rules:
- Use only packages available: requests, numpy, pandas, scipy, networkx, scikit-learn, sympy, matplotlib
- Save interesting outputs to /nex_workspace/outputs/
- Print a clear summary of what you built and what you found
- Be creative — this is your chance to ACT on your ideas, not just think about them
- Keep it under 60 seconds of execution time

Write ONLY the Python code. No explanation. No markdown. Just the code."""

            from llm_router import call_llm_deep

            result = call_llm_deep(prompt, timeout=180)
            code = result.get("response", "").strip()

            if not code or len(code) < 50:
                print("🐳 BUILD ABORTED: No code generated")
                return

            # Strip markdown if model wrapped it
            if code.startswith("```"):
                lines = code.split("\n")
                code = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            description = f"[Cycle {cycle}] {agent} builds on: {topic[:50]}"
            self.docker.execute(
                code=code,
                description=description,
                cycle=cycle,
                agent=agent,
                significance=significance,
            )

        except Exception as e:
            print(f"🐳 BUILD ERROR: {e}")
