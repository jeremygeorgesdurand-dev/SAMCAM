#!/usr/bin/env python3
"""
SAMCAM — Analyse des risques climatiques Kribi avec Phi-3 mini (Ollama)

Usage :
    python3 inference/analyser_kribi.py
    python3 inference/analyser_kribi.py --fichier data/kribi_2026-06-15.json
    python3 inference/analyser_kribi.py --json-only

Sortie :
    reports/rapport_kribi_YYYY-MM-DD.txt
    reports/rapport_kribi_YYYY-MM-DD.json
"""

import os
import json
import argparse
import datetime
import requests
import glob

# ─── CONFIG ───────────────────────────────────────────────────────────

OLLAMA_URL  = "http://localhost:11434/api/generate"
MODEL_NAME  = "phi3:mini"
DATA_DIR    = os.path.join(os.path.dirname(__file__), "..", "data")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# Seuils normaux pour Kribi selon le mois
SEUILS_SAISONNIERS = {
    1:  (30,  120), 2:  (50,  150), 3:  (120, 250),
    4:  (180, 320), 5:  (200, 350), 6:  (160, 300),
    7:  (80,  200), 8:  (100, 220), 9:  (180, 320),
    10: (200, 350), 11: (150, 280), 12: (50,  150),
}

NOMS_MOIS = ["","Janvier","Février","Mars","Avril","Mai","Juin",
             "Juillet","Août","Septembre","Octobre","Novembre","Décembre"]

SAISONS = {
    1: "petite saison sèche", 2: "petite saison sèche",
    3: "début grande saison des pluies", 4: "grande saison des pluies",
    5: "grande saison des pluies", 6: "grande saison des pluies",
    7: "petite saison sèche", 8: "petite saison sèche",
    9: "début petite saison des pluies", 10: "petite saison des pluies",
    11: "petite saison des pluies", 12: "grande saison sèche",
}

# ─── PROMPT SYSTÈME ───────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es SAMCAM, un système expert en surveillance des risques climatiques
pour la zone côtière de Kribi, Cameroun.

CONTEXTE CLIMATIQUE DE KRIBI :
Kribi reçoit 3000-4000 mm de pluie par an — l'une des zones les plus pluvieuses du Cameroun.
DEUX saisons des pluies normales : mars-juin (grande) et septembre-novembre (petite).
En juin, 150-200 mm sur 7 jours est PARFAITEMENT NORMAL.
Un risque réel = dépassement SIGNIFICATIF des normales saisonnières.

INTERPRÉTATION DES INDICES SATELLITES :
- NDVI 0.6-0.9 : forêt tropicale dense = état NORMAL pour Kribi
- NDVI < 0.4 : dégradation végétale anormale
- NDWI 0.1-0.4 en saison des pluies : normal (mangroves, zones humides)
- NDWI > 0.5 : inondation réelle possible
- sm_surface 0.3-0.5 m³/m³ en saison pluies : NORMAL
- sm_surface > 0.55 : saturation critique

NIVEAUX D'ALERTE (à relativiser par rapport aux normales saisonnières) :
- VERT  : situation normale, aucune action requise
- JAUNE : légère anomalie, surveillance accrue
- ORANGE: dépassement significatif, mesures préventives
- ROUGE : événement extrême, risque imminent

RÈGLES DE RÉDACTION :
- Toujours comparer aux normales saisonnières avant de conclure
- Être factuel et proportionné, éviter l'alarmisme injustifié
- Préciser si une valeur est "normale pour la saison" ou "anormale"
- Ne JAMAIS inventer une date — utiliser uniquement la date fournie dans le prompt
- Langue : français, ton professionnel et mesuré"""


# ─── CHARGEMENT ───────────────────────────────────────────────────────

def charger_dernier_json() -> str:
    fichiers = sorted(glob.glob(os.path.join(DATA_DIR, "kribi_*.json")))
    if not fichiers:
        raise FileNotFoundError(f"Aucun fichier kribi_*.json trouvé dans {DATA_DIR}")
    return fichiers[-1]


def construire_prompt(data: dict) -> str:
    # DATE SYSTÈME — forcée, pas laissée à Phi-3
    today_str = datetime.date.today().isoformat()

    ind    = data.get("indicateurs_risque", {})
    meta   = data.get("meta", {})
    contexte = data.get("contexte_phi3", "")

    mois = datetime.date.today().month
    nom_mois = NOMS_MOIS[mois]
    saison   = SAISONNS[mois] if mois in SAISONNS else "saison inconnue"
    seuil_normal, seuil_alerte = SEUILS_SAISONNIERS.get(mois, (120, 250))

    pluie_7j      = ind.get("pluie_cumulee_7j_mm",  0) or 0
    pluie_prev_7j = ind.get("pluie_prevue_7j_mm",   0) or 0
    anomalie_obs  = round(pluie_7j      - seuil_normal, 1)
    anomalie_prev = round(pluie_prev_7j - seuil_normal, 1)

    # Prévisions détaillées
    prev        = data.get("meteorologie", {}).get("previsions_daily", {})
    dates_prev  = prev.get("time",                         [])[:7]
    precip_prev = prev.get("precipitation_sum",            [])[:7]
    prob_prev   = prev.get("precipitation_probability_max",[])[:7]
    temp_max    = prev.get("temperature_2m_max",           [])[:7]
    vent_max    = prev.get("windspeed_10m_max",            [])[:7]

    lignes_prev = []
    for i, d in enumerate(dates_prev):
        p  = precip_prev[i] if i < len(precip_prev) else "?"
        pr = prob_prev[i]   if i < len(prob_prev)   else "?"
        t  = temp_max[i]    if i < len(temp_max)    else "?"
        v  = vent_max[i]    if i < len(vent_max)    else "?"
        lignes_prev.append(f"  {d}: {p}mm (prob {pr}%) | {t}°C max | vent {v}km/h")
    prev_texte = "\n".join(lignes_prev) if lignes_prev else "  Non disponible"

    # Données satellitaires
    sat     = data.get("satellitaire", {})
    capteur = meta.get("capteur_satellite", "inconnu")
    if "sentinel2" in sat:
        nb_img   = sat["sentinel2"].get("nb_images", "?")
        indices  = sat["sentinel2"].get("indices", {})
        ndvi_std = round(indices.get("NDVI_stdDev", 0) or 0, 4)
        nbr_val  = round(indices.get("NBR_mean",    0) or 0, 4)
        ndre_val = round(indices.get("NDRE_mean",   0) or 0, 4)
        sat_texte = (
            f"Capteur: {capteur} ({nb_img} images sur 60j)\n"
            f"  NDVI moyen: {ind.get('ndvi_moyen')} (±{ndvi_std}) — forêt tropicale dense attendue > 0.6\n"
            f"  NDWI moyen: {ind.get('ndwi_moyen')} — normal 0.1-0.4 en saison pluies\n"
            f"  NBR moyen:  {nbr_val}\n"
            f"  NDRE moyen: {ndre_val}"
        )
    elif "modis" in sat:
        nb_comp  = sat["modis"].get("nb_composites", "?")
        sat_texte = (
            f"Capteur: MODIS fallback ({nb_comp} composites 16j)\n"
            f"  NDVI moyen: {ind.get('ndvi_moyen')}\n"
            f"  Note: Sentinel-2 indisponible (couverture nuageuse totale)"
        )
    else:
        sat_texte = "Données satellitaires indisponibles"

    smap        = sat.get("smap", {})
    sm_surface  = smap.get("humidite_sol", {}).get("sm_surface",  "N/A")
    sm_rootzone = smap.get("humidite_sol", {}).get("sm_rootzone", "N/A")
    if isinstance(sm_surface,  float): sm_surface  = round(sm_surface,  4)
    if isinstance(sm_rootzone, float): sm_rootzone = round(sm_rootzone, 4)

    prompt = f"""DATE D'ANALYSE : {today_str}
Tu dois utiliser UNIQUEMENT cette date dans ton rapport. N'invente aucune autre date.

Analyse les données climatiques de Kribi du {today_str} et produis un rapport proportionné.

== CONTEXTE SAISONNIER ==
Mois : {nom_mois} ({saison})
Pluie 7j NORMALE pour {nom_mois} à Kribi : ~{seuil_normal} mm
Seuil d'alerte réel : > {seuil_alerte} mm sur 7j

{contexte}

== ANOMALIES PAR RAPPORT AUX NORMALES ==
Pluie observée 7j  : {round(pluie_7j,1)} mm  (anomalie : {'+' if anomalie_obs>=0 else ''}{anomalie_obs} mm vs normale)
Pluie prévue 7j    : {round(pluie_prev_7j,1)} mm  (anomalie : {'+' if anomalie_prev>=0 else ''}{anomalie_prev} mm vs normale)

== INDICES SATELLITAIRES ==
{sat_texte}
Humidité sol surface (0-5cm) SMAP  : {sm_surface} m³/m³  (normal 0.3-0.5 en saison pluies)
Humidité sol racines (0-100cm) SMAP: {sm_rootzone} m³/m³

== PRÉVISIONS 7 PROCHAINS JOURS ==
{prev_texte}

== INDICATEURS CALCULÉS ==
- Inondation observée : {ind.get('risque_inondation_observe','?')}
- Inondation prévue   : {ind.get('risque_inondation_prevu','?')}
- Sécheresse          : {ind.get('risque_secheresse','?')}
- Submersion côtière  : {ind.get('risque_submersion_cotiere','?')}
- Sol saturé          : {ind.get('risque_sol_sature','?')}

== RAPPORT DEMANDÉ ==
Produis un rapport PROPORTIONNÉ qui distingue ce qui est normal de ce qui est anormal.
Structure OBLIGATOIRE :
1. SITUATION DU {today_str} (normale / légère anomalie / anomalie significative)
2. ANALYSE DES RISQUES (inondation, submersion côtière, sécheresse — relativiser par rapport aux normales)
3. ÉVOLUTION PRÉVUE (7 prochains jours)
4. RECOMMANDATIONS (proportionnées au niveau réel de risque)
5. NIVEAU D'ALERTE : VERT / JAUNE / ORANGE / ROUGE (justifié par rapport aux normales saisonnières)"""

    return prompt


# ─── APPEL OLLAMA ─────────────────────────────────────────────────────

def appeler_phi3(prompt: str, stream: bool = True) -> str:
    payload = {
        "model": MODEL_NAME,
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "stream": stream,
        "options": {"temperature": 0.1, "top_p": 0.9, "num_predict": 1200},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, stream=stream, timeout=180)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise ConnectionError("\n❌ Ollama ne répond pas.\n   ollama serve\n   ollama list")

    texte_complet = ""
    if stream:
        print("\n" + "═" * 60)
        print("RAPPORT SAMCAM — Phi-3 mini")
        print("═" * 60 + "\n")
        for ligne in resp.iter_lines():
            if ligne:
                chunk = json.loads(ligne)
                token = chunk.get("response", "")
                print(token, end="", flush=True)
                texte_complet += token
                if chunk.get("done"):
                    break
        print("\n")
    else:
        texte_complet = resp.json().get("response", "")
    return texte_complet


# ─── SAUVEGARDE ───────────────────────────────────────────────────────

def sauvegarder_rapport(rapport: str, data_source: dict) -> dict:
    today = datetime.date.today().isoformat()
    base  = os.path.join(REPORTS_DIR, f"rapport_kribi_{today}")

    with open(f"{base}.txt", "w", encoding="utf-8") as f:
        f.write(f"RAPPORT SAMCAM — Kribi — {today}\n")
        f.write("=" * 60 + "\n\n")
        f.write(rapport)

    ind = data_source.get("indicateurs_risque", {})

    # Déterminer le niveau d'alerte depuis le texte du rapport
    niveau = "VERT"
    rapport_upper = rapport.upper()
    for lvl in ["ROUGE", "ORANGE", "JAUNE", "VERT"]:
        if lvl in rapport_upper:
            niveau = lvl
            break

    sortie_json = {
        "date": today,
        "zone": "Kribi",
        "modele": MODEL_NAME,
        "rapport_texte": rapport,
        "niveau_alerte": niveau,
        "indicateurs": ind,
        "capteur": data_source.get("meta", {}).get("capteur_satellite", "?"),
        "meteorologie": data_source.get("meteorologie", {}),
        "satellitaire": data_source.get("satellitaire", {}),
        "meta": data_source.get("meta", {}),
    }
    with open(f"{base}.json", "w", encoding="utf-8") as f:
        json.dump(sortie_json, f, ensure_ascii=False, indent=2)

    print(f"[SAMCAM] 💾 Rapport sauvegardé :")
    print(f"         Texte  : {base}.txt")
    print(f"         JSON   : {base}.json")
    print(f"         Alerte : {niveau}")
    return sortie_json


# ─── POINT D'ENTRÉE ───────────────────────────────────────────────────

# Correctif typo dans SAISONNS → SAISONS
SAISONNS = SAISONS  # alias

def main():
    parser = argparse.ArgumentParser(description="SAMCAM — Analyse Phi-3 mini")
    parser.add_argument("--fichier",   type=str,         default=None)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    fichier = args.fichier or charger_dernier_json()
    print(f"[SAMCAM] 📄 Analyse de : {fichier}")

    with open(fichier, "r", encoding="utf-8") as f:
        data = json.load(f)

    prompt = construire_prompt(data)

    if not args.json_only:
        print(f"[SAMCAM] 🤖 Envoi à Phi-3 mini (Ollama)...")

    rapport = appeler_phi3(prompt, stream=not args.json_only)
    sauvegarder_rapport(rapport, data)


if __name__ == "__main__":
    main()
