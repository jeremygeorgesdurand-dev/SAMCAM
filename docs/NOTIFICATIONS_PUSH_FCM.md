# Notifications push FCM — guide d'installation

## Pourquoi

Aujourd'hui, l'app SAMCAM vérifie les seuils d'alerte **à l'ouverture** et
affiche une notification *locale* (`flutter_local_notifications`). Si le
téléphone reste dans la poche, aucune alerte n'arrive — inacceptable pour un
système d'alerte précoce.

Firebase Cloud Messaging (FCM) permet d'envoyer une notification **même app
fermée**. Le serveur SAMCAM publie sur un *topic* par zone
(`zone_kribi`, `zone_maroua`, …) et chaque téléphone abonné reçoit l'alerte.

Le script serveur est déjà prêt : [`server/send_push_alerts.py`](../server/send_push_alerts.py)
(testé en `--dry-run`). Il ne manque que la configuration Firebase, qui
nécessite votre compte Google.

## Étape 1 — Créer le projet Firebase (~10 min)

1. Aller sur https://console.firebase.google.com → **Ajouter un projet**
   (nom : `samcam`, Analytics facultatif).
2. Dans le projet : **Ajouter une application → Android**.
   - Nom du package : `com.example.samcam_app`
     (⚠️ celui de `android/app/build.gradle.kts` — à changer avant une
     publication Play Store, et à re-déclarer dans Firebase le cas échéant).
3. Télécharger **`google-services.json`** et le placer dans
   `samcam_app/android/app/`.

## Étape 2 — Clé serveur

1. Console Firebase → ⚙️ **Paramètres du projet → Comptes de service**.
2. **Générer une nouvelle clé privée** → enregistrer le fichier sous
   `server/firebase-service-account.json`.
3. ⚠️ **Ne jamais committer cette clé.** Ajouter au `.gitignore` :
   ```
   server/firebase-service-account.json
   samcam_app/android/app/google-services.json
   ```
4. Côté Python : `pip install firebase-admin` (dans le venv).

## Étape 3 — Configurer l'app Flutter

1. Dépendances :
   ```bash
   cd samcam_app
   flutter pub add firebase_core firebase_messaging
   ```
2. Plugin Gradle Google Services :
   - `android/settings.gradle.kts`, bloc `plugins` :
     ```kotlin
     id("com.google.gms.google-services") version "4.4.2" apply false
     ```
   - `android/app/build.gradle.kts`, bloc `plugins` :
     ```kotlin
     id("com.google.gms.google-services")
     ```
3. Initialisation dans `lib/main.dart` (avant `runApp`) :
   ```dart
   await Firebase.initializeApp();
   ```
4. Abonnement aux topics — à brancher là où l'utilisateur choisit sa zone
   favorite (`settings_screen.dart`) :
   ```dart
   // À l'activation d'une zone favorite :
   await FirebaseMessaging.instance.subscribeToTopic('zone_kribi');
   // À la désactivation :
   await FirebaseMessaging.instance.unsubscribeFromTopic('zone_kribi');
   ```
   Convention de nommage : `zone_` + nom de zone en minuscules, accents
   retirés, espaces → `_` (ex. `Yaounde_peri` → `zone_yaounde_peri`) —
   identique à `topic_pour_zone()` du script serveur.
5. La permission `POST_NOTIFICATIONS` (Android 13+) est **déjà déclarée**
   dans le manifest ; demander l'autorisation à l'exécution :
   ```dart
   await FirebaseMessaging.instance.requestPermission();
   ```

## Étape 4 — Automatiser l'envoi côté serveur

Planifier le script après le calcul quotidien des prédictions :

```cron
# Pipeline quotidien SAMCAM (heure du serveur)
0 6 * * *  cd /path/SAMCAM && .venv/bin/python data_collection/collect_all_zones.py
10 6 * * * cd /path/SAMCAM && .venv/bin/python data_collection/append_daily_to_historical.py
20 6 * * * cd /path/SAMCAM && .venv/bin/python inference/compute_daily_predictions.py
30 6 * * * cd /path/SAMCAM && .venv/bin/python server/send_push_alerts.py
```

Le script :
- n'envoie que si une zone atteint **ORANGE** ou plus (`--seuil ROUGE` pour
  restreindre) ;
- ne renvoie pas la même alerte deux jours de suite
  (état dans `data/predictions/push_state.json`) ;
- se teste sans rien envoyer : `python server/send_push_alerts.py --dry-run`.

## Étape 5 — Vérifier

1. Builder et installer l'app, activer une zone favorite (= abonnement topic).
2. Sur le serveur : `python server/send_push_alerts.py --dry-run` pour voir
   ce qui partirait, puis sans `--dry-run` pour envoyer réellement.
3. La notification doit arriver app fermée. En cas d'échec, vérifier dans
   la console Firebase → Messaging → statistiques de livraison.

## iOS (plus tard)

FCM sur iOS exige un compte Apple Developer (99 $/an) et une clé APNs.
Les étapes Android ci-dessus n'en dépendent pas.
