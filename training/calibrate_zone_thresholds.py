#!/usr/bin/env python3
"""
calibrate_zone_thresholds.py — Ré-étalonne les facteurs de seuil (seuils_inondation/
secheresse/chaleur) de config/zones/<slug>.json pour que le taux de jours en alerte
de chaque nouvelle zone soit cohérent avec celui des zones déjà calibrées de la même
classe climatique (Kribi/Ebolowa/Kumba/Yaounde_peri, Bafoussam/Ngaoundere, Garoua/Maroua).

Pourquoi : generate_zone_config.py calcule des normales et percentiles réels depuis
l'historique de chaque zone, mais reprend les FACTEURS de seuil (flood_facteur_7j,
drought_facteur_30j, heat_sigma...) du profil climatique générique. Sur des zones au
climat plus extrême (ex. Kaélé/Guider en zone sahélienne stricte), ces facteurs
génériques produisent des taux d'alerte bien trop élevés (jusqu'à 68% des jours en
alerte chaleur) — le modèle apprend alors un signal display trop bruyant.

Méthode : recherche par dichotomie sur UN facteur par risque (le plus déterminant),
en gardant les autres facteurs génériques, jusqu'à ce que le taux de labels positifs
tombe dans la fourchette cible [0.5×, 1.8×] de la moyenne observée sur les zones
calibrées de la même classe climatique.

Usage :
  python training/calibrate_zone_thresholds.py --zone Kaele --climate sahelian
  python training/calibrate_zone_thresholds.py --all-new
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from training.build_labels import label_flood, label_drought, label_heat, load_zone_config

DATA_DIR = ROOT / "data" / "historical"
CONFIG_DIR = ROOT / "config" / "zones"

# Zones déjà calibrées (audit du 2026-07-08/10) servant de référence par classe climatique
REFERENCE_ZONES = {
    "equatorial": ["Kribi", "Ebolowa", "Kumba", "Yaounde_peri"],
    "tropical_highland": ["Bafoussam", "Ngaoundere"],
    "sahelian": ["Garoua", "Maroua"],
}

NEW_ZONES_CLIMATE = {
    "Ndop": "tropical_highland", "Foumbot": "tropical_highland",
    "Kaele": "sahelian", "Guider": "sahelian", "Meiganga": "tropical_highland",
    "Mbalmayo": "equatorial", "Bafia": "equatorial", "Bertoua": "equatorial",
    "Nkongsamba": "equatorial", "Buea": "equatorial",
}

TOLERANCE_LOW, TOLERANCE_HIGH = 0.5, 1.8  # fourchette cible = [0.5x, 1.8x] la référence


def _compute_target_rates() -> dict:
    """Taux de labels positifs moyens par classe climatique, sur les zones déjà calibrées."""
    targets = {}
    for climate, zones in REFERENCE_ZONES.items():
        sums = {"inondation": 0.0, "secheresse": 0.0, "chaleur": 0.0}
        for z in zones:
            df = pd.read_csv(DATA_DIR / f"{z}_labeled.csv")
            sums["inondation"] += df["label_inondation"].mean()
            sums["secheresse"] += df["label_secheresse"].mean()
            sums["chaleur"] += df["label_chaleur"].mean()
        n = len(zones)
        targets[climate] = {k: v / n for k, v in sums.items()}
    return targets


def _bisect_factor(df: pd.DataFrame, cfg: dict, label_fn, factor_key: str,
                    target: float, lo: float, hi: float, iters: int = 18) -> tuple:
    """Dichotomie générique : détermine le sens de variation automatiquement en testant
    les deux bornes, puis converge vers `target`. Retourne (valeur_calibrée, taux_final)."""
    def rate_at(v):
        test_cfg = dict(cfg)
        test_cfg[factor_key] = v
        return label_fn(df, test_cfg).mean()

    rate_lo, rate_hi = rate_at(lo), rate_at(hi)
    increasing = rate_hi > rate_lo  # le taux augmente-t-il avec le facteur ?

    best_v, best_rate, best_dist = cfg[factor_key], rate_at(cfg[factor_key]), float("inf")
    a, b = lo, hi
    for _ in range(iters):
        mid = (a + b) / 2
        r = rate_at(mid)
        dist = abs(r - target)
        if dist < best_dist:
            best_v, best_rate, best_dist = mid, r, dist
        if (r < target) == increasing:
            a = mid
        else:
            b = mid
    return round(best_v, 4), best_rate


def _calibrate_risk(df, cfg, label_fn, factor_key, score_min_key, target,
                     lo_mult, hi_mult, lo_cap=None, hi_cap=None):
    """Boucle externe sur score_min (1..3) : pour chaque valeur, dichotomie sur le
    facteur continu. Retient la combinaison (score_min, facteur) la plus proche de
    la cible — nécessaire quand un seul critère domine le score (score_min=1) et
    rend le facteur des AUTRES critères sans effet sur le taux global."""
    base_factor = cfg[factor_key]
    best = None
    for score_min in (1, 2, 3):
        test_cfg = dict(cfg)
        test_cfg[score_min_key] = score_min
        lo, hi = base_factor * lo_mult, base_factor * hi_mult
        if lo_cap is not None:
            lo = max(lo, lo_cap)
        if hi_cap is not None:
            hi = min(hi, hi_cap)
        if lo >= hi:
            continue
        val, rate = _bisect_factor(df, test_cfg, label_fn, factor_key, target, lo, hi)
        dist = abs(rate - target)
        if best is None or dist < best[2]:
            best = (score_min, val, dist, rate)
    return best  # (score_min, factor_value, dist, rate)


def calibrate(zone: str, climate: str, targets: dict, force: bool = False) -> None:
    slug = zone.lower().replace(" ", "_").replace("-", "_")
    config_path = CONFIG_DIR / f"{slug}.json"
    if not config_path.exists():
        print(f"[{zone}] ✗ {config_path} introuvable — lancez generate_zone_config.py d'abord.")
        return

    csv_path = DATA_DIR / f"{zone}_historical.csv"
    df = pd.read_csv(csv_path, parse_dates=["date"])
    cfg = load_zone_config(zone, climate)
    tgt = targets[climate]

    with open(config_path) as f:
        raw = json.load(f)

    if raw.get("_meta", {}).get("calibration_seuils") and not force:
        print(f"[{zone}] Déjà calibré — utilisez --force pour recalibrer.")
        return

    print(f"[{zone}] ({climate}) — cibles : "
          f"inond={tgt['inondation']*100:.1f}% sech={tgt['secheresse']*100:.1f}% chaleur={tgt['chaleur']*100:.1f}%")

    before = {
        "inondation": label_flood(df, cfg).mean(),
        "secheresse": label_drought(df, cfg).mean(),
        "chaleur": label_heat(df, cfg).mean(),
    }

    # --- Inondation : facteur pluie_7j (plus haut = moins sensible) + score_min ---
    sm_flood, new_flood_facteur, _, rate_flood = _calibrate_risk(
        df, cfg, label_flood, "flood_facteur_7j", "flood_score_min",
        target=tgt["inondation"], lo_mult=0.3, hi_mult=5.0,
    )

    # --- Sécheresse : facteur déficit pluie 30j (plus bas = moins sensible) + score_min ---
    sm_drought, new_drought_facteur, _, rate_drought = _calibrate_risk(
        df, cfg, label_drought, "drought_facteur_30j", "drought_score_min",
        target=tgt["secheresse"], lo_mult=0.15, hi_mult=1.6, lo_cap=0.05, hi_cap=0.97,
    )

    # --- Chaleur : sigma d'anomalie (plus haut = moins sensible) + score_min ---
    sm_heat, new_heat_sigma, _, rate_heat = _calibrate_risk(
        df, cfg, label_heat, "heat_sigma", "heat_score_min",
        target=tgt["chaleur"], lo_mult=0.3, hi_mult=6.0,
    )

    print(f"  inondation : {before['inondation']*100:5.1f}% → {rate_flood*100:5.1f}%  "
          f"(facteur {cfg['flood_facteur_7j']:.2f}→{new_flood_facteur:.2f}, "
          f"score_min {cfg['flood_score_min']}→{sm_flood})")
    print(f"  secheresse : {before['secheresse']*100:5.1f}% → {rate_drought*100:5.1f}%  "
          f"(facteur {cfg['drought_facteur_30j']:.2f}→{new_drought_facteur:.2f}, "
          f"score_min {cfg['drought_score_min']}→{sm_drought})")
    print(f"  chaleur    : {before['chaleur']*100:5.1f}% → {rate_heat*100:5.1f}%  "
          f"(sigma {cfg['heat_sigma']:.2f}→{new_heat_sigma:.2f}, "
          f"score_min {cfg['heat_score_min']}→{sm_heat})")

    raw["seuils_inondation"]["pluie_7j_facteur_normale"] = new_flood_facteur
    raw["seuils_inondation"]["score_min_label_1"] = sm_flood
    raw["seuils_inondation"]["commentaire"] = (
        f"Ré-étalonné automatiquement (calibrate_zone_thresholds.py) pour un taux "
        f"d'alerte cible ~{tgt['inondation']*100:.1f}% (référence classe '{climate}')."
    )
    raw["seuils_secheresse"]["pluie_30j_facteur_deficit"] = new_drought_facteur
    raw["seuils_secheresse"]["score_min_label_1"] = sm_drought
    raw["seuils_secheresse"]["commentaire"] = (
        f"Ré-étalonné automatiquement pour un taux d'alerte cible ~{tgt['secheresse']*100:.1f}%."
    )
    raw["seuils_chaleur"]["temp_max_anomalie_sigma"] = new_heat_sigma
    raw["seuils_chaleur"]["score_min_label_1"] = sm_heat
    raw["seuils_chaleur"]["commentaire"] = (
        f"Ré-étalonné automatiquement pour un taux d'alerte cible ~{tgt['chaleur']*100:.1f}%."
    )
    raw["_meta"]["calibration_seuils"] = (
        "Facteurs de seuil ré-étalonnés par dichotomie (calibrate_zone_thresholds.py) "
        "pour aligner les taux de jours en alerte sur la moyenne des zones déjà "
        "calibrées de la même classe climatique, au lieu des facteurs génériques bruts."
    )

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    print(f"[{zone}] ✓ {config_path} mis à jour.\n")


def main():
    parser = argparse.ArgumentParser(description="Ré-étalonnage des seuils de nouvelles zones")
    parser.add_argument("--zone", default=None)
    parser.add_argument("--climate", default=None, choices=["equatorial", "tropical_highland", "sahelian"])
    parser.add_argument("--all-new", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    targets = _compute_target_rates()

    if args.all_new:
        for zone, climate in NEW_ZONES_CLIMATE.items():
            calibrate(zone, climate, targets, force=args.force)
        return

    if not args.zone:
        parser.error("--zone requis (ou --all-new)")
    climate = args.climate or NEW_ZONES_CLIMATE.get(args.zone)
    if not climate:
        parser.error(f"--climate requis pour '{args.zone}'")
    calibrate(args.zone, climate, targets, force=args.force)


if __name__ == "__main__":
    main()
