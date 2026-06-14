# Ajouter des données à la base

*Rédigé par Claude parce que Damien Georges n'avait pas le temps*

---

## 1. Vue d'ensemble

- La base est un fichier unique : `dev/db/cac40.db` (SQLite).
- Ce fichier n'est pas dans Git. On le reconstruit depuis les scripts.
- Toutes les tables sont reliées par le **LEI** de l'entreprise : un code unique de 20 caractères (ex. `969500QZC2Q0TK11NV07` pour Accor).
- On ajoute des données via un script Python qui lit un fichier source (CSV, JSON…) et insère dans la base.

---

## 2. Setup (une seule fois)

```bash
python dev/db/migrate.py          # crée cac40.db et les tables
python dev/db/seed_companies.py   # charge les 40 entreprises du CAC40
```

Vérification :

```bash
sqlite3 dev/db/cac40.db ".tables"
# Company  Court_decision  Emissions  FinancialMetrics
```

---

## 3. Tables

| Table              | Contenu                                   | Équipe          |
|--------------------|-------------------------------------------|-----------------|
| `Company`          | Les 40 entreprises (déjà remplie)         | — (ne pas toucher) |
| `Emissions`        | Émissions de CO2                          | climat          |
| `FinancialMetrics` | Chiffres financiers (CA, dividende…)      | finance         |
| `Court_decision`   | Décisions de justice                      | justice         |

### Format long

`Emissions` et `FinancialMetrics` sont en format long : **une mesure = une ligne**. Pas de colonne par année ou par métrique. Ajouter une nouvelle année ou métrique ne demande jamais de modifier le schéma.

### Schémas

**Emissions** — clé unique : `(lei, reporting_year, scope, basis, category, source)`

| Colonne          | Exemple                  | Notes                       |
|------------------|--------------------------|-----------------------------|
| `lei`            | `969500QZC2Q0TK11NV07`   | obligatoire                 |
| `reporting_year` | `2023`                   | obligatoire                 |
| `scope`          | `1`, `2` ou `3`          | obligatoire                 |
| `basis`          | `location_based`, `market_based` ou `''` | scope 2 uniquement |
| `category`       | `'1'`..`'15'` ou `''`   | scope 3 uniquement          |
| `value`          | `123456.7`               |                             |
| `unit`           | `tCO2e`                  | défaut : `tCO2e`            |
| `source`         | `NZDPU/CDP`              | obligatoire                 |
| `restated`       | `0` ou `1`               |                             |
| `retrieved_at`   | `2026-06-13T...`         |                             |

**FinancialMetrics** — clé unique : `(lei, period, metric, source)`

| Colonne        | Exemple             | Notes       |
|----------------|---------------------|-------------|
| `lei`          | `969500QZC...`      | obligatoire |
| `period`       | `2023`, `2023-Q4`   | obligatoire |
| `metric`       | `revenue`, `dividend`, `market_cap` | obligatoire |
| `value`        | `5200000000`        |             |
| `currency`     | `EUR`               |             |
| `source`       | `yfinance`          | obligatoire |
| `retrieved_at` | `2026-06-13T...`    |             |

**Court_decision** — pas de contrainte UNIQUE (voir §5)

| Colonne         | Exemple                         | Notes                          |
|-----------------|---------------------------------|--------------------------------|
| `lei`           | `969500QZC...`                  | obligatoire                    |
| `decision_date` | `2022-05-12`                    |                                |
| `jurisdiction`  | `FR`                            |                                |
| `court`         | `Tribunal de commerce de Paris` |                                |
| `case_ref`      | `2022/01234`                    |                                |
| `summary`       | `Condamnation pour entente`     | affiché dans le bloc « Pénal » |
| `outcome`       | `Amende de 2 M€`                |                                |
| `url`           | `https://...`                   |                                |
| `source`        | `Légifrance`                    |                                |
| `retrieved_at`  | `2026-06-13T...`                |                                |

---

## 4. Trouver un LEI

La correspondance nom → LEI est dans `dev/finance_data/CAC40_LEI_ISIN_list.csv` (colonnes `input_name` et `lei`).

Toujours insérer par **LEI**, jamais par nom (les noms varient, le LEI est stable).

---

## 5. Modèle de script

Copiez ce fichier, renommez-le (ex. `dev/finance_data/load_finance.py`), adaptez les parties marquées `# À ADAPTER`. Inspiré de [seed_companies.py](seed_companies.py).

```python
#!/usr/bin/env python3
"""Charge mes données dans cac40.db. Idempotent."""
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "cac40.db"
LEI_CSV = Path(__file__).parent.parent / "finance_data" / "CAC40_LEI_ISIN_list.csv"
MON_FICHIER = Path(__file__).parent / "mes_donnees.csv"   # À ADAPTER

def charger_lei():
    with open(LEI_CSV, newline="", encoding="utf-8") as f:
        return {row["input_name"].upper(): row["lei"] for row in csv.DictReader(f)}

def main():
    now = datetime.now(timezone.utc).isoformat()
    lei_par_nom = charger_lei()
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    inseres, ignores = 0, 0
    try:
        with open(MON_FICHIER, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                lei = lei_par_nom.get(row["entreprise"].upper())   # À ADAPTER : nom de colonne
                if not lei:
                    print(f"  ⚠ entreprise inconnue, ignorée : {row['entreprise']}")
                    ignores += 1
                    continue
                # À ADAPTER : requête et valeurs selon la table cible
                con.execute(
                    "INSERT INTO FinancialMetrics (lei, period, metric, value, currency, source, retrieved_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(lei, period, metric, source) DO UPDATE SET "
                    "  value=excluded.value, currency=excluded.currency, retrieved_at=excluded.retrieved_at",
                    (lei, row["annee"], "revenue", float(row["ca"]), "EUR", "mon_source", now),
                )
                inseres += 1
        con.commit()
        print(f"OK : {inseres} lignes insérées/mises à jour, {ignores} ignorées")
    finally:
        con.close()

if __name__ == "__main__":
    main()
```

```bash
python dev/finance_data/load_finance.py
```


---

## 6. Mettre à jour le site

L'interface lit `data.json`, pas la base directement. Après insertion :

```bash
python dev/db/export_json.py
```

Pour voir le résultat :

```bash
python -m http.server -d dev/interface
# http://localhost:8000
```

Seul le bloc « Pénal » est branché pour l'instant. CA, dividende et CO2 restent vides jusqu'à ce que les requêtes commentées dans [export_json.py](export_json.py) soient activées.

---

## 7. À ne pas faire

- Ne modifiez pas un fichier `migrations/NNNN_*.sql` existant. Pour modifier le schéma, ajoutez un `migrations/0002_xxx.sql`.
- Ne committez pas `cac40.db`.
- N'insérez pas par nom d'entreprise — toujours par LEI.

---
