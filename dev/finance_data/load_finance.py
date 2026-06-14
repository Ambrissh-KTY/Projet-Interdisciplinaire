#!/usr/bin/env python3

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf


DB_PATH = Path(__file__).parent.parent / "db" / "cac40.db"
CSV_PATH = Path(__file__).parent / "CAC40_LEI_ISIN_list.csv"


def main():

    now = datetime.now(timezone.utc).isoformat()

    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")

    inserted = 0
    skipped = 0

    try:

        with open(CSV_PATH, newline="", encoding="utf-8") as f:

            reader = csv.DictReader(f)

            for row in reader:

                lei = row["lei"]
                ticker = row["input_ticker"]
                company = row["input_name"]

                if not ticker:
                    print(f"⚠ Pas de ticker pour {company}")
                    skipped += 1
                    continue

                try:

                    stock = yf.Ticker(ticker)
                    divs = stock.dividends

                    if divs is None or len(divs) == 0:
                        print(f"⚠ Aucun dividende pour {company}")
                        skipped += 1
                        continue

                    # Filtre 5 ans
                    divs = divs[divs.index >= "2020-01-01"]

                    if len(divs) == 0:
                        skipped += 1
                        continue

                    last_date = str(divs.index[-1].date())
                    div_sum = float(divs.sum())
                    last_div = float(divs.iloc[-1])
                    count_div = int(len(divs))

                    # =========================
                    # 1) somme dividendes
                    # =========================
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
                            div_sum,
                            "EUR",
                            "yfinance",
                            now,
                        ),
                    )

                    # =========================
                    # 2) dernier dividende
                    # =========================
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
                            str(divs.index[-1].year),
                            "last_dividend_per_share",
                            last_div,
                            "EUR",
                            "yfinance",
                            now,
                        ),
                    )

                    # =========================
                    # 3) nombre de dividendes
                    # =========================
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
                            "dividend_count",
                            count_div,
                            "unitless",
                            "yfinance",
                            now,
                        ),
                    )

                    # =========================
                    # 4) dernière date
                    # =========================
                    con.execute(
                        """
                        INSERT INTO FinancialMetrics
                        (lei, period, metric, value, currency, source, retrieved_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(lei, period, metric, source)
                        DO UPDATE SET
                            value=excluded.value,
                            retrieved_at=excluded.retrieved_at
                        """,
                        (
                            lei,
                            "2020-2026",
                            "last_dividend_date",
                            last_date,
                            None,
                            "yfinance",
                            now,
                        ),
                    )

                    inserted += 4

                    print(
                        f"✓ {company}: "
                        f"somme={div_sum:.2f} | "
                        f"dernier={last_div:.2f} | "
                        f"nb={count_div}"
                    )

                except Exception as e:
                    print(f"✗ {company} ({ticker}) : {e}")
                    skipped += 1

        con.commit()

        print()
        print(
            f"Terminé : {inserted} métriques insérées ; "
            f"{skipped} entreprises ignorées."
        )

    finally:
        con.close()


if __name__ == "__main__":
    main()