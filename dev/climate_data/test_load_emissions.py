#!/usr/bin/env python3
"""Self-check for load_emissions.load. Run: python dev/climate_data/test_load_emissions.py"""
import sqlite3
import tempfile
from pathlib import Path

from load_emissions import load

HEADER = "company,lei,reporting_year,scope,basis,category,value,unit,source\n"


def make_con():
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE company (lei TEXT PRIMARY KEY);
        CREATE TABLE Emissions (
            id INTEGER PRIMARY KEY, lei TEXT, reporting_year INT, scope INT,
            basis TEXT DEFAULT '', category TEXT DEFAULT '', value REAL,
            unit TEXT DEFAULT 'tCO2e', source TEXT DEFAULT '', retrieved_at TEXT,
            UNIQUE (lei, reporting_year, scope, basis, category, source));
        INSERT INTO company VALUES ('GOODLEI0000000000001');
    """)
    return con


def write_csv(body):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="")
    f.write(HEADER + body)
    f.close()
    return Path(f.name)


def test_load_validation_defaults_and_upsert():
    con = make_con()
    csv = write_csv(
        "Good,GOODLEI0000000000001,2023,1,,,1000,,NZDPU\n"        # unit defaults to tCO2e
        "Good,GOODLEI0000000000001,2023,3,,5,200,tCO2e,NZDPU\n"   # scope-3 category
        "Bad,UNKNOWNLEI,2023,1,,,50,,NZDPU\n"                     # unknown LEI -> skip
        "Bad,GOODLEI0000000000001,2023,7,,,50,,NZDPU\n"          # bad scope -> skip
        "Bad,GOODLEI0000000000001,2023,1,,,50,,\n"               # missing source -> skip
        "Bad,GOODLEI0000000000001,202X,1,,,50,,NZDPU\n"          # bad year -> skip
    )
    written, skipped = load(con, csv)
    assert (written, skipped) == (2, 4), (written, skipped)
    assert con.execute("SELECT count(*) FROM Emissions").fetchone()[0] == 2
    assert con.execute(
        "SELECT unit FROM Emissions WHERE scope=1"
    ).fetchone()[0] == "tCO2e"  # default applied

    # Re-loading the same file updates in place (idempotent), not duplicates.
    written2, _ = load(con, csv)
    assert written2 == 2
    assert con.execute("SELECT count(*) FROM Emissions").fetchone()[0] == 2
    print("ok: validation, unit default, scope-3 category, idempotent upsert")


if __name__ == "__main__":
    test_load_validation_defaults_and_upsert()
    print("PASS")
