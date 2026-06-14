#!/usr/bin/env python3

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf


# =========================================================
# PATHS OFFICIELS DU REPO
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "db" / "cac40.db"
CSV_PATH = BASE_DIR / "finance_data" / "CAC40_LEI_ISIN_list.csv"


# =========================================================
# MAIN PIPELINE
# =========================================================

def main():
    now = datetime.now(timezone.utc).isoformat()

    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")

    inserted = 0
    skipped = 0

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            lei = row["lei"]
            ticker = row["input_ticker"]
            company = row["input_name"]

            if not ticker:
                skipped += 1
                continue

            try:
                stock = yf.Ticker(ticker)
                divs = stock.dividends

                if divs is None or len(divs) == 0:
                    skipped += 1
                    continue

                # filtre période
                divs = divs[divs.index >= "2020-01-01"]

                if len(divs) == 0:
                    skipped += 1
                    continue

                total = float(divs.sum())
                last = float(divs.iloc[-1])
                last_year = str(divs.index[-1].year)

                # =================================================
                # INSERT 1 : somme dividendes
                # =================================================
                con.execute(
                    """
                    INSERT INTO FinancialMetrics
                    (lei, period, metric, value, currency, source, retrieved_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(lei, period, metric, source)
                    DO UPDATE SET
                        value=excluded.value,
                        currency=excluded.currency,
                        retrieved_at=excluded.retrieved_at
                    """,
                    (
                        lei,
                        "2020-2026",
                        "dividend_sum_per_share",
                        total,
                        "EUR",
                        "yfinance",
                        now,
                    ),
                )

                # =================================================
                # INSERT 2 : dernier dividende
                # =================================================
                con.execute(
                    """
                    INSERT INTO FinancialMetrics
                    (lei, period, metric, value, currency, source, retrieved_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(lei, period, metric, source)
                    DO UPDATE SET
                        value=excluded.value,
                        currency=excluded.currency,
                        retrieved_at=excluded.retrieved_at
                    """,
                    (
                        lei,
                        last_year,
                        "last_dividend_per_share",
                        last,
                        "EUR",
                        "yfinance",
                        now,
                    ),
                )

                inserted += 2

                print(f"✓ {company}: somme={total:.2f} dernier={last:.2f}")

            except Exception:
                skipped += 1

    con.commit()
    con.close()

    print(f"\nDone: {inserted} metrics inserted, {skipped} skipped")


if __name__ == "__main__":
    main()