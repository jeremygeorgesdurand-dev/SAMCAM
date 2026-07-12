#!/usr/bin/env python3
"""
SAMCAM — Évaluation des modèles zonaux contre des ÉVÉNEMENTS RÉELS documentés.

Les labels d'entraînement sont générés par des règles climatologiques
(build_labels.py) : l'AUC de validation croisée mesure donc la capacité à
reproduire ces règles, pas à détecter de vrais événements. Ce script mesure
la fiabilité RÉELLE : pour chaque événement documenté (EM-DAT, OCHA,
ReliefWeb), le modèle aurait-il alerté ?

Métriques par événement :
  - detecte      : max(proba) sur la fenêtre de l'événement ≥ seuil du modèle
  - proba_max    : pic de probabilité pendant l'événement
  - premier_depassement : première date où proba ≥ seuil (préavis)
  - taux_fausse_alerte  : fraction des AUTRES années où la même fenêtre
    calendaire dépasse aussi le seuil (contexte : un modèle qui alerte
    chaque année à cette saison ne "détecte" rien)

Les signalements communautaires (data/community_reports/signalements.jsonl)
sont automatiquement ajoutés comme événements à vérifier (fenêtre ±3 jours).

Usage :
    python training/evaluate_real_events.py
    python training/evaluate_real_events.py --zone Maroua
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "inference"))

from infer_zonal import (  # noqa: E402
    load_model,
    compute_derived_features,
    RISK_FEATURES,
)

DATA_DIR = ROOT / "data" / "historical"
SIGNALEMENTS_PATH = ROOT / "data" / "community_reports" / "signalements.jsonl"
RAPPORT_PATH = ROOT / "training" / "reports" / "evaluation_evenements_reels.json"

# ---------------------------------------------------------------------------
# Événements réels documentés (sources : EM-DAT, OCHA, ReliefWeb, presse)
# ---------------------------------------------------------------------------
EVENEMENTS = [
    # Inondations majeures de l'Extrême-Nord, août-sept 2012 — crues du
    # Logone + lâchers du barrage de Lagdo, des dizaines de morts, des
    # dizaines de milliers de déplacés (EM-DAT 2012-0448).
    {"zone": "Maroua", "risque": "inondation",
     "debut": "2012-08-15", "fin": "2012-09-30",
     "nom": "Inondations Extrême-Nord 2012 (Logone/Lagdo)"},
    {"zone": "Garoua", "risque": "inondation",
     "debut": "2012-08-15", "fin": "2012-09-30",
     "nom": "Inondations Nord 2012 (Bénoué/Lagdo)"},

    # Inondations Extrême-Nord août-sept 2020 (ReliefWeb/OCHA :
    # Logone-et-Chari, Mayo-Danay, >160 000 personnes affectées).
    {"zone": "Maroua", "risque": "inondation",
     "debut": "2020-08-01", "fin": "2020-09-15",
     "nom": "Inondations Extrême-Nord 2020"},

    # Inondations Extrême-Nord août-oct 2022 — parmi les pires depuis des
    # décennies (OCHA, >300 000 personnes affectées).
    {"zone": "Maroua", "risque": "inondation",
     "debut": "2022-08-01", "fin": "2022-10-15",
     "nom": "Inondations Extrême-Nord 2022"},
    {"zone": "Garoua", "risque": "inondation",
     "debut": "2022-08-01", "fin": "2022-10-15",
     "nom": "Inondations Nord 2022"},

    # Pluies torrentielles et éboulement meurtrier de Bafoussam,
    # 28 octobre 2019 (~43 morts, quartier Gouache).
    {"zone": "Bafoussam", "risque": "inondation",
     "debut": "2019-10-20", "fin": "2019-10-30",
     "nom": "Pluies torrentielles Bafoussam oct. 2019"},

    # Canicule sahélienne de mars-avril 2024 — étude d'attribution WWA,
    # >45 °C dans le nord du Cameroun.
    {"zone": "Maroua", "risque": "chaleur",
     "debut": "2024-03-20", "fin": "2024-04-20",
     "nom": "Canicule sahélienne 2024"},
    {"zone": "Garoua", "risque": "chaleur",
     "debut": "2024-03-20", "fin": "2024-04-20",
     "nom": "Canicule sahélienne 2024"},

    # Vague de chaleur exceptionnelle du Sahel, avril 2010.
    {"zone": "Maroua", "risque": "chaleur",
     "debut": "2010-04-01", "fin": "2010-04-30",
     "nom": "Canicule Sahel avril 2010"},

    # Sécheresse / crise alimentaire du Sahel 2011-2012 (saison des pluies
    # 2011 très déficitaire dans l'Extrême-Nord).
    {"zone": "Maroua", "risque": "secheresse",
     "debut": "2011-11-01", "fin": "2012-05-31",
     "nom": "Sécheresse Sahel 2011-2012"},
]

_TYPE_VERS_RISQUE = {
    "inondation": "inondation",
    "secheresse": "secheresse",
    "chaleur":    "chaleur",
}


def charger_signalements() -> list:
    """Convertit les signalements communautaires en événements à évaluer."""
    if not SIGNALEMENTS_PATH.is_file():
        return []
    evenements = []
    with open(SIGNALEMENTS_PATH, encoding="utf-8") as f:
        for ligne in f:
            if not ligne.strip():
                continue
            s = json.loads(ligne)
            risque = _TYPE_VERS_RISQUE.get(s.get("type_evenement"))
            if risque is None:
                continue  # "autre" : pas de modèle associé
            try:
                d = datetime.strptime(s["date_observation"], "%Y-%m-%d")
            except (KeyError, ValueError):
                continue
            evenements.append({
                "zone":   s["zone"],
                "risque": risque,
                "debut":  (d - timedelta(days=3)).strftime("%Y-%m-%d"),
                "fin":    (d + timedelta(days=3)).strftime("%Y-%m-%d"),
                "nom":    f"Signalement communautaire du {s['date_observation']}",
            })
    return evenements


def charger_historique(zone: str):
    path = DATA_DIR / f"{zone}_historical.csv"
    if not path.is_file():
        return None
    df = pd.read_csv(path, low_memory=False)
    date_col = next((c for c in ("date", "Date", "time") if c in df.columns), None)
    if date_col is None:
        return None
    df["date"] = pd.to_datetime(df[date_col], errors="coerce")
    return df.sort_values("date").dropna(subset=["date"]).reset_index(drop=True)


def _probas_sur_fenetre(model, df, cols, masque) -> np.ndarray:
    X = df.loc[masque, cols].copy()
    if X.empty:
        return np.array([])
    for col in X.columns:
        if X[col].isna().any():
            X[col] = X[col].fillna(df[col].median())
    return model.predict_proba(X)[:, 1]


def evaluer_evenement(ev: dict, cache_df: dict) -> dict:
    zone, risque = ev["zone"], ev["risque"]

    bundle = load_model(zone, risque)
    if bundle is None:
        return {**ev, "statut": "NO_MODEL"}

    if zone not in cache_df:
        cache_df[zone] = charger_historique(zone)
    df = cache_df[zone]
    if df is None:
        return {**ev, "statut": "NO_DATA"}

    df = compute_derived_features(df)
    seuil = float(bundle.get("threshold", 0.5))
    features = bundle.get("features_used") or bundle.get("features") \
        or RISK_FEATURES[risque]
    cols = [f for f in features if f in df.columns]
    if len(cols) < 3:
        return {**ev, "statut": "INSUFFICIENT_FEATURES"}

    debut = pd.Timestamp(ev["debut"])
    fin   = pd.Timestamp(ev["fin"])
    masque_ev = (df["date"] >= debut) & (df["date"] <= fin)
    if not masque_ev.any():
        return {**ev, "statut": "HORS_COUVERTURE"}

    probas = _probas_sur_fenetre(bundle["model"], df, cols, masque_ev)
    if probas.size == 0:
        return {**ev, "statut": "NO_DATA"}

    dates_ev = df.loc[masque_ev, "date"].reset_index(drop=True)
    au_dessus = probas >= seuil
    premier = (dates_ev[au_dessus.argmax()].strftime("%Y-%m-%d")
               if au_dessus.any() else None)

    # Comparaison inter-annuelle : même fenêtre calendaire dans les autres
    # années. Deux lectures complémentaires :
    #   - taux_fausse_alerte : fraction des autres années où le max dépasse
    #     aussi le seuil (un modèle saisonnier alerte "tous les ans")
    #   - percentile_annee : rang de la proba MOYENNE de l'année de
    #     l'événement parmi toutes les années — mesure si le modèle
    #     distingue vraiment cette année-là d'une saison ordinaire
    annees_alerte, annees_testees = 0, 0
    moyennes_autres = []
    for annee in sorted(df["date"].dt.year.unique()):
        if annee == debut.year:
            continue
        try:
            d0 = debut.replace(year=annee)
            d1 = fin.replace(year=annee + (fin.year - debut.year))
        except ValueError:
            continue  # 29 février etc.
        masque_an = (df["date"] >= d0) & (df["date"] <= d1)
        if masque_an.sum() < (fin - debut).days * 0.8:
            continue  # fenêtre incomplète (bord du jeu de données)
        p = _probas_sur_fenetre(bundle["model"], df, cols, masque_an)
        if p.size == 0:
            continue
        annees_testees += 1
        moyennes_autres.append(float(p.mean()))
        if p.max() >= seuil:
            annees_alerte += 1

    percentile_annee = (
        round(float(np.mean([m < probas.mean() for m in moyennes_autres])), 2)
        if moyennes_autres else None
    )

    return {
        **ev,
        "statut":               "OK",
        "detecte":              bool(au_dessus.any()),
        "proba_max":            round(float(probas.max()), 3),
        "proba_moyenne":        round(float(probas.mean()), 3),
        "seuil":                round(seuil, 3),
        "jours_au_dessus":      int(au_dessus.sum()),
        "jours_fenetre":        int(probas.size),
        "premier_depassement":  premier,
        "taux_fausse_alerte":   round(annees_alerte / annees_testees, 2)
                                if annees_testees else None,
        "percentile_annee":     percentile_annee,
        "annees_testees":       annees_testees,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zone", help="Limiter l'évaluation à une zone")
    args = parser.parse_args()

    evenements = EVENEMENTS + charger_signalements()
    if args.zone:
        evenements = [e for e in evenements
                      if e["zone"].lower() == args.zone.lower()]
    if not evenements:
        print("Aucun événement à évaluer.")
        return

    cache_df: dict = {}
    resultats = []
    print(f"\n{'='*100}")
    print("ÉVALUATION CONTRE ÉVÉNEMENTS RÉELS DOCUMENTÉS")
    print(f"{'='*100}\n")

    for ev in evenements:
        r = evaluer_evenement(ev, cache_df)
        resultats.append(r)
        if r["statut"] != "OK":
            print(f"⚠️  {ev['nom']:<48} [{ev['zone']}/{ev['risque']}] → {r['statut']}")
            continue
        icone = "✅" if r["detecte"] else "❌"
        fa = (f"fausses alertes {r['taux_fausse_alerte']:.0%} "
              f"({r['annees_testees']} ans)"
              if r["taux_fausse_alerte"] is not None else "fausses alertes n/a")
        print(f"{icone} {ev['nom']:<48} [{ev['zone']}/{ev['risque']}]")
        pctl = (f"percentile {r['percentile_annee']:.0%}"
                if r["percentile_annee"] is not None else "percentile n/a")
        print(f"    proba max {r['proba_max']:.2f} (seuil {r['seuil']:.2f}) — "
              f"{r['jours_au_dessus']}/{r['jours_fenetre']} j au-dessus — "
              f"1er dépassement : {r['premier_depassement'] or '—'} — {fa} — {pctl}")

    ok = [r for r in resultats if r["statut"] == "OK"]
    detectes = [r for r in ok if r["detecte"]]
    print(f"\n{'-'*100}")
    print(f"BILAN : {len(detectes)}/{len(ok)} événements détectés"
          + (f" — taux de détection {len(detectes)/len(ok):.0%}" if ok else ""))
    fa_vals = [r["taux_fausse_alerte"] for r in ok
               if r["taux_fausse_alerte"] is not None]
    if fa_vals:
        print(f"Taux de fausse alerte moyen (même saison, autres années) : "
              f"{np.mean(fa_vals):.0%}")
    pctl_vals = [r["percentile_annee"] for r in ok
                 if r["percentile_annee"] is not None]
    if pctl_vals:
        print(f"Percentile moyen de l'année de l'événement : "
              f"{np.mean(pctl_vals):.0%} "
              f"(>50% = le modèle distingue les années à événement)")
    print(f"{'-'*100}\n")

    RAPPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RAPPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "date_evaluation": datetime.now().isoformat(timespec="seconds"),
            "resultats": resultats,
        }, f, ensure_ascii=False, indent=2)
    print(f"Rapport JSON : {RAPPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
