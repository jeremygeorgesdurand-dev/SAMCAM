# Déploiement SAMCAM sur Raspberry Pi 4 (2 Go RAM, partagé entre plusieurs projets)

## Pourquoi Docker malgré seulement 2 Go de RAM

Sur macOS/Windows, Docker Desktop fait tourner une VM Linux complète en arrière-plan
(overhead de plusieurs centaines de Mo). **Sur Raspberry Pi OS (Linux natif), Docker
Engine n'a pas cet overhead** : les conteneurs sont des processus isolés par cgroups/
namespaces, pas des machines virtuelles. Le démon Docker consomme environ 30-50 Mo.
Docker reste donc un choix raisonnable même à 2 Go, à condition d'être strict sur les
limites mémoire — ce que fait `docker-compose.yml`.

**Ce qui NE tourne PAS sur le Pi** : l'entraînement des modèles (`training/*.py`).
Les 54 modèles `.pkl` sont entraînés une fois sur un poste de développement (Mac/PC)
puis committés dans le dépôt — le Pi ne fait que de l'inférence (chargement + prédiction,
peu coûteux) et la collecte de données quotidienne.

## Ollama partagé entre plusieurs projets — pas dans Docker

Le Pi héberge plusieurs projets qui utilisent le même Ollama (modèle `qwen3:0.6b`,
déjà installé). SAMCAM **ne lance donc pas son propre conteneur Ollama** — ce serait
gaspiller de la RAM à faire tourner deux instances du même modèle. `docker-compose.yml`
ne contient que 2 services (`api`, `collector`) qui se connectent à l'Ollama natif de
l'hôte via `network_mode: host` + `http://localhost:11434`.

Si un autre projet change le modèle par défaut d'Ollama ou le décharge, l'appel
`/api/assistant` de SAMCAM peut échouer temporairement (503) le temps qu'Ollama
recharge `qwen3:0.6b` — c'est normal avec un service partagé, l'API renvoie une
erreur propre plutôt qu'un crash.

## Budget mémoire (2048 Mo total, partagés avec les autres projets du Pi)

| Poste | RAM allouée | Notes |
|---|---|---|
| OS + démon Docker | ~250-350 Mo | Raspberry Pi OS Lite (64-bit) recommandé |
| Ollama natif (partagé) | variable | Géré hors de ce projet — `qwen3:0.6b` ≈ 500-600 Mo chargé, se décharge selon la config `OLLAMA_KEEP_ALIVE` du service Ollama lui-même |
| `api` SAMCAM (conteneur) | 300 Mo max | 1 seul worker uvicorn — jamais `--workers 2` sur le Pi |
| `collector` SAMCAM (conteneur) | 250 Mo max | Interpréteur Python ne tourne que ~qq minutes/jour (05h00 UTC), le reste du temps c'est une boucle bash quasi gratuite |
| Autres projets du Pi | variable | Hors périmètre SAMCAM |

SAMCAM ne réserve que 550 Mo (api + collector). Le reste (Ollama partagé + autres
projets + OS) doit tenir dans les ~1,5 Go restants — surveillez la RAM globale
(`free -h`) une fois tous les projets démarrés, pas seulement celle de SAMCAM.
Un swap de 2 Go (carte SD ou clé USB) reste un filet de sécurité recommandé, même
s'il est lent en cas de sollicitation continue.

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│ Raspberry Pi OS (hôte)                                          │
│                                                                   │
│  Ollama natif — partagé par plusieurs projets (qwen3:0.6b)      │
│  port 11434, PAS dans Docker                                    │
│                                                                   │
│  Tailscale (natif, pas dans Docker — accès distant §9.5)         │
│                                                                   │
│  ┌──────────────────┐        ┌──────────────────────┐          │
│  │   api (SAMCAM)    │        │  collector (SAMCAM)   │          │
│  │  FastAPI 1 worker  │        │  pipeline météo/       │          │
│  │  network_mode:host │        │  satellite (cron       │          │
│  │  → localhost:11434 │        │  interne 05h UTC)      │          │
│  │  port 8000          │        │                        │          │
│  └──────────────────┘        └──────────────────────┘          │
│         └─────────────────┬─────────────────┘                   │
│           volume partagé : data/ models/ config/                │
│                                                                   │
│  [ autres projets du Pi, utilisant le même Ollama ]              │
└───────────────────────────────────────────────────────────────┘
```

Le code et les données (`data/`, `models/`, `config/`) sont montés en volume (pas copiés
dans l'image) : un `git pull` suffit à mettre à jour, pas besoin de reconstruire les
images sauf changement de dépendances Python.

`network_mode: host` sur le conteneur `api` (au lieu d'un mapping de port classique)
évite toute la complexité réseau Docker↔hôte pour joindre l'Ollama natif : le
conteneur partage directement la pile réseau du Pi, donc `localhost:11434` désigne
bien l'Ollama installé sur l'hôte.

## Installation

```bash
git clone https://github.com/jeremygeorgesdurand-dev/SAMCAM.git
cd SAMCAM
bash install_pi.sh
```

Le script est idempotent (relançable après chaque `git pull`) et gère :
1. Augmentation du swap à 2 Go si insuffisant
2. Installation de Docker Engine + plugin Compose si absent
3. Vérification qu'Ollama est bien installé, démarré et joignable sur le port 11434
   (SAMCAM ne l'installe pas lui-même — partagé avec les autres projets)
4. Installation de Tailscale si absent (reste natif, hors Docker — accès distant gratuit)
5. Génération de `server/.env.docker` depuis `server/.env.local` (secrets WhatsApp)
6. Build des images + démarrage des 2 services SAMCAM (`api`, `collector`)

## Si le modèle Ollama change

`OLLAMA_MODEL=qwen3:0.6b` est défini dans `docker-compose.yml` (service `api`). Si le
modèle partagé change de nom/taille sur le Pi, mettez à jour cette valeur puis :
```bash
docker compose up -d --force-recreate api
```

## Clé Google Earth Engine (pour la collecte satellite)

Copiez votre clé de service GEE avant la première collecte :
```bash
mkdir -p ~/.config/gee
cp /chemin/vers/kribi-key.json ~/.config/gee/kribi-key.json
```
Sans cette clé, la collecte fonctionne quand même en dégradé (Open-Meteo + NASA POWER
seuls, sans les indices satellite Sentinel-2/SMAP).

## Commandes utiles

```bash
docker compose ps              # état des services SAMCAM (api, collector)
docker compose logs -f api     # logs en direct de l'API
docker compose logs -f collector
docker compose restart api     # redémarrer un seul service
docker compose down            # tout arrêter
git pull && bash install_pi.sh # mettre à jour et redémarrer
ollama list                    # modèles disponibles sur l'Ollama partagé
free -h                        # RAM globale du Pi (tous projets confondus)
```

## Accès distant

Identique au Mac (voir `docs/RAPPORT_SAMCAM.md` §9.5) : Tailscale reste installé
nativement sur l'hôte (pas dans Docker, car Funnel a besoin d'un accès réseau bas
niveau que la conteneurisation compliquerait inutilement).

```bash
sudo tailscale up --hostname=cameroun
sudo tailscale funnel --bg 8000
```

Une fois actif, promouvoir `https://cameroun.<tailnet>.ts.net` en première position
dans `samcam_app/lib/config.dart` (`defaultServerCandidates`) et retirer l'entrée de
secours du Mac, puis reconstruire l'APK.

## Si la mémoire globale du Pi ne suffit toujours pas

Par ordre de gain croissant (du moins au plus radical) :
1. Sur le service Ollama partagé (pas dans SAMCAM) : réduire `OLLAMA_KEEP_ALIVE`
   pour décharger le modèle plus vite entre deux utilisations par n'importe quel projet
2. Vérifier qu'aucun des 3 projets ne lance sa propre instance Ollama en parallèle
   (gaspillage direct de RAM — un seul Ollama partagé doit suffire)
3. Désactiver l'assistant IA de SAMCAM si nécessaire : ne pas définir `OLLAMA_URL`
   dans `docker-compose.yml` — l'API renverra une erreur 503 propre sur
   `/api/assistant`, tout le reste continue de fonctionner
4. Passer d'un Pi 4 2 Go à 4/8 Go si les 3 projets + Ollama saturent durablement la RAM
