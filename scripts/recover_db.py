#!/usr/bin/env python3
"""
PILIHAN TERAKHIR untuk pemulihan logging.db yang korup ("database disk image
is malformed"). **Coba `.recover` dari sqlite3 CLI dulu** (lihat README bagian
Troubleshooting / pesan commit ini) -- diuji langsung dengan database yang
sengaja dirusak (pola freelist + rowid-out-of-order yang mirip kejadian
nyata): sqlite3 CLI `.recover` menyelamatkan 199.985/200.000 baris (99,99%),
script Python di file ini cuma 70.522/200.000 (35%) pada kasus uji yang SAMA.
Cuma pakai script ini kalau benar-benar tidak bisa install paket `sqlite3` di
manapun (mis. tidak ada akses Docker sama sekali untuk container bantuan).

Cara pakai (dari working dir /app di dalam container):
    python3 recover_db.py

Strategi: salin tabel per tabel, BARIS PER BARIS lewat fetchone() di dalam
try/except -- bukan SELECT * lalu fetchall() sekaligus, yang gagal TOTAL
(nol baris) begitu cursor-nya ketemu satu halaman rusak saja. Dengan
fetchone() satu-satu, begitu cursor mentok di halaman korup, baris-baris
yang SUDAH berhasil dibaca sebelum titik itu tetap aman tersalin -- tidak
ikut hilang.

Sengaja TIDAK PERNAH menulis ke logging.db sumbernya -- cuma baca (SELECT),
hasil salvage ditulis ke file BARU (logging_recovered.db). logging.db asli
tidak tersentuh sama sekali, aman untuk dicoba berkali-kali.

Batasan (TERBUKTI SIGNIFIKAN dari pengujian di atas): baris valid yang
letaknya SETELAH halaman rusak dalam urutan b-tree TIDAK ikut tersalin --
Python sqlite3 tidak bisa "lompat" ke tengah tabel setelah cursor mentok di
korupsi. `.recover` tidak punya batasan ini karena scan mentah per halaman,
bukan lewat traversal b-tree yang sama yang lagi rusak.
"""
import os
import sqlite3

SRC = 'logging.db'
DST = 'logging_recovered.db'

if os.path.exists(DST):
    print(f"[RECOVER] {DST} sudah ada -- hapus/pindahkan dulu kalau mau ulang dari nol.")
    raise SystemExit(1)

print(f"[RECOVER] Sumber : {SRC} ({os.path.getsize(SRC):,} bytes)")
src = sqlite3.connect(SRC)
dst = sqlite3.connect(DST)

dst.executescript("""
CREATE TABLE cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, url TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    Tanggal TEXT, Waktu TEXT, Lokasi TEXT, Bukti TEXT, jenis TEXT DEFAULT ''
);
CREATE TABLE app_settings (
    key TEXT PRIMARY KEY, value TEXT
);
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
""")
dst.commit()

# Kecil & penting duluan (cameras/app_settings/users -- akun login ada di
# sini!), tabel `data` (paling besar & paling banyak korupsinya) terakhir.
TABLES = ['cameras', 'app_settings', 'users', 'data']

grand_total = 0
for table in TABLES:
    print(f"\n[RECOVER] === {table} ===")
    ok = 0
    bad_inserts = 0
    try:
        cur = src.execute(f"SELECT * FROM {table} ORDER BY rowid")
        cols = [d[0] for d in cur.description]
        col_list = ','.join(f'"{c}"' for c in cols)
        placeholders = ','.join('?' for _ in cols)
        insert_sql = f'INSERT OR IGNORE INTO {table} ({col_list}) VALUES ({placeholders})'
        while True:
            try:
                row = cur.fetchone()
            except sqlite3.DatabaseError as e:
                print(f"  [STOP] Cursor mentok di korupsi setelah {ok:,} baris: {e}")
                break
            if row is None:
                break
            try:
                dst.execute(insert_sql, row)
                ok += 1
            except sqlite3.Error:
                bad_inserts += 1
            if ok and ok % 100000 == 0:
                dst.commit()
                print(f"  ... {ok:,} baris tersalin")
    except sqlite3.DatabaseError as e:
        print(f"  [GAGAL TOTAL] SELECT awal gagal: {e}")
    dst.commit()
    grand_total += ok
    print(f"  Hasil: {ok:,} baris tersalin, {bad_inserts} gagal insert (duplikat/constraint)")

src.close()
dst.close()
print(f"\n[RECOVER] SELESAI. Total {grand_total:,} baris berhasil diselamatkan ke {DST}")
print("[RECOVER] JANGAN langsung timpa logging.db -- cek dulu isinya masuk akal:")
print("  python3 -c \"import sqlite3; c=sqlite3.connect('logging_recovered.db'); "
      "print('data:', c.execute('SELECT COUNT(*) FROM data').fetchone()); "
      "print('users:', c.execute('SELECT username, role FROM users').fetchall()); "
      "print('cameras:', c.execute('SELECT id, name FROM cameras').fetchall())\"")
