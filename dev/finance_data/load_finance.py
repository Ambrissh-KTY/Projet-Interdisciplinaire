#!/usr/bin/env python3
"""Load total dividends into cac40.db from Yahoo Finance. Idempotent (upsert).

For each CAC40 company (ticker from CAC40_LEI_ISIN_list.csv) this stores the
most recent COMPLETED calendar year's total dividend as a FinancialMetrics row
with metric='dividend' — the figure dev/db/export_json.py divides emissions by
for the CO2e/€ metric.

  total dividend = (sum of that year's per-share dividends) × shares outstanding

yfinance.dividends is per-share; shares outstanding is a current snapshot, so the
total is approximate for past years — we keep only the latest completed year,
where the current share count is closest. The incomplete current year is dropped
to avoid understating the total. See dev/db/CONTRIBUTING_DATA.md §3 for the schema.

Usage: python dev/finance_data/load_finance.py
"""
import csv
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "db" / "cac40.db"
CSV_PATH = BASE_DIR / "finance_data" / "CAC40_LEI_ISIN_list.csv"

UPSERT = (
    "INSERT INTO FinancialMetrics "
    "(lei, period, metric, value, currency, source, retrieved_at) "
    "VALUES (?, ?, ?, ?, ?, 'yfinance', ?) "
    "ON CONFLICT(lei, period, metric, source) DO UPDATE SET "
    "  value=excluded.value, currency=excluded.currency, retrieved_at=excluded.retrieved_at"
)


def annual_total_dividend(divs, shares, this_year):
    """(period, total) for the most recent COMPLETED calendar year, or None.
    total = sum of that year's per-share dividends × shares outstanding."""
    if not shares or divs is None or len(divs) == 0:
        return None
    past = divs[divs.index.year < this_year]   # drop the incomplete current year
    if len(past) == 0:
        return None
    by_year = past.groupby(past.index.year).sum()
    year = int(by_year.index.max())
    return str(year), float(by_year.loc[year]) * shares


def latest_revenue(income_stmt):
    """(period, value) for the most recent annual Total Revenue (CA), or None."""
    if income_stmt is None or "Total Revenue" not in income_stmt.index:
        return None
    rev = income_stmt.loc["Total Revenue"].dropna()
    if rev.empty:
        return None
    col = max(rev.index)
    return str(col.year), float(rev[col])


def load(con):
    """Upsert one 'dividend' row per company. Returns (written, skipped).
    A company with no ticker, no dividends, or no share count is skipped with a
    warning rather than aborting the run."""
    now = datetime.now(timezone.utc).isoformat()
    this_year = datetime.now(timezone.utc).year
    written = skipped = 0
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lei, ticker, company = row["lei"], row["input_ticker"], row["input_name"]
            if not ticker:
                skipped += 1
                continue
            try:
                t = yf.Ticker(ticker)
                fast = t.fast_info
                shares = fast.get("shares") or t.info.get("sharesOutstanding")  # fallback: fast_info misses some tickers (e.g. ML.PA)
                currency = fast.get("currency") or "EUR"
                div = annual_total_dividend(t.dividends, shares, this_year)
                rev = latest_revenue(t.income_stmt)
            except Exception as e:
                print(f"  ⚠ {company} ({ticker}): {type(e).__name__}: {e}", file=sys.stderr)
                skipped += 1
                continue
            if not div and not rev:
                print(f"  ⚠ {company} ({ticker}): no dividend or revenue, skipped", file=sys.stderr)
                skipped += 1
                continue
            parts = []
            if div:
                con.execute(UPSERT, (lei, div[0], "dividend", div[1], currency, now))
                written += 1
                parts.append(f"div {div[0]} ≈ {div[1]:,.0f}")
            if rev:
                con.execute(UPSERT, (lei, rev[0], "revenue", rev[1], currency, now))
                written += 1
                parts.append(f"CA {rev[0]} ≈ {rev[1]:,.0f}")
            print(f"✓ {company}: {', '.join(parts)} {currency}")
    return written, skipped


def main():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        written, skipped = load(con)
        con.commit()
        print(f"\nDone: {written} metric rows inserted/updated, {skipped} companies skipped")
    finally:
        con.close()


if __name__ == "__main__":
    main()
