# Comment ajouter des données à la base

Guide pas-à-pas pour les débutant·es. Objectif : que **n'importe qui** dans l'équipe
puisse charger ses données (émissions CO2, chiffres financiers, décisions de justice)
dans la base `cac40.db`, sans rien casser.

> Si un mot technique vous bloque, voyez le **glossaire** tout en bas.

---

## 1. Le principe en une minute

- La base est un seul fichier : `dev/db/cac40.db` (format **SQLite**).
- Ce fichier n'est **pas** dans Git (il est trop lourd). On le **reconstruit** à partir
  des scripts. Donc : pas de panique, on peut toujours le refaire de zéro.
- Toutes les tables sont reliées entre elles par le **LEI** de l'entreprise : un code
  unique de 20 caractères (ex. `969500QZC2Q0TK11NV07` pour Accor). C'est la « clé »
  qui dit « cette ligne d'émissions appartient à telle entreprise ».
- On ajoute des données en écrivant un **petit script Python** qui lit votre fichier
  (CSV, JSON…) et l'insère dans la base. On copie-colle un modèle, on l'adapte.

---

## 2. Avant de commencer (une seule fois)

Il vous faut **Python 3** (vérifiez avec `python --version` ou `python3 --version`).
Aucune bibliothèque à installer : tout utilise la librairie standard de Python.

Construisez la base depuis la racine du projet :

```bash
python dev/db/migrate.py          # crée cac40.db et toutes les tables
python dev/db/seed_companies.py   # charge les 40 entreprises du CAC40
```

Vérifiez que ça a marché :

```bash
sqlite3 dev/db/cac40.db ".tables"
# doit afficher : Company  Court_decision  Emissions  FinancialMetrics
```

Si `sqlite3` n'est pas installé, ce n'est pas grave, on peut tout faire en Python.

---

## 3. Comprendre les tables (où vont vos données ?)

| Table              | Ce qu'elle contient                       | Qui s'en occupe |
|--------------------|-------------------------------------------|-----------------|
| `Company`          | Les 40 entreprises (déjà remplie)         | — (ne pas toucher) |
| `Emissions`        | Émissions de CO2                          | équipe climat   |
| `FinancialMetrics` | Chiffres financiers (CA, dividende…)      | équipe finance  |
| `Court_decision`   | Décisions de justice / procès             | équipe justice  |

### Le format « long » (important)

Les tables `Emissions` et `FinancialMetrics` sont en **format long** : **une mesure =
une ligne**. On ne crée pas une colonne par année ou par métrique. Pour ajouter le CA
2023 ET le CA 2024 d'une entreprise, on ajoute **deux lignes**. Avantage : ajouter une
nouvelle année ou une nouvelle métrique ne demande **jamais** de modifier la structure
de la base.

### Les colonnes exactes

**Emissions** — une ligne par (entreprise, année, scope, base, catégorie, source) :

| Colonne          | Exemple             | Sens |
|------------------|---------------------|------|
| `lei`            | `969500QZC2Q0TK11NV07` | l'entreprise (obligatoire) |
| `reporting_year` | `2023`              | année (obligatoire) |
| `scope`          | `1`, `2` ou `3`     | type d'émission (obligatoire) |
| `basis`          | `location_based`, `market_based` ou `''` | base de calcul (scope 2) |
| `category`       | `'1'`..`'15'` ou `''` | catégorie scope 3 |
| `value`          | `123456.7`          | la valeur |
| `unit`           | `tCO2e`             | unité (par défaut `tCO2e`) |
| `source`         | `NZDPU/CDP`         | d'où vient la donnée (obligatoire) |
| `restated`       | `0` ou `1`          | donnée corrigée ? |
| `retrieved_at`   | `2026-06-13T...`    | date de récupération |

**FinancialMetrics** — une ligne par (entreprise, période, métrique, source) :

| Colonne        | Exemple        | Sens |
|----------------|----------------|------|
| `lei`          | `969500QZC...` | l'entreprise (obligatoire) |
| `period`       | `2023`, `2023-Q4` | la période (obligatoire) |
| `metric`       | `revenue`, `dividend`, `market_cap` | quelle mesure (obligatoire) |
| `value`        | `5200000000`   | la valeur |
| `currency`     | `EUR`          | la devise |
| `source`       | `yfinance`     | d'où vient la donnée (obligatoire) |
| `retrieved_at` | `2026-06-13T...` | date de récupération |

**Court_decision** — une ligne par décision de justice :

| Colonne         | Exemple                       | Sens |
|-----------------|-------------------------------|------|
| `lei`           | `969500QZC...`                | l'entreprise (obligatoire) |
| `decision_date` | `2022-05-12`                  | date de la décision |
| `jurisdiction`  | `FR`                          | pays / ressort |
| `court`         | `Tribunal de commerce de Paris` | la juridiction |
| `case_ref`      | `2022/01234`                  | numéro d'affaire |
| `summary`       | `Condamnation pour entente`   | **résumé affiché sur le site** |
| `outcome`       | `Amende de 2 M€`              | issue / verdict |
| `url`           | `https://...`                 | lien vers la source |
| `source`        | `Légifrance`                  | d'où vient la donnée |
| `retrieved_at`  | `2026-06-13T...`              | date de récupération |

> ⚠️ Le champ `summary` est celui qui s'affiche dans le bloc « Pénal » de l'interface.
> Rédigez-le en une phrase claire et lisible.

---

## 4. Trouver le LEI d'une entreprise

Vos données contiennent sûrement des **noms** d'entreprises, pas des LEI. La
correspondance nom → LEI se trouve dans
`dev/finance_data/CAC40_LEI_ISIN_list.csv` (colonnes `input_name` et `lei`).

**Règle d'or :** insérez toujours par **LEI**, jamais par nom. Les noms varient
(« L'Oréal » vs « L'OREAL SA »), le LEI est stable. Le script ci-dessous fait la
correspondance automatiquement à partir du CSV.

---

## 5. Ajouter vos données : le modèle de script

La façon recommandée. Copiez ce fichier, renommez-le (ex.
`dev/finance_data/load_finance.py`), et adaptez les deux parties marquées
`# À ADAPTER`. Il s'inspire de [seed_companies.py](seed_companies.py).

```python
#!/usr/bin/env python3
"""Charge mes données dans cac40.db. Relançable sans créer de doublons."""
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "cac40.db"
LEI_CSV = Path(__file__).parent.parent / "finance_data" / "CAC40_LEI_ISIN_list.csv"
MON_FICHIER = Path(__file__).parent / "mes_donnees.csv"   # À ADAPTER : votre fichier

def charger_lei():
    """Dictionnaire nom_majuscules -> lei, pour retrouver le LEI depuis un nom."""
    with open(LEI_CSV, newline="", encoding="utf-8") as f:
        return {row["input_name"].upper(): row["lei"] for row in csv.DictReader(f)}

def main():
    now = datetime.now(timezone.utc).isoformat()
    lei_par_nom = charger_lei()
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")   # refuse un LEI qui n'existe pas
    inseres, ignores = 0, 0
    try:
        with open(MON_FICHIER, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                lei = lei_par_nom.get(row["entreprise"].upper())   # À ADAPTER : nom de colonne
                if not lei:
                    print(f"  ⚠ entreprise inconnue, ignorée : {row['entreprise']}")
                    ignores += 1
                    continue
                # À ADAPTER : la requête et les valeurs selon votre table
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

Lancez-le :

```bash
python dev/finance_data/load_finance.py
```

### Pourquoi `ON CONFLICT ... DO UPDATE` ?

C'est ce qui rend le script **idempotent** : vous pouvez le relancer 10 fois, il ne
créera **pas** de doublons — il met simplement à jour les lignes existantes. C'est
possible grâce aux contraintes `UNIQUE` des tables :

- `Emissions` : `UNIQUE (lei, reporting_year, scope, basis, category, source)`
- `FinancialMetrics` : `UNIQUE (lei, period, metric, source)`

Adaptez la ligne `ON CONFLICT(...)` pour qu'elle liste **exactement** ces colonnes
selon la table que vous remplissez.

> ⚠️ **`Court_decision` n'a pas de contrainte `UNIQUE`.** Si vous relancez un script
> d'insertion, vous obtiendrez des **doublons**. Pour cette table, le plus simple est
> de tout effacer avant de réinsérer :
> `con.execute("DELETE FROM Court_decision WHERE source = ?", ("ma_source",))`
> puis un simple `INSERT` (sans `ON CONFLICT`).

---

## 6. Mettre à jour le site

L'interface ([../interface/index.html](../interface/index.html)) ne lit **pas** la
base directement : elle lit un fichier `data.json`. Après avoir ajouté des données,
régénérez-le :

```bash
python dev/db/export_json.py
```

Pour voir le résultat dans le navigateur (le `fetch` ne marche pas en ouvrant le
fichier directement, il faut un petit serveur) :

```bash
python -m http.server -d dev/interface
# puis ouvrez http://localhost:8000
```

> Pour l'instant, seul le bloc « Pénal » (procès) est branché. Le chiffre d'affaires,
> le dividende et le CO2 restent vides tant que le code de
> [export_json.py](export_json.py) n'a pas été complété (les requêtes sont déjà
> écrites en commentaire dedans, il suffit de les activer).

---

## 7. À NE JAMAIS FAIRE

- ❌ **Ne modifiez pas** un fichier `migrations/NNNN_*.sql` déjà existant. Pour changer
  la structure de la base, on **ajoute** un nouveau fichier `migrations/0002_xxx.sql`.
  (Voir la section « Migrations » du [README.md](README.md).)
- ❌ Ne committez pas `cac40.db` (il est ignoré par Git, et c'est voulu).
- ❌ N'insérez pas une entreprise par son nom : toujours par son **LEI**.

## En cas de pépin

- *« no such table »* → vous n'avez pas lancé `migrate.py`.
- *« FOREIGN KEY constraint failed »* → le LEI inséré n'existe pas dans `Company`
  (faute de frappe, ou entreprise hors CAC40).
- *Doublons* → vous insérez sans `ON CONFLICT` (ou dans `Court_decision`, voir §5).
- *Tout est cassé* → supprimez `cac40.db` et refaites l'étape 2. Rien n'est perdu.

---

## Glossaire

- **SQLite** : une base de données contenue dans un seul fichier, sans serveur.
- **LEI** : *Legal Entity Identifier*, code unique mondial de 20 caractères par entreprise.
- **Format long** : une mesure par ligne (plutôt qu'une colonne par mesure).
- **Idempotent** : qu'on peut relancer plusieurs fois sans changer le résultat
  (ici : sans créer de doublons).
- **Upsert** : *update + insert* — insérer, ou mettre à jour si la ligne existe déjà.
- **Migration** : un fichier `.sql` qui décrit la structure de la base.
