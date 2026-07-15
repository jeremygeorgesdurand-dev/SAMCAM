#!/usr/bin/env python3
"""
SAMCAM — Collecte quotidienne TOUTES ZONES
==========================================
Script à lancer chaque jour (cron ou scheduler) pour collecter les données
météo + satellitaires de toutes les zones agricoles du Cameroun.

Usage :
    python3 data_collection/collect_all_zones.py
    python3 data_collection/collect_all_zones.py --zones Kribi Garoua
    python3 data_collection/collect_all_zones.py --force   # ignore le cache 24h

Cron quotidien recommandé (6h00 WAT = 5h00 UTC) :
    0 5 * * * cd /chemin/vers/SAMCAM && python3 data_collection/collect_all_zones.py >> logs/collect.log 2>&1

L'ordre de collecte respecte les régions climatiques :
    1. Sud/Littoral (Kribi, Ebolowa, Kumba)
    2. Centre/Ouest (Yaounde_peri, Bafoussam)
    3. Adamaoua/Nord (Ngaoundere, Garoua, Maroua)
"""

import argparse
import importlib.util
import os
import sys
import time
from datetime import datetime, timedelta

# Ajoute la racine du projet au path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── Zones dans l'ordre de collecte recommandé ──────────────────────────────
ALL_ZONES = [
    "Kribi",
    "Ebolowa",
    "Kumba",
    "Yaounde_peri",
    "Bafoussam",
    "Ngaoundere",
    "Garoua",
    "Maroua",
    # Zones agricoles ajoutées
    "Ndop",
    "Foumbot",
    "Kaele",
    "Guider",
    "Meiganga",
    "Mbalmayo",
    "Bafia",
    "Bertoua",
    "Nkongsamba",
    "Buea",
]

DATA_DIR  = os.path.join(ROOT, "data")
LOGS_DIR  = os.path.join(ROOT, "logs")
os.makedirs(DATA_DIR,  exist_ok=True)
os.makedirs(LOGS_DIR,  exist_ok=True)


def _zone_slug(name: str) -> str:
    return name.lower().replace(" ", "_")


def _already_collected_today(zone: str) -> bool:
    """Vérifie si la collecte d'aujourd'hui existe déjà pour cette zone."""
    import glob
    today = datetime.now().strftime("%Y-%m-%d")
    slug  = _zone_slug(zone)
    files = glob.glob(os.path.join(DATA_DIR, f"{slug}_{today}*.json"))
    return len(files) > 0


def collect_zone(zone: str) -> bool:
    """Lance la collecte pour une zone. Retourne True si succès."""
    try:
        # Import dynamique de collect_zone.py
        spec   = importlib.util.spec_from_file_location(
            "collect_zone",
            os.path.join(os.path.dirname(__file__), "collect_zone.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Appelle la fonction principale du module de collecte
        # NB: collect() attend zone_name=<str> ou zone=<dict> — zone ici est
        # une chaîne (nom de zone), donc zone_name= (pas zone=, qui indexerait
        # une string comme un dict et lèverait "string indices must be integers").
        if hasattr(module, "collect"):
            module.collect(zone_name=zone)
        elif hasattr(module, "main"):
            # Simule les args CLI
            old_argv = sys.argv
            sys.argv  = ["collect_zone.py", "--zone", zone]
            module.main()
            sys.argv  = old_argv
        else:
            # Dernier recours : exécute le script comme sous-processus
            import subprocess
            result = subprocess.run(
                [sys.executable,
                 os.path.join(os.path.dirname(__file__), "collect_zone.py"),
                 "--zone", zone],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr[:500])
        return True
    except Exception as e:
        print(f"    ✗ Erreur : {e}")
        return False


def run(zones: list[str], force: bool = False) -> dict:
    """
    Lance la collecte pour chaque zone.
    Retourne un dict { zone: 'ok'|'skipped'|'error' }.
    """
    results = {}
    total   = len(zones)
    print(f"\n{'='*60}")
    print(f"  SAMCAM — Collecte quotidienne  {datetime.now().strftime('%Y-%m-%d %H:%M')} WAT")
    print(f"  {total} zone(s) à collecter")
    print(f"{'='*60}")

    for i, zone in enumerate(zones, 1):
        print(f"\n[{i}/{total}] {zone}")

        if not force and _already_collected_today(zone):
            print(f"    ⏭  Déjà collecté aujourd'hui — ignoré (--force pour forcer)")
            results[zone] = "skipped"
            continue

        t0      = time.time()
        success = collect_zone(zone)
        elapsed = time.time() - t0

        if success:
            print(f"    ✓ OK en {elapsed:.1f}s")
            results[zone] = "ok"
        else:
            results[zone] = "error"

        # Pause courte pour ne pas saturer Open-Meteo / NASA POWER
        if i < total:
            time.sleep(2)

    # ── Résumé ──────────────────────────────────────────────────────────
    ok      = sum(1 for v in results.values() if v == "ok")
    skipped = sum(1 for v in results.values() if v == "skipped")
    errors  = sum(1 for v in results.values() if v == "error")

    print(f"\n{'='*60}")
    print(f"  Résumé : {ok} OK   {skipped} ignorées   {errors} erreurs")
    if errors > 0:
        errs = [z for z, v in results.items() if v == "error"]
        print(f"  Zones en erreur : {', '.join(errs)}")
    print(f"  Terminé à {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Collecte quotidienne SAMCAM — toutes les zones agricoles"
    )
    parser.add_argument(
        "--zones", nargs="+", default=ALL_ZONES,
        help=f"Zones à collecter (défaut : toutes). Valeurs : {', '.join(ALL_ZONES)}"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force la collecte même si les données du jour existent déjà"
    )
    args = parser.parse_args()
    run(zones=args.zones, force=args.force)
