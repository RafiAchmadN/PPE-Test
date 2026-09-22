#!/usr/bin/env python3
"""Diagnostik cepat: tabel apa saja yang ada di logging.db saat ini, dan
apakah masing-masing bisa di-query tanpa error. Jalankan dari /work
(lihat cara pakai di scripts/recover_with_sqlite_cli.sh)."""
import sqlite3

conn = sqlite3.connect('logging.db')
print("=== Tabel yang ada ===")
tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(tables)

for t in tables:
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {count:,} baris")
    except sqlite3.DatabaseError as e:
        print(f"  {t}: ERROR -- {e}")
