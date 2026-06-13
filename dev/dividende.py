import pandas as pd
import yfinance as yf
import sqlite3

# =========================
# 1. CHARGEMENT DU DATASET CAC40
# =========================

df_companies = pd.read_csv("CAC40_LEI_ISIN_list.csv")

# Nettoyage colonnes importantes
df_companies = df_companies[[
    "input_name",
    "input_isin",
    "input_ticker"
]]

# =========================
# 2. CONSTRUCTION DES TICKERS YAHOO
# =========================
# règle simple : ISIN → ticker Euronext (.PA)
# (car Yahoo Finance fonctionne avec .PA)

def isin_to_yahoo(isin):
    return isin  # on garde ISIN pour mapping, pas utilisé directement

df_companies["yahoo_ticker"] = df_companies["input_isin"].apply(
    lambda x: None  # placeholder
)

# correction : on utilise en réalité le nom connu (plus fiable ici)
# on mappe directement via ticker manquant → fallback basé sur naming
# mais ton fichier est déjà propre, donc on reconstruit simplement :

df_companies["yahoo_ticker"] = df_companies["input_name"].apply(
    lambda x: None
)

# 👉 VERSION SIMPLE ET ROBUSTE :
# on utilise mapping manuel ISIN → ticker Yahoo (.PA)

isin_to_ticker = {
    "FR0000121014": "MC.PA",
    "FR0000120073": "AI.PA",
    "FR0000121972": "SU.PA",
    "FR0000120321": "OR.PA",
    "FR0000120271": "TTE.PA",
    "FR0000120578": "SAN.PA",
    "FR0000131104": "BNP.PA",
    "FR0000120503": "EN.PA",
    "FR0000124141": "VIE.PA",
    "FR0000121329": "HO.PA",
    "FR0000121667": "EL.PA",
    "FR0000127771": "VIV.PA",
    "FR0000125007": "SGO.PA",
    "FR0000120628": "CS.PA",
    "FR0000133308": "ORA.PA",
    "FR0000120693": "RI.PA",
    "FR0000130577": "PUB.PA",
    "FR0000121485": "KER.PA",
    "FR0000120321": "OR.PA",
}

df_companies["yahoo_ticker"] = df_companies["input_isin"].map(isin_to_ticker)

df_companies = df_companies.dropna(subset=["yahoo_ticker"])

# =========================
# 3. RECUPERATION DIVIDENDES
# =========================

results = []

for _, row in df_companies.iterrows():

    ticker = row["yahoo_ticker"]
    name = row["input_name"]

    try:
        stock = yf.Ticker(ticker)
        divs = stock.dividends

        if len(divs) == 0:
            continue

        divs = divs[divs.index >= "2020-01-01"]

        results.append({
            "ticker": ticker,
            "company": name,
            "total_dividends": float(divs.sum()),
            "last_dividend": float(divs.iloc[-1]),
            "last_date": str(divs.index[-1].date()),
            "n_payments": int(len(divs))
        })

    except Exception as e:
        print(f"Erreur {ticker}: {e}")

df = pd.DataFrame(results)

# =========================
# 4. SQLITE DATABASE
# =========================

conn = sqlite3.connect("cac40_project.db")

df.to_sql(
    "dividends",
    conn,
    if_exists="replace",
    index=False
)

df_companies.to_sql(
    "companies",
    conn,
    if_exists="replace",
    index=False
)

conn.close()

print(df.head())