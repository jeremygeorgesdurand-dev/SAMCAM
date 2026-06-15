#!/usr/bin/env python3
"""
SAMCAM — Analyse des risques climatiques Kribi avec Phi-3 mini (Ollama)

Usage :
    # Analyser le fichier du jour
    python3 inference/analyser_kribi.py

    # Analyser un fichier spécifique
    python3 inference/analyser_kribi.py --fichier data/kribi_2026-06-15.json

    # Mode silencieux (JSON uniquement, pour pipeline)
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
MODEL_NAME  = "phi3:mini"   # nom exact tel qu'installé : `ollama list`
DATA_DIR    = os.path.join(os.path.dirname(__file__), "..", "data")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# ─── PROMPT SYSTÈME ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es SAMCAM, un système expert en surveillance et analyse des risques climatiques
concernant la zone côtière de Kribi au Cameroun.

Tu maîtrises :
- La météorologie tropicale (précipitations, vents, humidité)
- L'interprétation des indices satellitaires (NDVI, NDWI, NBR, NDRE)
- L'analyse des risques d'inondation, de sécheresse et de submersion côtière
- Le contexte climatique du Cameroun : deux saisons des pluies (mars-juin et sept-nov)
- La zone de Kribi : côte Atlantique, forêts tropicales, mangroves, estuaires

Règles d'interprétation :
- NDVI > 0.6 : végétation dense et saine | NDVI 0.3-0.6 : végétation modérée | NDVI < 0.2 : stress végétal
- NDWI > 0.3 : présence d'eau en surface (risque submersion) | NDWI < 0 : sol sec
- sm_surface > 0.4 m³/m³ : sol saturé, ruissellement accru
- Pluie cumulée > 150 mm/7j : risque d'inondation élevé
- Pluie prévue > 100 mm/7j : vigilance requise

Format de réponse : structuré en sections, concis, actionnable.
Langue : français."""


# ─── CHARGEMENT DES DONNÉES ─────────────────────────────────────────────────

def charger_dernier_json() -> str:
    """Charge le fichier kribi_*.json le plus récent."""
    fichiers = sorted(glob.glob(os.path.join(DATA_DIR, "kribi_*.json")))
    if not fichiers:
        raise FileNotFoundError(f"Aucun fichier kribi_*.json trouvé dans {DATA_DIR}")
    return fichiers[-1]


def construire_prompt(data: dict) -> str:
    """
    Construit le prompt utilisateur à partir du JSON de collecte.
    Extrait les informations clés et les formate pour Phi-3 mini.
    """
    ind = data.get("indicateurs_risque", {})
    meta = data.get("meta", {})
    contexte = data.get("contexte_phi3", "")

    # Prévisions détaillées
    prev = data.get("meteorologie", {}).get("previsions_daily", {})
    dates_prev = prev.get("time", [])[:7]
    precip_prev = prev.get("precipitation_sum", [])[:7]
    prob_prev   = prev.get("precipitation_probability_max", [])[:7]
    temp_max    = prev.get("temperature_2m_max", [])[:7]
    vent_max    = prev.get("windspeed_10m_max", [])[:7]

    lignes_prev = []
    for i, d in enumerate(dates_prev):
        pluie = precip_prev[i] if i < len(precip_prev) else "?"
        prob  = prob_prev[i]   if i < len(prob_prev)   else "?"
        temp  = temp_max[i]    if i < len(temp_max)    else "?"
        vent  = vent_max[i]    if i < len(vent_max)    else "?"
        lignes_prev.append(f"  {d}: {pluie}mm (prob {prob}%) | temp max {temp}°C | vent {vent}km/h")

    prev_texte = "\n".join(lignes_prev) if lignes_prev else "  Non disponible"

    # Données satellitaires
    sat = data.get("satellitaire", {})
    capteur = meta.get("capteur_satellite", "inconnu")
    if "sentinel2" in sat:
        nb_img = sat["sentinel2"].get("nb_images", "?")
        indices = sat["sentinel2"].get("indices", {})
        ndvi_std = round(indices.get("NDVI_stdDev", 0) or 0, 4)
        nbr_val  = round(indices.get("NBR_mean",   0) or 0, 4)
        ndre_val = round(indices.get("NDRE_mean",  0) or 0, 4)
        sat_texte = (
            f"Capteur: {capteur} ({nb_img} images compositées)\n"
            f"  NDVI moyen: {ind.get('ndvi_moyen')} (±{ndvi_std})\n"
            f"  NDWI moyen: {ind.get('ndwi_moyen')}\n"
            f"  NBR moyen:  {nbr_val}\n"
            f"  NDRE moyen: {ndre_val}"
        )
    elif "modis" in sat:
        nb_comp = sat["modis"].get("nb_composites", "?")
        sat_texte = (
            f"Capteur: MODIS fallback ({nb_comp} composites 16j)\n"
            f"  NDVI moyen: {ind.get('ndvi_moyen')}\n"
            f"  Note: Sentinel-2 indisponible (couverture nuageuse totale)"
        )
    else:
        sat_texte = "Données satellitaires indisponibles"

    # Humidité sol
    smap = sat.get("smap", {})
    sm_surface  = smap.get("humidite_sol", {}).get("sm_surface",  "N/A")
    sm_rootzone = smap.get("humidite_sol", {}).get("sm_rootzone", "N/A")
    if isinstance(sm_surface,  float): sm_surface  = round(sm_surface,  4)
    if isinstance(sm_rootzone, float): sm_rootzone = round(sm_rootzone, 4)

    prompt = f"""Analyse les données climatiques suivantes pour Kribi et produis un rapport de risque structuré.

== CONTEXTE ==
{contexte}

== INDICES SATELLITAIRES ==
{sat_texte}
Humidité sol surface (0-5cm) SMAP: {sm_surface} m³/m³
Humidité sol racines (0-100cm) SMAP: {sm_rootzone} m³/m³

== PRÉVISIONS 7 PROCHAINS JOURS ==
{prev_texte}

== INDICATEURS DE RISQUE CALCULÉS ==
- Inondation observée : {ind.get('risque_inondation_observe', '?')}
- Inondation prévue   : {ind.get('risque_inondation_prevu', '?')}
- Sécheresse          : {ind.get('risque_secheresse', '?')}
- Submersion côtière  : {ind.get('risque_submersion_cotiere', '?')}
- Sol saturé          : {ind.get('risque_sol_sature', '?')}

== RAPPORT DEMANDÉ ==
Produis un rapport structuré avec :
1. RÉSUMÉ EXÉCUTIF (3-4 lignes max)
2. ANALYSE DES RISQUES (par catégorie : inondation, submersion, sécheresse)
3. ÉVOLUTION PRÉVUE (7 prochains jours)
4. RECOMMANDATIONS (actions concrètes pour les autorités locales)
5. NIVEAU D'ALERTE GÉNÉRAL : VERT / JAUNE / ORANGE / ROUGE"""

    return prompt


# ─── APPEL OLLAMA ─────────────────────────────────────────────────────────

def appeler_phi3(prompt: str, stream: bool = True) -> str:
    """
    Envoie le prompt à Phi-3 mini via l'API Ollama.
    stream=True : affiche la réponse en temps réel.
    """
    payload = {
        "model": MODEL_NAME,
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "stream": stream,
        "options": {
            "temperature": 0.3,    # faible = réponses plus factuelles
            "top_p": 0.9,
            "num_predict": 1024,   # longueur max de la réponse
        }
    }

    try:
        resp = requests.post(OLLAMA_URL, json=payload, stream=stream, timeout=120)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            "\n❌ Ollama ne répond pas. Vérifie qu'il est bien lancé :\n"
            "   ollama serve\n"
            "   ollama list  (pour vérifier que phi3:mini est installé)"
        )

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
        data = resp.json()
        texte_complet = data.get("response", "")

    return texte_complet


# ─── SAUVEGARDE ───────────────────────────────────────────────────────────

def sauvegarder_rapport(rapport: str, data_source: dict) -> dict:
    """Sauvegarde le rapport en .txt et .json."""
    today = datetime.date.today().isoformat()
    base  = os.path.join(REPORTS_DIR, f"rapport_kribi_{today}")

    # Fichier texte brut
    with open(f"{base}.txt", "w", encoding="utf-8") as f:
        f.write(f"RAPPORT SAMCAM — Kribi — {today}\n")
        f.write("=" * 60 + "\n\n")
        f.write(rapport)

    # Fichier JSON structuré (pour le dashboard)
    ind = data_source.get("indicateurs_risque", {})
    sortie_json = {
        "date": today,
        "zone": "Kribi",
        "modele": MODEL_NAME,
        "rapport_texte": rapport,
        "indicateurs": ind,
        "capteur": data_source.get("meta", {}).get("capteur_satellite", "?"),
    }
    with open(f"{base}.json", "w", encoding="utf-8") as f:
        json.dump(sortie_json, f, ensure_ascii=False, indent=2)

    print(f"[SAMCAM] 💾 Rapport sauvegardé :")
    print(f"         Texte : {base}.txt")
    print(f"         JSON  : {base}.json")

    return sortie_json


# ─── POINT D'ENTRÉE ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SAMCAM — Analyse Phi-3 mini")
    parser.add_argument(
        "--fichier", type=str, default=None,
        help="Chemin vers le fichier JSON à analyser (défaut: dernier fichier data/kribi_*.json)"
    )
    parser.add_argument(
        "--json-only", action="store_true",
        help="Mode silencieux : pas d'affichage en streaming, sortie JSON uniquement"
    )
    args = parser.parse_args()

    # 1. Charger les données
    if args.fichier:
        fichier = args.fichier
    else:
        fichier = charger_dernier_json()

    print(f"[SAMCAM] 📄 Analyse de : {fichier}")

    with open(fichier, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 2. Construire le prompt
    prompt = construire_prompt(data)

    if not args.json_only:
        print(f"[SAMCAM] 🤖 Envoi à Phi-3 mini (Ollama)...")

    # 3. Appeler Phi-3
    stream_mode = not args.json_only
    rapport = appeler_phi3(prompt, stream=stream_mode)

    # 4. Sauvegarder
    sauvegarder_rapport(rapport, data)


if __name__ == "__main__":
    main()
