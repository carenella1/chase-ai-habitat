"""
nex_docker_api.py
Flask API server running INSIDE the Docker container.
Chase's Habitat calls this to give Nex full Linux agency.
"""

import os
import sys
import json
import time
import uuid
import subprocess
import threading
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

WORKSPACE = "/nex_workspace"
LOG_FILE = "/nex_workspace/data/activity.jsonl"
os.makedirs("/nex_workspace/data", exist_ok=True)


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
    """Execute any Python code with full permissions."""
    data = request.get_json()
    code = data.get("code", "")
    description = data.get("description", "execution")
    timeout = data.get("timeout", 60)

    task_id = str(uuid.uuid4())[:8]
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
    path = data.get("path", "").lstrip("/")
    content = data.get("content", "")

    full_path = os.path.join(WORKSPACE, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, "w") as f:
        f.write(content)

    result = {"status": "written", "path": full_path, "size": len(content)}
    log_activity("file_write", f"Write {path}", content[:200], result)
    return jsonify(result)


@app.route("/read_file", methods=["GET"])
def read_file():
    """Read a file from Nex's workspace."""
    path = request.args.get("path", "").lstrip("/")
    full_path = os.path.join(WORKSPACE, path)
    if not os.path.exists(full_path):
        return jsonify({"error": "File not found"}), 404
    with open(full_path, "r") as f:
        content = f.read()
    return jsonify({"path": path, "content": content, "size": len(content)})


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
