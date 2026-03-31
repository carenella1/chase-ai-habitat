# =============================================================
# 🚀 CHASE AI HABITAT — DESKTOP LAUNCHER
# launch_habitat.py
# =============================================================

import sys
import os
import time
import threading
import subprocess
import requests
import signal

# =============================================================
# PROJECT PATH
# =============================================================
PROJECT_ROOT = r"C:\Users\User\Desktop\Github\chase-ai-habitat"

# =============================================================
# CONFIGURATION
# =============================================================
APP_TITLE = "Nexarion Habitat"
APP_URL = "http://127.0.0.1:5000"
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900

FLASK_SCRIPT = os.path.join(PROJECT_ROOT, "run_ui.py")
ICON_PATH = os.path.join(PROJECT_ROOT, "static", "icon.png")
OLLAMA_EXE = r"C:\Users\User\AppData\Local\Programs\Ollama\ollama.exe"
PYTHON_EXE = os.path.join(PROJECT_ROOT, "habitat-env", "Scripts", "python.exe")

STARTUP_TIMEOUT = 45

# =============================================================
# GLOBALS
# =============================================================
flask_process = None
webview_window = None


# =============================================================
# LOGGING — everything goes to habitat_debug.log
# =============================================================
LOG_PATH = os.path.join(PROJECT_ROOT, "habitat_debug.log")


def log(msg):
    print(msg)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


# =============================================================
# STEP 0: AUTO-START OLLAMA
# =============================================================
def ensure_ollama_running():
    log("Checking if Ollama is running...")
    try:
        requests.get("http://127.0.0.1:11434", timeout=2)
        log("Ollama already running.")
        return True
    except Exception:
        pass

    log("Starting Ollama...")
    ollama_path = OLLAMA_EXE if os.path.exists(OLLAMA_EXE) else "ollama"

    try:
        subprocess.Popen(
            [ollama_path, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for _ in range(30):
            time.sleep(0.5)
            try:
                requests.get("http://127.0.0.1:11434", timeout=2)
                log("Ollama is ready.")
                return True
            except Exception:
                pass
        log("Ollama did not respond in time — continuing anyway.")
    except Exception as e:
        log(f"Could not start Ollama: {e}")
    return False


# =============================================================
# STEP 1: KILL LEFTOVER FLASK
# =============================================================
def kill_existing_flask():
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if ":5000" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
                log(f"Killed existing process on port 5000 (PID {pid})")
                time.sleep(0.5)
    except Exception as e:
        log(f"Port cleanup error: {e}")


# =============================================================
# STEP 2: START FLASK
# =============================================================
def start_flask():
    global flask_process

    log("Starting Flask server...")

    python_exe = PYTHON_EXE if os.path.exists(PYTHON_EXE) else sys.executable
    log(f"Using Python: {python_exe}")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    # Clear and open debug log
    log_file = open(LOG_PATH, "w", encoding="utf-8")

    flask_process = subprocess.Popen(
        [python_exe, FLASK_SCRIPT],
        stdout=log_file,
        stderr=log_file,
        cwd=PROJECT_ROOT,
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    log(f"Flask process started (PID: {flask_process.pid})")


# =============================================================
# STEP 3: WAIT FOR FLASK
# =============================================================
def wait_for_flask(timeout=STARTUP_TIMEOUT):
    log(f"Waiting for Flask at {APP_URL}...")
    start = time.time()

    while time.time() - start < timeout:
        if flask_process and flask_process.poll() is not None:
            log("Flask process crashed — check habitat_debug.log")
            return False

        try:
            r = requests.get(APP_URL, timeout=2)
            if r.status_code == 200:
                log("Flask is ready!")
                return True
        except Exception:
            pass

        time.sleep(0.5)

    log("Flask did not respond in time.")
    return False


# =============================================================
# STEP 4: OPEN PYWEBVIEW WINDOW
# No tkinter here — PyWebView is the only GUI
# =============================================================
def open_window():
    global webview_window
    try:
        import webview

        # Persistent data dir — WebView2 remembers permissions across sessions
        user_data_dir = os.path.join(PROJECT_ROOT, "data", "webview_profile")
        os.makedirs(user_data_dir, exist_ok=True)

        webview_window = webview.create_window(
            title=APP_TITLE,
            url=APP_URL,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=(900, 600),
            resizable=True,
            text_select=True,
            background_color="#0a0a0f",
        )

        threading.Thread(target=_start_tray, daemon=True).start()

        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
            "--use-fake-ui-for-media-stream "
            "--allow-file-access-from-files "
            "--unsafely-treat-insecure-origin-as-secure=http://127.0.0.1:5000"
        )

        webview.start(
            gui="edgechromium",
            debug=True,
            http_server=False,
            private_mode=False,
        )

    except Exception as e:
        log(f"PyWebView error: {e}")
        import webbrowser

        webbrowser.open(APP_URL)


# =============================================================
# STEP 5: TRAY ICON (no tkinter dependency)
# =============================================================
def _start_tray():
    try:
        import pystray
        from PIL import Image, ImageDraw

        if os.path.exists(ICON_PATH):
            icon_image = Image.open(ICON_PATH).resize((64, 64))
        else:
            # Draw a simple cyan orb as fallback icon
            icon_image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(icon_image)
            draw.ellipse([4, 4, 60, 60], fill=(0, 255, 255, 255))
            draw.ellipse([12, 12, 52, 52], fill=(0, 20, 40, 255))
            draw.ellipse([20, 20, 44, 44], fill=(0, 255, 255, 255))

        def on_show(icon, item):
            if webview_window:
                webview_window.show()

        def on_quit(icon, item):
            icon.stop()
            shutdown()

        menu = pystray.Menu(
            pystray.MenuItem("Show Nexarion", on_show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit),
        )

        tray = pystray.Icon("nexarion", icon_image, APP_TITLE, menu)
        tray.run()

    except ImportError:
        log("pystray not installed — no tray icon")
    except Exception as e:
        log(f"Tray error: {e}")


# =============================================================
# SHUTDOWN
# =============================================================
def shutdown():
    log("Shutting down Nexarion Habitat...")
    global flask_process
    if flask_process:
        try:
            flask_process.terminate()
            flask_process.wait(timeout=5)
        except Exception:
            try:
                flask_process.kill()
            except Exception:
                pass
    os._exit(0)


# =============================================================
# MAIN — no tkinter splash, clean linear startup
# =============================================================
def main():
    log("=" * 50)
    log("  NEXARION HABITAT — DESKTOP MODE")
    log(f"  {PROJECT_ROOT}")
    log("=" * 50)

    ensure_ollama_running()
    kill_existing_flask()
    start_flask()

    ready = wait_for_flask(timeout=90)
    if not ready:
        log("Flask failed to start. Check habitat_debug.log.")
        shutdown()
        return

    open_window()
    shutdown()


# =============================================================
# RUN
# =============================================================
if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda s, f: shutdown())
    main()
