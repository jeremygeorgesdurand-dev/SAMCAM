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

# ── 0. Secrets locaux (server/.env.local, JAMAIS committé — voir .gitignore) ──
# Permet de définir une fois TAILSCALE_AUTHKEY, SAMCAM_HOSTNAME et les secrets
# WhatsApp dans ce fichier plutôt que de les retaper sur la ligne de commande à
# chaque exécution. Ne JAMAIS mettre ces valeurs dans un fichier suivi par git
# (une clé Tailscale committée permettrait à quiconque a accès au dépôt de
# rejoindre votre tailnet).
if [ -f server/.env.local ]; then
    set +u
    # shellcheck disable=SC1091
    source server/.env.local
    set -u
    echo -e "${GREEN}[secrets]${NC} server/.env.local chargé"
fi

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
    if curl -fsS --max-time 3 http://localhost:11434/api/tags | grep -qi "qwen3:0\.6b"; then
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
# le fait côté Mac.
#
# Deux modes d'authentification pour `tailscale up` :
#   - Automatique (recommandé pour déployer plusieurs Pi) : ajoutez
#     "export TAILSCALE_AUTHKEY=tskey-auth-..." dans server/.env.local (voir
#     étape 0 ci-dessus — jamais dans git). Clé à générer depuis
#     https://login.tailscale.com/admin/settings/keys — aucun clic navigateur
#     requis ensuite, idéal pour flasher plusieurs cartes SD avec ce script.
#   - Manuel (par défaut, sans clé) : nécessite de visiter un lien affiché dans un
#     navigateur, une seule fois par appareil.
#
# SAMCAM_HOSTNAME (défaut "cameroun") : nom de la machine sur le tailnet, doit être
# unique — indispensable à changer si vous déployez plusieurs stations
# (ex: SAMCAM_HOSTNAME=maroua bash install_pi.sh).
SAMCAM_HOSTNAME="${SAMCAM_HOSTNAME:-cameroun}"

# Prompts interactifs (déploiement multi-Pi) : si le Pi n'est pas encore
# authentifié et qu'on a un vrai terminal (pas un script automatisé), propose
# de saisir la clé et le nom d'hôte sur place plutôt que d'attendre un
# copier-coller dans server/.env.local. Sans terminal interactif ([ -t 0 ]
# faux), ce bloc est sauté silencieusement — le comportement précédent
# (variables d'env ou lien manuel) reste inchangé.
if ! tailscale status >/dev/null 2>&1 && [ -t 0 ]; then
    if [ -z "${TAILSCALE_AUTHKEY:-}" ]; then
        echo -e "${BLUE}[tailscale]${NC} Clé d'authentification (tskey-auth-..., vide = lien manuel classique) :"
        read -rs TAILSCALE_AUTHKEY
        echo ""
        if [ -n "$TAILSCALE_AUTHKEY" ]; then
            read -rp "$(echo -e "${BLUE}[tailscale]${NC} Sauvegarder cette clé dans server/.env.local pour les prochains Pi ? [o/N] ")" SAVE_KEY
            if [[ "$SAVE_KEY" =~ ^[oOyY]$ ]]; then
                echo "export TAILSCALE_AUTHKEY=\"$TAILSCALE_AUTHKEY\"" >> server/.env.local
                echo -e "${GREEN}[tailscale]${NC} Clé sauvegardée dans server/.env.local (jamais dans git — voir .gitignore)"
            fi
        fi
    fi
    if [ "$SAMCAM_HOSTNAME" = "cameroun" ]; then
        # DNS n'accepte pas les underscores dans un nom d'hôte — tirets uniquement
        # (ex: samcam-rpi1, samcam-rpi2, PAS samcam_rpi1).
        read -rp "$(echo -e "${BLUE}[tailscale]${NC} Nom de cette station, unique sur le tailnet (ex: samcam-rpi2) [cameroun] : ")" INPUT_HOSTNAME
        SAMCAM_HOSTNAME="${INPUT_HOSTNAME:-cameroun}"
    fi
fi

if ! command -v tailscale >/dev/null 2>&1; then
    echo -e "${YELLOW}[tailscale]${NC} Installation de Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
else
    echo -e "${GREEN}[tailscale]${NC} Déjà installé"
fi

if tailscale status >/dev/null 2>&1; then
    echo -e "${GREEN}[tailscale]${NC} Déjà connecté au tailnet"
elif [ -n "${TAILSCALE_AUTHKEY:-}" ]; then
    echo -e "${GREEN}[tailscale]${NC} Authentification automatique (clé fournie), hostname=${SAMCAM_HOSTNAME}..."
    sudo tailscale up --authkey="$TAILSCALE_AUTHKEY" --hostname="$SAMCAM_HOSTNAME"
else
    echo -e "${YELLOW}[tailscale]${NC} Pas encore authentifié sur ce Pi — étape manuelle unique requise :"
    echo -e "${YELLOW}[tailscale]${NC}   sudo tailscale up --hostname=${SAMCAM_HOSTNAME}"
    echo -e "${YELLOW}[tailscale]${NC}   (suivez le lien affiché pour authentifier l'appareil, une seule fois)"
    echo -e "${YELLOW}[tailscale]${NC} Puis relancez ce script — le Funnel s'activera automatiquement ensuite."
    echo -e "${YELLOW}[tailscale]${NC} Astuce déploiement multiple : ajoutez TAILSCALE_AUTHKEY dans server/.env.local pour sauter cette étape."
fi

if tailscale status >/dev/null 2>&1; then
    if sudo tailscale funnel --bg 8000 >/dev/null 2>&1; then
        FUNNEL_URL=$(tailscale funnel status 2>/dev/null | grep -o 'https://[^ ]*\.ts\.net[^ ]*' | head -1)
        echo -e "${GREEN}[funnel]${NC} API publiée sur Internet : ${FUNNEL_URL:-voir « tailscale funnel status »}"
    else
        echo -e "${YELLOW}[funnel]${NC} Activation automatique du Funnel impossible — lancez une fois : sudo tailscale funnel --bg 8000"
    fi
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
