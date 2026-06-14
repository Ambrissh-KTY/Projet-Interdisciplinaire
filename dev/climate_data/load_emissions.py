#!/usr/bin/env python3
"""Load CAC40 CO2e emissions into cac40.db from the Climate Data Utility export. Idempotent.

Reads cdu_cac40_cleaned.csv — a manual NZDPU / Climate Data Utility
(https://climatedatautility.org) export. Their terms forbid automated/bulk
download, so that fetch is by hand; this loader is the reproducible part. We keep
ONLY each company's latest reported Scope 1 and Scope 2 (location-based) — never
the 2026 projection nor the per-year history — tagged with the reporting year,
and upsert into Emissions (tCO2e). Companies are matched to their LEI by
normalised name against CAC40_LEI_ISIN_list.csv. See dev/db/CONTRIBUTING_DATA.md
§3 for the Emissions schema.

Usage: python dev/climate_data/load_emissions.py
"""
import csv
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE.parent / "db" / "cac40.db"
CDU_CSV = HERE / "cdu_cac40_cleaned.csv"
LEI_CSV = HERE.parent / "finance_data" / "CAC40_LEI_ISIN_list.csv"

SOURCE = "NZDPU/CDP"
LEGAL_SUFFIXES = {"SE", "SA", "NV", "PLC", "AG", "GROUP"}
# CDU names that don't normalise to a CAC40 name -> a name that does.
OVERRIDE = {"Stellantis NV (Fiat Chrysler + Groupe PSA)": "Stellantis"}

UPSERT = (
    "INSERT INTO Emissions "
    "(lei, reporting_year, scope, basis, category, value, unit, source, retrieved_at) "
    "VALUES (?, ?, ?, ?, '', ?, 'tCO2e', ?, ?) "
    "ON CONFLICT(lei, reporting_year, scope, basis, category, source) DO UPDATE SET "
    "  value=excluded.value, retrieved_at=excluded.retrieved_at"
)


def norm(s):
    """Uppercase, drop accents/punctuation and trailing legal-form tokens."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    toks = re.sub(r"[^A-Za-z0-9]+", " ", s).upper().split()
    while toks and toks[-1] in LEGAL_SUFFIXES:
        toks.pop()
    return " ".join(toks)


def _num(cell):
    cell = cell.replace(",", "").strip()
    return float(cell) if cell else None


def cdu_emission_rows(rows, name2lei):
    """Parse raw CDU csv rows into (company, lei, year, scope, basis, value)
    tuples — latest Scope 1 + Scope 2 (location-based) only, projection/history
    columns ignored. Returns (emission_rows, unmatched_company_names)."""
    start = next(i for i, r in enumerate(rows) if r and r[0].strip() == "Company") + 1
    out, missing = [], []
    for r in rows[start:]:
        if not r or not r[0].strip():
            continue
        company, year = r[0].strip(), r[1].strip()
        lei = name2lei.get(norm(OVERRIDE.get(company, company)))
        if not lei:
            missing.append(company)
            continue
        scope1, scope2_loc = _num(r[2]), _num(r[3])   # cols 4/5 = total/projection -> ignored
        if scope1 is not None:
            out.append((company, lei, int(year), 1, "", scope1))
        if scope2_loc is not None:
            out.append((company, lei, int(year), 2, "location_based", scope2_loc))
    return out, missing


def load(con):
    """Upsert the latest CDU emissions into Emissions. Returns (written, missing)."""
    name2lei = {}
    for r in csv.DictReader(open(LEI_CSV, newline="", encoding="utf-8")):
        name2lei[norm(r["matched_legal_name"])] = r["lei"]
        name2lei.setdefault(norm(r["input_name"]), r["lei"])

    rows = list(csv.reader(open(CDU_CSV, newline="", encoding="utf-8-sig")))
    emissions, missing = cdu_emission_rows(rows, name2lei)

    now = datetime.now(timezone.utc).isoformat()
    for _company, lei, year, scope, basis, value in emissions:
        con.execute(UPSERT, (lei, year, scope, basis, value, SOURCE, now))
    return len(emissions), missing


def main():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        written, missing = load(con)
        con.commit()
        print(f"OK: {written} emission rows inserted/updated ({written // 2} companies)")
        if missing:
            print(f"⚠ UNMATCHED (no LEI, skipped): {', '.join(missing)}", file=sys.stderr)
    finally:
        con.close()


if __name__ == "__main__":
    main()
