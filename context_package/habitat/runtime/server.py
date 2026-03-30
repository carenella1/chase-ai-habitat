@app.route("/api/cognition_events")
def cognition_events():

    import sqlite3

    conn = sqlite3.connect("habitat_memory.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT source, summary
        FROM memory_items
        ORDER BY id DESC
        LIMIT 5
    """)

    rows = cur.fetchall()

    events = []

    for r in rows:

        events.append({
            "agent": r[0],
            "action": r[1]
        })

    return {"events": events}