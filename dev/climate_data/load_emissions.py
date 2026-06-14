#!/usr/bin/env python3
"""Load CO2e emissions into cac40.db from emissions.csv. Idempotent (upsert).

Source: a manual export from NZDPU / Climate Data Utility
(https://climatedatautility.org) reshaped to emissions.csv. NZDPU's terms forbid
automated/bulk download, so the fetch step is by hand; this loader is the
reproducible part. See dev/db/CONTRIBUTING_DATA.md §3 for the Emissions schema.

emissions.csv columns (one measurement per row):
    company         human-readable name (for log messages only; matching is by lei)
    lei             20-char LEI, must exist in Company
    reporting_year  e.g. 2023
    scope           1, 2 or 3
    basis           'location_based' | 'market_based' | '' (scope 2 only)
    category        '1'..'15' | ''                         (scope 3 only)
    value           tCO2e
    unit            defaults to tCO2e if blank
    source          e.g. 'NZDPU/CDP' (required; part of the unique key)

Usage: python dev/climate_data/load_emissions.py
"""
import csv
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "cac40.db"
CSV_PATH = Path(__file__).parent / "emissions.csv"

UPSERT = (
    "INSERT INTO Emissions "
    "(lei, reporting_year, scope, basis, category, value, unit, source, retrieved_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(lei, reporting_year, scope, basis, category, source) DO UPDATE SET "
    "  value=excluded.value, unit=excluded.unit, retrieved_at=excluded.retrieved_at"
)


def load(con, csv_path):
    """Upsert rows from csv_path into Emissions. Returns (written, skipped).
    Rows with an unknown LEI or unparseable/out-of-range values are skipped with
    a warning rather than aborting the whole load."""
    known_leis = {r[0] for r in con.execute("SELECT lei FROM company")}
    now = datetime.now(timezone.utc).isoformat()
    written = skipped = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):  # line 1 = header
            who = (row.get("company") or row.get("lei") or "?").strip()
            try:
                lei = row["lei"].strip()
                if lei not in known_leis:
                    raise ValueError(f"unknown LEI {lei!r}")
                scope = int(row["scope"])
                if scope not in (1, 2, 3):
                    raise ValueError(f"scope must be 1/2/3, got {scope}")
                source = (row.get("source") or "").strip()
                if not source:
                    raise ValueError("source is required")
                values = (
                    lei,
                    int(row["reporting_year"]),
                    scope,
                    (row.get("basis") or "").strip(),
                    (row.get("category") or "").strip(),
                    float(row["value"]),
                    (row.get("unit") or "").strip() or "tCO2e",
                    source,
                    now,
                )
            except (KeyError, ValueError) as e:
                print(f"  ⚠ line {n} ({who}) skipped: {e}", file=sys.stderr)
                skipped += 1
                continue
            con.execute(UPSERT, values)
            written += 1
    return written, skipped


def main():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        written, skipped = load(con, CSV_PATH)
        con.commit()
        print(f"OK: {written} emissions rows inserted/updated, {skipped} skipped")
    finally:
        con.close()


if __name__ == "__main__":
    main()
