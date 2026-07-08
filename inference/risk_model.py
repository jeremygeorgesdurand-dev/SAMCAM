#!/usr/bin/env python3
"""
SAMCAM V5.0.0 — Module d'inférence des risques climatiques
Multi-horizons améliorés : J+1 / J+3 / J+7

NOUVEAUTÉS V5.0.0 :
    - FIX CRITIQUE chargement des modèles zonaux :
        La V4.7.x pointait uniquement vers models/ pour tous les modèles.
        Les modèles zonaux entraînés dans models/zonal/ n'étaient jamais utilisés.
        Nouveau comportement de _charger_modele(nom, horizon, zone) :
          1. models/zonal/model_{risque}_{Zone}.pkl  (zonal + spécifique zone)
          2. models/zonal/model_{risque}.pkl          (zonal générique)
          3. models/model_{risque}_j{horizon}.pkl     (global multi-horizon)
          4. models/model_{risque}.pkl                (global fallback final)
        predire_risques() et evaluer_previsions() propagent le paramètre `zone`.
        Le cache interne est keyed sur (cle, zone) pour éviter les collisions.

NOUVEAUTÉS V4.7.5 :
    - FIX CRITIQUE bug trend_sm double-appel :
        evaluer_previsions() appelle predire_risques() 4 fois de suite (J0/J1/J3/J7).
        L'ancienne _get_trend_sm() mutait un état global à chaque appel, corrompant
        l'historique glissant. Nouveau design : _get_trend_sm_pur() est une fonction
        PURE sans effet de bord. trend_sm est calculé une fois dans _lire_donnees()
        via sm_reference passé explicitement depuis _sm_surface_precedente.
        Résultat : trend_sm cohérent et identique pour tous les horizons d'un cycle.

NOUVEAUTÉS V4.7.4 :
    - CORRECTION CRITIQUE score_brut=1.0 :
        Le modèle ML model_secheresse.pkl retournait toujours 1.0 car entraîné
        avant la correction des normales Kribi. Fix : garde-fou de cohérence
        physique — si le score ML dépasse le score physique de plus de 0.30,
        on utilise automatiquement le fallback règles physiques.
    - NDVI contextuel selon saison (seuil variable) :
        Saison sèche (juil-août, déc-jan) : seuil 0.35 (végétation naturellement
        plus basse) — Saison des pluies : seuil 0.50 — Transition : 0.43
    - sm_rootzone comparé à la normale mensuelle SMAP de Kribi au lieu
        d'un seuil unique 0.28 (qui était trop haut pour la saison sèche)
    - Logs de diagnostic [RISK-DIAG] traçant la source du score retenu

NOUVEAUTÉS V4.7.3 :
    - NORMALES_MENSUELLES corrigées (régime bimodal côtier équatorial Kribi)
    - Bug *(30/7) supprimé dans _risque_secheresse_physique
    - Poids NDVI et déficit recalibrés pour zone tropicale humide

NOUVEAUTÉS V4.7.2 :
    - sauvegarder_rapport_json() sans dépendance Ollama/Phi-3

NOUVEAUTÉS V4.7.1 :
    - Correction critique du mapping des données JSON → features
    - Valeurs par défaut réalistes pour Kribi

NOUVEAUTÉS V4.7.0 :
    - 3 jeux de features distincts par horizon (J+1, J+3, J+7)
    - Dégradation explicite de la fiabilité par horizon
    - Intervalles de confiance bootstrap
    - Correction de biais sur précipitations prévisionnelles Kribi
"""

import os
import json
import datetime
import math
import random
from typing import Optional, Dict, Any

MODELS_DIR        = os.path.join(os.path.dirname(__file__), "..", "models")
ZONAL_MODELS_DIR  = os.path.join(os.path.dirname(__file__), "..", "models", "zonal")
REPORTS_DIR       = os.path.join(os.path.dirname(__file__), "..", "reports")
DATA_DIR          = os.path.join(os.path.dirname(__file__), "..", "data")

# ──────────────────────────────────────────────────────────────────────────────────
# CLIMATOLOGIE KRIBI — V4.7.3 (données réelles régime bimodal côtier équatorial)
# Source : données climatologiques Kribi (3°54'N, 9°54'E)
# Deux saisons des pluies : mars-juin et sept-nov
# Deux saisons sèches : juil-août (principale) et déc-fév (petite)
# ──────────────────────────────────────────────────────────────────────────────────

NORMALES_MENSUELLES = {
    1:  50,   # Janvier  — petite saison sèche
    2:  80,   # Février  — transition
    3: 150,   # Mars     — début grande saison pluies
    4: 230,   # Avril    — grande saison pluies
    5: 250,   # Mai      — pic grande saison pluies
    6: 200,   # Juin     — fin grande saison pluies
    7:  30,   # Juillet  — grande saison sèche (pic)
    8:  40,   # Août     — grande saison sèche
    9: 200,   # Septembre— début petite saison pluies
    10: 280,  # Octobre  — pic petite saison pluies
    11: 200,  # Novembre — fin petite saison pluies
    12:  70,  # Décembre — petite saison sèche
}

# ET0 (évapotranspiration de référence) — zone côtière équatoriale, faible variabilité
ET0_NORMALES_MENSUELLES = {
    1: 22, 2: 23, 3: 22, 4: 19, 5: 18, 6: 17,
    7: 20, 8: 21, 9: 19, 10: 18, 11: 18, 12: 21,
}

# Humidité sol normale — corrélée à la pluviométrie bimodale
SM_SURFACE_NORMALE_KRIBI = {
    1: 0.28, 2: 0.30, 3: 0.36, 4: 0.44, 5: 0.46, 6: 0.42,
    7: 0.24, 8: 0.26, 9: 0.42, 10: 0.47, 11: 0.43, 12: 0.30,
}

# Humidité sol rootzone normale (SMAP SPL4SMGP) — légèrement plus stable que surface
SM_ROOTZONE_NORMALE_KRIBI = {
    1: 0.30, 2: 0.32, 3: 0.38, 4: 0.45, 5: 0.47, 6: 0.43,
    7: 0.26, 8: 0.28, 9: 0.43, 10: 0.48, 11: 0.44, 12: 0.32,
}

# Seuil NDVI contextuel selon la saison — végétation tropicale Kribi
NDVI_SEUIL_ALERTE = {
    1: 0.38,
    2: 0.42,
    3: 0.48,
    4: 0.52,
    5: 0.52,
    6: 0.50,
    7: 0.35,
    8: 0.35,
    9: 0.48,
    10: 0.52,
    11: 0.50,
    12: 0.40,
}

# Percentiles hebdomadaires recalibrés (pluie sur 7 jours)
PERCENTILES_HEBDO = {
    1:  {"p25": 0,  "p50": 8,  "p75": 20,  "p90": 40},
    2:  {"p25": 2,  "p50": 15, "p75": 38,  "p90": 72},
    3:  {"p25": 8,  "p50": 30, "p75": 65,  "p90": 120},
    4:  {"p25": 18, "p50": 52, "p75": 100, "p90": 175},
    5:  {"p25": 22, "p50": 58, "p75": 112, "p90": 190},
    6:  {"p25": 15, "p50": 44, "p75": 88,  "p90": 150},
    7:  {"p25": 0,  "p50": 4,  "p75": 12,  "p90": 28},
    8:  {"p25": 0,  "p50": 6,  "p75": 18,  "p90": 38},
    9:  {"p25": 18, "p50": 46, "p75": 95,  "p90": 165},
    10: {"p25": 22, "p50": 62, "p75": 118, "p90": 210},
    11: {"p25": 16, "p50": 44, "p75": 90,  "p90": 155},
    12: {"p25": 2,  "p50": 12, "p75": 30,  "p90": 62},
}

BIAIS_CORRECTION_PLUIE = {
    1: 1.00, 3: 1.08, 7: 1.15,
}

FIABILITE_HORIZON = {
    1: 0.90,
    3: 0.68,
    7: 0.45,
}

GARDE_FOU_SECHERESSE = 0.30

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

# ──────────────────────────────────────────────────────────────────────────────────
# TREND SM — FONCTION PURE (V4.7.5 — fix bug double-appel)
# ──────────────────────────────────────────────────────────────────────────────────

_sm_surface_precedente: Optional[float] = None


def mettre_a_jour_sm_reference(sm_surface: float) -> None:
    """Appeler UNE SEULE FOIS par cycle de collecte (pipeline_complet.py)."""
    global _sm_surface_precedente
    _sm_surface_precedente = sm_surface


def _get_trend_sm_pur(sm_surface_actuel: float,
                      sm_reference: Optional[float]) -> float:
    """
    Calcule la tendance de l'humidité de surface de façon PURE.
    Aucun effet de bord — sm_reference est passé explicitement.
    Retourne 0.0 si aucune valeur de référence disponible.
    """
    if sm_reference is None:
        return 0.0
    return round(sm_surface_actuel - sm_reference, 4)


def reset_historique():
    global _sm_surface_precedente
    _sm_surface_precedente = None


# ──────────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────────

def _score_vers_niveau(score: float) -> str:
    for (lo, hi), niveau in SCORE_VERS_NIVEAU.items():
        if lo <= score < hi:
            return niveau
    return "VERT"


def _confidence(score: float, seuil: float) -> float:
    dist = abs(score - seuil)
    return round(min(1.0, dist / 0.5), 3)


def _percentile_pluie(pluie_mm: float, mois: int) -> float:
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
    return 1 if mois in (12, 1, 7, 8) else 0


def _corriger_pluie_prevision(pluie_mm: float, horizon: int) -> float:
    facteur = BIAIS_CORRECTION_PLUIE.get(horizon, 1.0)
    return round(pluie_mm * facteur, 2)


def _intervalle_confiance_bootstrap(score: float, fiabilite: float,
                                     n_iter: int = 50) -> Dict[str, float]:
    sigma_base = (1.0 - fiabilite) * 0.20
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


# ──────────────────────────────────────────────────────────────────────────────────
# LECTURE ROBUSTE DES DONNÉES JSON (V4.7.1)
# ──────────────────────────────────────────────────────────────────────────────────

def _lire_donnees(data: dict) -> dict:
    """
    Extrait toutes les variables utiles depuis le JSON collecté.
    Priorité : indicateurs_risque → satellitaire.smap → meteorologie → défauts Kribi.
    V4.7.5 : trend_sm calculé UNE SEULE FOIS ici via _get_trend_sm_pur(),
             stocké dans le dict retourné — partagé par tous les horizons du cycle.
    """
    mois = datetime.date.today().month

    ind   = data.get("indicateurs_risque", {}) or {}
    sat   = data.get("satellitaire", {}) or {}
    smap  = sat.get("smap", {}).get("humidite_sol", {}) or {}
    sent  = sat.get("sentinel2", {}) or {}
    meteo = data.get("meteorologie", {}) or {}
    meteo_act = meteo.get("actuel", {}) or {}
    prev  = meteo.get("previsions_daily", {}) or {}

    pluie_7j = float(
        ind.get("pluie_cumulee_7j_mm") or
        meteo.get("pluie_cumulee_7j_mm") or 0
    )
    pluie_30j = float(
        ind.get("pluie_cumulee_30j_mm") or
        meteo.get("pluie_cumulee_30j_mm") or
        pluie_7j * 4
    )
    pluie_prev_7j = float(
        ind.get("pluie_prevue_7j_mm") or
        meteo.get("pluie_prevue_7j_mm") or 0
    )

    sm_surface_defaut = SM_SURFACE_NORMALE_KRIBI.get(mois, 0.35)
    sm_surface = float(
        ind.get("humidite_sol_sm_surface") or
        smap.get("sm_surface") or
        smap.get("humidite_surface") or
        sm_surface_defaut
    )
    sm_rootzone = float(
        ind.get("humidite_sol_sm_rootzone") or
        smap.get("sm_rootzone") or
        smap.get("humidite_rootzone") or
        sm_surface * 0.85
    )

    ndvi = float(
        ind.get("ndvi_moyen") or
        sent.get("ndvi") or
        sent.get("ndvi_moyen") or
        0.50
    )
    ndwi = float(
        ind.get("ndwi_moyen") or
        sent.get("ndwi") or
        sent.get("ndwi_moyen") or
        -0.10
    )

    temp_max = float(
        ind.get("temperature_max_c") or
        ind.get("temp_max_c") or
        meteo_act.get("temperature_2m_max") or
        29.0
    )
    temp_max_3j_raw = ind.get("temperature_max_3j_c") or ind.get("temp_max_3j_c")
    if temp_max_3j_raw:
        temp_max_3j = float(temp_max_3j_raw)
    else:
        t3 = [float(t or temp_max) for t in (prev.get("temperature_2m_max", []) or [])[:3]]
        temp_max_3j = sum(t3) / len(t3) if t3 else temp_max - 0.5

    et0_raw = (
        ind.get("et0_semaine_mm") or
        meteo.get("et0_semaine_mm") or
        meteo_act.get("et0_fao_evapotranspiration") or
        None
    )
    et0_semaine = float(et0_raw) if et0_raw is not None else float(
        ET0_NORMALES_MENSUELLES.get(mois, 19)
    )

    precip_list = prev.get("precipitation_sum", []) or []
    temp_list   = prev.get("temperature_2m_max", []) or []
    et0_list    = prev.get("et0_fao_evapotranspiration", []) or []

    trend_sm_value = _get_trend_sm_pur(round(sm_surface, 4), _sm_surface_precedente)

    return {
        "mois":          mois,
        "pluie_7j":      round(pluie_7j, 2),
        "pluie_30j":     round(pluie_30j, 2),
        "pluie_prev_7j": round(pluie_prev_7j, 2),
        "sm_surface":    round(sm_surface, 4),
        "sm_rootzone":   round(sm_rootzone, 4),
        "ndvi":          round(ndvi, 4),
        "ndwi":          round(ndwi, 4),
        "temp_max":      round(temp_max, 2),
        "temp_max_3j":   round(temp_max_3j, 2),
        "et0_semaine":   round(et0_semaine, 2),
        "precip_list":   [float(p or 0) for p in precip_list],
        "temp_list":     [float(t or temp_max) for t in temp_list],
        "et0_list":      [float(e or 0) for e in et0_list],
        "trend_sm":      trend_sm_value,
    }


# ──────────────────────────────────────────────────────────────────────────────────
# CHARGEMENT DES MODÈLES — V5.0.0 (résolution zonale)
# ──────────────────────────────────────────────────────────────────────────────────
# Ordre de résolution pour _charger_modele(nom, horizon, zone) :
#   1. models/zonal/model_{nom}_{Zone}.pkl   → modèle zonal spécifique à la zone
#   2. models/zonal/model_{nom}.pkl          → modèle zonal générique
#   3. models/model_{nom}_j{horizon}.pkl     → modèle global multi-horizon
#   4. models/model_{nom}.pkl               → modèle global fallback
#
# Le cache est keyed sur (cle, zone) pour éviter les collisions entre zones.
# ──────────────────────────────────────────────────────────────────────────────────

_cache_modeles: dict = {}


def _charger_modele(nom: str, horizon: Optional[int] = None,
                    zone: Optional[str] = None):
    """
    Charge un modèle pickle en suivant l'ordre de priorité zonal.

    Paramètres
    ----------
    nom     : risque cible — 'inondation', 'secheresse' ou 'chaleur'
    horizon : horizon de prévision (1, 3 ou 7) — None pour J0
    zone    : nom de la zone (ex: 'Kribi', 'Garoua') — None = fallback global

    Retourne (clf, seuil, features) ou (None, 0.5, FEATURES_BASE) si introuvable.
    """
    cache_key = (nom, horizon, zone)
    if cache_key in _cache_modeles:
        return _cache_modeles[cache_key]

    # Construire la liste ordonnée des chemins à tester
    chemins_a_tester = []

    # 1. Modèle zonal spécifique à la zone (models/zonal/model_{nom}_{Zone}.pkl)
    if zone:
        chemins_a_tester.append(
            os.path.join(ZONAL_MODELS_DIR, f"model_{nom}_{zone}.pkl")
        )

    # 2. Modèle zonal générique (models/zonal/model_{nom}.pkl)
    chemins_a_tester.append(
        os.path.join(ZONAL_MODELS_DIR, f"model_{nom}.pkl")
    )

    # 3. Modèle global multi-horizon (models/model_{nom}_j{horizon}.pkl)
    if horizon is not None:
        chemins_a_tester.append(
            os.path.join(MODELS_DIR, f"model_{nom}_j{horizon}.pkl")
        )

    # 4. Modèle global fallback (models/model_{nom}.pkl)
    chemins_a_tester.append(
        os.path.join(MODELS_DIR, f"model_{nom}.pkl")
    )

    for chemin in chemins_a_tester:
        if not os.path.exists(chemin):
            continue
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
            print(f"[RISK] 📦 Modèle chargé : {os.path.relpath(chemin)} "
                  f"(zone={zone}, horizon={horizon})")
            _cache_modeles[cache_key] = (clf, seuil, features)
            return clf, seuil, features
        except Exception as e:
            print(f"[RISK] ⚠️  Impossible de charger {chemin} : {e}")
            continue

    # Aucun modèle trouvé → fallback règles physiques
    return None, 0.5, FEATURES_BASE


def modeles_disponibles() -> list:
    modeles = []
    for n in ["inondation", "secheresse", "chaleur"]:
        zonal_exists = (
            any(
                os.path.exists(os.path.join(ZONAL_MODELS_DIR, f"model_{n}_{z}.pkl"))
                for z in ["Kribi", "Garoua", "Maroua", "Bafoussam",
                           "Ebolowa", "Kumba", "Ngaoundere", "Yaounde_peri"]
            ) or
            os.path.exists(os.path.join(ZONAL_MODELS_DIR, f"model_{n}.pkl"))
        )
        global_exists = os.path.exists(os.path.join(MODELS_DIR, f"model_{n}.pkl"))
        if zonal_exists or global_exists:
            modeles.append(n)
    return modeles


# ──────────────────────────────────────────────────────────────────────────────────
# FALLBACK — Règles physiques (V4.7.4 — NDVI contextuel + sm_rootzone normale mensuelle)
# ──────────────────────────────────────────────────────────────────────────────────

def _risque_inondation_physique(pluie_7j, pluie_prev, sm_surface, ndwi, mois):
    normale = NORMALES_MENSUELLES.get(mois, 120)
    normale_7j = normale / 4.3
    score = 0.0
    score += min(0.35, max(0, (pluie_7j   / max(1.0, normale_7j) - 1.0) * 0.30))
    score += min(0.25, max(0, (pluie_prev / max(1.0, normale_7j) - 1.0) * 0.20))
    score += min(0.25, max(0, (sm_surface - 0.42) * 1.5))
    score += min(0.15, max(0, (ndwi - 0.30) * 0.5))
    return min(1.0, score)


def _risque_secheresse_physique(pluie_30j, ndvi, sm_rootzone, mois, et0_semaine=0.0):
    """
    V4.7.4 — NDVI contextuel + sm_rootzone vs normale mensuelle SMAP.
    """
    normale_30j       = NORMALES_MENSUELLES.get(mois, 120)
    et0_normale       = ET0_NORMALES_MENSUELLES.get(mois, 19)
    ndvi_seuil        = NDVI_SEUIL_ALERTE.get(mois, 0.45)
    sm_rootzone_seuil = SM_ROOTZONE_NORMALE_KRIBI.get(mois, 0.35) - 0.06

    score = 0.0
    deficit = max(0, (normale_30j - pluie_30j) / max(1.0, normale_30j))
    score += min(0.25, deficit * 0.40)
    score += min(0.20, max(0, (ndvi_seuil - ndvi) * 0.80))
    score += min(0.20, max(0, (sm_rootzone_seuil - sm_rootzone) * 2.5))
    score += min(0.15, max(0, (et0_semaine - et0_normale) / max(1.0, et0_normale) * 0.15))
    return min(1.0, score)


def _risque_chaleur_physique(temp_max, temp_max_3j):
    score = 0.0
    score += min(0.60, max(0, (temp_max    - 33.0) / 5.0 * 0.50))
    score += min(0.40, max(0, (temp_max_3j - 33.0) / 5.0 * 0.40))
    return min(1.0, score)


# ──────────────────────────────────────────────────────────────────────────────────
# CONSTRUCTION DES FEATURES PAR HORIZON (V4.7.5)
# ──────────────────────────────────────────────────────────────────────────────────

def _features_j0(data: dict) -> dict:
    d    = _lire_donnees(data)
    mois = d["mois"]

    normale      = NORMALES_MENSUELLES.get(mois, 120)
    normale_7j   = normale / 4.3
    sin_mois     = round(math.sin(2 * math.pi * mois / 12), 4)
    cos_mois     = round(math.cos(2 * math.pi * mois / 12), 4)
    anomalie     = round((d["pluie_7j"] - normale_7j) / max(1.0, normale_7j), 4)
    ratio        = round(d["pluie_30j"] / max(1.0, d["pluie_7j"] * (30 / 7)), 4) if d["pluie_7j"] > 0 else 1.0
    ratio        = min(ratio, 5.0)
    trend_sm     = d["trend_sm"]
    sm_def       = round(max(0.0, (SM_ROOTZONE_NORMALE_KRIBI.get(mois, 0.35) - d["sm_rootzone"]) / max(0.01, SM_ROOTZONE_NORMALE_KRIBI.get(mois, 0.35))), 4)
    ratio_et0    = round(d["et0_semaine"] / max(1.0, d["pluie_7j"]), 4)
    ratio_et0    = min(ratio_et0, 10.0)

    return {
        "mois":            mois,
        "pluie_7j":        d["pluie_7j"],
        "pluie_30j":       d["pluie_30j"],
        "pluie_prev_7j":   d["pluie_prev_7j"],
        "temp_max":        d["temp_max"],
        "temp_max_3j":     d["temp_max_3j"],
        "sm_surface":      d["sm_surface"],
        "sm_rootzone":     d["sm_rootzone"],
        "ndvi":            d["ndvi"],
        "ndwi":            d["ndwi"],
        "et0_semaine":     d["et0_semaine"],
        "sin_mois":        sin_mois,
        "cos_mois":        cos_mois,
        "anomalie_pluie":  anomalie,
        "ratio_30j_7j":    ratio,
        "trend_sm":        trend_sm,
        "sm_deficit":      sm_def,
        "ratio_et0_pluie": ratio_et0,
        "pluie_prev_1j":   round(_corriger_pluie_prevision(
            sum(d["precip_list"][:1]), 1), 2),
    }


def _features_horizon(data: dict, horizon: int) -> dict:
    d    = _lire_donnees(data)
    mois = d["mois"]

    sin_mois = round(math.sin(2 * math.pi * mois / 12), 4)
    cos_mois = round(math.cos(2 * math.pi * mois / 12), 4)
    sm_def   = round(max(0.0, (SM_ROOTZONE_NORMALE_KRIBI.get(mois, 0.35) - d["sm_rootzone"]) / max(0.01, SM_ROOTZONE_NORMALE_KRIBI.get(mois, 0.35))), 4)

    pluie_prev_brute = sum(d["precip_list"][:horizon])
    pluie_prev       = _corriger_pluie_prevision(pluie_prev_brute, horizon)

    t_hor        = [t for t in d["temp_list"][:horizon]]
    temp_max_hor = max(t_hor, default=d["temp_max"])
    t3           = d["temp_list"][:3]
    temp_max_3j  = sum(t3) / len(t3) if t3 else d["temp_max"]

    et0_hor = sum(d["et0_list"][:horizon]) if d["et0_list"] else (
        ET0_NORMALES_MENSUELLES.get(mois, 19) * (horizon / 7)
    )

    normale         = NORMALES_MENSUELLES.get(mois, 120)
    normale_horizon = normale * (horizon / 30.0)
    anomalie_prev   = round((pluie_prev - normale_horizon) / max(1.0, normale_horizon), 4)
    percentile      = _percentile_pluie(pluie_prev, mois)
    ratio_30j_prev  = round(d["pluie_30j"] / max(1.0, pluie_prev * (30 / horizon)), 4)
    ratio_30j_prev  = min(ratio_30j_prev, 5.0)
    ratio_et0_prev  = round(et0_hor / max(1.0, pluie_prev), 4)
    ratio_et0_prev  = min(ratio_et0_prev, 10.0)
    trend_sm        = d["trend_sm"] if horizon == 1 else 0.0

    p1 = _corriger_pluie_prevision(sum(d["precip_list"][:1]), 1)
    p3 = _corriger_pluie_prevision(sum(d["precip_list"][:3]), 3)
    p7 = _corriger_pluie_prevision(sum(d["precip_list"][:7]), 7)

    normale_1j = normale / 30.0
    normale_3j = normale * 3 / 30.0
    anom_1j = round((p1 - normale_1j) / max(1.0, normale_1j), 4)
    anom_3j = round((p3 - normale_3j) / max(1.0, normale_3j), 4)

    et0_3j = sum(d["et0_list"][:3]) if d["et0_list"] else ET0_NORMALES_MENSUELLES.get(mois, 19) * (3 / 7)
    et0_7j = sum(d["et0_list"][:7]) if d["et0_list"] else ET0_NORMALES_MENSUELLES.get(mois, 19)

    ratio_et0_3j = round(et0_3j / max(1.0, p3), 4)
    ratio_et0_3j = min(ratio_et0_3j, 10.0)
    ratio_et0_7j = round(et0_7j / max(1.0, p7), 4)
    ratio_et0_7j = min(ratio_et0_7j, 10.0)

    ratio_30j_3j = round(d["pluie_30j"] / max(1.0, p3 * (30 / 3)), 4)
    ratio_30j_3j = min(ratio_30j_3j, 5.0)

    return {
        "mois":               mois,
        "sin_mois":           sin_mois,
        "cos_mois":           cos_mois,
        "pluie_30j":          d["pluie_30j"],
        "sm_surface":         d["sm_surface"],
        "sm_rootzone":        d["sm_rootzone"],
        "ndvi":               d["ndvi"],
        "ndwi":               d["ndwi"],
        "sm_deficit":         sm_def,
        "trend_sm":           trend_sm,
        "saison_seche":       _saison_seche(mois),
        "percentile_pluie":   round(percentile, 3),
        "temp_max":           d["temp_max"],
        "temp_max_3j":        round(temp_max_3j, 2),
        "pluie_prev_1j":      round(p1, 2),
        "pluie_prev_3j":      round(p3, 2),
        "pluie_prev_7j":      round(p7, 2),
        "anomalie_pluie_1j":  anom_1j,
        "anomalie_pluie_3j":  anom_3j,
        "anomalie_pluie_7j":  round(anomalie_prev, 4),
        "anomalie_pluie":     round(anomalie_prev, 4),
        "et0_semaine":        round(et0_hor, 2),
        "et0_prev_3j":        round(et0_3j, 2),
        "et0_prev_7j":        round(et0_7j, 2),
        "ratio_30j_prev3j":   ratio_30j_3j,
        "ratio_30j_7j":       ratio_30j_prev,
        "ratio_et0_pluie":    ratio_et0_prev,
        "ratio_et0_pluie_3j": ratio_et0_3j,
        "ratio_et0_pluie_7j": ratio_et0_7j,
        "pluie_7j":           d["pluie_7j"],
    }


_FEATURES_PAR_HORIZON = {
    1: FEATURES_J1,
    3: FEATURES_J3,
    7: FEATURES_J7,
}


def _get_features_pour_horizon(horizon: Optional[int]) -> list:
    if horizon is None:
        return FEATURES_ORDER
    return _FEATURES_PAR_HORIZON.get(horizon, FEATURES_ORDER)


# ──────────────────────────────────────────────────────────────────────────────────
# GARDE-FOU DE COHÉRENCE PHYSIQUE (V4.7.4)
# ──────────────────────────────────────────────────────────────────────────────────

def _score_physique_secheresse(feats: dict) -> float:
    return _risque_secheresse_physique(
        feats.get("pluie_30j", 0),
        feats.get("ndvi", 0.50),
        feats.get("sm_rootzone", 0.30),
        feats.get("mois", 6),
        feats.get("et0_semaine", ET0_NORMALES_MENSUELLES.get(feats.get("mois", 6), 19)),
    )


def _appliquer_garde_fou(nom: str, score_ml: float, feats: dict) -> tuple:
    if nom != "secheresse":
        return score_ml, "modele_ml", ""

    score_physique = _score_physique_secheresse(feats)
    ecart = score_ml - score_physique

    if ecart > GARDE_FOU_SECHERESSE:
        print(f"[RISK-DIAG] Sécheresse : ML={score_ml:.3f} >> physique={score_physique:.3f} "
              f"(écart {ecart:.2f} > {GARDE_FOU_SECHERESSE}) → garde-fou activé, fallback physique")
        return score_physique, "regles_physiques_garde_fou", (
            f"Garde-fou activé : ML ({score_ml:.2f}) incohérent vs physique ({score_physique:.2f}). "
            f"Score physique V4.7.4 utilisé."
        )

    print(f"[RISK-DIAG] Sécheresse : ML={score_ml:.3f}, physique={score_physique:.3f} "
          f"(écart {ecart:.2f} ≤ {GARDE_FOU_SECHERESSE}) → ML accepté")
    return score_ml, "modele_ml", ""


# ──────────────────────────────────────────────────────────────────────────────────
# INFÉRENCE PRINCIPALE — V5.0.0 (propagation zone)
# ──────────────────────────────────────────────────────────────────────────────────

def predire_risques(data: dict, use_previsions: bool = False,
                    horizon_jours: int = 7,
                    zone: Optional[str] = None) -> dict:
    """
    Prédit les risques pour un horizon donné.

    Paramètre `zone` (V5.0.0) : nom de la zone (ex: 'Kribi', 'Garoua').
    Utilisé pour sélectionner le modèle zonal depuis models/zonal/.
    Si None, résolution globale (models/) uniquement.
    """
    if use_previsions:
        feats = _features_horizon(data, horizon_jours)
        fiabilite = FIABILITE_HORIZON.get(horizon_jours, 0.50)
    else:
        feats = _features_j0(data)
        fiabilite = 1.0
        horizon_jours = 0

    resultats = {}
    methode_utilisee = {}

    for nom in ["inondation", "secheresse", "chaleur"]:
        hor_key = horizon_jours if horizon_jours > 0 else None
        # V5.0.0 : passer `zone` pour résolution zonale
        clf, seuil, features_modele = _charger_modele(nom, horizon=hor_key, zone=zone)

        score_brut    = None
        garde_fou_msg = ""

        if clf is not None:
            try:
                feats_array = [float(feats.get(k, 0.0) or 0.0) for k in features_modele]
                import numpy as np
                X = np.array([feats_array])
                score_ml_brut = float(clf.predict_proba(X)[0][1])

                score_brut_valide, methode_valide, garde_fou_msg = _appliquer_garde_fou(
                    nom, score_ml_brut, feats
                )

                if methode_valide == "modele_ml":
                    score_brut = score_brut_valide
                    methode_utilisee[nom] = (
                        f"modele_zonal_v5_j{horizon_jours}" if horizon_jours > 0
                        else "modele_zonal_v5_j0"
                    ) if zone else (
                        f"modele_ml_v4.7_j{horizon_jours}" if horizon_jours > 0
                        else "modele_ml_v4.7_j0"
                    )
                else:
                    score_brut = score_brut_valide
                    methode_utilisee[nom] = methode_valide

            except Exception as e:
                print(f"[RISK] Erreur modèle {nom} h={horizon_jours} zone={zone} : {e} → fallback règles physiques")
                score_brut = None

        if score_brut is None:
            methode_utilisee[nom] = "regles_physiques"
            seuil = 0.5
            if nom == "inondation":
                score_brut = _risque_inondation_physique(
                    feats.get("pluie_7j", 0),
                    feats.get("pluie_prev_7j", feats.get("pluie_prev_3j", feats.get("pluie_prev_1j", 0))),
                    feats.get("sm_surface", 0.35), feats.get("ndwi", -0.10), feats.get("mois", 6))
            elif nom == "secheresse":
                score_brut = _score_physique_secheresse(feats)
            else:
                score_brut = _risque_chaleur_physique(
                    feats.get("temp_max", 29.0), feats.get("temp_max_3j", 28.5))

        if use_previsions:
            score_ajuste = round(score_brut * fiabilite, 4)
            avertissement = (
                f"Prévision J+{horizon_jours} — fiabilité {int(fiabilite * 100)}%. "
                f"Score brut : {round(score_brut, 3)} → ajusté : {score_ajuste}"
            )
        else:
            score_ajuste = round(score_brut, 4)
            avertissement = "Données observées — fiabilité maximale."

        if garde_fou_msg:
            avertissement = garde_fou_msg + " | " + avertissement

        ic = _intervalle_confiance_bootstrap(score_ajuste, fiabilite)
        niveau = _score_vers_niveau(score_ajuste)

        resultats[nom] = {
            "score":         score_ajuste,
            "score_brut":    round(score_brut, 4),
            "niveau":        niveau,
            "confiance":     _confidence(score_ajuste, seuil),
            "fiabilite":     fiabilite,
            "intervalle":    ic,
            "description":   DESCRIPTIONS[nom][niveau],
            "methode":       methode_utilisee[nom],
            "avertissement": avertissement,
        }

    niveaux_ordre = ["VERT", "JAUNE", "ORANGE", "ROUGE"]
    niveau_global = max(
        (r["niveau"] for r in resultats.values()),
        key=lambda n: niveaux_ordre.index(n)
    )

    return {
        "scores":             {k: v["score"]       for k, v in resultats.items()},
        "scores_bruts":       {k: v["score_brut"]  for k, v in resultats.items()},
        "niveaux":            {k: v["niveau"]      for k, v in resultats.items()},
        "confiances":         {k: v["confiance"]   for k, v in resultats.items()},
        "fiabilite":          fiabilite,
        "intervalles":        {k: v["intervalle"]  for k, v in resultats.items()},
        "descriptions":       {k: v["description"] for k, v in resultats.items()},
        "avertissements":     {k: v["avertissement"] for k, v in resultats.items()},
        "niveau_global":      niveau_global,
        "methode_globale":    (
            f"modele_zonal_v5 (zone={zone})" if zone and any(
                "modele_zonal" in v for v in methode_utilisee.values()
            ) else (
                "modele_ml_v4.7" if any(
                    "modele_ml" in v for v in methode_utilisee.values()
                ) else "regles_physiques"
            )
        ),
        "features_utilisees": feats,
        "modeles_charges":    modeles_disponibles(),
        "zone":               zone,
    }


def evaluer_previsions(data: dict, zone: Optional[str] = None) -> dict:
    """
    Évalue les prévisions de risque pour les 4 horizons (J0, J+1, J+3, J+7).

    Paramètre `zone` (V5.0.0) : propagé à predire_risques() pour la résolution
    zonale des modèles depuis models/zonal/.
    """
    risque_j0 = predire_risques(data, use_previsions=False, zone=zone)
    risque_j1 = predire_risques(data, use_previsions=True, horizon_jours=1, zone=zone)
    risque_j3 = predire_risques(data, use_previsions=True, horizon_jours=3, zone=zone)
    risque_j7 = predire_risques(data, use_previsions=True, horizon_jours=7, zone=zone)

    def _pack(r: dict, label: str) -> dict:
        return {
            "horizon_label":  label,
            "niveau_global":  r["niveau_global"],
            "niveaux":        r["niveaux"],
            "scores":         r["scores"],
            "scores_bruts":   r["scores_bruts"],
            "confiances":     r["confiances"],
            "fiabilite":      r["fiabilite"],
            "intervalles":    r["intervalles"],
            "descriptions":   r["descriptions"],
            "avertissements": r["avertissements"],
            "methode":        r["methode_globale"],
        }

    niveaux_ordre = ["VERT", "JAUNE", "ORANGE", "ROUGE"]

    def _tendance(n_from: str, n_to: str) -> str:
        idx_from = niveaux_ordre.index(n_from)
        idx_to   = niveaux_ordre.index(n_to)
        if idx_to > idx_from:  return "dégradation"
        if idx_to < idx_from:  return "amélioration"
        return "stable"

    return {
        "actuel":   _pack(risque_j0, "J0 — Observations"),
        "prevu_1j": _pack(risque_j1, "J+1 — Prévision 24h"),
        "prevu_3j": _pack(risque_j3, "J+3 — Prévision 72h"),
        "prevu_7j": _pack(risque_j7, "J+7 — Prévision 7 jours"),
        "tendance": {
            "j0_vers_j1": _tendance(risque_j0["niveau_global"], risque_j1["niveau_global"]),
            "j1_vers_j3": _tendance(risque_j1["niveau_global"], risque_j3["niveau_global"]),
            "j3_vers_j7": _tendance(risque_j3["niveau_global"], risque_j7["niveau_global"]),
        },
        "resume": {
            "niveau_max_horizon": max(
                [risque_j0["niveau_global"], risque_j1["niveau_global"],
                 risque_j3["niveau_global"], risque_j7["niveau_global"]],
                key=lambda n: niveaux_ordre.index(n)
            ),
            "fiabilite_j1": FIABILITE_HORIZON[1],
            "fiabilite_j3": FIABILITE_HORIZON[3],
            "fiabilite_j7": FIABILITE_HORIZON[7],
            "note": (
                "V5.0.0 — Modèles zonaux actifs (models/zonal/). "
                "trend_sm pur (fix bug double-appel). "
                "Garde-fou de cohérence physique activé pour sécheresse. "
                "NDVI seuil contextuel selon saison. sm_rootzone vs normale mensuelle SMAP."
            ),
        },
        "zone": zone,
    }


# ──────────────────────────────────────────────────────────────────────────────────
# SAUVEGARDE DU RAPPORT JSON (V4.7.5)
# ──────────────────────────────────────────────────────────────────────────────────

def sauvegarder_rapport_json(data_source: dict, previsions_risque: dict) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    today    = datetime.date.today().isoformat()
    chemin   = os.path.join(REPORTS_DIR, f"rapport_kribi_{today}.json")

    ind = data_source.get("indicateurs_risque", {})
    niveau_global = previsions_risque.get("actuel", {}).get("niveau_global", "VERT")

    sortie = {
        "date":            today,
        "zone":            "Kribi",
        "modele":          "risk_model_v5.0.0",
        "rapport_texte":   (
            f"Rapport automatisé SAMCAM V5.0.0 — {today}\n"
            f"Niveau global : {niveau_global}\n"
            f"Inondation : {previsions_risque.get('actuel', {}).get('niveaux', {}).get('inondation', '?')}\n"
            f"Sécheresse : {previsions_risque.get('actuel', {}).get('niveaux', {}).get('secheresse', '?')}\n"
            f"Chaleur    : {previsions_risque.get('actuel', {}).get('niveaux', {}).get('chaleur', '?')}"
        ),
        "niveau_alerte":   niveau_global,
        "risque_actuel":   previsions_risque.get("actuel",   {}),
        "risque_prevu_1j": previsions_risque.get("prevu_1j", {}),
        "risque_prevu_3j": previsions_risque.get("prevu_3j", {}),
        "risque_prevu_7j": previsions_risque.get("prevu_7j", {}),
        "tendance":        previsions_risque.get("tendance", {}),
        "resume":          previsions_risque.get("resume",   {}),
        "methode_risque":  previsions_risque.get("actuel", {}).get("methode", "?"),
        "indicateurs":     ind,
        "meteorologie":    data_source.get("meteorologie", {}),
        "satellitaire":    data_source.get("satellitaire", {}),
        "meta":            data_source.get("meta", {}),
    }

    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(sortie, f, ensure_ascii=False, indent=2)

    print(f"[RISK] 💾 Rapport sauvegardé : {chemin}")
    print(f"[RISK]    Niveau global : {niveau_global}")
    return chemin


# ──────────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE (standalone)
# ──────────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import glob

    fichiers = sorted(glob.glob(os.path.join(DATA_DIR, "kribi_*.json")))
    if not fichiers:
        data_source = {
            "indicateurs_risque": {
                "pluie_cumulee_7j_mm":       21.8,
                "pluie_prevue_7j_mm":        10.1,
                "pluie_cumulee_30j_mm":      88.0,
                "ndvi_moyen":                0.1971,
                "ndwi_moyen":               -0.111,
                "humidite_sol_sm_surface":   0.33093,
                "humidite_sol_sm_rootzone":  0.28,
                "temperature_max_c":         29.5,
                "temperature_max_3j_c":      29.2,
            },
            "meteorologie": {
                "et0_semaine_mm": 19.5,
                "previsions_daily": {
                    "precipitation_sum":          [2.1, 0.5, 1.8, 3.2, 0.0, 1.5, 0.9],
                    "temperature_2m_max":         [29, 30, 29, 28, 30, 30, 31],
                    "et0_fao_evapotranspiration": [2.7, 2.8, 2.6, 2.9, 3.0, 2.8, 2.9],
                },
            },
        }
        print("[RISK] ⚠️  Aucun fichier data/kribi_*.json — utilisation des données de test")
    else:
        fichier = max(fichiers, key=os.path.getmtime)
        print(f"[RISK] 📄 Chargement : {os.path.basename(fichier)}")
        with open(fichier, "r", encoding="utf-8") as f:
            data_source = json.load(f)

    # V5 : passer zone="Kribi" pour utiliser le modèle zonal
    previsions_risque = evaluer_previsions(data_source, zone="Kribi")
    print(json.dumps(previsions_risque, ensure_ascii=False, indent=2))

    print("\n=== RÉSUMÉ TENDANCE ===")
    for k, v in previsions_risque["tendance"].items():
        print(f"  {k}: {v}")
    print(f"\n  Niveau max sur tous horizons : {previsions_risque['resume']['niveau_max_horizon']}")
    print(f"  Fiabilités : J+1={previsions_risque['resume']['fiabilite_j1']} | "
          f"J+3={previsions_risque['resume']['fiabilite_j3']} | "
          f"J+7={previsions_risque['resume']['fiabilite_j7']}")

    sauvegarder_rapport_json(data_source, previsions_risque)
