#!/usr/bin/env python3
"""Export the DB to dev/interface/data.json, shaped for the static frontend.

One object per company: { nom, lei, ca, div, co2, proces }. The frontend (index.html)
fetches this instead of a hardcoded array. Rerun after seeding/loading data.

Usage: python dev/db/export_json.py
"""
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "cac40.db"
OUT_PATH = Path(__file__).parent.parent / "interface" / "data.json"


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    try:
        con.row_factory = sqlite3.Row
        companies = con.execute(
            "SELECT lei, input_name FROM company ORDER BY input_name"
        ).fetchall()

        data = []
        for c in companies:
            proces = [
                r["summary"]
                for r in con.execute(
                    "SELECT summary FROM court_decision "
                    "WHERE lei = ? ORDER BY decision_date DESC",
                    (c["lei"],),
                )
                if r["summary"]
            ]
            data.append({
                "nom": c["input_name"],
                "lei": c["lei"],
                # Empty until FinancialMetrics / Emissions are loaded and metric
                # keys are fixed. Then replace with e.g.:
                #   "ca":  latest FinancialMetrics.value WHERE metric='revenue'
                #   "div": latest FinancialMetrics.value WHERE metric='dividend'
                #   "co2": latest Emissions.value WHERE scope=1
                "ca": "",
                "div": "",
                "co2": "",
                "proces": proces,
            })

        OUT_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {len(data)} companies -> {OUT_PATH.name}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
