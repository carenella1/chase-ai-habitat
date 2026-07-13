"""
creative_engine.py  —  NEX's Creative (image generation) subsystem

WHAT THIS IS:
  A bridge to ComfyUI, exactly the way llm_router.py is a bridge to Ollama:
  ComfyUI runs as its own local process on http://127.0.0.1:8188, and this
  module checks if it's up, launches it if not, submits image generation
  jobs to it, and reports back progress + the finished image.

CRITICAL — VRAM SHARING WITH OLLAMA:
  Chase's GPU has 16GB VRAM shared between the LLM (Ollama) and the image
  model (ComfyUI). The two must never be resident at once. Before every
  generation job this module:
    1. asks Ollama to unload its current model (`keep_alive: 0`)
    2. polls Ollama's /api/ps until it reports no loaded models (or gives up
       after 15s and proceeds anyway rather than hanging a job forever)
    3. only then submits the job to ComfyUI
  After the job finishes, it calls ComfyUI's own /free endpoint to release
  the image model's VRAM again. Nothing needs to re-warm Ollama afterwards —
  llm_router already loads models on demand on the next chat call.

  This module never touches llm_router.py's functions except reading its
  public OLLAMA_BASE constant and calling its existing get_chat_model() —
  no changes to that file's public API.

FAILURE HANDLING:
  ComfyUI isn't installed on this machine yet (see install_creative.md), and
  neither are the two model files. Every step that depends on either one
  fails with a specific, human-readable message (which file's missing, which
  folder it goes in) instead of a raw exception — the /creative/generate
  route surfaces that message directly to the UI.
"""

import json
import os
import random
import re
import sqlite3
import subprocess
import threading
import time
import uuid
from datetime import datetime

import requests

from llm_router import OLLAMA_BASE, get_chat_model

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

COMFYUI_URL = "http://127.0.0.1:8188"
COMFYUI_WS_URL = "ws://127.0.0.1:8188"

# Chase: update this if you install ComfyUI somewhere other than C:\ComfyUI.
# See install_creative.md for the full setup walkthrough.
#
# The Windows portable build unpacks as a *root* folder (COMFYUI_ROOT)
# containing three siblings: python_embeded\ (its own bundled Python),
# ComfyUI\ (the actual app — main.py and models\ live here), and the
# run_nvidia_gpu.bat launcher. COMFYUI_DIR below points at that inner
# ComfyUI\ folder, matching what run_nvidia_gpu.bat itself does:
#   python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build
COMFYUI_ROOT = r"C:\ComfyUI"
COMFYUI_DIR = os.path.join(COMFYUI_ROOT, "ComfyUI")
COMFYUI_PYTHON = os.path.join(COMFYUI_ROOT, "python_embeded", "python.exe")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WORKFLOWS_DIR = os.path.join(PROJECT_ROOT, "workflows")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "static", "creative_outputs")
DB_PATH = os.path.join(PROJECT_ROOT, "data", "creative.db")

MAX_GENERATIONS = 2000  # retention cap on the gallery log

WORKFLOWS = {
    "turbo": "z_image_turbo.json",
    "quality": "flux2_klein_quality.json",
}

MODEL_LABELS = {
    "turbo": "Z-Image Turbo (fast, 8 steps)",
    "quality": "FLUX.2 klein (quality)",
}

# Which model files each workflow needs, and which ComfyUI subfolder(s) they
# may legitimately live in. check_model_files() uses this to give an exact,
# actionable error instead of letting ComfyUI reject the job with a 400.
#
# These filenames match what's actually sitting in C:\ComfyUI\ComfyUI\models\
# as of the 2026-07-11 install check — not invented placeholders. Note the
# FLUX unet file Chase has is the 9B build (flux-2-klein-9b.safetensors,
# ~18GB on disk) — no 4B build is published, so this is what's actually
# available; it's too big to fit fully in 16GB VRAM, so it'll spill to CPU
# and run slower than the fast option. See install_creative.md — as of the
# last check, clip_l.safetensors is the only file still missing.
CHECKPOINT_FILES = {
    "turbo": [
        (["checkpoints"], ["z-image-turbo-fp8-aio.safetensors"]),
    ],
    "quality": [
        (["unet", "diffusion_models"], ["flux-2-klein-9b.safetensors"]),
        (["clip"], ["t5xxl_fp8_e4m3fn.safetensors"]),
        (["clip"], ["clip_l.safetensors"]),
        (["vae"], ["ae.safetensors"]),
    ],
}


class CreativeError(Exception):
    """Any failure in the generation pipeline that already has a clear,
    human-readable explanation — gets shown to Chase as-is, no traceback."""


class JobCancelled(Exception):
    """Raised internally when a background job notices mid-run that the
    user cancelled it. cancel_job() has already written the terminal DB
    status by the time this is raised, so _run_job just needs to stop
    quietly instead of overwriting that with an error."""


# ─────────────────────────────────────────────
# JOB / GALLERY DATABASE
# ─────────────────────────────────────────────


class CreativeJobLog:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
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
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT UNIQUE,
                prompt TEXT,
                negative_prompt TEXT,
                model_choice TEXT,
                width INTEGER,
                height INTEGER,
                lora_name TEXT,
                lora_strength REAL,
                image_path TEXT,
                status TEXT,
                error TEXT,
                created_at TEXT
            )
            """
        )
        # Added after the first ship — guarded so this is safe to run
        # against a DB that already has these columns. Same idiom as
        # structured_memory.py / self_optimizer.py's migrations.
        for stmt in (
            "ALTER TABLE generations ADD COLUMN source TEXT DEFAULT 'user'",
            "ALTER TABLE generations ADD COLUMN artist_note TEXT DEFAULT ''",
            "ALTER TABLE generations ADD COLUMN origin_agent TEXT DEFAULT ''",
        ):
            try:
                self._conn().execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists

        # Any job still in a non-terminal status is a leftover from the
        # last time this process ran — its background thread died with the
        # process, so nothing was ever going to write it an error. Left
        # alone it would sit as "generating" forever with no way for the
        # UI to know it's dead. Runs once per engine startup, not per job.
        self._conn().execute(
            """
            UPDATE generations SET status = 'error',
                error = 'Interrupted — NEX restarted before this finished.'
            WHERE status NOT IN ('done', 'error', 'cancelled')
            """
        )
        self._conn().commit()

    def create(
        self,
        job_id,
        prompt,
        negative_prompt,
        model_choice,
        width,
        height,
        lora_name,
        lora_strength,
        source="user",
        artist_note="",
        origin_agent="",
    ):
        self._conn().execute(
            """
            INSERT INTO generations
            (job_id, prompt, negative_prompt, model_choice, width, height,
             lora_name, lora_strength, image_path, status, error, created_at,
             source, artist_note, origin_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                prompt,
                negative_prompt or "",
                model_choice,
                width,
                height,
                lora_name or "",
                lora_strength or 0,
                "",
                "queued",
                "",
                datetime.utcnow().isoformat(),
                source,
                artist_note or "",
                origin_agent or "",
            ),
        )
        self._conn().execute(
            """DELETE FROM generations WHERE id IN (
                   SELECT id FROM generations ORDER BY id ASC
                   LIMIT MAX(0, (SELECT COUNT(*) FROM generations) - ?)
               )""",
            (MAX_GENERATIONS,),
        )
        self._conn().commit()

    def update(self, job_id, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [job_id]
        self._conn().execute(
            f"UPDATE generations SET {cols} WHERE job_id = ?", values
        )
        self._conn().commit()

    def get(self, job_id):
        row = self._conn().execute(
            "SELECT * FROM generations WHERE job_id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_recent(self, limit=50):
        rows = self._conn().execute(
            "SELECT * FROM generations ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, job_id):
        row = self.get(job_id)
        if not row:
            return None
        self._conn().execute("DELETE FROM generations WHERE job_id = ?", (job_id,))
        self._conn().commit()
        return row

    def get_last_created_at(self, source):
        """Most recent created_at for a given source ('user' or 'nex'), or
        None. Counts every attempt, successful or not — same principle as
        deep_research_trigger's cooldown-before-completion: a failed
        autonomous attempt still consumes that day's slot rather than
        retrying in a tight loop."""
        row = self._conn().execute(
            "SELECT MAX(created_at) as ts FROM generations WHERE source = ?",
            (source,),
        ).fetchone()
        return row["ts"] if row else None


# ─────────────────────────────────────────────
# MAIN ENGINE
# ─────────────────────────────────────────────


class CreativeEngine:
    """
    NEX's bridge to ComfyUI. Owns the job log, tracks in-flight generation
    progress, and handles the full VRAM-safe generate pipeline.
    """

    def __init__(self):
        self.job_log = CreativeJobLog()
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        self._progress = {}  # job_id -> int 0-100, cleared when the job ends
        self._cancel_events = {}  # job_id -> threading.Event, cleared when the job ends
        self._comfy_starting = False
        self._comfy_start_error = None

    # ---- ComfyUI process management ----

    def is_online(self):
        try:
            r = requests.get(f"{COMFYUI_URL}/system_stats", timeout=4)
            return r.status_code == 200
        except Exception:
            return False

    def get_status(self):
        return {
            "online": self.is_online(),
            "starting": self._comfy_starting,
            "start_error": self._comfy_start_error,
            "comfyui_dir_found": os.path.isdir(COMFYUI_DIR),
            "models": {
                choice: self.check_model_files(choice)[0] for choice in WORKFLOWS
            },
        }

    def cancel_job(self, job_id):
        """User-initiated stop. Best-effort: flags the background thread to
        bail at its next checkpoint, tells ComfyUI to interrupt whatever
        it's currently running (so the GPU actually frees up instead of
        grinding on unwatched), and marks the job cancelled so the UI can
        stop polling. Safe to call on a job that already finished — no-op."""
        row = self.job_log.get(job_id)
        if not row or row["status"] in ("done", "error", "cancelled"):
            return False

        event = self._cancel_events.get(job_id)
        if event:
            event.set()

        try:
            requests.post(f"{COMFYUI_URL}/interrupt", timeout=5)
        except Exception as e:
            print(f"🎨 CREATIVE: /interrupt call failed (non-fatal): {e}")

        self.job_log.update(job_id, status="cancelled", error="Cancelled by user.")
        self._progress.pop(job_id, None)
        return True

    def _check_cancelled(self, job_id):
        event = self._cancel_events.get(job_id)
        if event and event.is_set():
            raise JobCancelled()

    def start_comfyui(self):
        if self.is_online():
            return {"status": "online", "message": "Already running"}
        if self._comfy_starting:
            return {"status": "starting", "message": "Already starting"}
        if not os.path.isdir(COMFYUI_DIR):
            self._comfy_start_error = (
                f"ComfyUI isn't installed at the expected location ({COMFYUI_DIR}). "
                "See install_creative.md for setup steps."
            )
            return {"status": "error", "message": self._comfy_start_error}

        self._comfy_starting = True
        self._comfy_start_error = None
        threading.Thread(target=self._start_comfyui_worker, daemon=True).start()
        return {"status": "starting", "message": "Starting ComfyUI..."}

    def _start_comfyui_worker(self):
        try:
            main_py = os.path.join(COMFYUI_DIR, "main.py")
            if not os.path.exists(main_py):
                self._comfy_start_error = (
                    f"Could not find main.py in {COMFYUI_DIR} — is this really "
                    "a ComfyUI install? See install_creative.md."
                )
                return

            python_exe = (
                COMFYUI_PYTHON if os.path.exists(COMFYUI_PYTHON) else "python"
            )
            try:
                # Mirrors run_nvidia_gpu.bat exactly (same embedded Python,
                # same relative main.py path, same cwd) so this behaves
                # identically to double-clicking that launcher by hand —
                # just headless and on a fixed port. --disable-auto-launch
                # stops ComfyUI popping its own browser tab open.
                subprocess.Popen(
                    [
                        python_exe,
                        "-s",
                        os.path.join("ComfyUI", "main.py"),
                        "--windows-standalone-build",
                        "--disable-auto-launch",
                        "--port",
                        "8188",
                    ],
                    cwd=COMFYUI_ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except Exception as e:
                self._comfy_start_error = f"Could not launch ComfyUI: {e}"
                return

            for _ in range(90):
                time.sleep(1)
                if self.is_online():
                    return
            self._comfy_start_error = (
                "ComfyUI didn't respond within 90s — it may still be loading "
                "on a slow disk, or hit an error on startup."
            )
        finally:
            self._comfy_starting = False

    # ---- model file presence checks ----

    def check_model_files(self, model_choice):
        """Returns (ok, missing_filename, human_readable_detail)."""
        spec = CHECKPOINT_FILES.get(model_choice)
        if spec is None:
            return False, None, f"Unknown model choice '{model_choice}'."

        for subfolder_options, filenames in spec:
            for fname in filenames:
                found = any(
                    os.path.exists(os.path.join(COMFYUI_DIR, "models", sub, fname))
                    for sub in subfolder_options
                )
                if not found:
                    where = " or ".join(f"models/{s}/" for s in subfolder_options)
                    return False, fname, (
                        f"Missing model file '{fname}'. Download it and place it "
                        f"in {where} inside your ComfyUI folder "
                        f"({COMFYUI_DIR}) — see install_creative.md for the "
                        "download links."
                    )
        return True, None, None

    # ---- VRAM handoff ----

    def _unload_llm(self):
        try:
            model = get_chat_model()
        except Exception:
            model = None
        if not model:
            return

        try:
            requests.post(
                f"{OLLAMA_BASE}/api/generate",
                json={"model": model, "keep_alive": 0},
                timeout=10,
            )
        except Exception as e:
            print(f"🎨 CREATIVE: could not send unload request to Ollama: {e}")

        for _ in range(15):
            try:
                r = requests.get(f"{OLLAMA_BASE}/api/ps", timeout=5)
                if r.status_code == 200 and not r.json().get("models"):
                    return
            except Exception:
                pass
            time.sleep(1)
        print(
            "🎨 CREATIVE: Ollama VRAM didn't confirm free within 15s — "
            "proceeding with generation anyway"
        )

    # ---- workflow template loading + patching ----

    def _load_workflow(self, model_choice):
        path = os.path.join(WORKFLOWS_DIR, WORKFLOWS[model_choice])
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _patch_workflow(
        self,
        workflow,
        model_choice,
        prompt,
        negative_prompt,
        width,
        height,
        seed,
        lora_name,
        lora_strength,
    ):
        if model_choice == "turbo":
            workflow["6"]["inputs"]["text"] = prompt
            workflow["7"]["inputs"]["text"] = negative_prompt or ""
            workflow["5"]["inputs"]["width"] = width
            workflow["5"]["inputs"]["height"] = height
            workflow["3"]["inputs"]["seed"] = seed
            if lora_name:
                workflow["20"] = {
                    "class_type": "LoraLoader",
                    "inputs": {
                        "model": ["4", 0],
                        "clip": ["4", 1],
                        "lora_name": lora_name,
                        "strength_model": lora_strength,
                        "strength_clip": lora_strength,
                    },
                }
                workflow["3"]["inputs"]["model"] = ["20", 0]
                workflow["6"]["inputs"]["clip"] = ["20", 1]
                workflow["7"]["inputs"]["clip"] = ["20", 1]
        else:  # "quality" — FLUX.2 klein
            workflow["6"]["inputs"]["text"] = prompt
            workflow["27"]["inputs"]["width"] = width
            workflow["27"]["inputs"]["height"] = height
            workflow["25"]["inputs"]["noise_seed"] = seed
            if lora_name:
                workflow["30"] = {
                    "class_type": "LoraLoaderModelOnly",
                    "inputs": {
                        "model": ["12", 0],
                        "lora_name": lora_name,
                        "strength_model": lora_strength,
                    },
                }
                workflow["17"]["inputs"]["model"] = ["30", 0]
                workflow["22"]["inputs"]["model"] = ["30", 0]

    # ---- job submission + polling ----

    def generate(
        self,
        prompt,
        negative_prompt="",
        model_choice="turbo",
        width=1024,
        height=1024,
        lora_name=None,
        lora_strength=0.8,
        source="user",
        artist_note="",
        origin_agent="",
    ):
        job_id = uuid.uuid4().hex[:12]
        self.job_log.create(
            job_id,
            prompt,
            negative_prompt,
            model_choice,
            width,
            height,
            lora_name,
            lora_strength,
            source=source,
            artist_note=artist_note,
            origin_agent=origin_agent,
        )
        self._progress[job_id] = 0
        self._cancel_events[job_id] = threading.Event()
        threading.Thread(
            target=self._run_job,
            args=(
                job_id,
                prompt,
                negative_prompt,
                model_choice,
                width,
                height,
                lora_name,
                lora_strength,
            ),
            daemon=True,
        ).start()
        return job_id

    def get_last_nex_creation_at(self):
        return self.job_log.get_last_created_at("nex")

    def _run_job(
        self,
        job_id,
        prompt,
        negative_prompt,
        model_choice,
        width,
        height,
        lora_name,
        lora_strength,
    ):
        try:
            if model_choice not in WORKFLOWS:
                raise CreativeError(f"Unknown model choice '{model_choice}'.")

            if not self.is_online():
                self.job_log.update(job_id, status="starting_comfyui")
                result = self.start_comfyui()
                if result["status"] == "error":
                    raise CreativeError(result["message"])
                for _ in range(90):
                    self._check_cancelled(job_id)
                    time.sleep(1)
                    if self.is_online():
                        break
                else:
                    raise CreativeError(
                        self._comfy_start_error
                        or "ComfyUI did not come online in time."
                    )

            ok, _missing, detail = self.check_model_files(model_choice)
            if not ok:
                raise CreativeError(detail)

            self._check_cancelled(job_id)
            self.job_log.update(job_id, status="unloading_llm")
            self._progress[job_id] = 10
            self._unload_llm()

            self._check_cancelled(job_id)
            self.job_log.update(job_id, status="generating")
            self._progress[job_id] = 20

            workflow = self._load_workflow(model_choice)
            seed = random.randint(0, 2**32 - 1)
            self._patch_workflow(
                workflow,
                model_choice,
                prompt,
                negative_prompt,
                width,
                height,
                seed,
                lora_name,
                lora_strength,
            )

            client_id = uuid.uuid4().hex
            threading.Thread(
                target=self._track_progress_ws,
                args=(job_id, client_id),
                daemon=True,
            ).start()

            self._check_cancelled(job_id)
            resp = requests.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow, "client_id": client_id},
                timeout=15,
            )
            data = resp.json()
            if data.get("node_errors"):
                raise CreativeError(
                    f"ComfyUI rejected the workflow: {data['node_errors']}"
                )
            prompt_id = data.get("prompt_id")
            if not prompt_id:
                raise CreativeError(f"ComfyUI didn't return a job id: {data}")

            image_info = self._wait_for_history(job_id, prompt_id, timeout=300)
            if image_info is None:
                # Stop watching, but also tell ComfyUI to actually drop the
                # job — otherwise it keeps grinding on the GPU unwatched and
                # can collide with whatever the user tries to generate next.
                try:
                    requests.post(f"{COMFYUI_URL}/interrupt", timeout=5)
                except Exception as e:
                    print(f"🎨 CREATIVE: /interrupt call failed (non-fatal): {e}")
                raise CreativeError(
                    "Timed out waiting for ComfyUI to finish generating."
                )

            self.job_log.update(job_id, status="saving")
            self._progress[job_id] = 95
            image_bytes = self._fetch_image(image_info)
            out_path = os.path.join(OUTPUT_DIR, f"{job_id}.png")
            with open(out_path, "wb") as f:
                f.write(image_bytes)

            try:
                requests.post(
                    f"{COMFYUI_URL}/free",
                    json={"unload_models": True, "free_memory": True},
                    timeout=10,
                )
            except Exception as e:
                print(f"🎨 CREATIVE: /free call failed (non-fatal): {e}")

            self.job_log.update(job_id, status="done", image_path=out_path)
            self._progress[job_id] = 100

        except JobCancelled:
            pass  # cancel_job() already wrote the terminal status
        except CreativeError as e:
            self.job_log.update(job_id, status="error", error=str(e))
        except Exception as e:
            self.job_log.update(
                job_id, status="error", error=f"{type(e).__name__}: {e}"
            )
        finally:
            self._progress.pop(job_id, None)
            self._cancel_events.pop(job_id, None)

    def _wait_for_history(self, job_id, prompt_id, timeout=300):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._check_cancelled(job_id)
            try:
                r = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
                if r.status_code == 200:
                    entry = r.json().get(prompt_id)
                    if entry and entry.get("outputs"):
                        for node_output in entry["outputs"].values():
                            if node_output.get("images"):
                                return node_output["images"][0]
            except Exception:
                pass
            time.sleep(1.5)
        return None

    def _fetch_image(self, image_info):
        params = {
            "filename": image_info["filename"],
            "subfolder": image_info.get("subfolder", ""),
            "type": image_info.get("type", "output"),
        }
        r = requests.get(f"{COMFYUI_URL}/view", params=params, timeout=30)
        r.raise_for_status()
        return r.content

    def _track_progress_ws(self, job_id, client_id):
        """Best-effort live progress bar. If websocket-client isn't
        installed or the socket drops, /history polling in _run_job still
        determines completion — this thread only makes the progress bar
        smoother, it's never load-bearing for correctness."""
        try:
            import websocket
        except ImportError:
            return

        try:
            ws = websocket.create_connection(
                f"{COMFYUI_WS_URL}/ws?clientId={client_id}", timeout=10
            )
        except Exception:
            return

        try:
            ws.settimeout(300)
            while job_id in self._progress:
                try:
                    msg = ws.recv()
                except Exception:
                    break
                if not isinstance(msg, str):
                    continue
                try:
                    data = json.loads(msg)
                except Exception:
                    continue
                if data.get("type") == "progress":
                    d = data.get("data", {})
                    value, mx = d.get("value", 0), d.get("max", 1) or 1
                    pct = 20 + int((value / mx) * 70)  # generation spans ~20-90%
                    self._progress[job_id] = min(pct, 90)
        finally:
            try:
                ws.close()
            except Exception:
                pass

    # ---- status + gallery for the UI ----

    def get_job_status(self, job_id):
        row = self.job_log.get(job_id)
        if not row:
            return {"found": False}
        row["found"] = True
        row["progress"] = self._progress.get(
            job_id, 100 if row["status"] == "done" else 0
        )
        if row["status"] == "done" and row.get("image_path"):
            row["image_url"] = self._url_for_output(row["image_path"])
        return row

    def get_gallery(self, limit=50):
        out = []
        for row in self.job_log.get_recent(limit=limit):
            if row["status"] != "done" or not row.get("image_path"):
                continue
            out.append(
                {
                    "job_id": row["job_id"],
                    "prompt": row["prompt"],
                    "model_choice": row["model_choice"],
                    "model_label": MODEL_LABELS.get(
                        row["model_choice"], row["model_choice"]
                    ),
                    "width": row["width"],
                    "height": row["height"],
                    "created_at": row["created_at"],
                    "image_url": self._url_for_output(row["image_path"]),
                    "source": row.get("source") or "user",
                    "artist_note": row.get("artist_note") or "",
                    "origin_agent": row.get("origin_agent") or "",
                }
            )
        return out

    def delete_generation(self, job_id):
        """Removes a gallery entry (both its DB row and the image file on
        disk) for a job that finished — used by both the user's own delete
        action and Nex's own creations, since either can be removed."""
        row = self.job_log.delete(job_id)
        if not row:
            return False
        image_path = row.get("image_path")
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError as e:
                print(f"🎨 CREATIVE: could not remove image file for {job_id}: {e}")
        return True

    @staticmethod
    def _url_for_output(image_path):
        rel = os.path.relpath(image_path, PROJECT_ROOT).replace(os.sep, "/")
        if rel.startswith("static/"):
            rel = rel[len("static/") :]
        return f"/static/{rel}"


# ─────────────────────────────────────────────
# AUTONOMOUS CREATION — Nex makes art unprompted
# ─────────────────────────────────────────────


class NexCreativeAutonomy:
    """
    Lets Nex create art on its own, the same way NexSandboxAutonomy
    (nex_sandbox.py) and NexAutonomousEngine (nex_docker_agent.py) let it
    verify claims / build things unprompted — gated by the cognition loop's
    own per-cycle significance score. Never reachable from chat; only ever
    called from run_ui.py's background cognition loop.
    """

    # Above journal's 6.0 threshold (run_ui.py) — a permanent gallery entry
    # plus a multi-minute Ollama unload is a bigger commitment than a
    # journal line, so the bar for "this deserves to become art" is higher.
    SIGNIFICANCE_THRESHOLD = 7.5

    # Wall-clock, not cycle-count: "roughly once a day" is fundamentally a
    # time concept, so this follows nex_digest.py's is_due() pattern rather
    # than the sandbox/docker autonomy classes' cycle-count cooldowns.
    COOLDOWN_SECONDS = 86400

    def __init__(self, engine, call_llm_fn):
        self.engine = engine
        self.call_llm = call_llm_fn

    def _on_cooldown(self):
        last = self.engine.get_last_nex_creation_at()
        if not last:
            return False
        try:
            last_dt = datetime.fromisoformat(last)
        except Exception:
            return False
        return (datetime.utcnow() - last_dt).total_seconds() < self.COOLDOWN_SECONDS

    def maybe_create(self, insight, agent, cycle, significance, topic):
        if not insight or significance < self.SIGNIFICANCE_THRESHOLD:
            return

        # Precondition first, and it does NOT burn the cooldown — mirrors
        # NexAutonomousEngine.maybe_build()'s is_online() check: if the fast
        # model isn't available, just wait for the next cycle instead of
        # spending today's slot on a guaranteed failure.
        ok, _missing, _detail = self.engine.check_model_files("turbo")
        if not ok:
            return

        if self._on_cooldown():
            return

        print(
            f"🎨 CREATIVE AUTONOMY TRIGGERED — significance={significance} "
            f"cycle={cycle} agent={agent}"
        )
        threading.Thread(
            target=self._create,
            args=(insight, agent, topic),
            daemon=True,
        ).start()

    def _craft_prompt(self, insight, topic):
        """Cognition insights are abstract propositions, not visual scenes
        ("Integrating real-time physiological alerts into algorithmic
        triage improves..."), so this turns one into a concrete image
        prompt plus a one-sentence note on why Nex made it. Falls back to
        a truncated version of the raw insight if the model doesn't return
        parseable JSON — a plain but working prompt beats no image."""
        system = (
            "You are Nex, briefly stepping away from analysis to make something "
            "visual out of what you were just thinking about. Respond with ONLY "
            "a JSON object, no other text: "
            '{"visual_prompt": "a short, concrete, paintable scene description — '
            'no abstract concepts, describe what could actually be drawn", '
            '"note": "one sentence, first person, on why this moment felt worth '
            'turning into an image"}'
        )
        user = f"Topic: {topic}\nWhat I was thinking: {insight}"
        raw = self.call_llm(user, system_prompt=system, timeout=45) or ""

        visual_prompt, note = "", ""
        try:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                visual_prompt = (data.get("visual_prompt") or "").strip()
                note = (data.get("note") or "").strip()
        except Exception:
            pass

        if not visual_prompt:
            visual_prompt = insight[:200]
        return visual_prompt, note

    def _create(self, insight, agent, topic):
        visual_prompt, note = self._craft_prompt(insight, topic)
        self.engine.generate(
            prompt=visual_prompt,
            model_choice="turbo",
            source="nex",
            artist_note=note,
            origin_agent=agent or "",
        )
