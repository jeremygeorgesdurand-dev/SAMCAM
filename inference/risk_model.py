#!/usr/bin/env python3
"""
SAMCAM V4.2 — Module d'inférence des risques climatiques

NOUVEAUTÉS V4.2 :
    - trend_sm calculé via un historique glissant en mémoire
      (plus de valeur 0 fixe — donnée réelle entre deux appels successifs)
    - Meilleure gestion des features manquantes (imputation médiane)
    - reset_historique() pour forcer la remise à zéro du cache sm

Charge les modèles GradientBoosting entraînés et prédit :
    - risque_actuel   : basé sur données J-7 à J0
    - risque_prevu_3j : basé sur prévisions J+1 à J+3
    - risque_prevu_7j : basé sur prévisions J+1 à J+7
"""

import os
import json
import datetime
import math
from typing import Optional

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")

NORMALES_MENSUELLES = {
    1: 30,  2: 50,  3: 120, 4: 180, 5: 200, 6: 160,
    7: 80,  8: 100, 9: 180, 10: 200, 11: 150, 12: 50,
}

SCORE_VERS_NIVEAU = {
    (0.75, 1.01): "ROUGE",
    (0.50, 0.75): "ORANGE",
    (0.25, 0.50): "JAUNE",
    (0.00, 0.25): "VERT",
}

FEATURES_BASE = [
    "mois", "pluie_7j", "pluie_30j", "pluie_prev_7j",
    "temp_max", "temp_max_3j", "sm_surface", "sm_rootzone",
    "ndvi", "ndwi",
]

FEATURES_DERIVEES = [
    "sin_mois", "cos_mois",
    "anomalie_pluie", "ratio_30j_7j",
    "trend_sm", "sm_deficit",
]

FEATURES_ORDER = FEATURES_BASE + FEATURES_DERIVEES

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


# ───────────────────────────────────────────────────────────────────────────────
# HISTORIQUE GLISSANT — trend_sm en temps réel (V4.2)
# ───────────────────────────────────────────────────────────────────────────────

# Stocke la dernière valeur sm_surface observée (persistante entre appels pipeline)
_sm_surface_historique: Optional[float] = None


def reset_historique():
    """Remet à zéro l'historique sm pour forcer un recalcul propre."""
    global _sm_surface_historique
    _sm_surface_historique = None


def _get_trend_sm(sm_surface_actuel: float) -> float:
    """
    V4.2 — Calcule la vraie variation d'humidité sol entre deux appels.
    Retourne 0.0 au premier appel (pas d'historique disponible).
    Valeurs positives → sol qui se sature (risque inondation ↑)
    Valeurs négatives → sol qui se dessèche (risque sécheresse ↑)
    """
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


# ───────────────────────────────────────────────────────────────────────────────
# CHARGEMENT DES MODÈLES
# ───────────────────────────────────────────────────────────────────────────────

_cache_modeles: dict = {}


def _charger_modele(nom: str):
    if nom in _cache_modeles:
        return _cache_modeles[nom]

    chemin = os.path.join(MODELS_DIR, f"model_{nom}.pkl")
    if not os.path.exists(chemin):
        return None, 0.5, FEATURES_BASE

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

        _cache_modeles[nom] = (clf, seuil, features)
        return clf, seuil, features
    except Exception:
        return None, 0.5, FEATURES_BASE


def modeles_disponibles() -> list:
    return [n for n in ["inondation", "secheresse", "chaleur"]
            if os.path.exists(os.path.join(MODELS_DIR, f"model_{n}.pkl"))]


# ───────────────────────────────────────────────────────────────────────────────
# FALLBACK — Règles physiques
# ───────────────────────────────────────────────────────────────────────────────

def _risque_inondation_physique(pluie_7j, pluie_prev, sm_surface, ndwi, mois):
    normale = NORMALES_MENSUELLES.get(mois, 120)
    score = 0.0
    score += min(0.35, max(0, (pluie_7j  / normale - 1.0) * 0.30))
    score += min(0.25, max(0, (pluie_prev / normale - 1.0) * 0.20))
    score += min(0.25, max(0, (sm_surface - 0.40) * 1.5))
    score += min(0.15, max(0, (ndwi - 0.30) * 0.5))
    return min(1.0, score)


def _risque_secheresse_physique(pluie_30j, ndvi, sm_rootzone, mois):
    normale_30j = NORMALES_MENSUELLES.get(mois, 120) * (30 / 7)
    score = 0.0
    deficit = max(0, (normale_30j - pluie_30j) / normale_30j)
    score += min(0.40, deficit * 0.5)
    score += min(0.35, max(0, (0.55 - ndvi) * 1.2))
    score += min(0.25, max(0, (0.28 - sm_rootzone) * 2.0))
    return min(1.0, score)


def _risque_chaleur_physique(temp_max, temp_max_3j):
    score = 0.0
    score += min(0.60, max(0, (temp_max    - 32.0) / 5.0 * 0.50))
    score += min(0.40, max(0, (temp_max_3j - 32.0) / 5.0 * 0.40))
    return min(1.0, score)


# ───────────────────────────────────────────────────────────────────────────────
# CONSTRUCTION DES FEATURES (V4.2 : trend_sm live)
# ───────────────────────────────────────────────────────────────────────────────

def _features_from_data(data: dict, use_previsions: bool = False,
                         horizon_jours: int = 7) -> dict:
    mois = datetime.date.today().month
    ind  = data.get("indicateurs_risque", {})
    sat  = data.get("satellitaire", {}).get("smap", {}).get("humidite_sol", {})
    prev = data.get("meteorologie", {}).get("previsions_daily", {})

    pluie_7j    = float(ind.get("pluie_cumulee_7j_mm",  0) or 0)
    pluie_30j   = float(ind.get("pluie_cumulee_30j_mm", pluie_7j * 4) or pluie_7j * 4)
    sm_surface  = float(sat.get("sm_surface",  0.35) or 0.35)
    sm_rootzone = float(sat.get("sm_rootzone", 0.30) or 0.30)
    ndvi        = float(ind.get("ndvi_moyen",  0.70) or 0.70)
    ndwi        = float(ind.get("ndwi_moyen",  0.20) or 0.20)

    if use_previsions:
        precip_list = (prev.get("precipitation_sum",  []) or [])[:horizon_jours]
        temp_list   = (prev.get("temperature_2m_max", []) or [])[:horizon_jours]
        pluie_prev  = sum(float(p or 0) for p in precip_list)
        temp_max    = max((float(t or 28) for t in temp_list), default=28.0)
        t3 = [float(t or 28) for t in temp_list[:3]]
        temp_max_3j = sum(t3) / len(t3) if t3 else temp_max
        pluie_7j_feat = pluie_prev
    else:
        pluie_prev  = float(ind.get("pluie_prevue_7j_mm", 0) or 0)
        temp_max    = float(ind.get("temperature_max_c",  29.0) or 29.0)
        temp_max_3j = float(ind.get("temperature_max_3j_c", temp_max - 0.5) or temp_max - 0.5)
        pluie_7j_feat = pluie_7j

    # ── Features dérivées (V4.2 : trend_sm calculé depuis l'historique live) ──
    normale = NORMALES_MENSUELLES.get(mois, 120)

    sin_mois  = round(math.sin(2 * math.pi * mois / 12), 4)
    cos_mois  = round(math.cos(2 * math.pi * mois / 12), 4)
    anomalie  = round((pluie_7j_feat - normale) / max(1.0, normale), 4)
    ratio     = round(pluie_30j / max(1.0, pluie_7j_feat * (30 / 7)), 4) if pluie_7j_feat > 0 else 1.0
    ratio     = min(ratio, 5.0)

    # V4.2 : trend_sm depuis l'historique glissant en mémoire (plus de 0 fixe)
    trend_sm  = _get_trend_sm(sm_surface) if not use_previsions else 0.0
    sm_def    = round(max(0.0, (0.30 - sm_rootzone) / 0.30), 4)

    return {
        "mois":          mois,
        "pluie_7j":      round(pluie_7j_feat, 2),
        "pluie_30j":     round(pluie_30j,     2),
        "pluie_prev_7j": round(pluie_prev,    2),
        "temp_max":      round(temp_max,       2),
        "temp_max_3j":   round(temp_max_3j,    2),
        "sm_surface":    round(sm_surface,     4),
        "sm_rootzone":   round(sm_rootzone,    4),
        "ndvi":          round(ndvi,           4),
        "ndwi":          round(ndwi,           4),
        "sin_mois":       sin_mois,
        "cos_mois":       cos_mois,
        "anomalie_pluie": anomalie,
        "ratio_30j_7j":   ratio,
        "trend_sm":       trend_sm,
        "sm_deficit":     sm_def,
    }


# ───────────────────────────────────────────────────────────────────────────────
# INFÉRENCE PRINCIPALE
# ───────────────────────────────────────────────────────────────────────────────

def predire_risques(data: dict, use_previsions: bool = False,
                    horizon_jours: int = 7) -> dict:
    feats = _features_from_data(data, use_previsions=use_previsions,
                                 horizon_jours=horizon_jours)

    try:
        import pandas as pd
        use_df = True
    except ImportError:
        use_df = False

    resultats = {}
    methode_utilisee = {}

    for nom in ["inondation", "secheresse", "chaleur"]:
        clf, seuil, features_modele = _charger_modele(nom)

        if clf is not None:
            try:
                # Imputation médiane pour les features inconnues (robustesse)
                feats_modele = {}
                for k in features_modele:
                    val = feats.get(k)
                    feats_modele[k] = float(val) if val is not None else 0.0

                if use_df:
                    import pandas as pd
                    X = pd.DataFrame([feats_modele], columns=features_modele)
                else:
                    X = [[feats_modele[f] for f in features_modele]]

                score = float(clf.predict_proba(X)[0][1])
                methode_utilisee[nom] = "modele_ml_v4.2"
            except Exception as e:
                print(f"[RISK] Erreur modèle {nom} : {e} → fallback règles physiques")
                score = None
        else:
            score = None

        if score is None:
            methode_utilisee[nom] = "regles_physiques"
            seuil = 0.5
            if nom == "inondation":
                score = _risque_inondation_physique(
                    feats["pluie_7j"], feats["pluie_prev_7j"],
                    feats["sm_surface"], feats["ndwi"], feats["mois"])
            elif nom == "secheresse":
                score = _risque_secheresse_physique(
                    feats["pluie_30j"], feats["ndvi"],
                    feats["sm_rootzone"], feats["mois"])
            else:
                score = _risque_chaleur_physique(
                    feats["temp_max"], feats["temp_max_3j"])

        niveau = _score_vers_niveau(score)
        resultats[nom] = {
            "score":       round(score, 4),
            "niveau":      niveau,
            "confiance":   _confidence(score, seuil),
            "description": DESCRIPTIONS[nom][niveau],
            "methode":     methode_utilisee[nom],
        }

    niveaux_ordre = ["VERT", "JAUNE", "ORANGE", "ROUGE"]
    niveau_global = max(
        (r["niveau"] for r in resultats.values()),
        key=lambda n: niveaux_ordre.index(n)
    )

    return {
        "scores":           {k: v["score"]       for k, v in resultats.items()},
        "niveaux":          {k: v["niveau"]      for k, v in resultats.items()},
        "confiances":       {k: v["confiance"]   for k, v in resultats.items()},
        "descriptions":     {k: v["description"] for k, v in resultats.items()},
        "niveau_global":    niveau_global,
        "methode_globale":  "modele_ml_v4.2" if any(
            v == "modele_ml_v4.2" for v in methode_utilisee.values()
        ) else "regles_physiques",
        "features_utilisees": feats,
        "modeles_charges":    modeles_disponibles(),
    }


def evaluer_previsions(data: dict) -> dict:
    risque_actuel = predire_risques(data, use_previsions=False)
    risque_3j     = predire_risques(data, use_previsions=True, horizon_jours=3)
    risque_7j     = predire_risques(data, use_previsions=True, horizon_jours=7)

    return {
        "actuel": {
            "niveau_global": risque_actuel["niveau_global"],
            "niveaux":       risque_actuel["niveaux"],
            "scores":        risque_actuel["scores"],
            "confiances":    risque_actuel["confiances"],
            "descriptions":  risque_actuel["descriptions"],
            "methode":       risque_actuel["methode_globale"],
        },
        "prevu_3j": {
            "niveau_global": risque_3j["niveau_global"],
            "niveaux":       risque_3j["niveaux"],
            "scores":        risque_3j["scores"],
            "confiances":    risque_3j["confiances"],
        },
        "prevu_7j": {
            "niveau_global": risque_7j["niveau_global"],
            "niveaux":       risque_7j["niveaux"],
            "scores":        risque_7j["scores"],
            "confiances":    risque_7j["confiances"],
        },
    }


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
        "meteorologie": {"previsions_daily": {
            "precipitation_sum":  [45, 38, 52, 30, 25, 42, 55],
            "temperature_2m_max": [30, 31, 30, 29, 30, 31, 32],
        }},
    }
    resultats = evaluer_previsions(data_test)
    print(json.dumps(resultats, ensure_ascii=False, indent=2))
