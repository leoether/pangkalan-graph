"""Layer Relate (Neo4j Relate, paket `relate-db` 1.2.0) untuk Pangkalan Graph.

Aturan Relate yang dipakai di sini (terverifikasi di VM ini):
- Satu writer per file store; koneksi thread-affine -> semua akses DB
  lewat satu threading.Lock dan koneksi dibuka/ditutup per operasi.
- Parameter Cypher pakai $nama + dict.
- shortestPath() menghitung JUMLAH HOP, bukan bobot -> rute TERMURAH
  dihitung sendiri dengan Dijkstra (heapq) di atas adjacency dari Relate.
"""
import heapq
import os
import threading
from datetime import datetime, timezone

import relate

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(BASE_DIR, "data", "pangkalan.rl")

_LOCK = threading.Lock()

PLACES = [
    ("Sambaliung", "pangkalan"),
    ("Tanjung Redeb", "kota"),
    ("Bandara Kalimarau", "bandara"),
    ("Pasar Sanggam", "pasar"),
    ("Gunung Tabur", "pangkalan"),
    ("Teluk Bayur", "pangkalan"),
]

DRIVERS = ["Leo", "Budi", "Agus", "Slamet", "Joko"]

# Pangkalan asal tiap driver (Leo -> Sambaliung).
DRIVER_HOME = {
    "Leo": "Sambaliung",
    "Budi": "Sambaliung",
    "Agus": "Tanjung Redeb",
    "Slamet": "Gunung Tabur",
    "Joko": "Teluk Bayur",
}


def _one(cur):
    """Satu baris pertama atau None (Relate .single() raise bila 0 baris)."""
    rows = list(cur)
    return rows[0] if rows else None


def _run(fn):
    """Jalankan fn(conn) dengan koneksi baru, di bawah lock global."""
    with _LOCK:
        conn = relate.connect(STORE_PATH)
        try:
            return fn(conn)
        finally:
            conn.close()


def store_exists():
    return os.path.exists(STORE_PATH)


def is_seeded():
    if not store_exists():
        return False
    return _run(lambda c: c.execute(
        "MATCH (p:Place) RETURN count(p) AS n").single()["n"]) > 0


def seed(routes):
    """Seed store dari daftar rute {from, to, km, fare}. Idempotent:
    hapus semua node/rel dulu, lalu bangun ulang dari nol."""
    def _seed(conn):
        conn.execute("MATCH (n) DETACH DELETE n")
        for name, kind in PLACES:
            conn.execute(
                "CREATE (:Place {name: $name, kind: $kind})",
                {"name": name, "kind": kind})
        for name in DRIVERS:
            conn.execute(
                "CREATE (:Driver {name: $name})", {"name": name})
        # CONNECTS_TO dua arah, distance/fare sama.
        for r in routes:
            conn.execute(
                "MATCH (a:Place {name: $a}), (b:Place {name: $b}) "
                "CREATE (a)-[:CONNECTS_TO {distance_km: $km, fare_rp: $fare}]->(b), "
                "       (b)-[:CONNECTS_TO {distance_km: $km, fare_rp: $fare}]->(a)",
                {"a": r["from"], "b": r["to"], "km": r["km"], "fare": r["fare"]})
        # SERVES: pangkalan asal tiap driver.
        for driver, home in DRIVER_HOME.items():
            conn.execute(
                "MATCH (d:Driver {name: $d}), (p:Place {name: $p}) "
                "CREATE (d)-[:SERVES]->(p)",
                {"d": driver, "p": home})
        # Antrean rotasi adil: rantai linier + node Queue penanda head.
        conn.execute("CREATE (:Queue {name: 'main'})")
        conn.execute(
            "MATCH (q:Queue {name: 'main'}), (d:Driver {name: $head}) "
            "CREATE (q)-[:HEAD]->(d)", {"head": DRIVERS[0]})
        for prev, nxt in zip(DRIVERS, DRIVERS[1:]):
            conn.execute(
                "MATCH (a:Driver {name: $a}), (b:Driver {name: $b}) "
                "CREATE (a)-[:QUEUE_NEXT]->(b)",
                {"a": prev, "b": nxt})
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    _run(_seed)


def get_places():
    return _run(lambda c: [
        {"name": r["name"], "kind": r["kind"]} for r in c.execute(
            "MATCH (p:Place) RETURN p.name AS name, p.kind AS kind ORDER BY p.name")])


def get_adjacency():
    """{asal: [(tujuan, distance_km, fare_rp), ...]} dari Relate."""
    def _q(conn):
        adj = {}
        for r in conn.execute(
                "MATCH (a:Place)-[rel:CONNECTS_TO]->(b:Place) "
                "RETURN a.name AS a, b.name AS b, "
                "rel.distance_km AS km, rel.fare_rp AS fare"):
            adj.setdefault(r["a"], []).append(
                (r["b"], float(r["km"]), int(r["fare"])))
        return adj
    return _run(_q)


def dijkstra(adj, start, goal):
    """Rute termurah (bobot = tarif Rp) antar dua tempat. None bila tak ada."""
    if start == goal:
        return {"route": [start], "total_km": 0.0, "total_fare_rp": 0, "hops": 0}
    dist = {start: 0}
    prev = {}
    heap = [(0, start)]
    visited = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        if u == goal:
            break
        for v, km, fare in adj.get(u, []):
            nd = d + fare
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = (u, km, fare)
                heapq.heappush(heap, (nd, v))
    if goal not in dist:
        return None
    route, total_km, hops = [], 0.0, 0
    node = goal
    while node != start:
        route.append(node)
        p, km, _fare = prev[node]
        total_km += km
        hops += 1
        node = p
    route.append(start)
    route.reverse()
    return {"route": route, "total_km": total_km,
            "total_fare_rp": dist[goal], "hops": hops}


def cheapest_route(start, goal):
    """Rute termurah (Dijkstra Python) + pembanding hop-terpendek (Cypher)."""
    adj = get_adjacency()
    cheapest = dijkstra(adj, start, goal)
    if cheapest is None:
        return None

    def _hop(conn):
        row = _one(conn.execute(
            "MATCH p = shortestPath((a:Place {name: $from})"
            "-[:CONNECTS_TO*]->(b:Place {name: $to})) "
            "RETURN [n IN nodes(p) | n.name] AS route, length(p) AS hops, "
            "reduce(t = 0, r IN relationships(p) | t + r.fare_rp) AS fare, "
            "reduce(t = 0, r IN relationships(p) | t + r.distance_km) AS km",
            {"from": start, "to": goal}))
        if row is None:
            return None
        return {"route": list(row["route"]), "hops": int(row["hops"]),
                "total_fare_rp": int(row["fare"]),
                "total_km": float(row["km"])}
    hop_shortest = _run(_hop)
    return {"cheapest": cheapest, "hop_shortest": hop_shortest}


def get_queue():
    """Urutan antrean dari HEAD mengikuti rantai QUEUE_NEXT."""
    def _q(conn):
        head = _one(conn.execute(
            "MATCH (q:Queue {name: 'main'})-[:HEAD]->(d:Driver) "
            "RETURN d.name AS name"))
        if head is None:
            return []
        order, seen = [], set()
        cur = head["name"]
        while cur and cur not in seen:
            seen.add(cur)
            order.append(cur)
            nxt = _one(conn.execute(
                "MATCH (d:Driver {name: $d})-[:QUEUE_NEXT]->(n:Driver) "
                "RETURN n.name AS name", {"d": cur}))
            cur = nxt["name"] if nxt else None
        return order
    return _run(_q)


def advance_queue():
    """Pindahkan driver depan ke belakang antrean (update QUEUE_NEXT).

    Rantai linier A->B->C->D->E, head=A. Sesudah maju: head=B,
    hapus A->B, tambah E->A. Mengembalikan (driver_yang_maju, head_baru).
    """
    def _adv(conn):
        head = _one(conn.execute(
            "MATCH (q:Queue {name: 'main'})-[:HEAD]->(d:Driver) "
            "RETURN d.name AS name"))["name"]
        nxt = _one(conn.execute(
            "MATCH (d:Driver {name: $d})-[:QUEUE_NEXT]->(n:Driver) "
            "RETURN n.name AS name", {"d": head}))
        if nxt is None:
            return head, head  # antrean tinggal 1 orang
        new_head = nxt["name"]
        tail = _one(conn.execute(
            "MATCH (d:Driver) WHERE NOT (d)-[:QUEUE_NEXT]->() "
            "RETURN d.name AS name"))["name"]
        conn.execute(
            "MATCH (q:Queue {name: 'main'})-[h:HEAD]->(old:Driver {name: $old}), "
            "      (n:Driver {name: $new}) "
            "DELETE h CREATE (q)-[:HEAD]->(n)",
            {"old": head, "new": new_head})
        conn.execute(
            "MATCH (a:Driver {name: $a})-[r:QUEUE_NEXT]->(b:Driver {name: $b}) "
            "DELETE r", {"a": head, "b": new_head})
        conn.execute(
            "MATCH (t:Driver {name: $t}), (a:Driver {name: $a}) "
            "CREATE (t)-[:QUEUE_NEXT]->(a)",
            {"t": tail, "a": head})
        return head, new_head
    return _run(_adv)


def record_trip(driver, start, goal):
    """Hitung tarif via Dijkstra, simpan (:Trip) + (:Driver)-[:TOOK]->(:Trip),
    lalu pindahkan driver yang narik ke belakang antrean."""
    adj = get_adjacency()
    route = dijkstra(adj, start, goal)
    if route is None:
        return None
    created_at = datetime.now(timezone.utc).isoformat()

    def _rec(conn):
        conn.execute(
            "MATCH (d:Driver {name: $driver}) "
            "CREATE (t:Trip {from: $from, to: $to, fare_rp: $fare, "
            "distance_km: $km, created_at: $ts}) "
            "CREATE (d)-[:TOOK]->(t)",
            {"driver": driver, "from": start, "to": goal,
             "fare": route["total_fare_rp"], "km": route["total_km"],
             "ts": created_at})
    _run(_rec)
    # Driver yang narik pindah ke belakang antrean — tapi hanya bila dia
    # sedang di depan; kalau bukan, putar antrean sampai dia di belakang.
    # Sederhana & adil untuk v1: majukan antrean sampai head bukan dia lagi
    # (maks. sekali putaran penuh).
    queue = get_queue()
    if queue and queue[0] == driver:
        advance_queue()
    elif driver in queue:
        for _ in range(len(queue)):
            advance_queue()
            if get_queue()[-1] == driver:
                break
    return {"driver": driver, "from": start, "to": goal,
            "route": route["route"], "total_km": route["total_km"],
            "total_fare_rp": route["total_fare_rp"], "hops": route["hops"],
            "created_at": created_at}


def get_trips(limit=20):
    return _run(lambda c: [
        {"driver": r["driver"], "from": r["from"], "to": r["to"],
         "fare_rp": int(r["fare"]), "distance_km": float(r["km"]),
         "created_at": r["ts"]} for r in c.execute(
            "MATCH (d:Driver)-[:TOOK]->(t:Trip) "
            "RETURN d.name AS driver, t.from AS from, t.to AS to, "
            "t.fare_rp AS fare, t.distance_km AS km, t.created_at AS ts "
            "ORDER BY t.created_at DESC LIMIT $n", {"n": limit})])


def get_drivers():
    return _run(lambda c: [
        {"name": r["name"], "home": r["home"]} for r in c.execute(
            "MATCH (d:Driver)-[:SERVES]->(p:Place) "
            "RETURN d.name AS name, p.name AS home ORDER BY d.name")])


def stats():
    def _s(conn):
        n_places = conn.execute(
            "MATCH (p:Place) RETURN count(p) AS n").single()["n"]
        n_edges = conn.execute(
            "MATCH ()-[r:CONNECTS_TO]->() RETURN count(r) AS n").single()["n"]
        n_trips = conn.execute(
            "MATCH (t:Trip) RETURN count(t) AS n").single()["n"]
        return {"places": n_places, "edges": n_edges, "trips": n_trips}
    return _run(_s)
