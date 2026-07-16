// SAMCAM — Configuration globale
// Modifiez SERVER_URL pour pointer vers votre serveur SAMCAM
// En local : http://localhost:8000
// Sur réseau WiFi : http://192.168.1.XX:8000

class Config {
  // Clé SharedPreferences pour persister l'URL
  static const String prefServerUrl = 'samcam_server_url';

  // URL par défaut (modifiable dans les réglages)
  static const String defaultServerUrl = 'http://localhost:8000';

  // Candidats essayés automatiquement au premier lancement, dans l'ordre,
  // jusqu'à trouver un serveur qui répond à /health. L'utilisateur n'a donc
  // AUCUNE configuration à faire si le serveur est joignable par l'une de
  // ces adresses. Une URL saisie dans les réglages garde toujours la priorité.
  static const List<String> defaultServerCandidates = [
    // Station Raspberry Pi « Cameroun » — serveur permanent, publié via
    // Tailscale Funnel (voir install_pi.sh + docs/DEPLOIEMENT_RASPBERRY_PI.md).
    'https://cameroun.tail7296d8.ts.net',
    // Mac de développement — conservé en secours (utile en local pendant le dev).
    'https://macbook-neo-de-jrmy.tail7296d8.ts.net',
    'http://192.168.1.186:8000', // IP LAN actuelle du Mac (change parfois — DHCP)
    'http://localhost:8000',     // même machine (dev, web)
    'http://10.0.2.2:8000',      // émulateur Android → machine hôte
  ];

  // Timeout des requêtes HTTP
  static const Duration httpTimeout = Duration(seconds: 10);

  // Zone favorite affichée par défaut au démarrage (null = mode GPS)
  static const String prefFavoriteZone = 'samcam_favorite_zone';

  // Seuils d'alerte personnalisés par risque (0.0-1.0). Clés : inondation/secheresse/chaleur.
  static const String prefThresholdPrefix = 'samcam_threshold_';
  static const double defaultAlertThreshold = 0.45; // aligné sur le seuil ORANGE par défaut

  // Notifications locales activées/désactivées
  static const String prefNotificationsEnabled = 'samcam_notifications_enabled';
  // Dernier niveau notifié par zone+risque, pour éviter de renotifier en boucle
  static const String prefLastNotifiedPrefix = 'samcam_last_notified_';

  // Couleurs des niveaux d'alerte
  static const Map<String, int> alertColors = {
    'VERT':   0xFF2E7D32,
    'JAUNE':  0xFFF9A825,
    'ORANGE': 0xFFE65100,
    'ROUGE':  0xFFC62828,
    'INCONNU': 0xFF757575,
  };

  // Labels lisibles pour les niveaux
  static const Map<String, String> alertLabels = {
    'VERT':   'Situation normale',
    'JAUNE':  'Vigilance',
    'ORANGE': 'Risque modéré',
    'ROUGE':  'Risque élevé',
    'INCONNU': 'Données indisponibles',
  };
}
