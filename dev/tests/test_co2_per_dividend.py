#!/usr/bin/env python3
"""Self-check for compute_co2_per_dividend. Run: python dev/tests/test_co2_per_dividend.py"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "db"))
from export_json import compute_co2_per_dividend


def make_con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE company (lei TEXT PRIMARY KEY);
        CREATE TABLE Emissions (lei TEXT, reporting_year INT, scope INT,
            category TEXT, value REAL);
        CREATE TABLE FinancialMetrics (lei TEXT, period TEXT, metric TEXT, value REAL);
    """)
    return con


def test_metric_rank_and_nulls():
    con = make_con()
    # CLEAN: low ratio. DIRTY: high ratio. ZERODIV: dividend 0. NOEM: no emissions.
    con.executemany("INSERT INTO company VALUES (?)",
                    [("CLEAN",), ("DIRTY",), ("ZERODIV",), ("NOEM",)])
    con.executemany("INSERT INTO Emissions VALUES (?,?,?,?,?)", [
        ("CLEAN", 2022, 1, "", 50),     # older year ignored
        ("CLEAN", 2023, 1, "", 100),    # latest year, two rows summed
        ("CLEAN", 2023, 2, "", 100),
        ("DIRTY", 2023, 1, "", 900),
        ("ZERODIV", 2023, 1, "", 100),
    ])
    con.executemany("INSERT INTO FinancialMetrics VALUES (?,?,?,?)", [
        ("CLEAN", "2023", "dividend", 100.0),    # 200/100 = 2.0
        ("DIRTY", "2023", "dividend", 100.0),    # 900/100 = 9.0
        ("ZERODIV", "2023", "dividend", 0.0),
        ("NOEM", "2023", "dividend", 100.0),
    ])

    out = compute_co2_per_dividend(con)
    assert out["CLEAN"]["value"] == 2.0e6, out["CLEAN"]   # tCO2e ×1e6 -> gCO2e/EUR
    assert out["DIRTY"]["value"] == 9.0e6, out["DIRTY"]
    # rank 1 = least intensive
    assert out["CLEAN"]["rank"] == 1
    assert out["DIRTY"]["rank"] == 2
    # missing / zero-dividend -> null & unranked
    assert out["ZERODIV"]["value"] is None and out["ZERODIV"]["rank"] is None
    assert out["NOEM"]["value"] is None and out["NOEM"]["rank"] is None
    # denominator = only companies with a valid ratio
    assert out["CLEAN"]["rank_total"] == 2
    print("ok: metric, ascending rank, null handling, rank_total")


def test_all_empty():
    con = make_con()
    con.execute("INSERT INTO company VALUES ('X')")
    out = compute_co2_per_dividend(con)
    assert out["X"] == {"value": None, "rank": None, "rank_total": 0,
                        "dividend": None, "emissions": None}
    print("ok: all-empty -> nulls and rank_total 0")


if __name__ == "__main__":
    test_metric_rank_and_nulls()
    test_all_empty()
    print("PASS")
