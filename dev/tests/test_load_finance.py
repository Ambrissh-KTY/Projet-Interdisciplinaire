#!/usr/bin/env python3
"""Self-check for annual_total_dividend. Run: python dev/tests/test_load_finance.py"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "finance_data"))
from load_finance import annual_total_dividend, latest_revenue


def series(pairs):
    idx = pd.DatetimeIndex([d for d, _ in pairs], tz="Europe/Paris")
    return pd.Series([v for _, v in pairs], index=idx)


def test_latest_completed_year_times_shares():
    divs = series([
        ("2023-05-01", 1.0), ("2023-11-01", 0.5),   # 2023 total per share = 1.5
        ("2024-05-01", 2.0),                          # 2024 total per share = 2.0
        ("2026-05-01", 9.9),                          # current year -> dropped
    ])
    period, total = annual_total_dividend(divs, shares=100, this_year=2026)
    assert period == "2024", period          # most recent COMPLETED year
    assert total == 2.0 * 100, total         # per-share sum × shares
    print("ok: picks latest completed year, multiplies by shares")


def test_none_cases():
    divs = series([("2023-05-01", 1.0)])
    assert annual_total_dividend(divs, shares=None, this_year=2026) is None   # no share count
    assert annual_total_dividend(series([]), shares=100, this_year=2026) is None  # no dividends
    only_current = series([("2026-05-01", 1.0)])
    assert annual_total_dividend(only_current, shares=100, this_year=2026) is None  # only current year
    print("ok: None when shares/dividends missing or only current year")


def test_latest_revenue():
    stmt = pd.DataFrame(
        [[100.0, 200.0]],
        index=["Total Revenue"],
        columns=[pd.Timestamp("2023-12-31"), pd.Timestamp("2024-12-31")],
    )
    assert latest_revenue(stmt) == ("2024", 200.0)            # most recent year
    assert latest_revenue(None) is None
    assert latest_revenue(pd.DataFrame(index=["Other"])) is None  # no Total Revenue row
    print("ok: latest revenue picks most recent year")


if __name__ == "__main__":
    test_latest_completed_year_times_shares()
    test_none_cases()
    test_latest_revenue()
    print("PASS")
