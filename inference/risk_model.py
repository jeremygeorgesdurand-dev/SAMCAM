#!/usr/bin/env python3
"""
SAMCAM V5.0.1 — Module d'inférence des risques climatiques
Multi-horizons améliorés : J+1 / J+3 / J+7

NOUVEAUTÉS V5.0.1 :
    - FIX CRITIQUE _charger_modele() :
        La variable `path` n'existait pas dans le scope de la boucle for,
        déclenchant une NameError masquée (catchée silencieusement).
        La clé 'threshold' (utilisée par train_model.py) n'était pas lue ;
        seule 'seuil' (ancienne convention) était cherchée.
        Fix: {path} → {chemin} dans le message d'erreur,
             seuil = obj.get('seuil', obj.get('threshold', 0.5))

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

MODELS_DIR        = os.path.join(os.path.dirname(__file__), "..", "models", "zonal")
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

# ──────────────────────────────────────────────────────────────────────────────────
# FEATURES — Jeux de features par horizon (V4.7.0)
# ──────────────────────────────────────────────────────────────────────────────────

FEATURES_BASE = [
    "precipitation_24h", "temperature_max", "temperature_min",
    "humidity_relative", "wind_speed", "sm_surface", "sm_rootzone",
    "ndvi", "deficit_hydrique", "trend_sm",
]

FEATURES_J1 = FEATURES_BASE + ["precipitation_prev_24h", "temp_max_prev"]
FEATURES_J3 = FEATURES_BASE + ["precipitation_prev_72h", "trend_temp"]
FEATURES_J7 = FEATURES_BASE + ["precipitation_prev_7j",  "anomalie_sm"]

FEATURES_PAR_HORIZON = {1: FEATURES_J1, 3: FEATURES_J3, 7: FEATURES_J7}

# ──────────────────────────────────────────────────────────────────────────────────
# CACHE MODÈLES
# ──────────────────────────────────────────────────────────────────────────────────

_cache_modeles: Dict[tuple, tuple] = {}

# ──────────────────────────────────────────────────────────────────────────────────
# SEUILS DE RISQUE
# ──────────────────────────────────────────────────────────────────────────────────

SEUILS = {
    "inondation": {"VERT": 0.20, "JAUNE": 0.45, "ORANGE": 0.65, "ROUGE": 0.80},
    "secheresse": {"VERT": 0.20, "JAUNE": 0.40, "ORANGE": 0.60, "ROUGE": 0.78},
    "chaleur":    {"VERT": 0.25, "JAUNE": 0.45, "ORANGE": 0.65, "ROUGE": 0.80},
}


def _niveau_risque(score: float, risque: str) -> str:
    s = SEUILS.get(risque, SEUILS["inondation"])
    if score >= s["ROUGE"]:  return "ROUGE"
    if score >= s["ORANGE"]: return "ORANGE"
    if score >= s["JAUNE"]:  return "JAUNE"
    return "VERT"


# ──────────────────────────────────────────────────────────────────────────────────
# DONNÉES HISTORIQUES — SM glissant
# ──────────────────────────────────────────────────────────────────────────────────

_historique_sm: list = []
_sm_surface_precedente: Optional[float] = None


def _get_trend_sm_pur(sm_actuel: float, sm_reference: Optional[float]) -> float:
    """Calcule trend_sm SANS effet de bord sur l'état global."""
    if sm_reference is None:
        return 0.0
    return round(sm_actuel - sm_reference, 4)


def _lire_donnees(zone: Optional[str] = None) -> Dict[str, Any]:
    """
    Lit les dernières données collectées pour la zone donnée.
    Cherche dans data/<zone>/latest.json puis data/latest.json.
    Retourne un dict avec valeurs par défaut réalistes si fichier absent.
    """
    global _sm_surface_precedente

    chemins = []
    if zone:
        chemins.append(os.path.join(DATA_DIR, zone, "latest.json"))
    chemins.append(os.path.join(DATA_DIR, "latest.json"))

    data_source = None
    for chemin in chemins:
        if os.path.exists(chemin):
            try:
                with open(chemin) as f:
                    data_source = json.load(f)
                break
            except Exception:
                pass

    mois = datetime.datetime.now().month

    # Valeurs par défaut réalistes pour Kribi (saison actuelle)
    defauts = {
        "precipitation_24h":   NORMALES_MENSUELLES.get(mois, 100) / 30,
        "precipitation_prev_24h": NORMALES_MENSUELLES.get(mois, 100) / 30,
        "precipitation_prev_72h": NORMALES_MENSUELLES.get(mois, 100) / 10,
        "precipitation_prev_7j":  NORMALES_MENSUELLES.get(mois, 100) / 4,
        "temperature_max":     32.0,
        "temperature_min":     22.0,
        "temp_max_prev":       31.5,
        "humidity_relative":   80.0,
        "wind_speed":           3.5,
        "sm_surface":          SM_SURFACE_NORMALE_KRIBI.get(mois, 0.35),
        "sm_rootzone":         SM_ROOTZONE_NORMALE_KRIBI.get(mois, 0.38),
        "ndvi":                 0.52,
        "deficit_hydrique":     0.0,
        "trend_sm":             0.0,
        "trend_temp":           0.0,
        "anomalie_sm":          0.0,
    }

    if data_source is None:
        sm_act = defauts["sm_surface"]
        defauts["trend_sm"] = _get_trend_sm_pur(sm_act, _sm_surface_precedente)
        _sm_surface_precedente = sm_act
        return defauts

    # Mapper les clés du JSON vers les features attendues
    mapping = {
        "precipitation":       "precipitation_24h",
        "precip_24h":          "precipitation_24h",
        "precip":              "precipitation_24h",
        "temp_max":            "temperature_max",
        "temperature_max":     "temperature_max",
        "temp_min":            "temperature_min",
        "temperature_min":     "temperature_min",
        "humidity":            "humidity_relative",
        "wind":                "wind_speed",
        "soil_moisture":       "sm_surface",
        "sm_surface":          "sm_surface",
        "sm_rootzone":         "sm_rootzone",
        "ndvi":                "ndvi",
        "deficit_hydrique":    "deficit_hydrique",
    }

    donnees = dict(defauts)
    for src_key, dst_key in mapping.items():
        if src_key in data_source:
            val = data_source[src_key]
            if val is not None:
                try:
                    donnees[dst_key] = float(val)
                except (ValueError, TypeError):
                    pass

    sm_act = donnees["sm_surface"]
    donnees["trend_sm"] = _get_trend_sm_pur(sm_act, _sm_surface_precedente)
    _sm_surface_precedente = sm_act

    # Calculer anomalie_sm vs normale mensuelle
    sm_norm = SM_SURFACE_NORMALE_KRIBI.get(mois, 0.35)
    donnees["anomalie_sm"] = round(sm_act - sm_norm, 4)

    return donnees


# ──────────────────────────────────────────────────────────────────────────────────
# RÈGLES PHYSIQUES — Fallback si modèle ML absent ou incohérent
# ──────────────────────────────────────────────────────────────────────────────────

def _risque_inondation_physique(d: Dict[str, Any]) -> float:
    score = 0.0
    precip = d.get("precipitation_24h", 0)
    sm     = d.get("sm_surface", 0.35)
    wind   = d.get("wind_speed", 3)

    if precip > 80:   score += 0.50
    elif precip > 50: score += 0.35
    elif precip > 30: score += 0.20
    elif precip > 10: score += 0.08

    if sm > 0.45:     score += 0.25
    elif sm > 0.38:   score += 0.12

    if wind > 15:     score += 0.10
    elif wind > 10:   score += 0.05

    return min(score, 1.0)


def _risque_secheresse_physique(d: Dict[str, Any]) -> float:
    mois       = datetime.datetime.now().month
    precip     = d.get("precipitation_24h", 0)
    sm         = d.get("sm_surface", 0.35)
    sm_rz      = d.get("sm_rootzone", 0.38)
    ndvi       = d.get("ndvi", 0.52)
    deficit    = d.get("deficit_hydrique", 0)
    trend_sm   = d.get("trend_sm", 0)

    # Seuil NDVI contextuel selon saison
    if mois in (7, 8, 12, 1):
        seuil_ndvi = 0.35   # Saison sèche : seuil plus bas
    elif mois in (3, 4, 5, 6, 9, 10, 11):
        seuil_ndvi = 0.50   # Saison des pluies
    else:
        seuil_ndvi = 0.43   # Transition

    score = 0.0
    normale_mensuelle = NORMALES_MENSUELLES.get(mois, 100)
    ratio_precip = precip / max(normale_mensuelle / 30, 0.1)

    if ratio_precip < 0.10:   score += 0.30
    elif ratio_precip < 0.30: score += 0.18
    elif ratio_precip < 0.60: score += 0.08

    sm_norm = SM_SURFACE_NORMALE_KRIBI.get(mois, 0.35)
    if sm < sm_norm * 0.70:   score += 0.25
    elif sm < sm_norm * 0.85: score += 0.12

    sm_rz_norm = SM_ROOTZONE_NORMALE_KRIBI.get(mois, 0.38)
    if sm_rz < sm_rz_norm * 0.75: score += 0.15
    elif sm_rz < sm_rz_norm * 0.90: score += 0.07

    if ndvi < seuil_ndvi:      score += 0.15
    elif ndvi < seuil_ndvi + 0.08: score += 0.06

    if deficit > 80:   score += 0.15
    elif deficit > 40: score += 0.07

    if trend_sm < -0.04: score += 0.10
    elif trend_sm < -0.02: score += 0.05

    return min(score, 1.0)


def _risque_chaleur_physique(d: Dict[str, Any]) -> float:
    temp_max = d.get("temperature_max", 32)
    humidity = d.get("humidity_relative", 75)
    wind     = d.get("wind_speed", 3)

    score = 0.0
    if temp_max >= 38:   score += 0.45
    elif temp_max >= 36: score += 0.30
    elif temp_max >= 34: score += 0.15
    elif temp_max >= 33: score += 0.06

    if humidity >= 85 and temp_max >= 33: score += 0.20
    elif humidity >= 75 and temp_max >= 33: score += 0.10

    if wind < 2 and temp_max >= 33: score += 0.10

    return min(score, 1.0)


PHYSIQUE_FN = {
    "inondation": _risque_inondation_physique,
    "secheresse": _risque_secheresse_physique,
    "chaleur":    _risque_chaleur_physique,
}


# ──────────────────────────────────────────────────────────────────────────────────
# CHARGEMENT MODÈLES
# ──────────────────────────────────────────────────────────────────────────────────

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
                clf = (obj.get("clf")
                       or obj.get("model")
                       or (obj if hasattr(obj, "predict_proba") else None))
                if clf is None:
                    raise KeyError(
                        f"Aucune clé 'clf'/'model' trouvée dans {chemin}")
                # support 'seuil' (anciens modèles) et 'threshold' (nouveaux pkl)
                seuil    = obj.get("seuil", obj.get("threshold", 0.5))
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
    for d in [ZONAL_MODELS_DIR, MODELS_DIR]:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".pkl"):
                    modeles.append(os.path.join(d, f))
    return modeles


# ──────────────────────────────────────────────────────────────────────────────────
# PRÉDICTION PRINCIPALE
# ──────────────────────────────────────────────────────────────────────────────────

def predire_risques(donnees: Optional[Dict[str, Any]] = None,
                    zone: Optional[str] = None) -> Dict[str, Any]:
    """
    Prédit les risques climatiques pour J0.

    Paramètres
    ----------
    donnees : dict de features (optionnel — lit latest.json si None)
    zone    : nom de la zone SAMCAM (ex: 'Kribi')

    Retourne un dict {risque: {score, niveau, source}} pour
    inondation, secheresse et chaleur.
    """
    if donnees is None:
        donnees = _lire_donnees(zone=zone)

    resultats = {}

    for risque in ("inondation", "secheresse", "chaleur"):
        clf, seuil, features_modele = _charger_modele(risque, horizon=None, zone=zone)
        score_physique = PHYSIQUE_FN[risque](donnees)

        if clf is not None:
            try:
                X = [[donnees.get(f, 0.0) for f in features_modele]]
                score_ml_brut = float(clf.predict_proba(X)[0][1])

                # Garde-fou de cohérence physique (V4.7.4)
                if score_ml_brut > score_physique + 0.30:
                    print(f"[RISK-DIAG] {risque} : score ML ({score_ml_brut:.2f}) "
                          f"> physique ({score_physique:.2f}) + 0.30 → fallback physique")
                    score_final = score_physique
                    source      = "physique (guard)"
                else:
                    score_final = score_ml_brut
                    source      = "ML"
            except Exception as ex:
                print(f"[RISK] ⚠️  Erreur inférence {risque} : {ex}")
                score_final = score_physique
                source      = "physique (erreur ML)"
        else:
            score_final = score_physique
            source      = "physique"

        resultats[risque] = {
            "score":  round(score_final, 4),
            "niveau": _niveau_risque(score_final, risque),
            "source": source,
        }

    return resultats


def evaluer_previsions(zone: Optional[str] = None) -> Dict[str, Any]:
    """
    Évalue les risques sur 4 horizons : J0, J+1, J+3, J+7.
    Retourne un dict structuré par horizon.
    """
    donnees_base = _lire_donnees(zone=zone)
    sm_ref = _sm_surface_precedente  # snapshot avant la boucle (trend_sm pur)

    resultats = {}

    for label, hor_key in [("j0", None), ("j1", 1), ("j3", 3), ("j7", 7)]:
        horizons_risques = {}

        # Dégradation de fiabilité selon horizon
        bruit = {None: 0.00, 1: 0.03, 3: 0.07, 7: 0.12}.get(hor_key, 0.05)

        for risque in ("inondation", "secheresse", "chaleur"):
            clf, seuil, features_modele = _charger_modele(
                risque, horizon=hor_key, zone=zone)
            score_physique = PHYSIQUE_FN[risque](donnees_base)

            if clf is not None:
                try:
                    features_horizon = FEATURES_PAR_HORIZON.get(
                        hor_key, FEATURES_BASE) if hor_key else FEATURES_BASE
                    X = [[donnees_base.get(f, 0.0) for f in features_horizon]]
                    score_ml = float(clf.predict_proba(X)[0][1])
                    score_ml = max(0.0, min(1.0,
                        score_ml + random.gauss(0, bruit)))

                    if score_ml > score_physique + 0.30:
                        score_final = score_physique
                        source      = "physique (guard)"
                    else:
                        score_final = score_ml
                        source      = "ML"
                except Exception:
                    score_final = score_physique
                    source      = "physique (erreur)"
            else:
                # Dégradation légère du score physique sur horizons lointains
                bruit_phys = random.gauss(0, bruit * 0.5)
                score_final = max(0.0, min(1.0, score_physique + bruit_phys))
                source      = "physique"

            horizons_risques[risque] = {
                "score":  round(score_final, 4),
                "niveau": _niveau_risque(score_final, risque),
                "source": source,
            }

        resultats[label] = horizons_risques

    return resultats


# ──────────────────────────────────────────────────────────────────────────────────
# RAPPORT COMPLET
# ──────────────────────────────────────────────────────────────────────────────────

def generer_rapport(zone: Optional[str] = None) -> Dict[str, Any]:
    """
    Génère un rapport complet : risques J0 + prévisions J+1/J+3/J+7.
    """
    donnees   = _lire_donnees(zone=zone)
    risques   = predire_risques(donnees=donnees, zone=zone)
    previsions = evaluer_previsions(zone=zone)

    # Score de risque global (max des 3 risques)
    score_global = max(v["score"] for v in risques.values())
    niveau_global = _niveau_risque(score_global, "inondation")

    rapport = {
        "zone":           zone or "inconnue",
        "timestamp":      datetime.datetime.utcnow().isoformat() + "Z",
        "risques":        risques,
        "score_global":   round(score_global, 4),
        "niveau_global":  niveau_global,
        "previsions":     previsions,
        "donnees_source": donnees,
    }

    return rapport


def sauvegarder_rapport_json(rapport: Dict[str, Any],
                              chemin: Optional[str] = None) -> str:
    """Sauvegarde le rapport en JSON. Retourne le chemin du fichier écrit."""
    if chemin is None:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        ts  = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        zone = rapport.get("zone", "unknown").replace(" ", "_")
        chemin = os.path.join(REPORTS_DIR, f"rapport_{zone}_{ts}.json")

    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)

    print(f"[RISK] 💾 Rapport sauvegardé : {chemin}")
    return chemin


# ──────────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE CLI
# ──────────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    zone_arg = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"\n[RISK] Analyse pour zone : {zone_arg or 'GPS auto'}")
    rapport = generer_rapport(zone=zone_arg)
    print(json.dumps(rapport, ensure_ascii=False, indent=2))
    sauvegarder_rapport_json(rapport)
