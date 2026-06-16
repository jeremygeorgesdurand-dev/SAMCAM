#!/usr/bin/env bash
# SAMCAM — Installation du cron de collecte automatique
#
# Lance le pipeline complet toutes les 6 heures.
# Exécuter UNE SEULE FOIS pour installer le crontab :
#
#   bash data_collection/scheduler_cron.sh
#
# Pour désactiver :
#   crontab -e   # supprimer la ligne SAMCAM

set -e

# Chemin absolu vers la racine du projet
PROJECT_DIR="$(cd "$(dirname "$0")/.."; pwd)"
PYTHON="$(which python3)"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/samcam_cron.log"

# Créer le dossier logs si besoin
mkdir -p "$LOG_DIR"

# La ligne cron à installer (toutes les 6h : 0h, 6h, 12h, 18h)
CRON_LINE="0 */6 * * * cd $PROJECT_DIR && $PYTHON inference/pipeline_complet.py --no-browser >> $LOG_FILE 2>&1"

echo "================================================"
echo " SAMCAM — Installation du cron automatique"
echo "================================================"
echo ""
echo " Projet  : $PROJECT_DIR"
echo " Python  : $PYTHON"
echo " Logs    : $LOG_FILE"
echo " Fréquence : toutes les 6h (0h, 6h, 12h, 18h)"
echo ""

# Vérifier si la ligne est déjà présente
if crontab -l 2>/dev/null | grep -q "pipeline_complet.py"; then
  echo "⚠️  Un cron SAMCAM existe déjà :"
  crontab -l 2>/dev/null | grep "pipeline_complet.py"
  echo ""
  read -p "Voulez-vous le remplacer ? [o/N] " confirm
  if [ "$confirm" != "o" ] && [ "$confirm" != "O" ]; then
    echo "Annulé."
    exit 0
  fi
  # Supprimer l'ancien
  crontab -l 2>/dev/null | grep -v "pipeline_complet.py" | crontab -
fi

# Ajouter la nouvelle ligne
(crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -

echo "✅ Cron installé avec succès !"
echo ""
echo " Vérification :"
crontab -l | grep "pipeline_complet.py"
echo ""
echo " Pour suivre les logs en temps réel :"
echo "   tail -f $LOG_FILE"
echo ""
echo " Pour désactiver :"
echo "   crontab -e   # supprimer la ligne SAMCAM"
