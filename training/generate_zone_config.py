#!/usr/bin/env python3
"""
generate_zone_config.py — Calibre config/zones/<slug>.json depuis l'historique réel
d'une zone (data/historical/<Zone>_historical.csv), au lieu de s'appuyer sur les
profils climatiques génériques FALLBACK_PROFILES de build_labels.py.

Pourquoi : build_labels.py utilise silencieusement un profil générique (équatorial/
altitude/sahélien) si config/zones/<slug>.json est absent — ce qui donne des labels
grossiers, pas calés sur la climatologie réelle de la zone. Ce script calcule les
normales mensuelles (pluie, ET0, températures, humidité du sol) et les percentiles
hebdomadaires de pluie directement depuis l'historique collecté, pour produire un
JSON de zone dans le même format que config/zones/kribi.json (déjà audité).

Les facteurs de seuil (flood_facteur_7j, drought_facteur_30j, heat_sigma, etc.) ne
sont pas dérivables des seules normales — ce sont des paramètres de classifieur.
Ils sont donc repris du profil générique correspondant à la classe climatique de la
zone (mêmes valeurs que FALLBACK_PROFILES), qui reste la meilleure estimation avant
tout ré-étalonnage a posteriori sur événements réels documentés.

Usage :
  python training/generate_zone_config.py --zone Ndop --climate tropical_highland
  python training/generate_zone_config.py --all-new   # zones sans JSON existant
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from training.build_labels import FALLBACK_PROFILES  # facteurs de seuil par classe climatique

DATA_DIR   = ROOT / "data" / "historical"
CONFIG_DIR = ROOT / "config" / "zones"

TIMEZONE = "Africa/Douala"

# Coordonnées + altitude approx des nouvelles zones (pour _meta/coordonnees)
ZONE_META = {
    "Ndop":       {"lat": 5.9833,  "lon": 10.4500, "alt": 1200, "regime": "hauts_plateaux_bimodal",
                    "desc": "Plaine du Noun (Ouest/Nord-Ouest) — riziculture irriguée, deux saisons des pluies"},
    "Foumbot":    {"lat": 5.5167,  "lon": 10.6333, "alt": 1000, "regime": "hauts_plateaux_bimodal",
                    "desc": "Plaine fertile du Noun (Ouest) — maraîchage/maïs sur sols volcaniques"},
    "Kaele":      {"lat": 10.1167, "lon": 14.4500, "alt": 380,  "regime": "sahelien_monomodal",
                    "desc": "Extrême-Nord — sorgho/mil pluvial, saison des pluies courte"},
    "Guider":     {"lat": 9.9333,  "lon": 13.9500, "alt": 320,  "regime": "sahelien_monomodal",
                    "desc": "Nord — ceinture cotonnière, sorgho/arachide"},
    "Meiganga":   {"lat": 6.5167,  "lon": 14.3000, "alt": 1050, "regime": "hauts_plateaux_transition",
                    "desc": "Adamaoua — élevage bovin extensif, transition soudano-guinéenne"},
    "Mbalmayo":   {"lat": 3.5167,  "lon": 11.5000, "alt": 660,  "regime": "equatorial_bimodal",
                    "desc": "Centre — bassin vivrier périurbain, manioc/plantain"},
    "Bafia":      {"lat": 4.7500,  "lon": 11.2333, "alt": 480,  "regime": "equatorial_bimodal",
                    "desc": "Centre — vivrier/arachide, transition forêt-savane"},
    "Bertoua":    {"lat": 4.5833,  "lon": 13.6833, "alt": 690,  "regime": "equatorial_bimodal",
                    "desc": "Est — café robusta/cacao, forêt dense"},
    "Nkongsamba": {"lat": 4.9547,  "lon": 9.9401,  "alt": 900,  "regime": "equatorial_bimodal",
                    "desc": "Littoral/Moungo — cacao/bananeraie d'exportation"},
    "Buea":       {"lat": 4.1560,  "lon": 9.2420,  "alt": 870,  "regime": "equatorial_bimodal",
                    "desc": "Sud-Ouest — palmier à huile/banane, piémont du Mont Cameroun, forte pluviométrie"},
}

CLIMATE_BY_ZONE = {
    "Ndop": "tropical_highland", "Foumbot": "tropical_highland",
    "Kaele": "sahelian", "Guider": "sahelian", "Meiganga": "tropical_highland",
    "Mbalmayo": "equatorial", "Bafia": "equatorial", "Bertoua": "equatorial",
    "Nkongsamba": "equatorial", "Buea": "equatorial",
}


def _rain_col(df: pd.DataFrame) -> str:
    for c in ["precipitation_sum", "nasa_prectotcorr"]:
        if c in df.columns:
            return c
    raise ValueError("Aucune colonne de pluie trouvée")


def _monthly_normals(df: pd.DataFrame, col: str) -> dict:
    """Moyenne journalière typique par mois (°C, humidité sol, etc.)."""
    means = df.groupby(df["date"].dt.month)[col].mean()
    return {str(m): round(float(means.get(m, 0.0)), 1) for m in range(1, 13)}


def _monthly_totals(df: pd.DataFrame, col: str) -> dict:
    """Total mensuel typique (mm/mois) — somme par (année, mois) puis moyenne
    inter-annuelle. Utilisé pour pluie/ET0, dont le JSON stocke des cumuls
    mensuels (pas des moyennes journalières) — cf. build_labels.py qui divise
    ces valeurs par 30 pour retrouver un équivalent journalier."""
    tmp = df[["date", col]].copy()
    tmp["year"] = tmp["date"].dt.year
    tmp["month"] = tmp["date"].dt.month
    monthly_sums = tmp.groupby(["year", "month"])[col].sum()
    avg_by_month = monthly_sums.groupby(level="month").mean()
    return {str(m): round(float(avg_by_month.get(m, 0.0)), 1) for m in range(1, 13)}


def _monthly_std(df: pd.DataFrame, col: str) -> dict:
    stds = df.groupby(df["date"].dt.month)[col].std()
    return {str(m): round(float(stds.get(m, 1.0)) or 1.0, 2) for m in range(1, 13)}


def _weekly_rain_percentiles(df: pd.DataFrame, rain_col: str) -> dict:
    """Cumul de pluie par semaine ISO, percentiles p25/50/75/90 groupés par mois."""
    tmp = df[["date", rain_col]].copy()
    tmp["iso_year_week"] = tmp["date"].dt.isocalendar().year.astype(str) + "-W" + \
        tmp["date"].dt.isocalendar().week.astype(str)
    tmp["month"] = tmp["date"].dt.month
    weekly = tmp.groupby("iso_year_week").agg(
        rain=(rain_col, "sum"), month=("month", lambda s: s.mode().iloc[0])
    )
    out = {}
    for m in range(1, 13):
        vals = weekly.loc[weekly["month"] == m, "rain"]
        if len(vals) < 4:
            out[str(m)] = {"p25": 0.0, "p50": 0.0, "p75": 0.0, "p90": 0.0}
            continue
        out[str(m)] = {
            "p25": round(float(vals.quantile(0.25)), 1),
            "p50": round(float(vals.quantile(0.50)), 1),
            "p75": round(float(vals.quantile(0.75)), 1),
            "p90": round(float(vals.quantile(0.90)), 1),
        }
    return out


def generate(zone: str, climate: str, force: bool = False) -> None:
    slug = zone.lower().replace(" ", "_").replace("-", "_")
    out_path = CONFIG_DIR / f"{slug}.json"
    if out_path.exists() and not force:
        print(f"[{zone}] {out_path} existe déjà — utilisez --force pour écraser.")
        return

    csv_path = DATA_DIR / f"{zone}_historical.csv"
    if not csv_path.exists():
        print(f"[{zone}] ✗ {csv_path} introuvable — lancez collect_historical.py d'abord.")
        return

    df = pd.read_csv(csv_path, parse_dates=["date"])
    if len(df) < 365 * 5:
        print(f"[{zone}] ⚠ Seulement {len(df)} jours d'historique (<5 ans) — "
              f"normales peu fiables, mais génération quand même.")

    rain_col = _rain_col(df)
    et0_col = "et0_fao_evapotranspiration" if "et0_fao_evapotranspiration" in df.columns else "nasa_evland"
    tmax_col = "temperature_2m_max" if "temperature_2m_max" in df.columns else "nasa_t2m_max"
    tmin_col = "temperature_2m_min" if "temperature_2m_min" in df.columns else "nasa_t2m_min"
    sm_surf_col = "soil_moisture_0_to_7cm_mean" if "soil_moisture_0_to_7cm_mean" in df.columns else "nasa_gwettop"
    sm_root_col = "soil_moisture_28_to_100cm_mean" if "soil_moisture_28_to_100cm_mean" in df.columns else "nasa_gwetroot"

    fb = FALLBACK_PROFILES[climate]
    meta = ZONE_META.get(zone, {"lat": 0.0, "lon": 0.0, "alt": 0, "regime": climate,
                                 "desc": f"Zone agricole ({climate})"})

    cfg = {
        "_meta": {
            "zone": slug,
            "label": zone,
            "version": "1.0.0",
            "regime": meta["regime"],
            "description": meta["desc"],
            "sources": f"Open-Meteo ERA5-Land + NASA POWER, {df['date'].min().date()} → {df['date'].max().date()}",
            "calibration_note": (
                f"Normales et percentiles calculés automatiquement depuis "
                f"l'historique réel ({len(df)} jours) par generate_zone_config.py. "
                f"Facteurs de seuil (flood/drought/heat) repris du profil générique "
                f"'{climate}' — à réétalonner sur événements réels documentés si disponibles."
            ),
        },
        "coordonnees": {
            "lat": meta["lat"], "lon": meta["lon"],
            "altitude_m": meta["alt"], "timezone": TIMEZONE,
        },
        "pluie_normales_mensuelles_mm": _monthly_totals(df, rain_col),
        "et0_normales_mensuelles_mm": _monthly_totals(df, et0_col),
        "temp_max_normales_mensuelles_c": _monthly_normals(df, tmax_col),
        "temp_max_std_mensuelles_c": _monthly_std(df, tmax_col),
        "temp_min_normales_mensuelles_c": _monthly_normals(df, tmin_col),
        "sm_surface_normales": _monthly_normals(df, sm_surf_col),
        "sm_rootzone_normales": _monthly_normals(df, sm_root_col),
        "ndvi_seuil_alerte": {str(m): 0.40 for m in range(1, 13)},  # pas de NDVI en historique brut
        "percentiles_hebdo_pluie": _weekly_rain_percentiles(df, rain_col),
        "seuils_inondation": {
            "pluie_7j_facteur_normale": fb["flood_facteur_7j"],
            "sm_surface_seuil_haut": fb["flood_sm_haut"],
            "score_min_label_1": fb["flood_score_min"],
            "commentaire": f"Facteurs génériques '{climate}' (non ré-étalonnés)",
        },
        "seuils_secheresse": {
            "pluie_30j_facteur_deficit": fb["drought_facteur_30j"],
            "sm_rootzone_delta_seuil": fb["drought_sm_delta"],
            "et0_facteur_stress": fb["drought_et0_facteur"],
            "score_min_label_1": fb["drought_score_min"],
            "commentaire": f"Facteurs génériques '{climate}' (non ré-étalonnés)",
        },
        "seuils_chaleur": {
            "temp_max_anomalie_sigma": fb["heat_sigma"],
            "temp_max_3j_anomalie_sigma": fb["heat_sigma_3j"],
            "et0_facteur_stress": 1.3,
            "pluie_7j_max_sec": fb["heat_pluie_max_sec"],
            "score_min_label_1": fb["heat_score_min"],
            "commentaire": f"Facteurs génériques '{climate}' (non ré-étalonnés)",
        },
        "saisons": {
            "grande_saison_pluies": [], "petite_saison_pluies": [],
            "grande_saison_seche": [], "petite_saison_seche": [],
        },
        "fichiers_historiques": {
            "dataset_csv": f"data/historical/{zone}_historical.csv",
            "flood_events_csv": "",
        },
    }

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"[{zone}] ✓ {out_path} généré depuis {len(df)} jours d'historique réel.")


def main():
    parser = argparse.ArgumentParser(description="Calibration config/zones/*.json depuis l'historique réel")
    parser.add_argument("--zone", default=None)
    parser.add_argument("--climate", default=None, choices=["equatorial", "tropical_highland", "sahelian"])
    parser.add_argument("--all-new", action="store_true",
                         help="Génère pour toutes les zones de CLIMATE_BY_ZONE sans JSON existant")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.all_new:
        for zone, climate in CLIMATE_BY_ZONE.items():
            generate(zone, climate, force=args.force)
        return

    if not args.zone:
        parser.error("--zone requis (ou --all-new)")
    climate = args.climate or CLIMATE_BY_ZONE.get(args.zone)
    if not climate:
        parser.error(f"--climate requis pour une zone inconnue de CLIMATE_BY_ZONE ('{args.zone}')")
    generate(args.zone, climate, force=args.force)


if __name__ == "__main__":
    main()
