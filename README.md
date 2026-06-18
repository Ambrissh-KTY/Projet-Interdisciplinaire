# ECO<sub>S</sub>INT

Par Cyrine BEN MESSAOUD, Oscar BOUDAILLIEZ, Damien GEORGES, Noah HORWITZ--CHENIEUX, Ambrissh KICHENAMOURTTY et Zoé PENG.

## Pitch

Our project aggregates data about CAC40 companies to display revenue, dividends paid to shareholders, court cases relating to environmental violations, and publicly-reported emissions data to display the environmental cost of their operations and its varying intensity depending on the company.

## Build — run order

Before building the database, run:

```zsh
pip install -r requirements.txt
```

Then, follow these steps:

```bash
# 1. schema + companies (always first, in this order)
python dev/db/migrate.py                  # create/upgrade cac40.db from migrations/
python dev/db/seed_companies.py           # load the 40 companies from the LEI/ISIN CSV

# 2. data loaders (need step 1; independent of each other, either order)
python dev/finance_data/load_finance.py    # yfinance -> FinancialMetrics (annual revenue/profit + quarterly dividends since 2018)
python dev/climate_data/load_emissions.py  # CDU export -> Emissions (latest year, no projections)

# 3. export (always last, after the loaders)
python dev/db/export_json.py 
```

Finally, to display the dashboard in your browser, run:

```zsh
python -m http.server -d dev/interface
```

then go to

```
http://localhost:8000
```


## Structure

```
.
├── dev
│   ├── climate_data
│   │   ├── cdu_cac40_cleaned.csv
│   │   └── load_emissions.py
│   ├── db
│   │   ├── cac40_combined.csv
│   │   ├── cac40.db
│   │   ├── CONTRIBUTING_DATA.md
│   │   ├── export_json.py
│   │   ├── migrate.py
│   │   ├── migrations
│   │   │   └── 0001_init.sql
│   │   ├── README.md
│   │   └── seed_companies.py
│   ├── finance_data
│   │   ├── CAC40_LEI_ISIN_list.csv
│   │   ├── csv_generation
│   │   │   ├── fetch_tickers.py
│   │   │   └── resolve_leis.py
│   │   └── load_finance.py
│   ├── guide.md
│   ├── interface
│   │   ├── accueil.html
│   │   ├── burger-header.html
│   │   ├── cdu_cac40_cleaned.csv
│   │   ├── chart.umd.min.js
│   │   ├── data.json
│   │   ├── étude_de_cas.pdf
│   │   ├── fonts
│   │   ├── footer.css
│   │   ├── footer.html
│   │   ├── general
│   │   │   ├── accueil.css
│   │   │   └── accueil.html
│   │   ├── graph_test.html
│   │   ├── graphique
│   │   ├── images
│   │   ├── index_old.html
│   │   ├── index.html
│   │   ├── logo cac40
│   │   ├── méthodo.html
│   │   ├── page_entreprise.html
│   │   ├── photo_nous
│   │   ├── qui_sommes_nous.html
│   │   └── vue-simple.html
│   ├── justice_data
│   │   └── justice_data_import.py
│   ├── misc
│   │   └── TTF
│   └── tests
│       ├── test_co2_per_dividend.py
│       ├── test_load_emissions.py
│       └── test_load_finance.py
├── README.md
└── requirements.txt
```

See [dev/db/README.md](dev/db/README.md) for more information about the database structure.
