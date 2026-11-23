# Pangkalan Graph 🛵

**Dispatch ojek Berau yang adil — rute termurah, antrean rotasi, riwayat trip — di atas graf Neo4j Relate.**

Dibangun untuk hackathon **Relate by Neo4j** (Devpost, deadline 12 Desember 2026).

## Cerita

Leo adalah driver ojek di Berau, Kalimantan Timur. Di pangkalan, dua hal selalu jadi soal: **berapa tarif yang adil ke tujuan** dan **siapa giliran narik berikutnya**. Pangkalan Graph menjawab keduanya dari satu graf:

- **Rute termurah** antar pangkalan/kota/bandara/pasar, dihitung dari data rute nyata (tarif Rp2.600/km).
- **Antrean rotasi adil** — siapa narik duluan, siapa berikutnya; yang sudah narik pindah ke belakang antrean.
- **Riwayat trip** — setiap trip tercatat di graf, terhubung ke drivernya.

Data rute yang dipakai adalah data asli dari lapangan (8 rute antar 6 tempat di Berau: Sambaliung, Tanjung Redeb, Bandara Kalimarau, Pasar Sanggam, Gunung Tabur, Teluk Bayur). Nama driver selain Leo (Budi, Agus, Slamet, Joko) adalah nama fiktif; tidak ada nomor HP asli siapa pun di aplikasi ini.

## Cara kerja graf (Relate)

Store Relate tersimpan sebagai satu file persistent: `data/pangkalan.rl` (bisa dibuka dan diperiksa juri — cukup `relate.connect("data/pangkalan.rl")`).

Model graf:

- `(:Place {name, kind})` — kind: `pangkalan` / `kota` / `bandara` / `pasar`
- `(:Driver {name})` — Leo, Budi, Agus, Slamet, Joko
- `(:Place)-[:CONNECTS_TO {distance_km, fare_rp}]->(:Place)` — dua arah, 8 rute = 16 edge
- `(:Driver)-[:SERVES]->(:Place)` — pangkalan asal tiap driver (Leo → Sambaliung)
- `(:Driver)-[:QUEUE_NEXT]->(:Driver)` — rantai rotasi adil, plus `(:Queue)-[:HEAD]->(:Driver)` penanda giliran depan
- `(:Trip {from, to, fare_rp, distance_km, created_at})` + `(:Driver)-[:TOOK]->(:Trip)` — dibuat tiap kali trip dicatat

**Catatan penting soal Relate:** `shortestPath()` / `allShortestPaths()` di Relate menghitung **jumlah hop, bukan bobot** — tidak ada Dijkstra berbobot (tidak ada APOC/GDS). Karena itu rute **termurah** dihitung sendiri dengan Dijkstra Python (`heapq`) di atas adjacency yang diambil dari Relate via Cypher (`graph.py: dijkstra()`), sementara `shortestPath()` Cypher tetap dipakai sebagai **pembanding hop-terpendek** di halaman utama.

## Setup & run

Butuh Python 3.12 (diuji di Python 3.12.3). Semua gratis, lokal, tanpa server/kredensial.

```bash
cd pangkalan-graph
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python seed.py
python app.py
```

Lalu buka **http://127.0.0.1:5000**.

- `python seed.py` — seed ulang store dari `data/seed-routes.json` (idempotent: hapus isi store, bangun ulang dari nol).
- `python app.py` — jalankan Flask di port 5000. Bila store belum ada/kosong, app auto-seed sendiri saat request pertama.
- `data/seed-routes.json` — salinan data rute asli, supaya repo mandiri.

## Fitur

1. **Cari rute termurah** — pilih asal + tujuan → Dijkstra di atas graf Relate → urutan tempat, total km, total tarif, jumlah hop. Rute hop-terpendek (Cypher `shortestPath`) ditampilkan sebagai pembanding bila berbeda. Contoh: Sambaliung → Gunung Tabur termurah via Tanjung Redeb (39 km, Rp101.500), bukan via Bandara (43 km).
2. **Antrean rotasi adil** — urutan driver + siapa giliran narik berikutnya. Tombol "Selesai trip / giliran berikutnya" memindahkan driver depan ke belakang antrean (edge `QUEUE_NEXT` + `HEAD` diperbarui di graf).
3. **Catat trip baru** — pilih driver, asal, tujuan → tarif dihitung via Dijkstra → tersimpan sebagai `(:Trip)` + `(:Driver)-[:TOOK]->(:Trip)` → muncul di riwayat trip, dan driver yang narik pindah ke belakang antrean.

API JSON: `GET /api/places`, `GET /api/drivers`, `GET /api/route?from=X&to=Y`, `GET /api/queue`, `POST /api/queue/advance`, `GET/POST /api/trips`, `GET /api/stats`.

## Struktur

```
pangkalan-graph/
├── app.py               # Flask app (port 5000) + API JSON
├── graph.py             # Layer Relate: seed/query, Dijkstra, antrean, trip
├── seed.py              # Seed store dari data/seed-routes.json
├── requirements.txt     # relate-db==1.2.0, Flask==3.1.0
├── data/
│   ├── pangkalan.rl     # Persistent Relate store (dibuat saat seed/run)
│   └── seed-routes.json # Data rute asli (8 rute, tarif Rp2.600/km)
├── templates/index.html # Satu halaman utama (Bahasa Indonesia)
└── static/              # (kosong — disiapkan bila perlu aset statis)
```

## Teknologi

- **Neo4j Relate** (`relate-db` 1.2.0, PyPI) — database graf embedded, file tunggal `.rl`, persistent, tanpa server. Import: `import relate`, koneksi: `relate.connect("./data/pangkalan.rl")`.
- **Flask** 3.1.0 + HTML/JS polos (tanpa framework JS berat).
- Python 3.12, semua dependency gratis dan berjalan lokal.

## AI-assisted development

Aplikasi ini dibangun dengan **bantuan AI agent (Muse / Hana)** atas arahan Leo: Leo merancang ide dan konsep (dispatch pangkalan ojek Berau yang adil), menyediakan data rute asli dari lapangan, dan memverifikasi hasil akhirnya. AI menulis kode, menguji, dan mendokumentasikan. Sesuai aturan hackathon, pengembangan berbantuan AI ini diungkapkan secara jujur di sini.

## Lisensi

MIT — lihat `LICENSE`.
