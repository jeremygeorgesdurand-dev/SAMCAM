// SAMCAM — Configuration globale
// Modifiez SERVER_URL pour pointer vers votre serveur SAMCAM
// En local : http://localhost:8000
// Sur réseau WiFi : http://192.168.1.XX:8000

class Config {
  static const String prefServerUrl = 'samcam_server_url';
  static const String defaultServerUrl = 'http://localhost:8000';
  static const Duration httpTimeout = Duration(seconds: 10);

  static const Map<String, int> alertColors = {
    'VERT':    0xFF2E7D32,
    'JAUNE':   0xFFF9A825,
    'ORANGE':  0xFFE65100,
    'ROUGE':   0xFFC62828,
    'INCONNU': 0xFF757575,
  };

  static const Map<String, String> alertLabels = {
    'VERT':    'Situation normale',
    'JAUNE':   'Vigilance',
    'ORANGE':  'Risque modéré',
    'ROUGE':   'Risque élevé',
    'INCONNU': 'Données indisponibles',
  };
}
