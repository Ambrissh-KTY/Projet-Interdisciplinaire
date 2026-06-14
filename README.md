# Projet-Interdisciplinaire

Par Ambrissh KICHENAMOURTTY, Cyrine BEN MESSAOUD, Noah HORWITZ-CHENIEUX, Oscar BOUDAILLIEZ, Zoé PENG et Damien GEORGES.

Avant exécutions du code, exécutez

```zsh
pip install -r requirements.txt
```

## Pitch

TBA

## Structure

```
.
├── dev
│   ├── climate_data
│   │   ├── emissions.csv
│   │   └── load_emissions.py
│   ├── db
│   │   ├── CONTRIBUTING_DATA.md
│   │   ├── export_json.py
│   │   ├── migrate.py
│   │   ├── migrations
│   │   │   └── 0001_init.sql
│   │   ├── README.md
│   │   └── seed_companies.py
│   ├── finance_data
│   │   ├── CAC40_LEI_ISIN_list.csv
│   │   └── csv_generation
│   │       ├── fetch_tickers.py
│   │       └── resolve_leis.py
│   ├── guide.md
│   ├── interface
│   │   ├── data.json
│   │   └── index.html
│   └── justice_data
├── README.md
└── requirements.txt
```

See [dev/db/README.md](dev/db/README.md) for more information about the database.
