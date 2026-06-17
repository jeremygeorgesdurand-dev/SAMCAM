# SAMCAM Mobile — Application Flutter V5

Application mobile de surveillance climatique pour la zone côtière de Kribi.
Consomme l'API REST du serveur SAMCAM V3/V4.

## Prérequis

- Flutter >= 3.44.0
- Serveur SAMCAM en cours d'exécution (`bash server/start.sh`)

## Installation

```bash
# 1. Copier le contenu de mobile/ dans votre projet Flutter
flutter create samcam_app
cp -r mobile/lib samcam_app/lib
cp mobile/pubspec.yaml samcam_app/pubspec.yaml

# 2. Installer les dépendances
cd samcam_app
flutter pub get

# 3. Lancer sur Chrome
flutter run -d chrome

# 4. Lancer sur Android (après installation Android Studio)
flutter run -d android
```

## Configuration

Au premier lancement, aller dans **Réglages** (icône ⚙️) et entrer l'URL de votre serveur :

- Local : `http://localhost:8000`
- Réseau WiFi : `http://192.168.1.XX:8000`

## Structure

```
lib/
├── main.dart                  # Point d'entrée + thème
├── config.dart                # URL serveur + couleurs alertes
├── models/
│   └── risk_report.dart       # Modèle données /api/risk
├── services/
│   └── api_service.dart       # Appels HTTP
└── screens/
    ├── home_screen.dart        # Écran principal — niveau alerte
    ├── history_screen.dart     # Historique des rapports
    └── settings_screen.dart    # Configuration IP serveur
```

## Écrans

| Écran | Description |
|---|---|
| **Accueil** | Niveau d'alerte global, scores ML, prévisions J+3/J+7, indicateurs météo |
| **Historique** | Liste des 30 derniers rapports avec niveaux d'alerte |
| **Réglages** | Configurer et tester l'URL du serveur SAMCAM |
