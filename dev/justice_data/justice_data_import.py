import requests
import pandas as pd
import time

# =====================================================================
# Configuration des accès (À configurer avec les nouvelles clés)
# =====================================================================
CLIENT_ID = "32619f93-f379-40db-a478-354b436a31cc"
CLIENT_SECRET = "ee8afee0-b835-4ce0-ba66-a0970ffa819f"
AUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
BASE_URL = "https://api.piste.gouv.fr/cassation/judilibre/v1.0"

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

# =====================================================================
# Exécution et extraction vers le CSV
# =====================================================================
if __name__ == "__main__":
    print("🔑 Connexion à l'API PISTE...")
    try:
        token = obtenir_token()
        print("✅ Authentification réussie.")
    except Exception as e:
        print(f"❌ Échec de l'authentification : {e}")
        exit()

    donnees_globales = []

    for i, entreprise in enumerate(cac40_companies, 1):
        print(f"[{i}/{len(cac40_companies)}] Analyse en cours : {entreprise}...")
        decisions = collecter_decisions(entreprise, mots_cles_env, token)
        
        # Extraction des 2 dernières décisions (Objectif 2)
        # On initialise des valeurs vides par défaut
        dec1_info = "Aucune décision trouvée"
        dec2_info = "Aucune décision trouvée"
        
        if len(decisions) >= 1:
            d1 = decisions[0]
            dec1_info = f"[{d1.get('decision_date', 'Date inconnue')}] {d1.get('jurisdiction', 'Inconnue')} - N°{d1.get('number', d1.get('id'))}"
        if len(decisions) >= 2:
            d2 = decisions[1]
            dec2_info = f"[{d2.get('decision_date', 'Date inconnue')}] {d2.get('jurisdiction', 'Inconnue')} - N°{d2.get('number', d2.get('id'))}"
            
        # Structure de la ligne pour cette entreprise
        ligne_entreprise = {
            "Entreprise": entreprise,
            "Nombre_Decisions_Environnement": len(decisions),
            "Derniere_Decision_1": dec1_info,
            "Derniere_Decision_2": dec2_info
        }
        
        donnees_globales.append(ligne_entreprise)
        
    # Conversion en DataFrame Pandas et sauvegarde
    df = pd.DataFrame(donnees_globales)
    nom_fichier = "resultats_judilibre_cac40.csv"
    df.to_csv(nom_fichier, index=False, encoding="utf-8-sig")
    
    print(f"\n🎉 Extraction terminée avec succès ! Le fichier '{nom_fichier}' a été généré.")