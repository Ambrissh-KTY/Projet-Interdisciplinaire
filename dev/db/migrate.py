#!/usr/bin/env python3
"""Apply pending SQL migrations to the SQLite DB, tracked via PRAGMA user_version.

Migrations are dev/db/migrations/NNNN_*.sql, applied in numeric order. Each file
bumps user_version to its number. Running this is idempotent: already-applied
files are skipped.

Usage: python dev/db/migrate.py
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "cac40.db"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def main() -> None:
    files = sorted(MIGRATIONS_DIR.glob("[0-9]*.sql"))
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        current = con.execute("PRAGMA user_version").fetchone()[0]
        applied = 0
        for path in files:
            version = int(path.name.split("_", 1)[0])
            if version <= current:
                continue
            con.executescript(path.read_text())
            con.execute(f"PRAGMA user_version = {version}")
            con.commit()
            print(f"applied {path.name} -> user_version {version}")
            applied += 1
        if applied == 0:
            print(f"up to date (user_version {current})")
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
