#!/usr/bin/env python3
"""
compute_daily_predictions.py — Précalcule les risques J0/J+1/J+3/J+7 pour les
8 zones × 3 risques, et les sauvegarde dans data/predictions/latest.json.

Pourquoi : infer_zone_risk()/infer_zone_risk_horizon() rechargent et recalculent
les fenêtres glissantes (7/14/30/90j) sur tout l'historique zonal (9500-13000
lignes) à CHAQUE appel — 9 calculs par requête API (3 risques × 3 horizons).
Ce script fait ce travail UNE FOIS par jour (après la collecte quotidienne et
la fusion dans l'historique — voir data_collection/append_daily_to_historical.py),
et server/api.py lit le résultat pré-calculé au lieu de recalculer à chaque
requête HTTP.

Doit être lancé APRÈS :
  1. data_collection/collect_all_zones.py   (collecte du jour)
  2. data_collection/append_daily_to_historical.py  (fusion dans l'historique)

Usage :
  python3 inference/compute_daily_predictions.py
  python3 inference/compute_daily_predictions.py --zones Kribi Maroua
"""

import argparse
import glob
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from inference.infer_zonal import (
    infer_zone_risk, infer_zone_risk_horizon, infer_zone_risk_series, ZONES, RISKS,
)

DATA_DIR       = ROOT / "data"
PRED_DIR       = ROOT / "data" / "predictions"
PRED_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH    = PRED_DIR / "latest.json"

HORIZONS = (1, 3, 7, 10, 14)  # bornés par la longueur des prévisions Open-Meteo (~16j dispo)

# Nombre de jours d'historique pré-calculé et mis en cache pour /api/history —
# supérieur aux 14 jours affichés par défaut dans l'app, pour garder une marge.
HISTORY_DAYS = 30


def compute_zone_history(zone: str, days: int = HISTORY_DAYS) -> dict:
    """
    Pré-calcule la série jour par jour des 3 risques sur `days` jours, pour le
    cache lu par /api/history (server/api.py). Avant ce cache, /api/history
    recalculait tout en direct à chaque requête (3 risques × inférence sur
    toute la fenêtre) — plusieurs dizaines de secondes par zone sur un
    Raspberry Pi, cause de timeouts observés en usage réel.
    """
    par_date: dict = {}
    for risk in RISKS:
        r = infer_zone_risk_series(zone, risk, days=days)
        if r.get("status") != "OK":
            continue
        for e in r.get("serie", []):
            par_date.setdefault(e["date"], {})[risk] = e["proba"]
    return par_date


def _previsions_daily_pour_zone(zone: str) -> dict:
    """Lit le bloc meteorologie.previsions_daily de la dernière collecte du jour."""
    pattern  = DATA_DIR / f"{zone.lower()}_*.json"
    fichiers = sorted(glob.glob(str(pattern)))
    if not fichiers:
        return {}
    with open(fichiers[-1], encoding="utf-8") as f:
        d = json.load(f)
    return d.get("meteorologie", {}).get("previsions_daily", {}) or {}


def compute_zone(zone: str) -> dict:
    previsions_daily = _previsions_daily_pour_zone(zone)
    resultat = {"zone": zone, "date_calcul": date.today().isoformat(), "risques": {}}

    for risk in RISKS:
        r0 = infer_zone_risk(zone, risk, days=30, verbose=False)
        entry = {
            "j0": {
                "score":  r0.get("proba_last", 0.0) if r0.get("status") == "OK" else None,
                "niveau": r0.get("level"),
                "status": r0.get("status"),
            }
        }
        for h in HORIZONS:
            if previsions_daily and r0.get("status") == "OK":
                rh = infer_zone_risk_horizon(zone, risk, previsions_daily, h, days=30, verbose=False)
                entry[f"j{h}"] = {
                    "score":      rh.get("proba", entry["j0"]["score"]) if rh.get("status") == "OK" else entry["j0"]["score"],
                    "niveau":     rh.get("level", entry["j0"]["niveau"]),
                    "date_cible": rh.get("date_cible"),
                    "status":     rh.get("status"),
                }
            else:
                entry[f"j{h}"] = dict(entry["j0"])
        resultat["risques"][risk] = entry

    return resultat


def main():
    parser = argparse.ArgumentParser(description="Précalcule les risques J0/J1/J3/J7 pour toutes les zones")
    parser.add_argument("--zones", nargs="+", default=None)
    args = parser.parse_args()

    zones = args.zones or ZONES
    predictions = {}
    for zone in zones:
        try:
            predictions[zone] = compute_zone(zone)
            statuts = {r: predictions[zone]["risques"][r]["j0"]["status"] for r in RISKS}
            print(f"[{zone}] {statuts}")
        except Exception as e:
            print(f"[{zone}] ⚠️  Erreur : {e}")
            predictions[zone] = {"zone": zone, "date_calcul": date.today().isoformat(),
                                  "risques": {}, "error": str(e)}

        try:
            predictions[zone]["historique"] = compute_zone_history(zone)
            print(f"[{zone}] historique : {len(predictions[zone]['historique'])} jours en cache")
        except Exception as e:
            print(f"[{zone}] ⚠️  Erreur historique : {e}")
            predictions[zone]["historique"] = {}

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(predictions, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Prédictions sauvegardées : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
