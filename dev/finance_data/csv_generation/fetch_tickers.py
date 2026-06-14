#!/usr/bin/env python3
"""Fill the input_ticker column of the CAC40 CSV with Yahoo Finance tickers.

Looks each company up by ISIN via yfinance and prefers its Euronext Paris
(.PA) listing. Idempotent: rewrites input_ticker on
every run, preserving all other columns. Run seed_companies.py afterwards to
load the tickers into cac40.db.

Usage: python dev/finance_data/fetch_tickers.py
"""
import csv
from pathlib import Path

import yfinance as yf

CSV_PATH = Path(__file__).parent / "CAC40_LEI_ISIN_list.csv"

# ISINs whose Yahoo lookup needs help. Stellantis defaults to Milan (.MI) but
# trades on Euronext Paris as STLAP.PA, which is the CAC40 listing.
# ArcelorMittal has no working .PA listing, so its Amsterdam .AS is kept as-is.
OVERRIDE = {"NL00150001Q9": "STLAP.PA"}


def yahoo_ticker(isin: str) -> str:
    if isin in OVERRIDE:
        return OVERRIDE[isin]
    quotes = yf.Search(isin, max_results=5).quotes
    if not quotes:
        raise RuntimeError(f"no Yahoo match for ISIN {isin}")
    paris = [q for q in quotes if str(q.get("symbol", "")).endswith(".PA")]
    return (paris[0] if paris else quotes[0])["symbol"]


def main() -> None:
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    for row in rows:
        row["input_ticker"] = yahoo_ticker(row["input_isin"])
        print(f"{row['input_name']:28} {row['input_isin']}  {row['input_ticker']}")

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} tickers to {CSV_PATH.name}")


if __name__ == "__main__":
    main()
