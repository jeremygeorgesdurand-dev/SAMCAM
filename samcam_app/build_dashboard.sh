#!/usr/bin/env bash
# Reconstruit le build web Flutter servi comme écran local (route /dashboard
# de server/api.py) — le même code que `flutter run -d chrome`, compilé en
# statique (HTML/JS) pour être servi par FastAPI sans dépendance à Flutter
# sur la Raspberry Pi.
#
# À relancer après toute modification de l'app, puis synchroniser
# build/web/ vers le Pi (inclus automatiquement par le rsync habituel).
set -euo pipefail
cd "$(dirname "$0")"
flutter build web --release --base-href /dashboard/ --no-tree-shake-icons
echo "OK : build/web/ prêt, servi sur /dashboard par l'API"
