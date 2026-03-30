from flask import Flask, render_template, jsonify, redirect
from habitat.runtime.kernel import HabitatKernel
import threading
import time
import traceback

app = Flask(__name__)

kernel = HabitatKernel()

cycle_count = 0


def cognition_loop():

    global cycle_count

    print("\nHabitat background cognition started.\n")

    while True:

        try:

            print("\n=== HABITAT COGNITION CYCLE ===\n")

            kernel.run_cycle()

            cycle_count += 1

        except Exception as e:

            print("\nCognition cycle crashed:\n")
            traceback.print_exc()

        # never exit loop
        time.sleep(10)


def start_cognition():

    thread = threading.Thread(target=cognition_loop)

    thread.daemon = False

    thread.start()


@app.route("/")
def index():
    return redirect("/chat")


@app.route("/chat")
def chat():
    return render_template("chat.html")


@app.route("/habitat")
def habitat():
    return render_template("habitat.html")


@app.route("/api/status")
def status():

    memory_counts = kernel.memory.count_by_tier()

    recent = kernel.memory.get_recent_memories(5)

    return jsonify({
        "cycles": cycle_count,
        "memory": memory_counts,
        "recent_activity": recent
    })


def run_ui():

    start_cognition()

    print("\nChase AI Habitat Control Panel running at:")
    print("http://127.0.0.1:5000\n")

    app.run(host="127.0.0.1", port=5000)