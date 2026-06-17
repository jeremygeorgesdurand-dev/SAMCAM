#!/usr/bin/env python3
"""
SAMCAM — Analyse des risques climatiques Kribi avec Phi-3 mini (Ollama)

V4.2 : enrichit le JSON de sortie avec un objet `meteo` complet
       (température actuelle, code WMO, prévisions horaires, prévisions 7j)
       pour l'application mobile Flutter.

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

JOURS_FR = ["Dim", "Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"]

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

NIVEAUX D'ALERTE :
- VERT   : situation normale, aucune action requise
- JAUNE  : légère anomalie, surveillance accrue
- ORANGE : dépassement significatif, mesures préventives
- ROUGE  : événement extrême, risque imminent

RÈGLES DE RÉDACTION :
- Toujours comparer aux normales saisonnières avant de conclure
- Être factuel et proportionné, éviter l'alarmisme injustifié
- Distinguer risque actuel (J0) et risque prévisionnel (J+3, J+7)
- Mentionner si le score est issu d'un modèle ML ou de règles physiques
- Ne JAMAIS inventer une date — utiliser uniquement la date fournie
- Langue : français, ton professionnel et mesuré"""


# ─── CHARGEMENT ───────────────────────────────────────────────────────

def charger_dernier_json() -> str:
    fichiers = sorted(glob.glob(os.path.join(DATA_DIR, "kribi_*.json")))
    if not fichiers:
        raise FileNotFoundError(f"Aucun fichier kribi_*.json trouvé dans {DATA_DIR}")
    return fichiers[-1]


def construire_prompt(data: dict, previsions_risque: dict) -> str:
    today_str = datetime.date.today().isoformat()
    ind       = data.get("indicateurs_risque", {})
    meta      = data.get("meta", {})
    contexte  = data.get("contexte_phi3", "")

    mois = datetime.date.today().month
    nom_mois = NOMS_MOIS[mois]
    saison   = SAISONS.get(mois, "saison inconnue")
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

    # Scores de risque V4
    act     = previsions_risque.get("actuel",   {})
    prev3j  = previsions_risque.get("prevu_3j", {})
    prev7j  = previsions_risque.get("prevu_7j", {})
    methode = act.get("methode", "règles_physiques")

    def fmt_niveaux(niveaux_dict: dict) -> str:
        return " | ".join(f"{k}: {v}" for k, v in niveaux_dict.items())

    def fmt_scores(scores_dict: dict) -> str:
        return " | ".join(f"{k}: {v:.2f}" for k, v in scores_dict.items())

    scores_section = f"""
== SCORES DE RISQUE (V4 — {methode}) ==
Risque ACTUEL (J0)   : {act.get('niveau_global', '?')} — {fmt_niveaux(act.get('niveaux', {}))}
  Scores  : {fmt_scores(act.get('scores', {}))}
Risque PREVU J+3     : {prev3j.get('niveau_global', '?')} — {fmt_niveaux(prev3j.get('niveaux', {}))}
  Scores  : {fmt_scores(prev3j.get('scores', {}))}
Risque PREVU J+7     : {prev7j.get('niveau_global', '?')} — {fmt_niveaux(prev7j.get('niveaux', {}))}
  Scores  : {fmt_scores(prev7j.get('scores', {}))}
"""

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
{scores_section}
== RAPPORT DEMANDÉ ==
Produis un rapport PROPORTIONNÉ en 5 sections :
1. SITUATION DU {today_str} — risque actuel avec niveau et scores
2. ANALYSE DES RISQUES — inondation, sécheresse, vague de chaleur (relativiser vs normales)
3. ÉVOLUTION PRÉVISIONNELLE J+3 et J+7 — mentionner si tendance haussiere ou baissiere
4. RECOMMANDATIONS — proportionnées au niveau réel
5. NIVEAU D'ALERTE GLOBAL : VERT / JAUNE / ORANGE / ROUGE"""

    return prompt


# ─── APPEL OLLAMA ─────────────────────────────────────────────────────

def appeler_phi3(prompt: str, stream: bool = True) -> str:
    payload = {
        "model": MODEL_NAME,
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "stream": stream,
        "options": {"temperature": 0.1, "top_p": 0.9, "num_predict": 1400},
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


# ─── CONSTRUCTION OBJET MÉTÉO POUR FLUTTER ────────────────────────────

def construire_meteo_flutter(data: dict) -> dict:
    """
    Extrait les données Open-Meteo depuis le JSON de collecte et les
    reformate pour l'application Flutter.
    Format cible :
    {
      "temperature": 27.4,
      "temp_min": 22.0,
      "temp_max": 31.0,
      "humidite": 82,
      "vent_kmh": 14.0,
      "pluie_24h_mm": 5.2,
      "code_meteo": 80,
      "heures": [{"heure": "08:00", "temperature": 25.1, "pluie": 0.0, "humidite": 85, "code_meteo": 2}, ...],
      "jours":  [{"jour": "Lun", "temp_min": 22.0, "temp_max": 31.0, "pluie": 12.0, "code_meteo": 80}, ...]
    }
    """
    meteo_raw   = data.get("meteorologie", {})
    actuel_raw  = meteo_raw.get("actuel", {})
    hourly_raw  = meteo_raw.get("previsions_hourly", {})
    daily_raw   = meteo_raw.get("previsions_daily",  {})
    today       = datetime.date.today()
    today_str   = today.isoformat()

    # ── Météo courante ───────────────────────────────────────────────
    temp_actuelle = actuel_raw.get("temperature_2m",       0.0) or 0.0
    humidite      = actuel_raw.get("relativehumidity_2m",  0)   or 0
    vent_kmh      = actuel_raw.get("windspeed_10m",        0.0) or 0.0
    code_wmo      = actuel_raw.get("weathercode",          0)   or 0

    # ── Températures min/max du jour (depuis daily) ──────────────────
    daily_times = daily_raw.get("time", [])
    temp_min = 0.0
    temp_max = 0.0
    pluie_24h = 0.0
    if today_str in daily_times:
        idx = daily_times.index(today_str)
        temp_min  = (daily_raw.get("temperature_2m_min",    []) + [0.0])[idx] or 0.0
        temp_max  = (daily_raw.get("temperature_2m_max",    []) + [0.0])[idx] or 0.0
        pluie_24h = (daily_raw.get("precipitation_sum",     []) + [0.0])[idx] or 0.0
    # Fallback sur indicateurs si daily absent
    ind = data.get("indicateurs_risque", {})
    if temp_max == 0.0:
        temp_max = ind.get("temperature_max_c", 0.0) or 0.0

    # ── Prévisions horaires (24 prochaines heures) ──────────────────
    h_times  = hourly_raw.get("time",                        [])
    h_temps  = hourly_raw.get("temperature_2m",              [])
    h_pluies = hourly_raw.get("precipitation",               [])
    h_humid  = hourly_raw.get("relativehumidity_2m",         [])
    h_wmo    = hourly_raw.get("weathercode",                 [])

    heures = []
    now_hour = datetime.datetime.now().hour
    count    = 0
    for i, t in enumerate(h_times):
        # Garder uniquement les heures d'aujourd'hui et demain, max 24
        try:
            dt = datetime.datetime.fromisoformat(t)
        except Exception:
            continue
        if dt.date() < today:
            continue
        if dt.date() > today + datetime.timedelta(days=1):
            break
        if count >= 24:
            break
        heures.append({
            "heure":       dt.strftime("%H:%M"),
            "temperature": round(float(h_temps[i])  if i < len(h_temps)  else 0.0, 1),
            "pluie":       round(float(h_pluies[i]) if i < len(h_pluies) else 0.0, 1),
            "humidite":    int(h_humid[i])           if i < len(h_humid)  else 0,
            "code_meteo":  int(h_wmo[i])             if i < len(h_wmo)    else 0,
        })
        count += 1

    # ── Prévisions journalières (7 jours) ───────────────────────────
    d_times   = daily_raw.get("time",                         [])
    d_tmin    = daily_raw.get("temperature_2m_min",           [])
    d_tmax    = daily_raw.get("temperature_2m_max",           [])
    d_pluie   = daily_raw.get("precipitation_sum",            [])
    d_wmo     = daily_raw.get("weathercode",                  [])

    jours = []
    for i, t in enumerate(d_times[:7]):
        try:
            dt = datetime.date.fromisoformat(t)
        except Exception:
            continue
        # Label : Auj., dem., ou nom du jour
        if dt == today:
            label = "Auj."
        elif dt == today + datetime.timedelta(days=1):
            label = "Dem."
        else:
            label = JOURS_FR[dt.weekday() + 1 if dt.weekday() < 6 else 0]
        jours.append({
            "jour":       label,
            "temp_min":   round(float(d_tmin[i])  if i < len(d_tmin)  else 0.0, 1),
            "temp_max":   round(float(d_tmax[i])  if i < len(d_tmax)  else 0.0, 1),
            "pluie":      round(float(d_pluie[i]) if i < len(d_pluie) else 0.0, 1),
            "code_meteo": int(d_wmo[i])           if i < len(d_wmo)   else 0,
        })

    # ── Code WMO courant : priorité actuel, fallback 1ère heure dispo ─
    if code_wmo == 0 and heures:
        code_wmo = heures[0]["code_meteo"]

    return {
        "temperature":  round(temp_actuelle, 1),
        "temp_min":     round(temp_min,      1),
        "temp_max":     round(temp_max,      1),
        "humidite":     int(humidite),
        "vent_kmh":     round(vent_kmh,      1),
        "pluie_24h_mm": round(pluie_24h,     1),
        "code_meteo":   code_wmo,
        "heures":       heures,
        "jours":        jours,
    }


# ─── SAUVEGARDE ───────────────────────────────────────────────────────

def sauvegarder_rapport(rapport: str, data_source: dict,
                        previsions_risque: dict) -> dict:
    today = datetime.date.today().isoformat()
    base  = os.path.join(REPORTS_DIR, f"rapport_kribi_{today}")

    with open(f"{base}.txt", "w", encoding="utf-8") as f:
        f.write(f"RAPPORT SAMCAM — Kribi — {today}\n")
        f.write("=" * 60 + "\n\n")
        f.write(rapport)

    ind = data_source.get("indicateurs_risque", {})

    # Niveau d'alerte depuis le modèle V4 (priorité) ou parsing texte
    niveau = previsions_risque.get("actuel", {}).get("niveau_global", None)
    if not niveau:
        rapport_upper = rapport.upper()
        for lvl in ["ROUGE", "ORANGE", "JAUNE", "VERT"]:
            if lvl in rapport_upper:
                niveau = lvl
                break
    niveau = niveau or "VERT"

    # ── Objet météo enrichi pour Flutter ────────────────────────────
    meteo_flutter = construire_meteo_flutter(data_source)

    sortie_json = {
        "date":            today,
        "zone":            "Kribi",
        "modele":          MODEL_NAME,
        "rapport_texte":   rapport,
        "niveau_alerte":   niveau,
        "risque_actuel":   previsions_risque.get("actuel",   {}),
        "risque_prevu_3j": previsions_risque.get("prevu_3j", {}),
        "risque_prevu_7j": previsions_risque.get("prevu_7j", {}),
        "methode_risque":  previsions_risque.get("actuel", {}).get("methode", "?"),
        "indicateurs":     ind,
        "meteo":           meteo_flutter,          # <-- NOUVEAU : pour Flutter
        "capteur":         data_source.get("meta", {}).get("capteur_satellite", "?"),
        "meteorologie":    data_source.get("meteorologie", {}),
        "satellitaire":    data_source.get("satellitaire", {}),
        "meta":            data_source.get("meta", {}),
    }
    with open(f"{base}.json", "w", encoding="utf-8") as f:
        json.dump(sortie_json, f, ensure_ascii=False, indent=2)

    print(f"[SAMCAM] 💾 Rapport sauvegardé :")
    print(f"         Texte  : {base}.txt")
    print(f"         JSON   : {base}.json")
    print(f"         Alerte : {niveau}")
    print(f"         Météo  : {meteo_flutter['temperature']}°C, WMO={meteo_flutter['code_meteo']}, "
          f"{len(meteo_flutter['heures'])}h horaires, {len(meteo_flutter['jours'])}j prévisions")
    return sortie_json


# ─── POINT D'ENTRÉE ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SAMCAM V4.2 — Analyse Phi-3 mini + météo Flutter")
    parser.add_argument("--fichier",   type=str,         default=None)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    fichier = args.fichier or charger_dernier_json()
    print(f"[SAMCAM] 📄 Analyse de : {fichier}")

    with open(fichier, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"[SAMCAM] 🤖 Calcul des risques (modèle V4)...")
    try:
        from inference.risk_model import evaluer_previsions
    except ImportError:
        from risk_model import evaluer_previsions

    previsions_risque = evaluer_previsions(data)
    print(f"[SAMCAM] Risque actuel   : {previsions_risque['actuel']['niveau_global']}")
    print(f"[SAMCAM] Risque prévu J+3: {previsions_risque['prevu_3j']['niveau_global']}")
    print(f"[SAMCAM] Risque prévu J+7: {previsions_risque['prevu_7j']['niveau_global']}")

    prompt = construire_prompt(data, previsions_risque)

    if not args.json_only:
        print(f"[SAMCAM] 🤖 Envoi à Phi-3 mini (Ollama)...")

    rapport = appeler_phi3(prompt, stream=not args.json_only)
    sauvegarder_rapport(rapport, data, previsions_risque)


if __name__ == "__main__":
    main()
