#!/usr/bin/env python3
"""
SAMCAM V1.0 — Pipeline d'analyse multi-zones

Lit le JSON collecté du jour pour une ou toutes les zones,
exécute l'inférence de risque (risk_model) et sauvegarde un rapport
dans reports/rapport_<slug>_<date>.json.

Usage :
    python3 inference/analyse_zone.py --zone Kribi
    python3 inference/analyse_zone.py --zone Garoua
    python3 inference/analyse_zone.py --all
    python3 inference/analyse_zone.py --all --date 2026-07-01

Sortie :
    reports/rapport_kribi_2026-07-03.json
    reports/rapport_garoua_2026-07-03.json
    ...
"""

import os
import sys
import json
import glob
import argparse
import datetime

# ─── PATHS ────────────────────────────────────────────────────────────────────

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(BASE, ".."))

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA_DIR    = os.path.join(ROOT, "data")
REPORTS_DIR = os.path.join(ROOT, "reports")
MODELS_DIR  = os.path.join(ROOT, "models", "zonal")

# ─── ZONES (miroir de collect_zone.py et api.py) ──────────────────────────────

ZONES = [
    {"name": "Kribi",        "slug": "kribi"},
    {"name": "Ebolowa",      "slug": "ebolowa"},
    {"name": "Kumba",        "slug": "kumba"},
    {"name": "Bafoussam",    "slug": "bafoussam"},
    {"name": "Yaounde_peri", "slug": "yaounde_peri"},
    {"name": "Ngaoundere",   "slug": "ngaoundere"},
    {"name": "Garoua",       "slug": "garoua"},
    {"name": "Maroua",       "slug": "maroua"},
]

ZONES_BY_SLUG = {z["slug"]: z for z in ZONES}
ZONES_BY_NAME = {z["name"].lower(): z for z in ZONES}


def resolve_zone(name_or_slug: str) -> dict:
    """Résout un nom ou slug de zone → dict {name, slug}."""
    key = name_or_slug.lower().replace(" ", "_")
    z = ZONES_BY_SLUG.get(key) or ZONES_BY_NAME.get(key)
    if z is None:
        noms = ", ".join(z["name"] for z in ZONES)
        raise ValueError(f"Zone inconnue : '{name_or_slug}'. Zones disponibles : {noms}")
    return z


# ─── CHARGEMENT DONNÉES ───────────────────────────────────────────────────────

def charger_donnees(slug: str, date_str: str) -> dict:
    """
    Charge le JSON collecté pour une zone et une date donnée.
    Cherche d'abord le fichier exact, puis le plus récent si absent.
    """
    fichier_exact = os.path.join(DATA_DIR, f"{slug}_{date_str}.json")
    if os.path.exists(fichier_exact):
        with open(fichier_exact, encoding="utf-8") as f:
            return json.load(f)

    # Fallback : fichier le plus récent pour cette zone
    candidats = sorted(glob.glob(os.path.join(DATA_DIR, f"{slug}_*.json")))
    if not candidats:
        raise FileNotFoundError(
            f"Aucun fichier data/{slug}_*.json trouvé. "
            f"Lance d'abord : python3 data_collection/collect_zone.py"
        )
    fichier = max(candidats, key=os.path.getmtime)
    print(f"  [ANALYSE] ⚠️  Pas de données du {date_str} — utilisation de : {os.path.basename(fichier)}")
    with open(fichier, encoding="utf-8") as f:
        return json.load(f)


# ─── SAUVEGARDE RAPPORT ───────────────────────────────────────────────────────

def sauvegarder_rapport(zone: dict, data_source: dict,
                        previsions_risque: dict, date_str: str) -> str:
    """
    Écrit reports/rapport_<slug>_<date>.json.
    Version multi-zones de risk_model.sauvegarder_rapport_json().
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)
    chemin = os.path.join(REPORTS_DIR, f"rapport_{zone['slug']}_{date_str}.json")

    ind           = data_source.get("indicateurs_risque", {})
    niveau_global = previsions_risque.get("actuel", {}).get("niveau_global", "VERT")
    niveaux       = previsions_risque.get("actuel", {}).get("niveaux", {})

    sortie = {
        "date":            date_str,
        "zone":            zone["name"],
        "zone_slug":       zone["slug"],
        "modele":          "risk_model_v4.7.5",
        "rapport_texte": (
            f"Rapport automatisé SAMCAM — {date_str}\n"
            f"Zone          : {zone['name']}\n"
            f"Niveau global : {niveau_global}\n"
            f"Inondation    : {niveaux.get('inondation', '?')}\n"
            f"Sécheresse    : {niveaux.get('secheresse', '?')}\n"
            f"Chaleur       : {niveaux.get('chaleur', '?')}"
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

    return chemin


# ─── ANALYSE D'UNE ZONE ───────────────────────────────────────────────────────

def analyser_zone(zone: dict, date_str: str, verbose: bool = True) -> dict:
    """
    Pipeline complet pour une zone :
      1. Charge les données collectées
      2. Évalue les prévisions de risque (J0 / J+1 / J+3 / J+7)
      3. Sauvegarde le rapport JSON

    Retourne un dict avec {zone, chemin, niveau, ok, erreur}.
    """
    slug = zone["slug"]
    name = zone["name"]

    try:
        from inference.risk_model import evaluer_previsions
    except ImportError:
        from risk_model import evaluer_previsions

    try:
        if verbose:
            print(f"\n  📍 {name}")
            print(f"  [1/3] Chargement des données...")

        data_source = charger_donnees(slug, date_str)

        if verbose:
            print(f"  [2/3] Inférence des risques (J0/J+1/J+3/J+7)...")

        previsions_risque = evaluer_previsions(data_source)
        niveau_global     = previsions_risque.get("actuel", {}).get("niveau_global", "?")
        niveaux           = previsions_risque.get("actuel", {}).get("niveaux", {})

        if verbose:
            print(f"  [3/3] Sauvegarde du rapport...")

        chemin = sauvegarder_rapport(zone, data_source, previsions_risque, date_str)

        if verbose:
            emoji = {"VERT": "🟢", "JAUNE": "🟡", "ORANGE": "🟠", "ROUGE": "🔴"}.get(niveau_global, "⚪")
            print(f"  ✅ {emoji} Niveau : {niveau_global}  "
                  f"| Inond={niveaux.get('inondation','?')} "
                  f"| Séch={niveaux.get('secheresse','?')} "
                  f"| Chal={niveaux.get('chaleur','?')}")
            print(f"  💾 {chemin}")

        return {"zone": name, "slug": slug, "chemin": chemin,
                "niveau": niveau_global, "ok": True, "erreur": None}

    except Exception as e:
        if verbose:
            print(f"  ❌ {name} — {e}")
        return {"zone": name, "slug": slug, "chemin": None,
                "niveau": None, "ok": False, "erreur": str(e)}


# ─── POINT D'ENTRÉE ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SAMCAM — Analyse des risques climatiques par zone"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--zone", metavar="NOM",
        help="Zone à analyser (ex: Kribi, Garoua, Maroua...)"
    )
    group.add_argument(
        "--all", action="store_true",
        help="Analyser toutes les zones"
    )
    parser.add_argument(
        "--date", metavar="YYYY-MM-DD",
        default=datetime.date.today().isoformat(),
        help="Date des données à analyser (défaut : aujourd'hui)"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Sortie minimale"
    )
    args = parser.parse_args()

    date_str = args.date
    verbose  = not args.quiet

    if args.all:
        zones_a_analyser = ZONES
    else:
        try:
            zones_a_analyser = [resolve_zone(args.zone)]
        except ValueError as e:
            print(f"❌ {e}")
            sys.exit(1)

    print("=" * 60)
    print(f"SAMCAM — Analyse des risques")
    print(f"Date    : {date_str}")
    print(f"Zones   : {len(zones_a_analyser)} zone(s)")
    print("=" * 60)

    resultats = []
    for zone in zones_a_analyser:
        r = analyser_zone(zone, date_str, verbose=verbose)
        resultats.append(r)

    ok     = [r for r in resultats if r["ok"]]
    errors = [r for r in resultats if not r["ok"]]

    print("\n" + "=" * 60)
    print(f"✅ {len(ok)} OK   ❌ {len(errors)} erreur(s)")
    for r in ok:
        emoji = {"VERT": "🟢", "JAUNE": "🟡", "ORANGE": "🟠", "ROUGE": "🔴"}.get(r["niveau"], "⚪")
        print(f"  {emoji} {r['zone']:<20} → {r['chemin']}")
    for r in errors:
        print(f"  ❌ {r['zone']:<20} → {r['erreur']}")
    print("=" * 60)

    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
