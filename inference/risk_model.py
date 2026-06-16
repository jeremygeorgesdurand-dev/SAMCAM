#!/usr/bin/env python3
"""
SAMCAM V4 — Module d'inférence des risques climatiques

Charge les modèles RandomForest entraînés et prédit :
    - risque_actuel    : basé sur données J-7 à J0
    - risque_prevu_3j  : basé sur prévisions J+1 à J+3
    - risque_prevu_7j  : basé sur prévisions J+1 à J+7

Utilisé par analyser_kribi.py. Peut aussi être importé directement.

Fallback : si les modèles .pkl sont absents, utilise les règles
seuils physiques calibrées (compatibilité V2/V3).
"""

import os
import json
import datetime
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

FEATURES_ORDER = [
    "mois", "pluie_7j", "pluie_30j", "pluie_prev_7j",
    "temp_max", "temp_max_3j", "sm_surface", "sm_rootzone",
    "ndvi", "ndwi",
]


def _score_vers_niveau(score: float) -> str:
    for (lo, hi), niveau in SCORE_VERS_NIVEAU.items():
        if lo <= score < hi:
            return niveau
    return "VERT"


def _niveau_vers_score(niveau: str) -> float:
    mapping = {"VERT": 0.10, "JAUNE": 0.35, "ORANGE": 0.60, "ROUGE": 0.85}
    return mapping.get(niveau, 0.10)


# ───────────────────────────────────────────────────────────────────────────────
# CHARGEMENT DES MODÈLES
# ───────────────────────────────────────────────────────────────────────────────

_cache_modeles: dict = {}


def _charger_modele(nom: str):
    """Charge un modèle pkl avec cache mémoire. Retourne None si absent."""
    if nom in _cache_modeles:
        return _cache_modeles[nom]
    chemin = os.path.join(MODELS_DIR, f"model_{nom}.pkl")
    if not os.path.exists(chemin):
        return None
    try:
        import joblib
        clf = joblib.load(chemin)
        _cache_modeles[nom] = clf
        return clf
    except Exception:
        return None


def modeles_disponibles() -> list:
    return [n for n in ["inondation", "secheresse", "chaleur"]
            if os.path.exists(os.path.join(MODELS_DIR, f"model_{n}.pkl"))]


# ───────────────────────────────────────────────────────────────────────────────
# FALLBACK — Règles physiques (si modèles absents)
# ───────────────────────────────────────────────────────────────────────────────

def _risque_inondation_physique(pluie_7j: float, pluie_prev: float,
                                sm_surface: float, ndwi: float, mois: int) -> float:
    normale = NORMALES_MENSUELLES.get(mois, 120)
    score = 0.0
    score += min(0.35, max(0, (pluie_7j / normale - 1.0) * 0.30))
    score += min(0.25, max(0, (pluie_prev / normale - 1.0) * 0.20))
    score += min(0.25, max(0, (sm_surface - 0.40) * 1.5))
    score += min(0.15, max(0, (ndwi - 0.30) * 0.5))
    return min(1.0, score)


def _risque_secheresse_physique(pluie_30j: float, ndvi: float,
                                sm_rootzone: float, mois: int) -> float:
    normale_30j = NORMALES_MENSUELLES.get(mois, 120) * (30 / 7)
    score = 0.0
    deficit = max(0, (normale_30j - pluie_30j) / normale_30j)
    score += min(0.40, deficit * 0.5)
    score += min(0.35, max(0, (0.55 - ndvi) * 1.2))
    score += min(0.25, max(0, (0.28 - sm_rootzone) * 2.0))
    return min(1.0, score)


def _risque_chaleur_physique(temp_max: float, temp_max_3j: float) -> float:
    score = 0.0
    score += min(0.60, max(0, (temp_max   - 32.0) / 5.0 * 0.50))
    score += min(0.40, max(0, (temp_max_3j - 32.0) / 5.0 * 0.40))
    return min(1.0, score)


# ───────────────────────────────────────────────────────────────────────────────
# CONSTRUCTION DES FEATURES
# ───────────────────────────────────────────────────────────────────────────────

def _features_from_data(data: dict, use_previsions: bool = False,
                         horizon_jours: int = 7) -> dict:
    """
    Extrait les features nécessaires depuis le dict de données collectées.
    Si use_previsions=True, utilise les prévisions météo pour la période horizon.
    """
    mois = datetime.date.today().month
    ind  = data.get("indicateurs_risque", {})
    sat  = data.get("satellitaire", {})
    smap = sat.get("smap", {}).get("humidite_sol", {})
    prev = data.get("meteorologie", {}).get("previsions_daily", {})

    pluie_7j       = float(ind.get("pluie_cumulee_7j_mm",  0) or 0)
    pluie_30j      = float(ind.get("pluie_cumulee_30j_mm", pluie_7j * 4) or pluie_7j * 4)
    sm_surface     = float(smap.get("sm_surface",  0.35) or 0.35)
    sm_rootzone    = float(smap.get("sm_rootzone", 0.30) or 0.30)
    ndvi           = float(ind.get("ndvi_moyen",   0.70) or 0.70)
    ndwi           = float(ind.get("ndwi_moyen",   0.20) or 0.20)

    if use_previsions:
        precip_list = (prev.get("precipitation_sum",         []) or [])[:horizon_jours]
        temp_list   = (prev.get("temperature_2m_max",        []) or [])[:horizon_jours]
        pluie_prev  = sum(float(p or 0) for p in precip_list)
        temp_max    = max((float(t or 28) for t in temp_list), default=28.0)
        temp_max_3j = max((float(t or 28) for t in temp_list[:3]), default=28.0)
        pluie_7j_feat = pluie_prev
    else:
        pluie_prev  = float(ind.get("pluie_prevue_7j_mm", 0) or 0)
        temp_max    = float(ind.get("temperature_max_c",  29.0) or 29.0)
        temp_max_3j = temp_max - 0.5
        pluie_7j_feat = pluie_7j

    return {
        "mois":          mois,
        "pluie_7j":      pluie_7j_feat,
        "pluie_30j":     pluie_30j,
        "pluie_prev_7j": pluie_prev,
        "temp_max":      temp_max,
        "temp_max_3j":   temp_max_3j,
        "sm_surface":    sm_surface,
        "sm_rootzone":   sm_rootzone,
        "ndvi":          ndvi,
        "ndwi":          ndwi,
    }


# ───────────────────────────────────────────────────────────────────────────────
# INFÉRENCE PRINCIPALE
# ───────────────────────────────────────────────────────────────────────────────

def predire_risques(data: dict, use_previsions: bool = False,
                    horizon_jours: int = 7) -> dict:
    """
    Prédit les trois risques (inondation, sécheresse, chaleur) à partir
    des données collectées.

    Utilise les modèles RandomForest si disponibles, sinon les règles physiques.
    Passe un DataFrame pandas à predict_proba pour éviter le UserWarning
    'X does not have valid feature names'.

    Retourne un dict avec :
        scores    : probabilités 0-1 pour chaque risque
        niveaux   : VERT/JAUNE/ORANGE/ROUGE pour chaque risque
        niveau_global : niveau maximal parmi les 3 risques
        methode   : 'modele_ml' ou 'regles_physiques'
    """
    feats = _features_from_data(data, use_previsions=use_previsions,
                                 horizon_jours=horizon_jours)

    # DataFrame pandas avec les noms de colonnes corrects → supprime le UserWarning sklearn
    try:
        import pandas as pd
        X_df = pd.DataFrame([feats], columns=FEATURES_ORDER)
        use_df = True
    except ImportError:
        use_df = False
        X_list = [[feats[f] for f in FEATURES_ORDER]]

    resultats = {}
    methode_utilisee = {}

    for nom in ["inondation", "secheresse", "chaleur"]:
        clf = _charger_modele(nom)
        if clf is not None:
            try:
                X = X_df if use_df else X_list
                score = float(clf.predict_proba(X)[0][1])
                methode_utilisee[nom] = "modele_ml"
            except Exception:
                score = None
        else:
            score = None

        if score is None:
            methode_utilisee[nom] = "regles_physiques"
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

        resultats[nom] = {
            "score":   round(score, 4),
            "niveau":  _score_vers_niveau(score),
            "methode": methode_utilisee[nom],
        }

    niveaux_ordre = ["VERT", "JAUNE", "ORANGE", "ROUGE"]
    niveau_global = max(
        (r["niveau"] for r in resultats.values()),
        key=lambda n: niveaux_ordre.index(n)
    )

    return {
        "scores":          {k: v["score"]  for k, v in resultats.items()},
        "niveaux":         {k: v["niveau"] for k, v in resultats.items()},
        "niveau_global":   niveau_global,
        "methode_globale": "modele_ml" if any(
            v == "modele_ml" for v in methode_utilisee.values()) else "regles_physiques",
        "features_utilisees": feats,
        "modeles_charges":    modeles_disponibles(),
    }


def evaluer_previsions(data: dict) -> dict:
    """
    Calcule les risques prévisionnels sur J+3 et J+7.
    Retourne un dict prêt à intégrer dans le rapport JSON.
    """
    risque_actuel = predire_risques(data, use_previsions=False)
    risque_3j     = predire_risques(data, use_previsions=True, horizon_jours=3)
    risque_7j     = predire_risques(data, use_previsions=True, horizon_jours=7)

    return {
        "actuel": {
            "niveau_global":  risque_actuel["niveau_global"],
            "niveaux":        risque_actuel["niveaux"],
            "scores":         risque_actuel["scores"],
            "methode":        risque_actuel["methode_globale"],
        },
        "prevu_3j": {
            "niveau_global":  risque_3j["niveau_global"],
            "niveaux":        risque_3j["niveaux"],
            "scores":         risque_3j["scores"],
        },
        "prevu_7j": {
            "niveau_global":  risque_7j["niveau_global"],
            "niveaux":        risque_7j["niveaux"],
            "scores":         risque_7j["scores"],
        },
    }


if __name__ == "__main__":
    data_test = {
        "indicateurs_risque": {
            "pluie_cumulee_7j_mm": 320,
            "pluie_prevue_7j_mm": 280,
            "pluie_cumulee_30j_mm": 950,
            "ndvi_moyen": 0.68,
            "ndwi_moyen": 0.48,
            "temperature_max_c": 31.0,
        },
        "satellitaire": {"smap": {"humidite_sol": {
            "sm_surface": 0.54, "sm_rootzone": 0.41
        }}},
        "meteorologie": {"previsions_daily": {
            "precipitation_sum": [45, 38, 52, 30, 25, 42, 55],
            "temperature_2m_max": [30, 31, 30, 29, 30, 31, 32],
        }},
    }
    resultats = evaluer_previsions(data_test)
    print(json.dumps(resultats, ensure_ascii=False, indent=2))
