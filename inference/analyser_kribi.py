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

SEUILS_SAISONNIERS = {
    1:  (30,  120), 2:  (50,  150),
    3:  (120, 250), 4:  (180, 320),
    5:  (200, 350), 6:  (160, 300),
    7:  (80,  200), 8:  (100, 220),
    9:  (180, 320), 10: (200, 350),
    11: (150, 280), 12: (50,  150),
}

# ─── PROMPT SYSTÈME ───────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es SAMCAM, un système expert en surveillance des risques climatiques
pour la zone côtière de Kribi, Cameroun.

CONTEXTE CLIMATIQUE DE KRIBI (ESSENTIEL) :
Kribi est l'une des zones les plus pluvieuses du Cameroun (3000-4000mm/an).
DEUX saisons des pluies normales :
  - Grande saison des pluies : mars à juin (jusqu'à 300-400mm/mois = NORMAL)
  - Petite saison des pluies : septembre à novembre
  - Saisons sèches : juillet-août et décembre-février

RÈGLE FONDAMENTALE : Ne jamais confondre pluie saisonnière normale avec un risque.
En juin, 150-200mm sur 7 jours est PARFAITEMENT NORMAL à Kribi.
Un risque réel = dépassement SIGNIFICATIF des normales saisonnières.

INTERPRÉTATION :
- NDVI 0.6-0.9 : forêt tropicale dense = état NORMAL pour Kribi
- NDWI 0.1-0.4 en saison des pluies : normal (mangroves, zones humides)
- NDWI > 0.5 : inondation réelle possible
- sm_surface 0.3-0.5 m³/m³ en saison des pluies : NORMAL
- sm_surface > 0.55 m³/m³ : saturation critique

SEUILS D'ALERTE :
- VERT  : dans les normales saisonnières, aucune action
- JAUNE : légère anomalie, surveillance accrue
- ORANGE: dépassement significatif, mesures préventives
- ROUGE : événement extrême, risque imminent

RÈGLES DE RÉDACTION :
- Toujours indiquer la DATE EXACTE fournie dans le prompt (ne pas inventer de date)
- Être factuel et proportionné, éviter l'alarmisme
- Préciser si une valeur est "normale pour la saison" ou "anormale"
- Si la valeur est INFÉRIEURE au seuil d'alerte, ne pas dire qu'elle dépasse ce seuil
- Langue : français, ton professionnel"""


# ─── CHARGEMENT ───────────────────────────────────────────────────────

def charger_dernier_json() -> str:
    fichiers = sorted(glob.glob(os.path.join(DATA_DIR, "kribi_*.json")))
    if not fichiers:
        raise FileNotFoundError(f"Aucun fichier kribi_*.json trouvé dans {DATA_DIR}")
    return fichiers[-1]


def construire_prompt(data: dict) -> str:
    ind      = data.get("indicateurs_risque", {})
    meta     = data.get("meta", {})

    # → DATE FORCÉE au jour réel d'exécution (corrige le bug de date dans Phi-3)
    today_real = datetime.date.today().isoformat()
    date_collecte = today_real  # ignore meta.date_collecte qui peut être erronée

    mois = datetime.date.today().month
    noms_mois = ["","Janvier","Février","Mars","Avril","Mai","Juin",
                 "Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
    nom_mois = noms_mois[mois]
    seuil_normal, seuil_alerte = SEUILS_SAISONNIERS.get(mois, (120, 250))

    pluie_7j      = ind.get("pluie_cumulee_7j_mm",  0) or 0
    pluie_prev_7j = ind.get("pluie_prevue_7j_mm",   0) or 0
    anomalie_obs  = round(pluie_7j      - seuil_normal, 1)
    anomalie_prev = round(pluie_prev_7j - seuil_normal, 1)

    # Évaluation comparée
    if pluie_7j < seuil_normal * 0.5:
        eval_obs = f"{pluie_7j:.1f} mm → NETTEMENT EN DESSOUS de la normale ({seuil_normal} mm)"
    elif pluie_7j < seuil_normal:
        eval_obs = f"{pluie_7j:.1f} mm → légèrement sous la normale ({seuil_normal} mm)"
    elif pluie_7j < seuil_alerte:
        eval_obs = f"{pluie_7j:.1f} mm → dans les normales ({seuil_normal} mm), seuil d'alerte à {seuil_alerte} mm NON atteint"
    else:
        eval_obs = f"{pluie_7j:.1f} mm → DÉPASSE le seuil d'alerte ({seuil_alerte} mm)"

    if pluie_prev_7j < seuil_alerte:
        eval_prev = f"{pluie_prev_7j:.1f} mm prévus → sous le seuil d'alerte ({seuil_alerte} mm), situation normale attendue"
    else:
        eval_prev = f"{pluie_prev_7j:.1f} mm prévus → DÉPASSE le seuil d'alerte ({seuil_alerte} mm)"

    # Prévisions
    prev       = data.get("meteorologie", {}).get("previsions_daily", {})
    dates_prev = prev.get("time",                        [])[:7]
    prec_prev  = prev.get("precipitation_sum",           [])[:7]
    prob_prev  = prev.get("precipitation_probability_max",[])[:7]
    temp_max   = prev.get("temperature_2m_max",          [])[:7]
    vent_max   = prev.get("windspeed_10m_max",           [])[:7]

    lignes = []
    for i, d in enumerate(dates_prev):
        p  = prec_prev[i]  if i < len(prec_prev)  else "?"
        pr = prob_prev[i]  if i < len(prob_prev)  else "?"
        t  = temp_max[i]   if i < len(temp_max)   else "?"
        v  = vent_max[i]   if i < len(vent_max)   else "?"
        lignes.append(f"  {d}: {p}mm (prob {pr}%) | {t}°C max | vent {v}km/h")
    prev_texte = "\n".join(lignes) if lignes else "  Non disponible"

    # Satellite
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
            f"  NDVI moyen: {ind.get('ndvi_moyen')} (±{ndvi_std}) — normal pour Kribi : 0.6-0.9\n"
            f"  NDWI moyen: {ind.get('ndwi_moyen')} — normal en saison pluies : 0.1-0.4\n"
            f"  NBR moyen : {nbr_val} | NDRE moyen : {ndre_val}"
        )
    elif "modis" in sat:
        sat_texte = f"MODIS fallback | NDVI: {ind.get('ndvi_moyen')} | Sentinel-2 indisponible"
    else:
        sat_texte = "Données satellitaires indisponibles"

    smap        = sat.get("smap", {})
    sm_surf     = smap.get("humidite_sol", {}).get("sm_surface",  "N/A")
    sm_root     = smap.get("humidite_sol", {}).get("sm_rootzone", "N/A")
    if isinstance(sm_surf, float): sm_surf = round(sm_surf, 4)
    if isinstance(sm_root, float): sm_root = round(sm_root, 4)

    prompt = f"""Date d'analyse : {date_collecte}  ← c'est la date EXACTE, utilise-la dans ton rapport.
Mois : {nom_mois} → grande saison des pluies à Kribi.

== ÉVALUATION DES PRÉCIPITATIONS ==
Observé (7 derniers jours) : {eval_obs}
Prévu   (7 prochains jours) : {eval_prev}
Anomalie observée  vs normale : {'+' if anomalie_obs >= 0 else ''}{anomalie_obs} mm
Anomalie prévue    vs normale : {'+' if anomalie_prev >= 0 else ''}{anomalie_prev} mm

== INDICES SATELLITAIRES ==
{sat_texte}
Humidité sol surface (0-5cm)   SMAP : {sm_surf} m³/m³  (normal 0.3-0.5 en saison pluies)
Humidité sol racines (0-100cm) SMAP : {sm_root} m³/m³

== PRÉVISIONS 7 PROCHAINS JOURS ==
{prev_texte}

== INDICATEURS CALCULÉS ==
- Inondation observée : {ind.get('risque_inondation_observe','?')}
- Inondation prévue   : {ind.get('risque_inondation_prevu','?')}
- Sécheresse          : {ind.get('risque_secheresse','?')}
- Submersion côtière  : {ind.get('risque_submersion_cotiere','?')}
- Sol saturé          : {ind.get('risque_sol_sature','?')}

== RAPPORT DEMANDÉ ==
Rédige un rapport PROPORTIONNÉ utilisant la date {date_collecte}.
1. SITUATION DU {date_collecte} (la pluie est-elle normale ou anormale ? appuie-toi sur l'évaluation ci-dessus)
2. ANALYSE DES RISQUES (inondation / sécheresse / submersion — proportionné aux anomalies réelles)
3. ÉVOLUTION PRÉVUE (7 prochains jours)
4. RECOMMANDATIONS (proportionnées au niveau réel de risque)
5. NIVEAU D'ALERTE : VERT / JAUNE / ORANGE / ROUGE"""

    return prompt


# ─── APPEL OLLAMA ─────────────────────────────────────────────────────

def appeler_phi3(prompt: str, stream: bool = True) -> str:
    payload = {
        "model": MODEL_NAME,
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "stream": stream,
        "options": {"temperature": 0.1, "top_p": 0.85, "num_predict": 1200}
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, stream=stream, timeout=180)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise ConnectionError("\n❌ Ollama ne répond pas. Lance : ollama serve")

    texte = ""
    if stream:
        print("\n" + "═" * 60 + "\nRAPPORT SAMCAM — Phi-3 mini\n" + "═" * 60 + "\n")
        for ligne in resp.iter_lines():
            if ligne:
                chunk = json.loads(ligne)
                token = chunk.get("response", "")
                print(token, end="", flush=True)
                texte += token
                if chunk.get("done"): break
        print("\n")
    else:
        texte = resp.json().get("response", "")
    return texte


# ─── SAUVEGARDE ───────────────────────────────────────────────────────

def sauvegarder_rapport(rapport: str, data_source: dict) -> dict:
    today = datetime.date.today().isoformat()  # date réelle toujours
    base  = os.path.join(REPORTS_DIR, f"rapport_kribi_{today}")

    with open(f"{base}.txt", "w", encoding="utf-8") as f:
        f.write(f"RAPPORT SAMCAM — Kribi — {today}\n" + "=" * 60 + "\n\n" + rapport)

    ind = data_source.get("indicateurs_risque", {})
    out = {
        "date": today,
        "zone": "Kribi",
        "modele": MODEL_NAME,
        "rapport_texte": rapport,
        "indicateurs": ind,
        "capteur": data_source.get("meta", {}).get("capteur_satellite", "?"),
    }
    with open(f"{base}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[SAMCAM] 💾 Rapport : {base}.txt / .json")
    return out


# ─── MAIN ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fichier",   type=str, default=None)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    fichier = args.fichier or charger_dernier_json()
    print(f"[SAMCAM] 📄 Analyse de : {fichier}")

    with open(fichier, "r", encoding="utf-8") as f:
        data = json.load(f)

    prompt = construire_prompt(data)
    if not args.json_only:
        print(f"[SAMCAM] 🤖 Envoi à Phi-3 mini...")

    rapport = appeler_phi3(prompt, stream=not args.json_only)
    sauvegarder_rapport(rapport, data)


if __name__ == "__main__":
    main()
