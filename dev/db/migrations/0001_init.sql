-- 0001_init.sql — CAC40 climate/finance/justice foundation schema.
-- Applied by migrate.py, which sets PRAGMA user_version = 1 afterwards.
-- Portable SQL (no SQLite-only types); dates/times stored as ISO-8601 TEXT.

-- Company dimension. Natural PK = LEI (stable global identifier).
-- Columns mirror dev/finance_data/CAC40_LEI_ISIN_list.csv.
CREATE TABLE IF NOT EXISTS Company (
    lei                 TEXT PRIMARY KEY,
    isin                TEXT,
    input_name          TEXT,
    legal_name          TEXT,
    ticker              TEXT,
    match_method        TEXT,
    jurisdiction        TEXT,
    country             TEXT,
    city                TEXT,
    entity_status       TEXT,
    registration_status TEXT,
    index_membership    TEXT DEFAULT 'CAC40',  -- for later enlargement
    added_at            TEXT
);

-- Emissions facts (long format) — populated later from NZDPU/CDP.
-- One row per (company, year, scope, basis, scope-3 category, source).
CREATE TABLE IF NOT EXISTS Emissions (
    id             INTEGER PRIMARY KEY,
    lei            TEXT NOT NULL REFERENCES company(lei),
    reporting_year INTEGER NOT NULL,
    scope          INTEGER NOT NULL,   -- 1, 2 or 3
    basis          TEXT NOT NULL DEFAULT '',  -- 'location_based' | 'market_based' | '' (scope 2)
    category       TEXT NOT NULL DEFAULT '',  -- scope-3 category '1'..'15' | ''
    value          REAL,
    unit           TEXT DEFAULT 'tCO2e',
    source         TEXT NOT NULL DEFAULT '',
    restated       INTEGER,            -- 0/1
    retrieved_at   TEXT,
    UNIQUE (lei, reporting_year, scope, basis, category, source)
);

-- Financial metrics (long format) — placeholder, empty until a source is chosen.
CREATE TABLE IF NOT EXISTS FinancialMetrics (
    id           INTEGER PRIMARY KEY,
    lei          TEXT NOT NULL REFERENCES company(lei),
    period       TEXT NOT NULL,        -- '2023' | '2023-Q4' | ...
    metric       TEXT NOT NULL,        -- 'revenue' | 'market_cap' | ...
    value        REAL,
    currency     TEXT,
    source       TEXT NOT NULL DEFAULT '',
    retrieved_at TEXT,
    UNIQUE (lei, period, metric, source)
);

-- Court decisions (justice_data) — one row per legal decision per company.
-- Populated later; the frontend renders `summary` as a bullet per company.
CREATE TABLE IF NOT EXISTS Court_decision (
    id            INTEGER PRIMARY KEY,
    lei           TEXT NOT NULL REFERENCES company(lei),
    decision_date TEXT,
    jurisdiction  TEXT,
    court         TEXT,
    case_ref      TEXT,
    summary       TEXT,
    outcome       TEXT,
    url           TEXT,
    source        TEXT,
    retrieved_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_emissions_lei_year ON emissions (lei, reporting_year);
CREATE INDEX IF NOT EXISTS idx_financial_lei_period ON FinancialMetrics (lei, period);
CREATE INDEX IF NOT EXISTS idx_court_lei ON court_decision (lei);