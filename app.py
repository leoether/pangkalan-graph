"""Pangkalan Graph — Flask app (port 5000).

Satu halaman utama (Bahasa Indonesia): cari rute termurah, antrean rotasi
adil, catat trip. Semua data tinggal di Relate store data/pangkalan.rl.
"""
import os

from flask import Flask, jsonify, render_template, request

import graph

app = Flask(__name__)


@app.before_request
def _ensure_seed():
    # Auto-seed sekali bila store belum ada / masih kosong (mis. juri
    # langsung menjalankan app.py tanpa seed.py dulu).
    if not graph.is_seeded():
        import json
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "data", "seed-routes.json"),
                  encoding="utf-8") as f:
            graph.seed(json.load(f))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/places")
def api_places():
    return jsonify(graph.get_places())


@app.route("/api/drivers")
def api_drivers():
    return jsonify(graph.get_drivers())


@app.route("/api/route")
def api_route():
    start = request.args.get("from", "")
    goal = request.args.get("to", "")
    if not start or not goal:
        return jsonify({"error": "Parameter 'from' dan 'to' wajib diisi."}), 400
    if start == goal:
        return jsonify({"error": "Asal dan tujuan tidak boleh sama."}), 400
    result = graph.cheapest_route(start, goal)
    if result is None:
        return jsonify({"error": f"Tidak ada rute {start} -> {goal}."}), 404
    return jsonify(result)


@app.route("/api/queue")
def api_queue():
    queue = graph.get_queue()
    return jsonify({"queue": queue, "next": queue[0] if queue else None})


@app.route("/api/queue/advance", methods=["POST"])
def api_queue_advance():
    moved, new_head = graph.advance_queue()
    return jsonify({"moved": moved, "next": new_head,
                    "queue": graph.get_queue()})


@app.route("/api/trips", methods=["GET", "POST"])
def api_trips():
    if request.method == "GET":
        return jsonify(graph.get_trips())
    data = request.get_json(force=True, silent=True) or {}
    driver, start, goal = data.get("driver"), data.get("from"), data.get("to")
    if not driver or not start or not goal:
        return jsonify({"error": "driver, from, dan to wajib diisi."}), 400
    if start == goal:
        return jsonify({"error": "Asal dan tujuan tidak boleh sama."}), 400
    trip = graph.record_trip(driver, start, goal)
    if trip is None:
        return jsonify({"error": f"Tidak ada rute {start} -> {goal}."}), 404
    trip["queue"] = graph.get_queue()
    return jsonify(trip), 201


@app.route("/api/stats")
def api_stats():
    return jsonify(graph.stats())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, threaded=True)
