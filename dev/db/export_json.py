#!/usr/bin/env python3
"""Export the DB to dev/interface/data.json, shaped for the static frontend.

One object per company: { nom, lei, ca, div, co2, co2e_per_eur_dividend,
co2e_per_eur_dividend_rank, co2e_per_eur_dividend_rank_total, proces }.

Usage: python dev/db/export_json.py
"""
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(__file__).parent / "cac40.db"
OUT_PATH = Path(__file__).parent.parent / "interface" / "data.json"


# --- CO2e/€ metric configuration ------------------------------------------
# Which emissions rows feed the metric's numerator. All rows for now; to scope
# it later, return a condition, e.g.
#   return row["scope"] in (1, 2)
#   return row["scope"] == 3 and row["category"] in ("1", "2")
# NOTE: summing a scope-3 total (category='') alongside its per-category rows
# double-counts — narrow this predicate then. (Filtering in Python, not in SQL,
# keeps this a plain function instead of an injected WHERE fragment.)
def include_emission(row):
    return True


def compute_co2_per_dividend(con):
    """Return {lei: {"value", "rank", "rank_total"}} for CO2e per euro of
    dividend. value is tCO2e / EUR (no unit conversion). rank 1 = least
    intensive (lowest ratio); companies missing emissions, missing dividend, or
    with a zero dividend get value=None and rank=None. rank_total counts only
    the companies with a valid ratio. Prints a VERY loud message when data is missing.
    """
    # Numerator: sum each company's most recent reporting year.
    totals = defaultdict(lambda: defaultdict(float))  # lei -> year -> tCO2e
    for r in con.execute("SELECT lei, reporting_year, scope, category, value FROM Emissions"):
        if r["value"] is not None and include_emission(r):
            totals[r["lei"]][r["reporting_year"]] += r["value"]
    emissions = {lei: years[max(years)] for lei, years in totals.items()}

    # Denominator: each company's dividend at its most recent period.
    dividend = {}  # lei -> (period, value)
    for r in con.execute("SELECT lei, period, value FROM FinancialMetrics WHERE metric = 'dividend'"):
        if r["value"] is not None and r["period"] > dividend.get(r["lei"], ("", 0))[0]:
            dividend[r["lei"]] = (r["period"], r["value"])

    leis = [r["lei"] for r in con.execute("SELECT lei FROM company")]
    ratios = {}
    for lei in leis:
        div = dividend.get(lei, ("", 0))[1]
        if lei in emissions and div != 0:
            ratios[lei] = emissions[lei] / div

    # rank 1 = least intensive (lowest ratio).
    ranked = sorted(ratios, key=ratios.get)
    rank = {lei: i + 1 for i, lei in enumerate(ranked)}

    missing = len(leis) - len(ratios)
    if not ratios:
        print(
            "\n" + "!" * 70 + "\n"
            "!! NO CO2e/€ DATA: no company has both emissions and a non-zero!!!!!!!\n"
            "!! dividend, so the metric is null for all of them. Load Emissions!!!!\n"
            "!! and FinancialMetrics (metric='dividend'), then re-run.!!!!!!!!!!!!!\n"
            + "!" * 70 + "\n",
            file=sys.stderr,
        )
    elif missing:
        print(
            f"⚠ CO2e/€ metric: {len(ratios)}/{len(leis)} companies ranked "
            f"({missing} without emissions or a non-zero dividend → null).",
            file=sys.stderr,
        )

    return {
        lei: {"value": ratios.get(lei), "rank": rank.get(lei), "rank_total": len(ratios)}
        for lei in leis
    }


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    try:
        con.row_factory = sqlite3.Row
        companies = con.execute(
            "SELECT lei, input_name FROM company ORDER BY input_name"
        ).fetchall()

        co2_per_div = compute_co2_per_dividend(con)

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
            m = co2_per_div[c["lei"]]
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
                # tCO2e per euro of dividend. rank 1 = least intensive; null
                # value/rank when emissions or dividend data is missing.
                "co2e_per_eur_dividend": m["value"],
                "co2e_per_eur_dividend_rank": m["rank"],
                "co2e_per_eur_dividend_rank_total": m["rank_total"],
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
