#!/usr/bin/env python3
"""Self-checks for the yfinance finance loader + annualization (offline).
Run: python dev/tests/test_load_finance.py"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "finance_data"))
sys.path.insert(0, str(ROOT / "db"))
from load_finance import annual_income, quarterly_dividends
from export_json import latest_value


def test_annual_income_revenue_and_profit():
    stmt = pd.DataFrame(
        [[100.0, 200.0], [10.0, 25.0]],
        index=["Total Revenue", "Net Income"],
        columns=[pd.Timestamp("2023-12-31"), pd.Timestamp("2024-12-31")],
    )
    out = set(annual_income(stmt))
    assert ("2024", "revenue", 200.0) in out
    assert ("2023", "profit", 10.0) in out
    assert annual_income(None) == []
    print("ok: annual_income emits revenue+profit per year")


def test_quarterly_dividends_buckets_and_filters():
    idx = pd.DatetimeIndex(["2017-05-01", "2018-05-10", "2018-06-20", "2024-11-03"], tz="Europe/Paris")
    divs = pd.Series([9.9, 1.0, 0.5, 2.0], index=idx)
    out = dict(quarterly_dividends(divs, shares=100, start_year=2018))
    assert "2017-Q2" not in out                 # before start_year dropped
    assert out["2018-Q2"] == (1.0 + 0.5) * 100  # two payments same quarter summed × shares
    assert out["2024-Q4"] == 2.0 * 100
    assert quarterly_dividends(divs, shares=None) == []   # no share count
    print("ok: quarterly_dividends buckets by quarter, filters year, scales by shares")


def test_latest_value_annual_and_sparse_dividend():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE FinancialMetrics (lei TEXT, period TEXT, metric TEXT, value REAL)")
    con.executemany(
        "INSERT INTO FinancialMetrics (lei,period,metric,value) VALUES (?,?,?,?)",
        [("L1", "2023", "revenue", 100.0), ("L1", "2024", "revenue", 200.0),   # annual -> latest year
         ("L1", "2023-Q2", "dividend", 100.0), ("L1", "2024-Q2", "dividend", 120.0)],  # once/year -> latest YEAR only
    )
    con.commit()
    assert latest_value(con, "revenue") == {"L1": 200.0}    # most recent year
    assert latest_value(con, "dividend") == {"L1": 120.0}   # NOT 220 — no cross-year sum
    print("ok: latest_value takes latest calendar year, never sums across years")


def test_latest_value_drops_in_progress_year():
    from datetime import datetime, timezone
    cur = datetime.now(timezone.utc).year
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE FinancialMetrics (lei TEXT, period TEXT, metric TEXT, value REAL)")
    con.executemany(
        "INSERT INTO FinancialMetrics (lei,period,metric,value) VALUES (?,?,?,?)",
        [("L1", f"{cur-1}-Q2", "dividend", 90.0),   # last complete year
         ("L1", f"{cur}-Q1", "dividend", 20.0)],    # in-progress year (partial) -> ignored
    )
    con.commit()
    assert latest_value(con, "dividend") == {"L1": 90.0}   # not the partial current year
    print("ok: latest_value ignores the in-progress current year when a complete one exists")


if __name__ == "__main__":
    test_annual_income_revenue_and_profit()
    test_quarterly_dividends_buckets_and_filters()
    test_latest_value_annual_and_sparse_dividend()
    test_latest_value_drops_in_progress_year()
    print("PASS")
