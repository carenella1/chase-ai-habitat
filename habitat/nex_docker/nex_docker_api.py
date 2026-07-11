"""
nex_docker_api.py
Flask API server running INSIDE the Docker container.
Chase's Habitat calls this to give Nex full Linux agency.

This container is deliberately full-agency by design (see the Dockerfile
identity message: "full access to Python, the filesystem, and the
internet") -- that is intentional and not something this file overrides.
What IS hardened here:
  - A path-traversal bug in /write_file and /read_file: a path like
    "../../etc/passwd" previously escaped the workspace directory
    entirely, since the old code only stripped a leading slash.
  - A guard against a narrow set of catastrophically destructive
    commands (wiping the filesystem, forkbombs, killing the API's own
    process) -- a seatbelt against self-inflicted disaster, not a
    general sandbox. Network access and the Python stdlib/installed
    packages remain fully available, matching the container's design.
"""

import os
import sys
import json
import time
import uuid
import base64
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify

app = Flask(__name__)

IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
}

WORKSPACE = "/nex_workspace"
LOG_FILE = "/nex_workspace/data/activity.jsonl"
os.makedirs("/nex_workspace/data", exist_ok=True)

MAX_CODE_SIZE = 200_000  # 200KB -- generous, but not unbounded

# Catastrophic patterns to block outright, regardless of the container's
# otherwise-full agency. These aren't "dangerous capabilities" (network,
# subprocess, file access are all intentionally available) -- they're
# specifically self-destructive or self-sabotaging actions.
CATASTROPHIC_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "shutil.rmtree('/')",
    'shutil.rmtree("/")',
    "shutil.rmtree('/nex_workspace')",
    'shutil.rmtree("/nex_workspace")',
    ":(){ :|:& };:",  # classic bash forkbomb
    "mkfs.",
    "dd if=/dev/zero of=/dev/",
    "pkill -9 python",
    "killall -9 python",
]


def _check_catastrophic(code: str):
    """Returns (is_safe, reason). Only blocks clearly self-destructive
    actions -- not a general safety check."""
    for pattern in CATASTROPHIC_PATTERNS:
        if pattern in code:
            return False, f"Blocked catastrophic pattern: '{pattern}'"
    return True, "ok"


def _resolve_within_workspace(path: str):
    """
    Resolve a user-supplied path safely within WORKSPACE, rejecting any
    attempt to escape it via '..' segments or an absolute path pointing
    elsewhere. Returns the resolved absolute path, or None if unsafe.
    """
    candidate = (Path(WORKSPACE) / path.lstrip("/")).resolve()
    workspace_root = Path(WORKSPACE).resolve()
    if candidate == workspace_root or workspace_root in candidate.parents:
        return str(candidate)
    return None


def log_activity(task_type, description, code, result):
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "task_type": task_type,
        "description": description,
        "code_preview": (code or "")[:300],
        "status": result.get("status", ""),
        "output_preview": (result.get("stdout") or result.get("output", ""))[:500],
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


@app.route("/status", methods=["GET"])
def status():
    """Health check — confirms container is alive."""
    files = []
    for root, dirs, filenames in os.walk(WORKSPACE):
        dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git"]]
        for fname in filenames:
            fpath = os.path.join(root, fname)
            files.append(fpath.replace(WORKSPACE, ""))
    return jsonify(
        {
            "status": "online",
            "workspace": WORKSPACE,
            "python": sys.version,
            "file_count": len(files),
            "files": files[:50],
            "timestamp": datetime.utcnow().isoformat(),
        }
    )


@app.route("/execute", methods=["POST"])
def execute():
    """Execute Python code with full permissions, except for a narrow
    blocklist of catastrophically self-destructive actions."""
    data = request.get_json()
    code = data.get("code", "")
    description = data.get("description", "execution")
    timeout = data.get("timeout", 60)

    task_id = str(uuid.uuid4())[:8]

    if len(code) > MAX_CODE_SIZE:
        out = {
            "task_id": task_id,
            "status": "blocked",
            "reason": f"Code exceeds {MAX_CODE_SIZE} byte limit",
            "stdout": "",
            "stderr": "",
            "duration": 0,
        }
        log_activity("code_execution", description, code[:500], out)
        return jsonify(out)

    is_safe, reason = _check_catastrophic(code)
    if not is_safe:
        out = {
            "task_id": task_id,
            "status": "blocked",
            "reason": reason,
            "stdout": "",
            "stderr": "",
            "duration": 0,
        }
        log_activity("code_execution", description, code, out)
        return jsonify(out)

    tmp_file = f"/tmp/nex_{task_id}.py"

    with open(tmp_file, "w") as f:
        f.write(code)

    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, tmp_file],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=WORKSPACE,
        )
        duration = round(time.time() - start, 2)
        out = {
            "task_id": task_id,
            "status": "success" if result.returncode == 0 else "error",
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode,
            "duration": duration,
        }
    except subprocess.TimeoutExpired:
        out = {
            "task_id": task_id,
            "status": "timeout",
            "stdout": "",
            "stderr": "",
            "duration": timeout,
        }
    except Exception as e:
        out = {
            "task_id": task_id,
            "status": "error",
            "stdout": "",
            "stderr": str(e),
            "duration": 0,
        }
    finally:
        try:
            os.remove(tmp_file)
        except Exception:
            pass

    log_activity("code_execution", description, code, out)
    return jsonify(out)


@app.route("/write_file", methods=["POST"])
def write_file():
    """Write a file into Nex's workspace."""
    data = request.get_json()
    path = data.get("path", "")
    content = data.get("content", "")

    full_path = _resolve_within_workspace(path)
    if full_path is None:
        result = {"status": "blocked", "reason": "Path escapes workspace"}
        log_activity("file_write", f"Blocked write {path}", content[:200], result)
        return jsonify(result), 400

    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, "w") as f:
        f.write(content)

    result = {"status": "written", "path": full_path, "size": len(content)}
    log_activity("file_write", f"Write {path}", content[:200], result)
    return jsonify(result)


@app.route("/read_file", methods=["GET"])
def read_file():
    """Read a file from Nex's workspace. Images come back base64-encoded
    (SVG excluded — it's text and reads fine as content); everything else
    is read as text, same as before."""
    path = request.args.get("path", "")
    full_path = _resolve_within_workspace(path)
    if full_path is None:
        return jsonify({"error": "Path escapes workspace"}), 400
    if not os.path.exists(full_path):
        return jsonify({"error": "File not found"}), 404

    ext = os.path.splitext(full_path)[1].lower()
    mime_type = IMAGE_MIME_TYPES.get(ext)

    if mime_type and ext != ".svg":
        with open(full_path, "rb") as f:
            raw = f.read()
        return jsonify(
            {
                "path": path,
                "is_binary": True,
                "mime_type": mime_type,
                "content_base64": base64.b64encode(raw).decode("ascii"),
                "size": len(raw),
            }
        )

    with open(full_path, "r") as f:
        content = f.read()
    return jsonify(
        {"path": path, "is_binary": False, "content": content, "size": len(content)}
    )


@app.route("/files", methods=["GET"])
def list_files():
    """List all files Nex has created."""
    files = []
    for root, dirs, filenames in os.walk(WORKSPACE):
        dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git"]]
        for fname in filenames:
            fpath = os.path.join(root, fname)
            stat = os.stat(fpath)
            files.append(
                {
                    "path": fpath.replace(WORKSPACE, ""),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )
    return jsonify({"files": files, "count": len(files)})


@app.route("/activity", methods=["GET"])
def activity():
    """Return recent activity log."""
    entries = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
    return jsonify({"activity": list(reversed(entries[-50:]))})


if __name__ == "__main__":
    print("🐳 NEX DOCKER API ONLINE — port 7700")
    print(f"📁 Workspace: {WORKSPACE}")
    app.run(host="0.0.0.0", port=7700, debug=False)
