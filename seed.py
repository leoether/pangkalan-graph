"""Seed store Relate Pangkalan Graph dari data/seed-routes.json.

Idempotent: setiap run menghapus isi store lalu membangun ulang dari nol
(tempat, driver, CONNECTS_TO dua arah, SERVES, rantai QUEUE_NEXT).
Jalankan:  python seed.py
"""
import json
import os

import graph

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROUTES_PATH = os.path.join(BASE_DIR, "data", "seed-routes.json")


def main():
    with open(ROUTES_PATH, encoding="utf-8") as f:
        routes = json.load(f)
    graph.seed(routes)
    s = graph.stats()
    print(f"Seed selesai: {len(routes)} rute dari {ROUTES_PATH}")
    print(f"Store: {graph.STORE_PATH}")
    print(f"Place: {s['places']} | CONNECTS_TO (dua arah): {s['edges']} "
          f"| Driver: {len(graph.DRIVERS)} | Trip: {s['trips']}")
    print("Antrean:", " -> ".join(graph.get_queue()))


if __name__ == "__main__":
    main()
