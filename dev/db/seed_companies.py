#!/usr/bin/env python3
"""Seed the company table from the CAC40 LEI/ISIN CSV. Idempotent (upsert on LEI).

Usage: python dev/db/seed_companies.py
"""
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "cac40.db"
CSV_PATH = Path(__file__).parent.parent / "finance_data" / "CAC40_LEI_ISIN_list.csv"

# CSV column -> company column
FIELD_MAP = {
    "lei": "lei",
    "input_isin": "isin",
    "input_name": "input_name",
    "matched_legal_name": "legal_name",
    "input_ticker": "ticker",
    "match_method": "match_method",
    "jurisdiction": "jurisdiction",
    "country": "country",
    "city": "city",
    "entity_status": "entity_status",
    "registration_status": "registration_status",
}


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    cols = list(FIELD_MAP.values()) + ["added_at"]
    placeholders = ", ".join("?" for _ in cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "lei")
    sql = (
        f"INSERT INTO company ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(lei) DO UPDATE SET {updates}"
    )

    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            values = [row.get(src) or None for src in FIELD_MAP] + [now]
            con.execute(sql, values)
        con.commit()
        total = con.execute("SELECT count(*) FROM company").fetchone()[0]
        print(f"seeded {len(rows)} rows; company now has {total} rows")
    finally:
        con.close()


if __name__ == "__main__":
    main()
