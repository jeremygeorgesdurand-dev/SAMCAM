#!/usr/bin/env bash
# SAMCAM v3.0 — Installation du cron de collecte automatique multi-zones
#
# Lance la collecte sur toutes les zones agricoles, puis le pipeline d'analyse.
#
# Fréquence :
#   - Collecte multi-zones  : toutes les 6h (0h, 6h, 12h, 18h)
#   - Pipeline d'analyse    : toutes les 6h, 30 min après la collecte
#
# Exécuter UNE SEULE FOIS pour installer le crontab :
#
#   bash data_collection/scheduler_cron.sh
#
# Pour ne collecter qu'une seule zone :
#   bash data_collection/scheduler_cron.sh --zone Garoua
#
# Pour désactiver :
#   crontab -e   # supprimer les lignes SAMCAM

set -e

# ── ARGUMENTS ──────────────────────────────────────────────────────────────────
ZONE_ARG=""
for arg in "$@"; do
  case $arg in
    --zone=*) ZONE_ARG="--zone ${arg#*=}" ;;
    --zone)   shift; ZONE_ARG="--zone $1" ;;
  esac
done

# ── CHEMINS ────────────────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")/.."; pwd)"
PYTHON="$(which python3)"
LOG_DIR="$PROJECT_DIR/logs"
LOG_COLLECT="$LOG_DIR/samcam_collect.log"
LOG_PIPELINE="$LOG_DIR/samcam_pipeline.log"

mkdir -p "$LOG_DIR"

# ── LIGNES CRON ────────────────────────────────────────────────────────────────
# Collecte multi-zones : toutes les 6h
CRON_COLLECT="0 */6 * * * cd $PROJECT_DIR && $PYTHON data_collection/collect_zone.py $ZONE_ARG >> $LOG_COLLECT 2>&1"
# Pipeline d'analyse (inférence + rapport) : 30 min après la collecte
CRON_PIPELINE="30 */6 * * * cd $PROJECT_DIR && $PYTHON inference/pipeline_complet.py --no-browser >> $LOG_PIPELINE 2>&1"

# ── AFFICHAGE ──────────────────────────────────────────────────────────────────
echo "================================================"
echo " SAMCAM v3.0 — Cron multi-zones agricoles"
echo "================================================"
echo ""
echo " Projet    : $PROJECT_DIR"
echo " Python    : $PYTHON"
echo " Logs      : $LOG_DIR/"
echo " Fréquence : toutes les 6h (0h, 6h, 12h, 18h)"
if [ -n "$ZONE_ARG" ]; then
  echo " Zone      : ${ZONE_ARG#--zone }"
else
  echo " Zones     : TOUTES les zones agricoles"
fi
echo ""
echo " Planning :"
echo "   :00  Collecte multi-zones  (collect_zone.py)"
echo "   :30  Pipeline d'analyse    (pipeline_complet.py)"
echo ""

# ── VÉRIFICATION CRON EXISTANT ────────────────────────────────────────────────
CRON_EXISTANT=$(crontab -l 2>/dev/null | grep -E "collect_zone\.py|pipeline_complet\.py" || true)
if [ -n "$CRON_EXISTANT" ]; then
  echo "⚠️  Des crons SAMCAM existent déjà :"
  echo "$CRON_EXISTANT"
  echo ""
  read -p "Voulez-vous les remplacer ? [o/N] " confirm
  if [ "$confirm" != "o" ] && [ "$confirm" != "O" ]; then
    echo "Annulé."
    exit 0
  fi
  # Supprimer les anciennes lignes SAMCAM (collect + pipeline)
  crontab -l 2>/dev/null \
    | grep -v "collect_zone.py" \
    | grep -v "collect_kribi.py" \
    | grep -v "pipeline_complet.py" \
    | crontab -
  echo "🗑️  Anciens crons supprimés."
fi

# ── INSTALLATION ──────────────────────────────────────────────────────────────
(
  crontab -l 2>/dev/null
  echo "# SAMCAM — collecte multi-zones"
  echo "$CRON_COLLECT"
  echo "# SAMCAM — pipeline d'analyse"
  echo "$CRON_PIPELINE"
) | crontab -

echo "✅ Crons installés avec succès !"
echo ""
echo " Vérification :"
crontab -l | grep -E "SAMCAM|collect_zone|pipeline_complet"
echo ""
echo "═══════════════════════════════════════════════"
echo " Commandes utiles"
echo "═══════════════════════════════════════════════"
echo ""
echo " Suivre la collecte en temps réel :"
echo "   tail -f $LOG_COLLECT"
echo ""
echo " Suivre le pipeline en temps réel :"
echo "   tail -f $LOG_PIPELINE"
echo ""
echo " Lancer une collecte manuelle (toutes les zones) :"
echo "   python3 $PROJECT_DIR/data_collection/collect_zone.py"
echo ""
echo " Lancer une collecte manuelle (une zone) :"
echo "   python3 $PROJECT_DIR/data_collection/collect_zone.py --zone Garoua"
echo ""
echo " Lister les zones disponibles :"
echo "   python3 $PROJECT_DIR/data_collection/collect_zone.py --list"
echo ""
echo " Désactiver les crons :"
echo "   crontab -e   # supprimer les lignes SAMCAM"
echo ""
