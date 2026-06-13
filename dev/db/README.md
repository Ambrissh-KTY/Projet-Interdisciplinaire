# Database

SQLite foundation for CAC40 climate / finance / justice data (later).

## Build

```bash
python dev/db/migrate.py          # create/upgrade cac40.db from migrations/
python dev/db/seed_companies.py   # load the 40 companies from the LEI/ISIN CSV
```

`cac40.db` is NOT in the repo (gitignored), but fully rebuildable from `migrations/` + the seed CSV.

## Schema

- **company** — dimension, PK = `lei`. Seeded from
  `dev/finance_data/CAC40_LEI_ISIN_list.csv`. `index_membership` 
- **emissions** — long-format facts (one row per company/year/scope/basis/
  scope-3 category/source). Empty until I put the data from the API
- **FinancialMetric** — long-format placeholder, empty until I get the yfinance data or docs.

Long format means new metrics, years, or scope-3 categories are new *rows*, not
schema changes. LEIs are used across the board for consistency - you can find them in dev/finance_data/CAC40_LEI_ISIN_list.csv.

## Migrations

The schema is the sum of `migrations/NNNN_*.sql` applied in order. `migrate.py`
tracks progress with SQLite's built-in `PRAGMA user_version` and skips files
already applied (idempotent). To change the schema, add the next-numbered file —
never edit an applied migration once the DB holds real data.

### *DO NOT UNDER ANY COMMIT A MODIFIED VERSION OF AN EXISTING .sql FILE ! IT WILL BREAK THE DATABASE !*

thank you. - Damien

## Pour après - Climate Data Utility (NZDPU) ingestion

The **Climate Data Utility / Net-Zero Data Public Utility** is a free, open
repository of company climate data (CDP-sourced), keyed by **LEI** — which we
already have for all 40 companies. It exposes a public REST API.

Planned `dev/climate_data/fetch_nzdpu.py`:

1. Confirm the live API host + paths from the service's `openapi.json`
   (`climatedatautility.org` / `nzdpu.com`).
2. For each `company.lei`: fetch disclosures, save the raw JSON to
   `dev/climate_data/raw/<lei>.json` (so we can reprocess without re-fetching).
3. Map into `emissions` rows (`source='NZDPU/CDP'`):
   - Scope 1 → `scope=1`
   - Scope 2 → `scope=2`, `basis` = location_based / market_based
   - Scope 3 → `scope=3`, `category` = 1..15
4. Upsert via the `UNIQUE(lei, reporting_year, scope, basis, category, source)`
   constraint.

stdlib `urllib.request` should suffice; add `requests` only if auth/retry needs grow.
