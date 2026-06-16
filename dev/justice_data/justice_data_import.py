"""Load CAC40 environmental court decisions into cac40.db from the Judilibre API.

Queries the Cour de cassation Judilibre API (via PISTE) for each CAC40 company
crossed with environmental keywords, dedups the hits, matches each company to its
LEI (by normalised name against CAC40_LEI_ISIN_list.csv) and writes one row per
decision into Court_decision. export_json.py renders `summary` as a bullet per
company. Idempotent: clears this source's rows before reloading.

Usage: python dev/justice_data/justice_data_import.py
"""
import csv
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).parent
DB_PATH = HERE.parent / "db" / "cac40.db"
LEI_CSV = HERE.parent / "finance_data" / "CAC40_LEI_ISIN_list.csv"

# =====================================================================
# Configuration des accès (À configurer avec les nouvelles clés)
# =====================================================================
CLIENT_ID = "32619f93-f379-40db-a478-354b436a31cc"
CLIENT_SECRET = "ee8afee0-b835-4ce0-ba66-a0970ffa819f"
AUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
BASE_URL = "https://api.piste.gouv.fr/cassation/judilibre/v1.0"
SOURCE = "judilibre"

# =====================================================================
# Liste des entreprises et mots-clés
# =====================================================================
cac40_companies = [
    "Air Liquide", "Airbus", "Alstom", "Accor", "ArcelorMittal", "AXA", "BNP Paribas",
    "Bouygues", "Capgemini", "Carrefour", "Crédit Agricole", "Danone", "Dassault Systèmes",
    "Edenred", "Engie", "EssilorLuxottica", "Eurofins Scientific", "Hermès International",
    "Kering", "L'Oréal", "Legrand", "LVMH", "Michelin", "Orange", "Pernod Ricard",
    "Publicis Groupe", "Renault", "Safran", "Saint-Gobain", "Sanofi", "Schneider Electric",
    "Société Générale", "Stellantis", "STMicroelectronics", "Teleperformance", "Thales",
    "TotalEnergies", "Unibail-Rodamco-Westfield", "Veolia", "Vinci", "Vivendi"]

# Optimisation des mots-clés pour limiter les faux positifs du mot "environnement" seul
mots_cles_env = ["émissions de CO2", "code de l'environnement", "pollution", "préjudice écologique"]

LEGAL_SUFFIXES = {"SE", "SA", "NV", "PLC", "AG", "GROUP", "INTERNATIONAL", "GROUPE", "SCIENTIFIC"}


def norm(s):
    """Uppercase, drop accents/punctuation and trailing legal-form tokens."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    toks = re.sub(r"[^A-Za-z0-9]+", " ", s).upper().split()
    while toks and toks[-1] in LEGAL_SUFFIXES:
        toks.pop()
    return " ".join(toks)


def load_name2lei():
    name2lei = {}
    for r in csv.DictReader(open(LEI_CSV, newline="", encoding="utf-8")):
        name2lei[norm(r["matched_legal_name"])] = r["lei"]
        name2lei.setdefault(norm(r["input_name"]), r["lei"])
    return name2lei


# =====================================================================
# Fonctions de requêtage
# =====================================================================
def obtenir_token():
    """Récupère le jeton d'accès OAuth2."""
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    response = requests.post(AUTH_URL, data=data)
    response.raise_for_status()
    return response.json().get("access_token")


def collecter_decisions(entreprise, mots_cles, token):
    """Interroge l'API pour chaque mot-clé et dédoublonne les décisions."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    decisions_uniques = {}

    for mot in mots_cles:
        # Requête combinée : "Nom Entreprise" ET "Mot-clé"
        query_str = f'"{entreprise}" "{mot}"'
        params = {
            "query": query_str,
            "page_size": 20,
            "sort": "date",
            "order": "desc"
        }

        try:
            res = requests.get(f"{BASE_URL}/search", headers=headers, params=params)

            # Gestion de la limitation de débit de l'API (Rate Limiting)
            if res.status_code == 429:
                print("⏱️ Taux de requêtes atteint. Pause forcée de 5 secondes...")
                time.sleep(5)
                res = requests.get(f"{BASE_URL}/search", headers=headers, params=params)

            res.raise_for_status()
            data = res.json()

            for decision in data.get("results", []):
                dec_id = decision.get("id")
                # Filtrage strict des faux positifs si le mot "environnement" est utilisé seul
                texte_aperçu = decision.get("snippet", "").lower()
                if mot == "environnement" and "environnement de travail" in texte_aperçu:
                    continue # On ignore cette décision

                if dec_id and dec_id not in decisions_uniques:
                    decisions_uniques[dec_id] = decision

        except requests.exceptions.RequestException as e:
            print(f"⚠️ Erreur pour {entreprise} avec le mot '{mot}': {e}")

        # Pause de sécurité entre les mots-clés pour respecter l'infrastructure PISTE
        time.sleep(0.3)

    # Tri final des décisions de la plus récente à la plus ancienne
    liste_decisions = list(decisions_uniques.values())
    liste_decisions.sort(key=lambda x: x.get('decision_date', x.get('update_date', '')), reverse=True)
    return liste_decisions


def decision_row(lei, d, now):
    """Map one Judilibre decision to a Court_decision row tuple."""
    date = d.get("decision_date")
    juridiction = d.get("jurisdiction", "Inconnue")
    numero = d.get("number", d.get("id"))
    summary = f"[{date or 'Date inconnue'}] {juridiction} - N°{numero}"
    return (
        lei, date, juridiction, d.get("chamber"), str(numero) if numero else None,
        summary, d.get("solution"), d.get("url"), SOURCE, now,
    )


INSERT = (
    "INSERT INTO Court_decision "
    "(lei, decision_date, jurisdiction, court, case_ref, summary, outcome, url, source, retrieved_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


# =====================================================================
# Exécution et chargement en base
# =====================================================================
def main():
    print("🔑 Connexion à l'API PISTE...")
    try:
        token = obtenir_token()
        print("✅ Authentification réussie.")
    except Exception as e:
        print(f"❌ Échec de l'authentification : {e}")
        sys.exit(1)

    name2lei = load_name2lei()
    now = datetime.now(timezone.utc).isoformat()
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        # ponytail: clear-and-reload by source — Court_decision has no UNIQUE key,
        # so this keeps the run idempotent without a migration. Switch to UPSERT
        # if another source ever writes the table concurrently.
        con.execute("DELETE FROM Court_decision WHERE source = ?", (SOURCE,))

        written, missing = 0, []
        for i, entreprise in enumerate(cac40_companies, 1):
            lei = name2lei.get(norm(entreprise))
            if not lei:
                missing.append(entreprise)
                continue
            print(f"[{i}/{len(cac40_companies)}] Analyse en cours : {entreprise}...")
            for d in collecter_decisions(entreprise, mots_cles_env, token):
                con.execute(INSERT, decision_row(lei, d, now))
                written += 1
        con.commit()
    finally:
        con.close()

    print(f"\n🎉 Terminé : {written} décisions insérées dans Court_decision.")
    if missing:
        print(f"⚠ NON APPARIÉES (pas de LEI, ignorées) : {', '.join(missing)}", file=sys.stderr)


if __name__ == "__main__":
    main()
