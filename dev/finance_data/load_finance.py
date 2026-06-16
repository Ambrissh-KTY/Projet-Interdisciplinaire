#!/usr/bin/env python3
"""Load CAC40 finance metrics into cac40.db from Yahoo Finance (best-effort). Idempotent.

yfinance is the free fallback after SimFin's free tier turned out to be US-only.
It does NOT expose quarterly revenue/profit back to 2018 (only ~4 annual years), so:
  revenue, profit : ANNUAL, one row per available year   (period 'YYYY')
  dividend        : QUARTERLY since 2018                  (period 'YYYY-Qn')

Dividend total = sum of that quarter's per-share dividends × CURRENT shares
outstanding. Shares are a present-day snapshot, so totals for older years are
approximate (buyback/issuance drift). source='yfinance'. No schema change —
FinancialMetrics.period is free-text TEXT holding both 'YYYY' and 'YYYY-Qn'.

Usage: python dev/finance_data/load_finance.py
"""
import csv
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "db" / "cac40.db"
CSV_PATH = BASE_DIR / "finance_data" / "CAC40_LEI_ISIN_list.csv"

START_YEAR = 2018
SOURCE = "yfinance"
INCOME_ROWS = {"revenue": "Total Revenue", "profit": "Net Income"}

UPSERT = (
    "INSERT INTO FinancialMetrics "
    "(lei, period, metric, value, currency, source, retrieved_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(lei, period, metric, source) DO UPDATE SET "
    "  value=excluded.value, currency=excluded.currency, retrieved_at=excluded.retrieved_at"
)


def annual_income(income_stmt):
    """[(period 'YYYY', metric, value)] for revenue + profit across all available years."""
    out = []
    if income_stmt is None:
        return out
    for metric, label in INCOME_ROWS.items():
        if label in income_stmt.index:
            for col, val in income_stmt.loc[label].dropna().items():
                out.append((str(col.year), metric, float(val)))
    return out


def quarterly_dividends(divs, shares, start_year=START_YEAR):
    """[(period 'YYYY-Qn', total)] — per-share dividends summed per quarter × shares,
    for years >= start_year. Empty if no share count or no dividends."""
    if not shares or divs is None or len(divs) == 0:
        return []
    by_q = defaultdict(float)
    for ts, dps in divs.items():
        if ts.year >= start_year:
            by_q[f"{ts.year}-Q{(ts.month - 1) // 3 + 1}"] += float(dps)
    return [(p, v * shares) for p, v in sorted(by_q.items())]


def load(con):
    """Upsert annual revenue/profit + quarterly dividends per company.
    Returns (written, skipped). Skips (with a warning) companies with no usable data."""
    now = datetime.now(timezone.utc).isoformat()
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
                shares = fast.get("shares") or t.info.get("sharesOutstanding")  # fast_info misses some tickers
                currency = fast.get("currency") or "EUR"
                income = annual_income(t.income_stmt)
                divs = quarterly_dividends(t.dividends, shares)
            except Exception as e:
                print(f"  ⚠ {company} ({ticker}): {type(e).__name__}: {e}", file=sys.stderr)
                skipped += 1
                continue
            if not income and not divs:
                print(f"  ⚠ {company} ({ticker}): no income or dividends, skipped", file=sys.stderr)
                skipped += 1
                continue
            for period, metric, value in income:
                con.execute(UPSERT, (lei, period, metric, value, currency, SOURCE, now))
                written += 1
            for period, total in divs:
                con.execute(UPSERT, (lei, period, "dividend", total, currency, SOURCE, now))
                written += 1
            print(f"✓ {company}: {len(income)} annual income rows, {len(divs)} dividend quarters {currency}")
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
