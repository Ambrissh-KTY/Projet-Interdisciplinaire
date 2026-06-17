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
from datetime import datetime, timezone
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


def latest_value(con, metric):
    """{lei: latest COMPLETE-year figure} for `metric`. Groups periods by calendar year
    (annual 'YYYY' or quarterly 'YYYY-Qn'), sums each year, and takes the most recent year
    that is fully past — so an annual metric is the latest year and a quarterly one (e.g.
    dividends stored per quarter) is annualized without summing across years or counting the
    in-progress current year (which would understate quarterly dividend payers)."""
    cur_year = datetime.now(timezone.utc).year
    by_year = defaultdict(lambda: defaultdict(float))  # lei -> year -> sum
    for r in con.execute(
        "SELECT lei, period, value FROM FinancialMetrics WHERE metric = ?", (metric,)
    ):
        if r["value"] is not None:
            by_year[r["lei"]][int(r["period"][:4])] += r["value"]
    out = {}
    for lei, years in by_year.items():
        complete = [y for y in years if y < cur_year]
        out[lei] = years[max(complete) if complete else max(years)]  # fall back if only current year
    return out

def history_values(con, metric):
    """{lei: {year: value}} — all complete years for `metric`."""
    cur_year = datetime.now(timezone.utc).year
    by_year = defaultdict(lambda: defaultdict(float))
    for r in con.execute(
        "SELECT lei, period, value FROM FinancialMetrics WHERE metric = ?", (metric,)
    ):
        if r["value"] is not None:
            by_year[r["lei"]][int(r["period"][:4])] += r["value"]
    out = {}
    for lei, years in by_year.items():
        out[lei] = {y: years[y] for y in sorted(years) if y < cur_year}
    return out


def compute_co2_per_dividend(con):
    """Return {lei: {"value", "rank", "rank_total"}} for CO2e per euro of
    dividend. value is gCO2e / EUR (emissions stored in tCO2e ×1e6). rank 1 = least
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

    # Denominator: each company's most recent dividend.
    dividend = latest_value(con, "dividend")  # lei -> value

    G_PER_TONNE = 1e6   # emissions stored in tCO2e; express the metric in grams/EUR
    leis = [r["lei"] for r in con.execute("SELECT lei FROM company")]
    ratios = {}
    for lei in leis:
        div = dividend.get(lei) or 0
        if lei in emissions and div != 0:
            ratios[lei] = emissions[lei] * G_PER_TONNE / div

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
        lei: {
            "value": ratios.get(lei),
            "rank": rank.get(lei),
            "rank_total": len(ratios),
            "dividend": dividend.get(lei),
            "emissions": emissions.get(lei),
        }
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
        revenue = latest_value(con, "revenue")
        revenue_history = history_values(con, "revenue")
        dividend_history = history_values(con, "dividend")

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
                "ca": revenue.get(c["lei"]),   # latest annual revenue (EUR), null if absent
                "div": m["dividend"],   # latest total dividend (EUR), null if absent
                # latest-year Scope 1 + Scope 2 (location-based) total, tCO2e
                "co2": m["emissions"],
                # gCO2e per euro of dividend. rank 1 = least intensive; null
                # value/rank when emissions or dividend data is missing.
                "co2e_per_eur_dividend": m["value"],
                "co2e_per_eur_dividend_rank": m["rank"],
                "co2e_per_eur_dividend_rank_total": m["rank_total"],
                "proces": proces,
                "ca_history": revenue_history.get(c["lei"], {}),
                "div_history": dividend_history.get(c["lei"], {}),
            })

        OUT_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {len(data)} companies -> {OUT_PATH.name}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
