#!/usr/bin/env python3
"""
SAMCAM — Envoi d'alertes push FCM quand une zone passe en ORANGE/ROUGE.

Lit le cache de prédictions (data/predictions/latest.json) et envoie une
notification Firebase Cloud Messaging sur le topic de chaque zone dont le
niveau d'alerte atteint le seuil. Les téléphones abonnés au topic
("zone_kribi", "zone_maroua"…) reçoivent l'alerte MÊME APP FERMÉE —
contrairement aux notifications locales actuelles de l'app.

Prérequis (voir docs/NOTIFICATIONS_PUSH_FCM.md) :
  1. Un projet Firebase avec l'app Android déclarée
  2. Une clé de compte de service : server/firebase-service-account.json
     (Console Firebase → Paramètres → Comptes de service → Générer une clé)
  3. pip install firebase-admin
  4. Côté app : firebase_messaging + abonnement aux topics des zones suivies

Usage :
    python server/send_push_alerts.py            # envoie si ORANGE/ROUGE
    python server/send_push_alerts.py --dry-run  # affiche sans envoyer
    python server/send_push_alerts.py --seuil ROUGE

À planifier en cron juste après compute_daily_predictions.py, ex. :
    30 6 * * * cd /path/SAMCAM && .venv/bin/python server/send_push_alerts.py
"""

import argparse
import json
import os
import sys
import unicodedata

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PRED_CACHE_PATH = os.path.join(ROOT, "data", "predictions", "latest.json")
SERVICE_ACCOUNT_PATH = os.path.join(ROOT, "server", "firebase-service-account.json")
ETAT_PATH = os.path.join(ROOT, "data", "predictions", "push_state.json")

NIVEAUX = ["VERT", "JAUNE", "ORANGE", "ROUGE"]
LABELS = {
    "ORANGE": "Risque modéré",
    "ROUGE":  "Risque élevé",
}
RISQUE_LABELS = {
    "score_inondation": "inondation",
    "score_secheresse": "sécheresse",
    "score_chaleur":    "chaleur",
}


def topic_pour_zone(zone: str) -> str:
    """'Yaounde_peri' → 'zone_yaounde_peri' (FCM n'accepte que [a-zA-Z0-9-_.~%])."""
    s = unicodedata.normalize("NFKD", zone).encode("ascii", "ignore").decode()
    return "zone_" + s.lower().replace(" ", "_")


def _niveau_depuis_scores(scores: dict) -> str:
    best = max((v for v in scores.values() if isinstance(v, (int, float))),
               default=0.0)
    if best >= 0.70: return "ROUGE"
    if best >= 0.45: return "ORANGE"
    if best >= 0.25: return "JAUNE"
    return "VERT"


def charger_alertes(seuil: str) -> list:
    """Extrait du cache les zones dont le niveau J0 atteint le seuil.

    Structure du cache (compute_daily_predictions.py) :
      { "<Zone>": { "risques": { "<risque>": { "j0": {"score": X, ...}, ... } } } }
    """
    with open(PRED_CACHE_PATH, encoding="utf-8") as f:
        cache = json.load(f)

    seuil_idx = NIVEAUX.index(seuil)
    alertes = []
    for zone, contenu in cache.items():
        if not isinstance(contenu, dict):
            continue
        risques = contenu.get("risques", {})
        scores_j0 = {
            f"score_{nom}": bloc.get("j0", {}).get("score")
            for nom, bloc in risques.items()
            if isinstance(bloc, dict)
            and bloc.get("j0", {}).get("status") == "OK"
        }
        scores_j0 = {k: v for k, v in scores_j0.items() if v is not None}
        if not scores_j0:
            continue
        niveau = _niveau_depuis_scores(scores_j0)
        if NIVEAUX.index(niveau) < seuil_idx:
            continue
        pire = max(scores_j0, key=lambda k: scores_j0.get(k) or 0)
        alertes.append({
            "zone":    zone,
            "niveau":  niveau,
            "risque":  RISQUE_LABELS.get(pire, pire),
            "score":   scores_j0[pire],
        })
    return alertes


def filtrer_deja_notifiees(alertes: list) -> list:
    """Ne renvoie pas la même alerte (zone+niveau) deux jours de suite."""
    etat = {}
    if os.path.isfile(ETAT_PATH):
        try:
            with open(ETAT_PATH, encoding="utf-8") as f:
                etat = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    a_envoyer = [a for a in alertes if etat.get(a["zone"]) != a["niveau"]]
    nouvel_etat = {a["zone"]: a["niveau"] for a in alertes}
    with open(ETAT_PATH, "w", encoding="utf-8") as f:
        json.dump(nouvel_etat, f, ensure_ascii=False, indent=2)
    return a_envoyer


def envoyer(alertes: list, dry_run: bool) -> None:
    if dry_run:
        for a in alertes:
            print(f"[dry-run] {topic_pour_zone(a['zone'])} : "
                  f"{a['niveau']} — {a['risque']} {a['score']:.0%}")
        return

    if not os.path.isfile(SERVICE_ACCOUNT_PATH):
        sys.exit(
            f"Clé de compte de service absente : {SERVICE_ACCOUNT_PATH}\n"
            "Suivez docs/NOTIFICATIONS_PUSH_FCM.md pour la générer."
        )

    import firebase_admin
    from firebase_admin import credentials, messaging

    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred)

    for a in alertes:
        message = messaging.Message(
            topic=topic_pour_zone(a["zone"]),
            notification=messaging.Notification(
                title=f"⚠️ {LABELS.get(a['niveau'], a['niveau'])} — {a['zone']}",
                body=(f"Risque de {a['risque']} : {a['score']:.0%}. "
                      "Ouvrez SAMCAM pour les détails et les prévisions."),
            ),
            data={"zone": a["zone"], "niveau": a["niveau"]},
            android=messaging.AndroidConfig(priority="high"),
        )
        message_id = messaging.send(message)
        print(f"✅ {a['zone']} ({a['niveau']}) → {message_id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Afficher les alertes sans les envoyer")
    parser.add_argument("--seuil", default="ORANGE",
                        choices=["JAUNE", "ORANGE", "ROUGE"],
                        help="Niveau minimum déclenchant une notification")
    args = parser.parse_args()

    if not os.path.isfile(PRED_CACHE_PATH):
        sys.exit(f"Cache de prédictions absent : {PRED_CACHE_PATH}\n"
                 "Lancez d'abord inference/compute_daily_predictions.py")

    alertes = charger_alertes(args.seuil)
    if not alertes:
        print(f"Aucune zone au niveau {args.seuil} ou plus — rien à envoyer.")
        return

    # En dry-run, ne pas toucher l'état de déduplication
    if not args.dry_run:
        alertes = filtrer_deja_notifiees(alertes)
        if not alertes:
            print("Toutes les alertes actives ont déjà été notifiées hier — rien à envoyer.")
            return

    envoyer(alertes, args.dry_run)


if __name__ == "__main__":
    main()
