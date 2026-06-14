#!/usr/bin/env python3
"""
resolve_leis.py — Resolve GLEIF Level-1 LEIs for a list of companies.

MVP scope: CAC 40. Designed to scale to the full Euronext universe by
swapping the input list (see load_companies()).

Resolution strategy (in order of reliability):
    1. ISIN  -> LEI   via  GET /lei-records?filter[isin]=...
    2. name  -> LEI   via  fuzzy name search (fallback for ISIN misses)

Architecture:
    - BRONZE: every raw GLEIF JSON response is written to ./data/bronze/
      (timestamped). Re-runs read cached bronze instead of re-hitting the API.
    - OUTPUT: a clean master table ./data/companies_lei.csv that becomes the
      join spine for the rest of your pipeline (yfinance, climate, court data).

No API key required. GLEIF is open data (mind their Terms of Use).

Usage:
    python resolve_leis.py                 # uses built-in CAC 40 seed list
    python resolve_leis.py --input my.csv  # CSV with columns: name[,isin][,ticker]
    python resolve_leis.py --no-cache      # ignore bronze cache, force fresh calls
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

API_BASE = "https://api.gleif.org/api/v1"
HEADERS = {
    "Accept": "application/vnd.api+json",
    "User-Agent": "euronext-esg-research/0.1 (academic project)",
}

DATA_DIR = Path("data")
BRONZE_DIR = DATA_DIR / "bronze"
OUTPUT_CSV = DATA_DIR / "companies_lei.csv"

# Polite rate limiting. GLEIF throttles aggressive clients.
REQUEST_DELAY = 0.4          # seconds between calls
MAX_RETRIES = 4
BACKOFF_BASE = 2.0           # exponential backoff factor


# ---------------------------------------------------------------------------
# Input: CAC 40 seed list.
# ISINs verified against public sources (Wikipedia / Euronext) at time of
# writing. The index is reviewed QUARTERLY, so treat this as a starting seed,
# not gospel — re-verify membership before each production run.
# ---------------------------------------------------------------------------
CAC40_SEED = [
    ("Accor", "FR0000120404"),
    ("Air Liquide", "FR0000120073"),
    ("Airbus", "NL0000235190"),
    ("ArcelorMittal", "LU1598757687"),
    ("AXA", "FR0000120628"),
    ("BNP Paribas", "FR0000131104"),
    ("Bouygues", "FR0000120503"),
    ("Capgemini", "FR0000125338"),
    ("Carrefour", "FR0000120172"),
    ("Crédit Agricole", "FR0000045072"),
    ("Danone", "FR0000120644"),
    ("Dassault Systèmes", "FR0014003TT8"),
    ("Edenred", "FR0010908533"),
    ("Engie", "FR0010208488"),
    ("EssilorLuxottica", "FR0000121667"),
    ("Eurofins Scientific", "FR0014000MR3"),
    ("Hermès International", "FR0000052292"),
    ("Kering", "FR0000121485"),
    ("Legrand", "FR0010307819"),
    ("L'Oréal", "FR0000120321"),
    ("LVMH", "FR0000121014"),
    ("Michelin", "FR001400AJ45"),
    ("Orange", "FR0000133308"),
    ("Pernod Ricard", "FR0000120693"),
    ("Publicis Groupe", "FR0000130577"),
    ("Renault", "FR0000131906"),
    ("Safran", "FR0000073272"),
    ("Saint-Gobain", "FR0000125007"),
    ("Sanofi", "FR0000120578"),
    ("Schneider Electric", "FR0000121972"),
    ("Société Générale", "FR0000130809"),
    ("Stellantis", "NL00150001Q9"),
    ("STMicroelectronics", "NL0000226223"),
    ("Teleperformance", "FR0000051807"),
    ("Thales", "FR0000121329"),
    ("TotalEnergies", "FR0000120271"),
    ("Unibail-Rodamco-Westfield", "FR0013326246"),
    ("Veolia", "FR0000124141"),
    ("Vinci", "FR0000125486"),
    ("Vivendi", "FR0000127771"),
]


# ---------------------------------------------------------------------------
# HTTP helper with retries + backoff
# ---------------------------------------------------------------------------
def gleif_get(path: str, params: dict) -> Optional[dict]:
    """GET a GLEIF endpoint with retry/backoff. Returns parsed JSON or None."""
    url = f"{API_BASE}/{path}"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
        except requests.RequestException as exc:
            wait = BACKOFF_BASE ** attempt
            print(f"    network error ({exc}); retry in {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
            continue

        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return None  # no record — a normal "miss", not an error
        if resp.status_code == 429:
            wait = BACKOFF_BASE ** attempt
            print(f"    rate limited; backing off {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
            continue
        # other 4xx/5xx
        print(f"    HTTP {resp.status_code} on {url} {params}", file=sys.stderr)
        time.sleep(BACKOFF_BASE ** attempt)
    return None


# ---------------------------------------------------------------------------
# Bronze cache
# ---------------------------------------------------------------------------
def bronze_path(key: str) -> Path:
    safe = key.replace("/", "_").replace(" ", "_")
    return BRONZE_DIR / f"{safe}.json"


def write_bronze(key: str, payload: dict) -> None:
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "key": key,
        "response": payload,
    }
    bronze_path(key).write_text(json.dumps(record, ensure_ascii=False, indent=2))


def read_bronze(key: str) -> Optional[dict]:
    p = bronze_path(key)
    if p.exists():
        return json.loads(p.read_text())["response"]
    return None


# ---------------------------------------------------------------------------
# Resolution logic
# ---------------------------------------------------------------------------
def parse_lei_record(payload: dict) -> Optional[dict]:
    """Extract the fields we care about from a /lei-records response."""
    data = payload.get("data")
    if not data:
        return None
    rec = data[0] if isinstance(data, list) else data
    attr = rec.get("attributes", {})
    entity = attr.get("entity", {})
    legal_name = (entity.get("legalName") or {}).get("name")
    addr = entity.get("legalAddress", {})
    return {
        "lei": rec.get("id"),
        "legal_name": legal_name,
        "jurisdiction": entity.get("jurisdiction"),
        "entity_status": entity.get("status"),
        "registration_status": (attr.get("registration") or {}).get("status"),
        "country": addr.get("country"),
        "city": addr.get("city"),
    }


def resolve_by_isin(isin: str, use_cache: bool) -> Optional[dict]:
    key = f"isin_{isin}"
    payload = read_bronze(key) if use_cache else None
    if payload is None:
        payload = gleif_get("lei-records", {"filter[isin]": isin})
        if payload is not None:
            write_bronze(key, payload)
        time.sleep(REQUEST_DELAY)
    if not payload:
        return None
    return parse_lei_record(payload)


def resolve_by_name(name: str, use_cache: bool) -> Optional[dict]:
    """Fallback: fuzzy-search the legal name, then fetch the top candidate's record."""
    key = f"name_{name}"
    payload = read_bronze(key) if use_cache else None
    if payload is None:
        payload = gleif_get(
            "fuzzycompletions",
            {"field": "entity.legalName", "q": name},
        )
        if payload is not None:
            write_bronze(key, payload)
        time.sleep(REQUEST_DELAY)
    if not payload or not payload.get("data"):
        return None

    # fuzzycompletions returns candidates with a relationship to the lei-record.
    top = payload["data"][0]
    lei = (
        top.get("relationships", {})
        .get("lei-records", {})
        .get("data", {})
        .get("id")
    )
    if not lei:
        # Some responses inline the value instead of a relationship id.
        lei = top.get("attributes", {}).get("value")
    if not lei:
        return None

    # Hydrate the full record so output columns are consistent with ISIN path.
    rec_key = f"lei_{lei}"
    rec_payload = read_bronze(rec_key) if use_cache else None
    if rec_payload is None:
        rec_payload = gleif_get(f"lei-records/{lei}", {})
        if rec_payload is not None:
            write_bronze(rec_key, rec_payload)
        time.sleep(REQUEST_DELAY)
    if not rec_payload:
        return {"lei": lei, "legal_name": None, "jurisdiction": None,
                "entity_status": None, "registration_status": None,
                "country": None, "city": None}
    return parse_lei_record(rec_payload)


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------
def load_companies(input_csv: Optional[str]) -> list[dict]:
    if input_csv:
        rows = []
        with open(input_csv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append({
                    "name": (r.get("name") or "").strip(),
                    "isin": (r.get("isin") or "").strip() or None,
                    "ticker": (r.get("ticker") or "").strip() or None,
                })
        return rows
    # default: CAC 40 seed
    return [{"name": n, "isin": i, "ticker": None} for n, i in CAC40_SEED]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve GLEIF LEIs for companies.")
    ap.add_argument("--input", help="CSV with columns name[,isin][,ticker]")
    ap.add_argument("--no-cache", action="store_true",
                    help="ignore bronze cache; force fresh API calls")
    args = ap.parse_args()
    use_cache = not args.no_cache

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    companies = load_companies(args.input)
    print(f"Resolving LEIs for {len(companies)} companies "
          f"(cache {'on' if use_cache else 'off'})...\n")

    results = []
    hits_isin = hits_name = misses = 0

    for i, c in enumerate(companies, 1):
        name, isin = c["name"], c["isin"]
        print(f"[{i:>2}/{len(companies)}] {name}")
        rec = None
        method = None

        if isin:
            rec = resolve_by_isin(isin, use_cache)
            if rec and rec.get("lei"):
                method = "isin"
                hits_isin += 1

        if (not rec or not rec.get("lei")) and name:
            rec = resolve_by_name(name, use_cache)
            if rec and rec.get("lei"):
                method = "name_fuzzy"
                hits_name += 1

        if not rec or not rec.get("lei"):
            misses += 1
            print(f"      -> NO MATCH")
            results.append({
                "input_name": name, "input_isin": isin, "input_ticker": c["ticker"],
                "lei": None, "matched_legal_name": None, "match_method": None,
                "jurisdiction": None, "entity_status": None,
                "registration_status": None, "country": None, "city": None,
            })
            continue

        print(f"      -> {rec['lei']}  ({method})  {rec.get('legal_name')}")
        results.append({
            "input_name": name,
            "input_isin": isin,
            "input_ticker": c["ticker"],
            "lei": rec["lei"],
            "matched_legal_name": rec.get("legal_name"),
            "match_method": method,
            "jurisdiction": rec.get("jurisdiction"),
            "entity_status": rec.get("entity_status"),
            "registration_status": rec.get("registration_status"),
            "country": rec.get("country"),
            "city": rec.get("city"),
        })

    # Write master table
    fieldnames = ["input_name", "input_isin", "input_ticker", "lei",
                  "matched_legal_name", "match_method", "jurisdiction",
                  "entity_status", "registration_status", "country", "city"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print("\n" + "=" * 50)
    print(f"ISIN hits:   {hits_isin}")
    print(f"Name hits:   {hits_name}")
    print(f"Misses:      {misses}")
    print(f"Output:      {OUTPUT_CSV}")
    print(f"Raw cache:   {BRONZE_DIR}/")
    if misses:
        print("\nReview misses manually — likely ISIN typos, delisted entities,")
        print("or holding-vs-operating entity mismatches.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
