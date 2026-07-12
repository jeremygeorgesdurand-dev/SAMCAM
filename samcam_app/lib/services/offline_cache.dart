// SAMCAM — Cache hors-ligne des réponses API.
//
// Chaque réponse réseau réussie est stockée brute (JSON string) dans
// SharedPreferences avec son horodatage. En cas d'échec réseau, l'app
// retombe sur la dernière réponse connue et l'affiche avec un bandeau
// indiquant l'ancienneté des données — essentiel en zone rurale où la
// connectivité est intermittente.

import 'package:shared_preferences/shared_preferences.dart';

/// Entrée de cache : contenu JSON brut + date de mise en cache.
class CachedEntry {
  final String json;
  final DateTime cachedAt;
  const CachedEntry(this.json, this.cachedAt);

  /// Ancienneté lisible, ex. "il y a 3 h" / "il y a 2 j".
  String get age {
    final d = DateTime.now().difference(cachedAt);
    if (d.inMinutes < 1) return "à l'instant";
    if (d.inMinutes < 60) return 'il y a ${d.inMinutes} min';
    if (d.inHours < 24) return 'il y a ${d.inHours} h';
    return 'il y a ${d.inDays} j';
  }
}

class OfflineCache {
  static const String _prefix = 'samcam_cache_';

  /// Enregistre une réponse API brute sous [key].
  static Future<void> put(String key, String json) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('$_prefix$key', json);
    await prefs.setInt(
        '$_prefix${key}_ts', DateTime.now().millisecondsSinceEpoch);
  }

  /// Relit la dernière réponse enregistrée sous [key], ou null si absente.
  static Future<CachedEntry?> get(String key) async {
    final prefs = await SharedPreferences.getInstance();
    final json = prefs.getString('$_prefix$key');
    final ts = prefs.getInt('$_prefix${key}_ts');
    if (json == null || ts == null) return null;
    return CachedEntry(json, DateTime.fromMillisecondsSinceEpoch(ts));
  }
}
