#!/usr/bin/env python3
"""
SAMCAM V4.7.0 — Module d'inférence des risques climatiques
Multi-horizons améliorés : J+1 / J+3 / J+7

NOUVEAUTÉS V4.7.0 :
    - 3 jeux de features distincts par horizon (J+1, J+3, J+7)
      → J+1 : données quasi-observées + état du sol actuel
      → J+3 : cumuls + anomalie climatologique + tendance SM
      → J+7 : saisonnalité forte + percentile historique + bilan hydrique
    - Dégradation explicite de la fiabilité par horizon
      → J+1 : 0.90 | J+3 : 0.68 | J+7 : 0.45
    - Intervalles de confiance bootstrap (±1 écart-type sur score)
    - Champ "fiabilite" dans chaque horizon de réponse
    - Correction de biais sur précipitations prévisionnelles Kribi
      (côte équatoriale : Open-Meteo sous-estime convection ~15% à 7j)
    - score_ajuste = score_brut * fiabilite_horizon
    - Nouveau champ "horizon_label" et "avertissement_fiabilite"
    - Rétrocompatibilité totale avec evaluer_previsions()

FEATURES par horizon :
    J+1 (18 features) : pluie_7j, sm_surface, sm_rootzone, ndvi, ndwi,
                         temp_max, temp_max_3j, et0_semaine, mois,
                         sin_mois, cos_mois, anomalie_pluie, ratio_30j_7j,
                         trend_sm, sm_deficit, ratio_et0_pluie,
                         pluie_prev_1j, pluie_30j
    J+3 (16 features) : pluie_prev_3j, anomalie_pluie_3j, sm_surface,
                         sm_rootzone, ndvi, ndwi, et0_prev_3j, mois,
                         sin_mois, cos_mois, ratio_30j_prev3j, sm_deficit,
                         ratio_et0_pluie_3j, temp_max_3j, pluie_30j, trend_sm
    J+7 (14 features) : pluie_prev_7j, anomalie_pluie_7j, percentile_pluie,
                         ndvi, et0_prev_7j, mois, sin_mois, cos_mois,
                         sm_deficit, ratio_et0_pluie_7j, temp_max,
                         saison_seche, pluie_30j, sm_rootzone

CONSERVATION V4.3 :
    - et0_semaine dans FEATURES_BASE
    - ratio_et0_pluie dans FEATURES_DERIVEES
    - fallback règles physiques inchangé
"""

import os
import json
import datetime
import math
import random
from typing import Optional, Dict, Any

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")

# ───────────────────────────────────────────────────────────────────────────────
# CLIMATOLOGIE KRIBI
# ───────────────────────────────────────────────────────────────────────────────

NORMALES_MENSUELLES = {
    1: 30,  2: 50,  3: 120, 4: 180, 5: 200, 6: 160,
    7: 80,  8: 100, 9: 180, 10: 200, 11: 150, 12: 50,
}

ET0_NORMALES_MENSUELLES = {
    1: 25, 2: 27, 3: 24, 4: 21, 5: 20, 6: 19,
    7: 18, 8: 18, 9: 19, 10: 20, 11: 21, 12: 23,
}

# Percentiles historiques pluie hebdomadaire Kribi (ERA5-Land 1984-2024)
# Utilisés pour calculer percentile_pluie à J+7
PERCENTILES_HEBDO = {
    1:  {"p25": 0, "p50": 5,  "p75": 18,  "p90": 40},
    2:  {"p25": 2, "p50": 12, "p75": 35,  "p90": 70},
    3:  {"p25": 8, "p50": 28, "p75": 65,  "p90": 120},
    4:  {"p25": 15,"p50": 42, "p75": 90,  "p90": 160},
    5:  {"p25": 20,"p50": 50, "p75": 105, "p90": 180},
    6:  {"p25": 12,"p50": 38, "p75": 82,  "p90": 140},
    7:  {"p25": 5, "p50": 18, "p75": 45,  "p90": 90},
    8:  {"p25": 8, "p50": 25, "p75": 58,  "p90": 105},
    9:  {"p25": 18,"p50": 45, "p75": 95,  "p90": 165},
    10: {"p25": 20,"p50": 52, "p75": 108, "p90": 185},
    11: {"p25": 14,"p50": 38, "p75": 80,  "p90": 140},
    12: {"p25": 2, "p50": 10, "p75": 28,  "p90": 60},
}

# Facteur de correction biais Open-Meteo Kribi côte équatoriale
# Sous-estimation convection tropicale en prévision longue portée
BIAIS_CORRECTION_PLUIE = {
    1: 1.00, 3: 1.08, 7: 1.15,  # J+1, J+3, J+7
}

# Fiabilité des prévisions par horizon
FIABILITE_HORIZON = {
    1: 0.90,
    3: 0.68,
    7: 0.45,
}

SCORE_VERS_NIVEAU = {
    (0.75, 1.01): "ROUGE",
    (0.50, 0.75): "ORANGE",
    (0.25, 0.50): "JAUNE",
    (0.00, 0.25): "VERT",
}

DESCRIPTIONS = {
    "inondation": {
        "ROUGE":  "Risque d'inondation critique — évacuations préventives recommandées.",
        "ORANGE": "Risque d'inondation modéré — surveiller les zones basses.",
        "JAUNE":  "Risque d'inondation faible — vigilance maintenue.",
        "VERT":   "Pas de risque d'inondation en ce moment.",
    },
    "secheresse": {
        "ROUGE":  "Sécheresse sévère — restriction d'eau et soutien aux cultures urgent.",
        "ORANGE": "Sécheresse modérée — irrigation recommandée.",
        "JAUNE":  "Légère tension hydrique — surveiller l'évolution.",
        "VERT":   "Humidité du sol normale pour la saison.",
    },
    "chaleur": {
        "ROUGE":  "Vague de chaleur extrême — risque sanitaire élevé.",
        "ORANGE": "Chaleur intense — limiter les activités en plein air.",
        "JAUNE":  "Températures élevées — hydratation conseillée.",
        "VERT":   "Températures normales pour la saison.",
    },
}

# Features V4.3 (compatibilité rétro — utilisées comme base J0)
FEATURES_BASE = [
    "mois", "pluie_7j", "pluie_30j", "pluie_prev_7j",
    "temp_max", "temp_max_3j", "sm_surface", "sm_rootzone",
    "ndvi", "ndwi", "et0_semaine",
]
FEATURES_DERIVEES = [
    "sin_mois", "cos_mois",
    "anomalie_pluie", "ratio_30j_7j",
    "trend_sm", "sm_deficit",
    "ratio_et0_pluie",
]
FEATURES_ORDER = FEATURES_BASE + FEATURES_DERIVEES

# ───────────────────────────────────────────────────────────────────────────────
# FEATURES SPÉCIFIQUES PAR HORIZON (V4.7.0)
# ───────────────────────────────────────────────────────────────────────────────

FEATURES_J1 = [
    "mois", "sin_mois", "cos_mois",
    "pluie_7j", "pluie_prev_1j", "pluie_30j",
    "sm_surface", "sm_rootzone", "ndvi", "ndwi",
    "temp_max", "temp_max_3j", "et0_semaine",
    "anomalie_pluie", "ratio_30j_7j", "trend_sm",
    "sm_deficit", "ratio_et0_pluie",
]

FEATURES_J3 = [
    "mois", "sin_mois", "cos_mois",
    "pluie_prev_3j", "anomalie_pluie_3j", "pluie_30j",
    "sm_surface", "sm_rootzone", "ndvi", "ndwi",
    "temp_max_3j", "et0_prev_3j",
    "ratio_30j_prev3j", "sm_deficit",
    "ratio_et0_pluie_3j", "trend_sm",
]

FEATURES_J7 = [
    "mois", "sin_mois", "cos_mois",
    "pluie_prev_7j", "anomalie_pluie_7j", "percentile_pluie",
    "ndvi", "sm_rootzone", "sm_deficit",
    "et0_prev_7j", "ratio_et0_pluie_7j",
    "temp_max", "saison_seche", "pluie_30j",
]

# ───────────────────────────────────────────────────────────────────────────────
# HISTORIQUE GLISSANT — trend_sm (V4.2)
# ───────────────────────────────────────────────────────────────────────────────

_sm_surface_historique: Optional[float] = None


def reset_historique():
    global _sm_surface_historique
    _sm_surface_historique = None


def _get_trend_sm(sm_surface_actuel: float) -> float:
    global _sm_surface_historique
    if _sm_surface_historique is None:
        trend = 0.0
    else:
        trend = round(sm_surface_actuel - _sm_surface_historique, 4)
    _sm_surface_historique = sm_surface_actuel
    return trend


# ───────────────────────────────────────────────────────────────────────────────
# HELPERS
# ───────────────────────────────────────────────────────────────────────────────

def _score_vers_niveau(score: float) -> str:
    for (lo, hi), niveau in SCORE_VERS_NIVEAU.items():
        if lo <= score < hi:
            return niveau
    return "VERT"


def _confidence(score: float, seuil: float) -> float:
    dist = abs(score - seuil)
    return round(min(1.0, dist / 0.5), 3)


def _percentile_pluie(pluie_mm: float, mois: int) -> float:
    """Retourne le rang percentile (0-1) de la pluie dans la distribution historique Kribi."""
    p = PERCENTILES_HEBDO.get(mois, {"p25": 10, "p50": 30, "p75": 70, "p90": 130})
    if pluie_mm <= p["p25"]:
        return 0.15
    elif pluie_mm <= p["p50"]:
        return 0.38
    elif pluie_mm <= p["p75"]:
        return 0.62
    elif pluie_mm <= p["p90"]:
        return 0.80
    else:
        return 0.95


def _saison_seche(mois: int) -> int:
    """1 si en saison sèche principale Kribi (déc-fév, juil-août), 0 sinon."""
    return 1 if mois in (12, 1, 2, 7, 8) else 0


def _corriger_pluie_prevision(pluie_mm: float, horizon: int) -> float:
    """Correction de biais sur précipitations prévisionnelles Open-Meteo à Kribi.
    La convection tropicale côtière est sous-estimée sur longue portée (~15% à J+7)."""
    facteur = BIAIS_CORRECTION_PLUIE.get(horizon, 1.0)
    return round(pluie_mm * facteur, 2)


def _intervalle_confiance_bootstrap(score: float, fiabilite: float,
                                     n_iter: int = 50) -> Dict[str, float]:
    """
    Estime un intervalle de confiance ±1σ via bootstrap simplifié.
    Simule la variabilité inhérente à l'incertitude météo par horizon.
    L'écart-type augmente avec la distance à la frontière de décision
    et diminue avec la fiabilité de l'horizon.
    """
    sigma_base = (1.0 - fiabilite) * 0.20  # variabilité croissante avec l'horizon
    # Plus proche du seuil de décision → moins certains
    dist_seuil = min(abs(score - 0.25), abs(score - 0.50), abs(score - 0.75))
    sigma_seuil = max(0.0, 0.12 - dist_seuil * 0.8)
    sigma = sigma_base + sigma_seuil

    random.seed(42)
    echantillons = [max(0.0, min(1.0, score + random.gauss(0, sigma))) for _ in range(n_iter)]
    echantillons.sort()

    p16 = echantillons[int(0.16 * n_iter)]
    p84 = echantillons[int(0.84 * n_iter)]

    return {
        "borne_basse": round(p16, 3),
        "borne_haute": round(p84, 3),
        "sigma": round(sigma, 3),
    }


# ───────────────────────────────────────────────────────────────────────────────
# CHARGEMENT DES MODÈLES
# ───────────────────────────────────────────────────────────────────────────────

_cache_modeles: dict = {}


def _charger_modele(nom: str, horizon: Optional[int] = None):
    """
    Cherche d'abord un modèle horizon-spécifique (model_inondation_j1.pkl),
    puis fallback sur le modèle générique (model_inondation.pkl).
    """
    cles_a_tester = []
    if horizon is not None:
        cles_a_tester.append(f"{nom}_j{horizon}")
    cles_a_tester.append(nom)

    for cle in cles_a_tester:
        if cle in _cache_modeles:
            return _cache_modeles[cle]
        chemin = os.path.join(MODELS_DIR, f"model_{cle}.pkl")
        if os.path.exists(chemin):
            try:
                import joblib
                obj = joblib.load(chemin)
                if isinstance(obj, dict):
                    clf      = obj["clf"]
                    seuil    = obj.get("seuil",    0.5)
                    features = obj.get("features", FEATURES_BASE)
                else:
                    clf      = obj
                    seuil    = 0.5
                    features = FEATURES_BASE
                _cache_modeles[cle] = (clf, seuil, features)
                return clf, seuil, features
            except Exception:
                continue

    return None, 0.5, FEATURES_BASE


def modeles_disponibles() -> list:
    modeles = []
    for n in ["inondation", "secheresse", "chaleur"]:
        if os.path.exists(os.path.join(MODELS_DIR, f"model_{n}.pkl")):
            modeles.append(n)
    return modeles


# ───────────────────────────────────────────────────────────────────────────────
# FALLBACK — Règles physiques (inchangées V4.3)
# ───────────────────────────────────────────────────────────────────────────────

def _risque_inondation_physique(pluie_7j, pluie_prev, sm_surface, ndwi, mois):
    normale = NORMALES_MENSUELLES.get(mois, 120)
    score = 0.0
    score += min(0.35, max(0, (pluie_7j   / normale - 1.0) * 0.30))
    score += min(0.25, max(0, (pluie_prev / normale - 1.0) * 0.20))
    score += min(0.25, max(0, (sm_surface - 0.40) * 1.5))
    score += min(0.15, max(0, (ndwi - 0.30) * 0.5))
    return min(1.0, score)


def _risque_secheresse_physique(pluie_30j, ndvi, sm_rootzone, mois, et0_semaine=0.0):
    normale_30j = NORMALES_MENSUELLES.get(mois, 120) * (30 / 7)
    et0_normale = ET0_NORMALES_MENSUELLES.get(mois, 21)
    score = 0.0
    deficit = max(0, (normale_30j - pluie_30j) / normale_30j)
    score += min(0.35, deficit * 0.5)
    score += min(0.30, max(0, (0.55 - ndvi) * 1.2))
    score += min(0.20, max(0, (0.28 - sm_rootzone) * 2.0))
    score += min(0.15, max(0, (et0_semaine - et0_normale) / et0_normale * 0.15))
    return min(1.0, score)


def _risque_chaleur_physique(temp_max, temp_max_3j):
    score = 0.0
    score += min(0.60, max(0, (temp_max    - 32.0) / 5.0 * 0.50))
    score += min(0.40, max(0, (temp_max_3j - 32.0) / 5.0 * 0.40))
    return min(1.0, score)


# ───────────────────────────────────────────────────────────────────────────────
# CONSTRUCTION DES FEATURES PAR HORIZON (V4.7.0)
# ───────────────────────────────────────────────────────────────────────────────

def _features_j0(data: dict) -> dict:
    """Features J0 (observées) — identiques V4.3 pour la rétrocompatibilité."""
    mois    = datetime.date.today().month
    ind     = data.get("indicateurs_risque", {})
    sat     = data.get("satellitaire", {}).get("smap", {}).get("humidite_sol", {})
    meteo   = data.get("meteorologie", {})

    pluie_7j    = float(ind.get("pluie_cumulee_7j_mm",  0) or 0)
    pluie_30j   = float(ind.get("pluie_cumulee_30j_mm", pluie_7j * 4) or pluie_7j * 4)
    sm_surface  = float(sat.get("sm_surface",  0.35) or 0.35)
    sm_rootzone = float(sat.get("sm_rootzone", 0.30) or 0.30)
    ndvi        = float(ind.get("ndvi_moyen",  0.70) or 0.70)
    ndwi        = float(ind.get("ndwi_moyen",  0.20) or 0.20)
    temp_max    = float(ind.get("temperature_max_c",    29.0) or 29.0)
    temp_max_3j = float(ind.get("temperature_max_3j_c", temp_max - 0.5) or temp_max - 0.5)
    pluie_prev  = float(ind.get("pluie_prevue_7j_mm",   0) or 0)

    et0_raw = (
        meteo.get("et0_semaine_mm") or
        meteo.get("actuel", {}).get("et0_fao_evapotranspiration") or
        ind.get("et0_semaine_mm")
    )
    et0_semaine = float(et0_raw) if et0_raw is not None else float(ET0_NORMALES_MENSUELLES.get(mois, 21))

    normale       = NORMALES_MENSUELLES.get(mois, 120)
    sin_mois      = round(math.sin(2 * math.pi * mois / 12), 4)
    cos_mois      = round(math.cos(2 * math.pi * mois / 12), 4)
    anomalie      = round((pluie_7j - normale) / max(1.0, normale), 4)
    ratio         = round(pluie_30j / max(1.0, pluie_7j * (30 / 7)), 4) if pluie_7j > 0 else 1.0
    ratio         = min(ratio, 5.0)
    trend_sm      = _get_trend_sm(sm_surface)
    sm_def        = round(max(0.0, (0.30 - sm_rootzone) / 0.30), 4)
    ratio_et0     = round(et0_semaine / max(1.0, pluie_7j), 4)
    ratio_et0     = min(ratio_et0, 10.0)

    return {
        "mois":           mois,
        "pluie_7j":       round(pluie_7j, 2),
        "pluie_30j":      round(pluie_30j, 2),
        "pluie_prev_7j":  round(pluie_prev, 2),
        "temp_max":       round(temp_max, 2),
        "temp_max_3j":    round(temp_max_3j, 2),
        "sm_surface":     round(sm_surface, 4),
        "sm_rootzone":    round(sm_rootzone, 4),
        "ndvi":           round(ndvi, 4),
        "ndwi":           round(ndwi, 4),
        "et0_semaine":    round(et0_semaine, 2),
        "sin_mois":       sin_mois,
        "cos_mois":       cos_mois,
        "anomalie_pluie": anomalie,
        "ratio_30j_7j":   ratio,
        "trend_sm":       trend_sm,
        "sm_deficit":     sm_def,
        "ratio_et0_pluie": ratio_et0,
    }


def _features_horizon(data: dict, horizon: int) -> dict:
    """
    Construit un jeu de features adapté à l'horizon de prévision.
    Applique la correction de biais sur les précipitations prévisionnelles.

    Args:
        data    : dictionnaire JSON collecté
        horizon : 1, 3 ou 7 jours
    Returns:
        dictionnaire de features enrichies pour cet horizon
    """
    mois    = datetime.date.today().month
    ind     = data.get("indicateurs_risque", {})
    sat     = data.get("satellitaire", {}).get("smap", {}).get("humidite_sol", {})
    prev    = data.get("meteorologie", {}).get("previsions_daily", {})

    # Données communes
    pluie_30j   = float(ind.get("pluie_cumulee_30j_mm", 0) or 0)
    sm_surface  = float(sat.get("sm_surface",  0.35) or 0.35)
    sm_rootzone = float(sat.get("sm_rootzone", 0.30) or 0.30)
    ndvi        = float(ind.get("ndvi_moyen",  0.70) or 0.70)
    ndwi        = float(ind.get("ndwi_moyen",  0.20) or 0.20)
    temp_max    = float(ind.get("temperature_max_c", 29.0) or 29.0)

    sin_mois = round(math.sin(2 * math.pi * mois / 12), 4)
    cos_mois = round(math.cos(2 * math.pi * mois / 12), 4)
    sm_def   = round(max(0.0, (0.30 - sm_rootzone) / 0.30), 4)

    # Extraction des listes prévisionnelles jusqu'à l'horizon
    precip_list = (prev.get("precipitation_sum",           []) or [])[:horizon]
    temp_list   = (prev.get("temperature_2m_max",          []) or [])[:horizon]
    et0_list    = (prev.get("et0_fao_evapotranspiration",  []) or [])[:horizon]

    pluie_prev_brute = sum(float(p or 0) for p in precip_list)
    pluie_prev       = _corriger_pluie_prevision(pluie_prev_brute, horizon)

    temp_max_hor = max((float(t or 28) for t in temp_list), default=28.0)
    t3           = [float(t or 28) for t in temp_list[:3]]
    temp_max_3j  = sum(t3) / len(t3) if t3 else temp_max_hor

    et0_hor = sum(float(e or 0) for e in et0_list) if et0_list else (
        ET0_NORMALES_MENSUELLES.get(mois, 21) * (horizon / 7)
    )

    normale          = NORMALES_MENSUELLES.get(mois, 120)
    normale_horizon  = normale * (horizon / 7)
    anomalie_prev    = round((pluie_prev - normale_horizon) / max(1.0, normale_horizon), 4)
    percentile       = _percentile_pluie(pluie_prev, mois)
    ratio_30j_prev   = round(pluie_30j / max(1.0, pluie_prev * (30 / horizon)), 4)
    ratio_30j_prev   = min(ratio_30j_prev, 5.0)
    ratio_et0_prev   = round(et0_hor / max(1.0, pluie_prev), 4)
    ratio_et0_prev   = min(ratio_et0_prev, 10.0)
    trend_sm         = _get_trend_sm(sm_surface) if horizon == 1 else 0.0

    return {
        # Communs
        "mois":             mois,
        "sin_mois":         sin_mois,
        "cos_mois":         cos_mois,
        "pluie_30j":        round(pluie_30j, 2),
        "sm_surface":       round(sm_surface, 4),
        "sm_rootzone":      round(sm_rootzone, 4),
        "ndvi":             round(ndvi, 4),
        "ndwi":             round(ndwi, 4),
        "sm_deficit":       sm_def,
        "trend_sm":         trend_sm,
        "saison_seche":     _saison_seche(mois),
        "percentile_pluie": round(percentile, 3),
        "temp_max":         round(temp_max, 2),
        "temp_max_3j":      round(temp_max_3j, 2),

        # Nommage unifié pour usage interne
        "pluie_prev_1j":    round(_corriger_pluie_prevision(
            sum(float(p or 0) for p in (prev.get("precipitation_sum", []) or [])[:1]), 1
        ), 2),
        "pluie_prev_3j":    round(_corriger_pluie_prevision(
            sum(float(p or 0) for p in (prev.get("precipitation_sum", []) or [])[:3]), 3
        ), 2),
        "pluie_prev_7j":    round(pluie_prev if horizon == 7 else _corriger_pluie_prevision(
            sum(float(p or 0) for p in (prev.get("precipitation_sum", []) or [])[:7]), 7
        ), 2),

        # Anomalies par horizon
        "anomalie_pluie_1j": round(
            (_corriger_pluie_prevision(
                sum(float(p or 0) for p in (prev.get("precipitation_sum", []) or [])[:1]), 1
            ) - normale * (1 / 7)) / max(1.0, normale * (1 / 7)), 4
        ),
        "anomalie_pluie_3j": round(
            (_corriger_pluie_prevision(
                sum(float(p or 0) for p in (prev.get("precipitation_sum", []) or [])[:3]), 3
            ) - normale * (3 / 7)) / max(1.0, normale * (3 / 7)), 4
        ),
        "anomalie_pluie_7j": round(anomalie_prev, 4),
        "anomalie_pluie":    round(anomalie_prev, 4),  # alias rétrocompat

        # ET0 par horizon
        "et0_semaine":      round(et0_hor, 2),
        "et0_prev_3j":      round(
            sum(float(e or 0) for e in (prev.get("et0_fao_evapotranspiration", []) or [])[:3])
            or ET0_NORMALES_MENSUELLES.get(mois, 21) * (3 / 7), 2
        ),
        "et0_prev_7j":      round(et0_hor if horizon == 7 else
            sum(float(e or 0) for e in (prev.get("et0_fao_evapotranspiration", []) or [])[:7])
            or ET0_NORMALES_MENSUELLES.get(mois, 21), 2
        ),

        # Ratios par horizon
        "ratio_30j_prev3j":    round(pluie_30j / max(1.0, _corriger_pluie_prevision(
            sum(float(p or 0) for p in (prev.get("precipitation_sum", []) or [])[:3]), 3
        ) * (30 / 3)), 4),
        "ratio_et0_pluie":     ratio_et0_prev,
        "ratio_et0_pluie_3j":  round(
            (sum(float(e or 0) for e in (prev.get("et0_fao_evapotranspiration", []) or [])[:3])
             or ET0_NORMALES_MENSUELLES.get(mois, 21) * (3 / 7))
            / max(1.0, _corriger_pluie_prevision(
                sum(float(p or 0) for p in (prev.get("precipitation_sum", []) or [])[:3]), 3
            )), 4
        ),
        "ratio_et0_pluie_7j":  round(ratio_et0_prev, 4),
        "ratio_30j_7j":        round(ratio_30j_prev, 4),
    }


# ───────────────────────────────────────────────────────────────────────────────
# SÉLECTION DES FEATURES PAR HORIZON
# ───────────────────────────────────────────────────────────────────────────────

_FEATURES_PAR_HORIZON = {
    1: FEATURES_J1,
    3: FEATURES_J3,
    7: FEATURES_J7,
}


def _get_features_pour_horizon(horizon: Optional[int]) -> list:
    """Retourne la liste de features recommandée pour un horizon donné."""
    if horizon is None:
        return FEATURES_ORDER
    return _FEATURES_PAR_HORIZON.get(horizon, FEATURES_ORDER)


# ───────────────────────────────────────────────────────────────────────────────
# INFÉRENCE PRINCIPALE (V4.7.0)
# ───────────────────────────────────────────────────────────────────────────────

def predire_risques(data: dict, use_previsions: bool = False,
                    horizon_jours: int = 7) -> dict:
    """
    Prédit les risques climatiques pour un horizon donné.

    V4.7.0 : utilise des features adaptées à l'horizon, applique la
    dégradation de fiabilité et calcule les intervalles de confiance.
    """
    if use_previsions:
        feats = _features_horizon(data, horizon_jours)
        fiabilite = FIABILITE_HORIZON.get(horizon_jours, 0.50)
    else:
        feats = _features_j0(data)
        fiabilite = 1.0
        horizon_jours = 0  # sentinel pour J0

    try:
        import pandas as pd
        use_df = True
    except ImportError:
        use_df = False

    resultats = {}
    methode_utilisee = {}

    for nom in ["inondation", "secheresse", "chaleur"]:
        # Tentative modèle horizon-spécifique en premier
        hor_key = horizon_jours if horizon_jours > 0 else None
        clf, seuil, features_modele = _charger_modele(nom, horizon=hor_key)

        if clf is not None:
            try:
                feats_modele = {}
                for k in features_modele:
                    val = feats.get(k)
                    feats_modele[k] = float(val) if val is not None else 0.0

                if use_df:
                    import pandas as pd
                    X = pd.DataFrame([feats_modele], columns=features_modele)
                else:
                    X = [[feats_modele[f] for f in features_modele]]

                score_brut = float(clf.predict_proba(X)[0][1])
                methode_utilisee[nom] = f"modele_ml_v4.7_j{horizon_jours}" if horizon_jours > 0 else "modele_ml_v4.7_j0"
            except Exception as e:
                print(f"[RISK] Erreur modèle {nom} h={horizon_jours} : {e} → fallback règles physiques")
                score_brut = None
        else:
            score_brut = None

        if score_brut is None:
            methode_utilisee[nom] = "regles_physiques"
            seuil = 0.5
            if nom == "inondation":
                score_brut = _risque_inondation_physique(
                    feats.get("pluie_7j", 0),
                    feats.get("pluie_prev_7j", feats.get("pluie_prev_3j", feats.get("pluie_prev_1j", 0))),
                    feats.get("sm_surface", 0.35), feats.get("ndwi", 0.20), feats.get("mois", 6))
            elif nom == "secheresse":
                score_brut = _risque_secheresse_physique(
                    feats.get("pluie_30j", 0), feats.get("ndvi", 0.70),
                    feats.get("sm_rootzone", 0.30), feats.get("mois", 6),
                    feats.get("et0_semaine", ET0_NORMALES_MENSUELLES.get(feats.get("mois", 6), 21)))
            else:
                score_brut = _risque_chaleur_physique(
                    feats.get("temp_max", 29.0), feats.get("temp_max_3j", 28.5))

        # Ajustement du score selon la fiabilité de l'horizon
        if use_previsions:
            score_ajuste = round(score_brut * fiabilite, 4)
            avertissement = (
                f"Prévision J+{horizon_jours} — fiabilité {int(fiabilite * 100)}%. "
                f"Score brut : {round(score_brut, 3)} → ajusté : {score_ajuste}"
            )
        else:
            score_ajuste = round(score_brut, 4)
            avertissement = "Données observées — fiabilité maximale."

        ic = _intervalle_confiance_bootstrap(score_ajuste, fiabilite)
        niveau = _score_vers_niveau(score_ajuste)

        resultats[nom] = {
            "score":          score_ajuste,
            "score_brut":     round(score_brut, 4),
            "niveau":         niveau,
            "confiance":      _confidence(score_ajuste, seuil),
            "fiabilite":      fiabilite,
            "intervalle":     ic,
            "description":    DESCRIPTIONS[nom][niveau],
            "methode":        methode_utilisee[nom],
            "avertissement":  avertissement,
        }

    niveaux_ordre = ["VERT", "JAUNE", "ORANGE", "ROUGE"]
    niveau_global = max(
        (r["niveau"] for r in resultats.values()),
        key=lambda n: niveaux_ordre.index(n)
    )

    return {
        "scores":            {k: v["score"]       for k, v in resultats.items()},
        "scores_bruts":      {k: v["score_brut"]  for k, v in resultats.items()},
        "niveaux":           {k: v["niveau"]      for k, v in resultats.items()},
        "confiances":        {k: v["confiance"]   for k, v in resultats.items()},
        "fiabilite":         fiabilite,
        "intervalles":       {k: v["intervalle"]  for k, v in resultats.items()},
        "descriptions":      {k: v["description"] for k, v in resultats.items()},
        "avertissements":    {k: v["avertissement"] for k, v in resultats.items()},
        "niveau_global":     niveau_global,
        "methode_globale":   "modele_ml_v4.7" if any(
            "modele_ml" in v for v in methode_utilisee.values()
        ) else "regles_physiques",
        "features_utilisees": feats,
        "modeles_charges":    modeles_disponibles(),
    }


def evaluer_previsions(data: dict) -> dict:
    """
    Retourne les prédictions pour J0, J+1, J+3 et J+7.

    V4.7.0 : chaque horizon a ses propres features, sa fiabilité et
    ses intervalles de confiance. Le format de réponse est enrichi
    mais rétrocompatible avec les versions précédentes.
    """
    risque_j0  = predire_risques(data, use_previsions=False)
    risque_j1  = predire_risques(data, use_previsions=True, horizon_jours=1)
    risque_j3  = predire_risques(data, use_previsions=True, horizon_jours=3)
    risque_j7  = predire_risques(data, use_previsions=True, horizon_jours=7)

    def _pack(r: dict, label: str) -> dict:
        return {
            "horizon_label":    label,
            "niveau_global":    r["niveau_global"],
            "niveaux":          r["niveaux"],
            "scores":           r["scores"],
            "scores_bruts":     r["scores_bruts"],
            "confiances":       r["confiances"],
            "fiabilite":        r["fiabilite"],
            "intervalles":      r["intervalles"],
            "descriptions":     r["descriptions"],
            "avertissements":   r["avertissements"],
            "methode":          r["methode_globale"],
        }

    # Tendance : compare niveau_global entre horizons
    niveaux_ordre = ["VERT", "JAUNE", "ORANGE", "ROUGE"]

    def _tendance(n_from: str, n_to: str) -> str:
        idx_from = niveaux_ordre.index(n_from)
        idx_to   = niveaux_ordre.index(n_to)
        if idx_to > idx_from:   return "dégradation"
        if idx_to < idx_from:   return "amélioration"
        return "stable"

    return {
        "actuel":    _pack(risque_j0, "J0 — Observations"),
        "prevu_1j":  _pack(risque_j1, "J+1 — Prévision 24h"),
        "prevu_3j":  _pack(risque_j3, "J+3 — Prévision 72h"),
        "prevu_7j":  _pack(risque_j7, "J+7 — Prévision 7 jours"),
        "tendance": {
            "j0_vers_j1":  _tendance(risque_j0["niveau_global"], risque_j1["niveau_global"]),
            "j1_vers_j3":  _tendance(risque_j1["niveau_global"], risque_j3["niveau_global"]),
            "j3_vers_j7":  _tendance(risque_j3["niveau_global"], risque_j7["niveau_global"]),
        },
        "resume": {
            "niveau_max_horizon":  max(
                [risque_j0["niveau_global"], risque_j1["niveau_global"],
                 risque_j3["niveau_global"], risque_j7["niveau_global"]],
                key=lambda n: niveaux_ordre.index(n)
            ),
            "fiabilite_j1":  FIABILITE_HORIZON[1],
            "fiabilite_j3":  FIABILITE_HORIZON[3],
            "fiabilite_j7":  FIABILITE_HORIZON[7],
            "note":          (
                "Les scores sont ajustés par la fiabilité de l'horizon. "
                "Les intervalles de confiance reflètent l'incertitude croissante "
                "avec la distance temporelle. Correction de biais appliquée sur "
                "les précipitations prévisionnelles Open-Meteo (côte équatoriale Kribi)."
            ),
        },
    }


# ───────────────────────────────────────────────────────────────────────────────
# TEST AUTONOME
# ───────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    data_test = {
        "indicateurs_risque": {
            "pluie_cumulee_7j_mm":   320,
            "pluie_prevue_7j_mm":    280,
            "pluie_cumulee_30j_mm":  950,
            "ndvi_moyen":            0.68,
            "ndwi_moyen":            0.48,
            "temperature_max_c":     31.0,
            "temperature_max_3j_c":  30.5,
        },
        "satellitaire": {"smap": {"humidite_sol": {
            "sm_surface": 0.54, "sm_rootzone": 0.41
        }}},
        "meteorologie": {
            "et0_semaine_mm": 18.5,
            "previsions_daily": {
                "precipitation_sum":          [45, 38, 52, 30, 25, 42, 55],
                "temperature_2m_max":         [30, 31, 30, 29, 30, 31, 32],
                "et0_fao_evapotranspiration": [2.8, 2.9, 2.7, 3.0, 3.1, 2.9, 3.0],
            },
        },
    }

    resultats = evaluer_previsions(data_test)
    print(json.dumps(resultats, ensure_ascii=False, indent=2))

    print("\n=== RÉSUMÉ TENDANCE ===")
    for k, v in resultats["tendance"].items():
        print(f"  {k}: {v}")
    print(f"\n  Niveau max sur tous horizons : {resultats['resume']['niveau_max_horizon']}")
    print(f"  Fiabilités : J+1={resultats['resume']['fiabilite_j1']} | "
          f"J+3={resultats['resume']['fiabilite_j3']} | "
          f"J+7={resultats['resume']['fiabilite_j7']}")
