// SAMCAM — Configuration globale
// Modifiez SERVER_URL pour pointer vers votre serveur SAMCAM
// En local : http://localhost:8000
// Sur réseau WiFi : http://192.168.1.XX:8000

class Config {
  // Clé SharedPreferences pour persister l'URL
  static const String prefServerUrl = 'samcam_server_url';

  // URL par défaut (modifiable dans les réglages)
  static const String defaultServerUrl = 'http://localhost:8000';

  // Timeout des requêtes HTTP
  static const Duration httpTimeout = Duration(seconds: 10);

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
