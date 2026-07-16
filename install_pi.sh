#!/usr/bin/env bash
# ============================================================
# SAMCAM — Installation automatique sur Raspberry Pi (2 Go RAM)
# ============================================================
# Usage : bash install_pi.sh
#
# Ce script est idempotent : relancez-le sans risque après un `git pull`
# pour mettre à jour et redémarrer les services.
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
echo -e "${BLUE}\n══════════════════════════════════════════════"
echo -e "  SAMCAM — Installation Raspberry Pi"
echo -e "══════════════════════════════════════════════${NC}\n"

# ── 1. Swap — indispensable à 2 Go de RAM, filet de sécurité anti-OOM ────────
CURRENT_SWAP_MB=$(free -m | awk '/^Swap:/{print $2}')
if [ "${CURRENT_SWAP_MB:-0}" -lt 1024 ]; then
    echo -e "${YELLOW}[swap]${NC} Swap actuel: ${CURRENT_SWAP_MB:-0} Mo — augmentation à 2048 Mo recommandée"
    if [ -f /etc/dphys-swapfile ]; then
        sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
        sudo dphys-swapfile setup
        sudo dphys-swapfile swapon
        echo -e "${GREEN}[swap]${NC} Swap porté à 2048 Mo"
    else
        echo -e "${YELLOW}[swap]${NC} dphys-swapfile absent (pas Raspberry Pi OS ?) — configurez le swap manuellement."
    fi
else
    echo -e "${GREEN}[swap]${NC} Swap déjà suffisant (${CURRENT_SWAP_MB} Mo)"
fi

# ── 2. Docker Engine (pas Docker Desktop — overhead minimal sur Linux natif) ─
if ! command -v docker >/dev/null 2>&1; then
    echo -e "${YELLOW}[docker]${NC} Installation de Docker Engine..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    echo -e "${GREEN}[docker]${NC} Installé. Vous devrez peut-être vous reconnecter (nouveau groupe 'docker')."
else
    echo -e "${GREEN}[docker]${NC} Déjà installé ($(docker --version))"
fi

if ! docker compose version >/dev/null 2>&1; then
    echo -e "${RED}[docker compose]${NC} Le plugin 'docker compose' est introuvable — réinstallez Docker via get.docker.com"
    exit 1
fi

# ── 2b. Ollama natif (PAS dans Docker — partagé avec les autres projets du Pi) ─
if ! command -v ollama >/dev/null 2>&1; then
    echo -e "${RED}[ollama]${NC} Ollama n'est pas installé/trouvé sur ce Pi."
    echo -e "${RED}[ollama]${NC} SAMCAM suppose un Ollama natif partagé — installez-le d'abord :"
    echo -e "${RED}[ollama]${NC}   curl -fsSL https://ollama.com/install.sh | sh"
    exit 1
fi
if curl -fsS --max-time 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo -e "${GREEN}[ollama]${NC} Service Ollama natif joignable sur le port 11434"
    if curl -fsS --max-time 3 http://localhost:11434/api/tags | grep -q "qwen3:0.6b"; then
        echo -e "${GREEN}[ollama]${NC} Modèle qwen3:0.6b déjà présent"
    else
        echo -e "${YELLOW}[ollama]${NC} qwen3:0.6b introuvable dans 'ollama list' — vérifiez le nom exact"
        echo -e "${YELLOW}[ollama]${NC} et ajustez OLLAMA_MODEL dans docker-compose.yml si besoin."
    fi
else
    echo -e "${YELLOW}[ollama]${NC} Ollama installé mais pas encore démarré/joignable — démarrez le service :"
    echo -e "${YELLOW}[ollama]${NC}   sudo systemctl start ollama"
fi

# ── 3. Tailscale (accès distant, reste natif — voir docs/RAPPORT_SAMCAM.md §9.5) ─
# Installe et active le Funnel automatiquement dès que possible, comme server/start.sh
# le fait côté Mac. Seule l'authentification initiale (`tailscale up`) reste manuelle :
# elle nécessite de visiter un lien dans un navigateur, impossible à automatiser sur
# un appareil headless sans clé d'auth pré-générée.
if ! command -v tailscale >/dev/null 2>&1; then
    echo -e "${YELLOW}[tailscale]${NC} Installation de Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
else
    echo -e "${GREEN}[tailscale]${NC} Déjà installé"
fi

if tailscale status >/dev/null 2>&1; then
    echo -e "${GREEN}[tailscale]${NC} Déjà connecté au tailnet"
    if sudo tailscale funnel --bg 8000 >/dev/null 2>&1; then
        FUNNEL_URL=$(tailscale funnel status 2>/dev/null | grep -o 'https://[^ ]*\.ts\.net[^ ]*' | head -1)
        echo -e "${GREEN}[funnel]${NC} API publiée sur Internet : ${FUNNEL_URL:-voir « tailscale funnel status »}"
    else
        echo -e "${YELLOW}[funnel]${NC} Activation automatique du Funnel impossible — lancez une fois : sudo tailscale funnel --bg 8000"
    fi
else
    echo -e "${YELLOW}[tailscale]${NC} Pas encore authentifié sur ce Pi — étape manuelle unique requise :"
    echo -e "${YELLOW}[tailscale]${NC}   sudo tailscale up --hostname=cameroun"
    echo -e "${YELLOW}[tailscale]${NC}   (suivez le lien affiché pour authentifier l'appareil, une seule fois)"
    echo -e "${YELLOW}[tailscale]${NC} Puis relancez ce script — le Funnel s'activera automatiquement ensuite."
fi

# ── 4. Secrets — génère server/.env.docker (format KEY=VALUE) depuis .env.local
#    (server/.env.local est en syntaxe bash `export KEY=VALUE` pour start.sh ;
#    Docker Compose attend du KEY=VALUE brut, sans `export`.)
mkdir -p server
if [ -f server/.env.local ]; then
    sed 's/^export //' server/.env.local > server/.env.docker
    echo -e "${GREEN}[secrets]${NC} server/.env.docker généré depuis server/.env.local"
else
    touch server/.env.docker
    echo -e "${YELLOW}[secrets]${NC} server/.env.local absent — server/.env.docker vide créé (WhatsApp désactivé)."
    echo -e "${YELLOW}[secrets]${NC} Pour l'activer : créez server/.env.local (export WHATSAPP_ACCESS_TOKEN=..., etc.) puis relancez ce script."
fi

# ── 5. Clé de service Google Earth Engine (nécessaire au conteneur collecteur) ─
GEE_KEY_DIR="${HOME}/.config/gee"
if [ ! -f "${GEE_KEY_DIR}/kribi-key.json" ]; then
    echo -e "${YELLOW}[gee]${NC} Clé GEE introuvable dans ${GEE_KEY_DIR}/kribi-key.json"
    echo -e "${YELLOW}[gee]${NC} Copiez-y votre clé de service Earth Engine avant la première collecte."
fi
export GEE_KEY_DIR

# ── 6. Répertoires nécessaires (partagés avec les conteneurs via bind-mount) ──
mkdir -p data reports logs dashboard models data/predictions

# ── 7. Build + démarrage ──────────────────────────────────────────────────────
echo -e "${GREEN}[docker]${NC} Construction des images (peut prendre plusieurs minutes sur Pi)..."
docker compose build

echo -e "${GREEN}[docker]${NC} Démarrage des services (api, collector)..."
docker compose up -d

echo -e "\n${BLUE}══════════════════════════════════════════════"
echo -e "  ✅ SAMCAM est démarré"
echo -e "══════════════════════════════════════════════${NC}"
echo -e "  API locale        : http://localhost:8000"
echo -e "  Statut conteneurs : docker compose ps"
echo -e "  Logs              : docker compose logs -f"
echo -e "  Arrêt             : docker compose down"
echo -e "  Mise à jour       : git pull && bash install_pi.sh"
if command -v tailscale >/dev/null 2>&1 && tailscale status >/dev/null 2>&1; then
    echo -e "  Accès Internet    : ${FUNNEL_URL:-voir « tailscale funnel status »}"
else
    echo -e "  ${YELLOW}Accès Internet pas encore actif${NC} — authentifiez Tailscale (voir ci-dessus) puis relancez ce script."
fi
echo ""
