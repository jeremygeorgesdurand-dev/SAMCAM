import 'dart:convert';
import 'package:flutter/foundation.dart' show kDebugMode, kIsWeb;
import 'package:http/http.dart' as http;
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';
import '../models/risk_report.dart';
import '../models/custom_location.dart';
import 'offline_cache.dart';

/// Coordonnées GPS retournées par getPosition()
class GpsPosition {
  final double lat;
  final double lon;
  const GpsPosition(this.lat, this.lon);
}

class ApiService {
  // ── URL serveur ──────────────────────────────────────────────────────

  /// URL résolue par auto-détection, mémorisée pour la session.
  static String? _resolvedUrl;

  /// Retourne l'URL du serveur, sans configuration manuelle nécessaire :
  /// 1. une URL saisie dans les réglages a toujours la priorité ;
  /// 2. sinon, chaque candidat de Config.defaultServerCandidates est testé
  ///    (GET /health, 3 s max) et le premier qui répond est retenu pour
  ///    toute la session ;
  /// 3. en dernier recours, l'URL par défaut (sans la mémoriser, pour
  ///    réessayer la détection au prochain appel).
  static Future<String> getServerUrl() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(Config.prefServerUrl);
    if (saved != null && saved.isNotEmpty) return saved;

    if (_resolvedUrl != null) return _resolvedUrl!;

    for (final base in Config.defaultServerCandidates) {
      try {
        final r = await http
            .get(Uri.parse('$base/health'))
            .timeout(const Duration(seconds: 3));
        if (r.statusCode == 200) {
          _resolvedUrl = base;
          return base;
        }
      } catch (_) {}
    }
    return Config.defaultServerUrl;
  }

  static Future<void> setServerUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(Config.prefServerUrl, url);
    _resolvedUrl = null; // forcer une nouvelle détection si l'URL est effacée
  }

  // ── Position GPS ───────────────────────────────────────────────────

  /// Retourne la position GPS de l'utilisateur.
  /// En debug web, lit ?lat=...&lon=... depuis l'URL.
  /// Fallback sur Kribi si GPS refusé.
  static Future<GpsPosition> getPosition() async {
    // Mode debug web : lire depuis l'URL
    if (kDebugMode && kIsWeb) {
      final uri = Uri.base;
      final latStr = uri.queryParameters['lat'];
      final lonStr = uri.queryParameters['lon'];
      if (latStr != null && lonStr != null) {
        final lat = double.tryParse(latStr);
        final lon = double.tryParse(lonStr);
        if (lat != null && lon != null) {
          return GpsPosition(lat, lon);
        }
      }
    }

    // Vérifier que le service de localisation est activé
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      return const GpsPosition(2.9399, 9.9094); // Fallback Kribi
    }

    // Vérifier les permissions GPS
    LocationPermission perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      perm = await Geolocator.requestPermission();
    }
    if (perm == LocationPermission.deniedForever ||
        perm == LocationPermission.denied) {
      return const GpsPosition(2.9399, 9.9094); // Fallback Kribi
    }

    try {
      final pos = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.medium,
      ).timeout(const Duration(seconds: 10));
      return GpsPosition(pos.latitude, pos.longitude);
    } catch (_) {
      return const GpsPosition(2.9399, 9.9094); // Fallback Kribi
    }
  }

  // ── GET /api/risk — GPS-aware, zone explicite, ou coordonnées explicites ──
  //
  // Si [zone] est fourni       : appelle /api/risk?zone=<zone>
  // Sinon si [lat]/[lon] fournis : appelle /api/nearest?lat=X&lon=Y (endroit personnalisé)
  // Sinon                      : appelle /api/nearest?lat=X&lon=Y  (GPS auto)

  static Future<RiskReport> getRisk({String? zone, double? lat, double? lon}) async {
    final base = await getServerUrl();

    if (zone != null) {
      // Mode zone explicite → endpoint dédié
      final cacheKey = 'risk_$zone';
      final uri = Uri.parse('$base/api/risk?zone=' + Uri.encodeQueryComponent(zone));
      try {
        final response = await http
            .get(uri, headers: {'Accept': 'application/json'})
            .timeout(Config.httpTimeout);

        if (response.statusCode != 200) {
          throw Exception('Erreur serveur : ' + response.statusCode.toString());
        }

        final body = utf8.decode(response.bodyBytes);
        await OfflineCache.put(cacheKey, body);
        final json = jsonDecode(body) as Map<String, dynamic>;
        // /api/risk retourne directement un objet compatible _nearestToRiskReport
        return _nearestToRiskReport(json, null);
      } catch (e) {
        final report = await _riskFromCache(cacheKey, null);
        if (report != null) return report;
        // Zone jamais consultée en détail hors-ligne (pas de cache risk_<zone>)
        // → repli sur /api/overview mis en cache, qui couvre les 18 zones en
        // un seul appel et est donc disponible même pour une zone jamais
        // ouverte individuellement.
        final fromOverview = await _riskFromOverviewCache(zone);
        if (fromOverview != null) return fromOverview;
        rethrow;
      }
    }

    // Mode coordonnées (endroit personnalisé) ou GPS automatique
    final pos = (lat != null && lon != null) ? GpsPosition(lat, lon) : await getPosition();
    const cacheKey = 'risk_nearest'; // dernière réponse GPS/coordonnées connue
    final uri = Uri.parse('$base/api/nearest').replace(
      queryParameters: {
        'lat': pos.lat.toString(),
        'lon': pos.lon.toString(),
      },
    );
    try {
      final response = await http
          .get(uri, headers: {'Accept': 'application/json'})
          .timeout(Config.httpTimeout);

      if (response.statusCode != 200) {
        throw Exception('Erreur serveur : ' + response.statusCode.toString());
      }

      final body = utf8.decode(response.bodyBytes);
      await OfflineCache.put(cacheKey, body);
      final json = jsonDecode(body) as Map<String, dynamic>;
      return _nearestToRiskReport(json, pos);
    } catch (e) {
      final report = await _riskFromCache(cacheKey, pos);
      if (report != null) return report;
      rethrow;
    }
  }

  /// Reconstruit un RiskReport depuis le cache hors-ligne, marqué comme périmé.
  /// Retourne null si aucune entrée n'existe pour [cacheKey].
  static Future<RiskReport?> _riskFromCache(
      String cacheKey, GpsPosition? pos) async {
    final entry = await OfflineCache.get(cacheKey);
    if (entry == null) return null;
    try {
      final json = jsonDecode(entry.json) as Map<String, dynamic>;
      return _nearestToRiskReport(json, pos,
          fromCache: true, cachedAt: entry.cachedAt);
    } catch (_) {
      return null;
    }
  }

  /// Repli hors-ligne pour une zone jamais consultée individuellement :
  /// reconstruit un RiskReport minimal (risque actuel uniquement, pas de
  /// météo ni de prévisions à 3j/7j/10j/14j) à partir du cache 'overview',
  /// qui liste le score courant des 18 zones en une seule entrée.
  static Future<RiskReport?> _riskFromOverviewCache(String zone) async {
    final entry = await OfflineCache.get('overview');
    if (entry == null) return null;
    try {
      final data  = jsonDecode(entry.json) as Map<String, dynamic>;
      final zones = (data['zones'] as List?) ?? [];
      final match = zones
          .cast<Map<String, dynamic>>()
          .where((z) => (z['zone'] as String?)?.toLowerCase() == zone.toLowerCase())
          .toList();
      if (match.isEmpty) return null;

      final z = match.first;
      final fakeJson = {
        'zone': z['zone'],
        'risque_actuel': {
          'scores':        z['scores'],
          'niveau_alerte': z['niveau_alerte'],
        },
      };
      return _nearestToRiskReport(fakeJson, null,
          fromCache: true, cachedAt: entry.cachedAt);
    } catch (_) {
      return null;
    }
  }

  // ── Recherche de ville (géocodage) ──────────────────────────────────

  /// Cherche une ville par son nom via Nominatim (jusqu'à 5 résultats), pour
  /// que l'utilisateur puisse vérifier/choisir le bon lieu avant de l'ajouter.
  /// Retourne une liste vide si aucun résultat n'est trouvé.
  static Future<List<GeocodeResult>> searchCity(String query) async {
    final trimmed = query.trim();
    if (trimmed.isEmpty) return [];
    try {
      final uri = Uri.parse(
        'https://nominatim.openstreetmap.org/search'
        '?q=' + Uri.encodeQueryComponent(trimmed) +
        '&format=json&limit=5&accept-language=fr',
      );
      final response = await http.get(
        uri,
        headers: {'User-Agent': 'SAMCAM-App/1.0'},
      ).timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) return [];
      final results = jsonDecode(response.body) as List;
      return results
          .map((r) => r as Map<String, dynamic>)
          .map((r) {
            final lat = double.tryParse(r['lat'] as String? ?? '');
            final lon = double.tryParse(r['lon'] as String? ?? '');
            if (lat == null || lon == null) return null;
            final displayName = (r['display_name'] as String?) ?? trimmed;
            final shortName = displayName.split(',').first.trim();
            return GeocodeResult(
              shortName:   shortName.isNotEmpty ? shortName : trimmed,
              fullAddress: displayName,
              lat: lat,
              lon: lon,
            );
          })
          .whereType<GeocodeResult>()
          .toList();
    } catch (_) {
      return [];
    }
  }

  // ── Endroits personnalisés (persistance locale) ─────────────────────

  static const String _prefCustomLocations = 'samcam_custom_locations';

  static Future<List<CustomLocation>> getCustomLocations() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList(_prefCustomLocations) ?? [];
    return raw
        .map((s) => CustomLocation.fromJson(jsonDecode(s) as Map<String, dynamic>))
        .toList();
  }

  static Future<void> addCustomLocation(CustomLocation location) async {
    final prefs = await SharedPreferences.getInstance();
    final current = await getCustomLocations();
    if (current.any((l) => l.name == location.name)) return;
    current.add(location);
    await prefs.setStringList(
      _prefCustomLocations,
      current.map((l) => jsonEncode(l.toJson())).toList(),
    );
  }

  static Future<void> removeCustomLocation(String name) async {
    final prefs = await SharedPreferences.getInstance();
    final current = await getCustomLocations();
    current.removeWhere((l) => l.name == name);
    await prefs.setStringList(
      _prefCustomLocations,
      current.map((l) => jsonEncode(l.toJson())).toList(),
    );
  }

  // ── GET /api/zones — liste des zones disponibles ──────────────────

  static Future<List<String>> listZones() async {
    final base = await getServerUrl();
    final uri  = Uri.parse('$base/api/zones');

    final response = await http
        .get(uri, headers: {'Accept': 'application/json'})
        .timeout(Config.httpTimeout);

    if (response.statusCode != 200) {
      throw Exception('Zones indisponibles');
    }

    final data = jsonDecode(utf8.decode(response.bodyBytes));
    // Le serveur peut retourner : ["Kribi", ...] ou {"zones": [...]}
    if (data is List) {
      return List<String>.from(data);
    } else if (data is Map && data['zones'] is List) {
      return List<String>.from(data['zones'] as List);
    }
    return [];
  }

  // ── GET /api/overview — niveau de risque actuel des 8 zones ─────────

  static Future<List<Map<String, dynamic>>> getOverview() async {
    final base = await getServerUrl();
    final uri  = Uri.parse('$base/api/overview');

    try {
      final response = await http
          .get(uri, headers: {'Accept': 'application/json'})
          .timeout(Config.httpTimeout);

      if (response.statusCode != 200) {
        throw Exception('Vue d\'ensemble indisponible');
      }

      final body = utf8.decode(response.bodyBytes);
      await OfflineCache.put('overview', body);
      final data = jsonDecode(body) as Map<String, dynamic>;
      return List<Map<String, dynamic>>.from(data['zones'] ?? []);
    } catch (e) {
      final entry = await OfflineCache.get('overview');
      if (entry != null) {
        final data = jsonDecode(entry.json) as Map<String, dynamic>;
        return List<Map<String, dynamic>>.from(data['zones'] ?? []);
      }
      rethrow;
    }
  }

  // ── GET /api/nearest-live ───────────────────────────────────────────

  static Future<Map<String, dynamic>> getNearestLive() async {
    final base = await getServerUrl();
    final pos  = await getPosition();
    final uri  = Uri.parse('$base/api/nearest-live').replace(queryParameters: {'lat': pos.lat.toString(), 'lon': pos.lon.toString()});

    final response = await http
        .get(uri, headers: {'Accept': 'application/json'})
        .timeout(Config.httpTimeout);

    if (response.statusCode == 200) {
      return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    }
    throw Exception('Erreur serveur : ' + response.statusCode.toString());
  }

  // ── GET /health ────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> getHealth() async {
    final base = await getServerUrl();
    final uri  = Uri.parse('$base/health');

    final response = await http.get(uri).timeout(Config.httpTimeout);

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Serveur inaccessible');
  }

  // ── GET /api/history ───────────────────────────────────────────────────
  //
  // Retourne l'évolution jour par jour des scores de risque pour une zone
  // (calculée directement par les modèles, pas figée sur la valeur du jour).
  // Si [zone] est omis, utilise la zone SAMCAM la plus proche de la position GPS.

  static Future<List<Map<String, dynamic>>> getHistory({
    String? zone,
    int days = 14,
  }) async {
    final base = await getServerUrl();
    final zoneName = zone ?? await _nearestZoneName(base, await getPosition());

    final uri = Uri.parse('$base/api/history').replace(queryParameters: {
      'zone': zoneName,
      'days': days.toString(),
    });

    try {
      final response = await http
          .get(uri, headers: {'Accept': 'application/json'})
          .timeout(Config.httpTimeout);

      if (response.statusCode != 200) {
        throw Exception('Historique indisponible');
      }
      final body = utf8.decode(response.bodyBytes);
      await OfflineCache.put('history_$zoneName', body);
      final data = jsonDecode(body);
      return List<Map<String, dynamic>>.from(data['history'] ?? []);
    } catch (e) {
      final entry = await OfflineCache.get('history_$zoneName');
      if (entry != null) {
        final data = jsonDecode(entry.json);
        return List<Map<String, dynamic>>.from(data['history'] ?? []);
      }
      rethrow;
    }
  }

  // ── POST /api/signalement — signalement communautaire ───────────────

  /// Envoie un signalement d'événement climatique observé sur le terrain.
  /// [typeEvenement] : inondation | secheresse | chaleur | autre.
  static Future<void> submitSignalement({
    required String zone,
    required String typeEvenement,
    String description = '',
    double? lat,
    double? lon,
  }) async {
    final base = await getServerUrl();
    final uri  = Uri.parse('$base/api/signalement');

    final response = await http
        .post(
          uri,
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'zone':           zone,
            'type_evenement': typeEvenement,
            'description':    description,
            if (lat != null) 'lat': lat,
            if (lon != null) 'lon': lon,
          }),
        )
        .timeout(Config.httpTimeout);

    if (response.statusCode != 200) {
      throw Exception('Signalement refusé (${response.statusCode})');
    }
  }

  // ── POST /api/assistant — assistant IA (Ollama), grounded sur le bulletin réel ──
  //
  // Délai volontairement plus long que Config.httpTimeout : un modèle de
  // langage local (Ollama) peut mettre du temps à répondre, surtout au
  // premier appel après inactivité (chargement du modèle en mémoire) ou
  // sur le matériel modeste d'un Raspberry Pi.
  static const Duration _assistantTimeout = Duration(seconds: 90);

  /// [question] absente → l'assistant résume le bulletin actuel de [zone].
  /// [question] fournie → réponse ciblée, basée uniquement sur les données réelles.
  static Future<String> askAssistant({required String zone, String? question}) async {
    final base = await getServerUrl();
    final uri  = Uri.parse('$base/api/assistant');

    final response = await http
        .post(
          uri,
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'zone': zone,
            if (question != null && question.trim().isNotEmpty) 'question': question.trim(),
          }),
        )
        .timeout(_assistantTimeout);

    if (response.statusCode != 200) {
      throw Exception('Assistant indisponible (${response.statusCode})');
    }
    final json = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    return (json['reponse'] as String?) ?? '';
  }

  // ── Helpers privés ─────────────────────────────────────────────────

  static Future<String> _nearestZoneName(String base, GpsPosition pos) async {
    try {
    final uri = Uri.parse('$base/api/nearest').replace(
      queryParameters: {
        'lat': pos.lat.toString(),
        'lon': pos.lon.toString(),
      },
    );      
    final r = await http.get(uri).timeout(Config.httpTimeout);
      if (r.statusCode == 200) {
        final j = jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
        return (j['zone'] as String?) ?? 'Kribi';
      }
    } catch (_) {}
    return 'Kribi';
  }

  /// Convertit la réponse de /api/nearest (ou /api/risk) en RiskReport.
  ///
  /// Structure attendue de l'API :
  ///   {
  ///     "zone": "Kribi",
  ///     "risque_actuel":   { "scores": { "score_inondation": 0.05, "score_secheresse": 0.30, "score_chaleur": 0.01 }, "niveau_alerte": "JAUNE" },
  ///     "risque_prevu_3j": { "scores": { ... }, "niveau_alerte": "VERT" },
  ///     "risque_prevu_7j": { "scores": { ... }, "niveau_alerte": "VERT" },
  ///     "indicateurs":     { ... },
  ///     "meteo":           { ... }
  ///   }
  static RiskReport _nearestToRiskReport(
    Map<String, dynamic> json,
    GpsPosition? pos, {
    bool fromCache = false,
    DateTime? cachedAt,
  }) {
    final zone        = (json['zone']        as String?) ?? 'Kribi';
    final distanceKm  = (json['distance_km'] as num?)?.toDouble() ?? 0.0;
    final hors_zone   = json['hors_zone'] as bool? ?? false;
    final indicateurs = (json['indicateurs'] as Map<String, dynamic>?) ?? {};
    final meteo       = (json['meteo']       as Map<String, dynamic>?) ?? {};

    // ── Extraction des blocs de scores ──────────────────────────────────
    // Les blocs risque_actuel / risque_prevu_3j / risque_prevu_7j sont à la
    // RACINE du JSON (pas dans indicateurs). Chaque bloc a la forme :
    //   { "scores": { "score_inondation": X, "score_secheresse": Y, "score_chaleur": Z },
    //     "niveau_alerte": "VERT|JAUNE|ORANGE|ROUGE" }
    bool hasHorizon(String key) =>
        json.containsKey(key) || indicateurs.containsKey(key);

    Map<String, dynamic> extractScores(String key) {
      final bloc = (json[key] as Map<String, dynamic>?) ??
                   (indicateurs[key] as Map<String, dynamic>?) ?? {};
      // Retourne le sous-objet "scores" s'il existe, sinon le bloc entier
      return (bloc['scores'] as Map<String, dynamic>?) ?? bloc;
    }

    final scores    = extractScores('risque_actuel');
    final scores3j  = extractScores('risque_prevu_3j');
    final scores7j  = extractScores('risque_prevu_7j');
    final scores10j = extractScores('risque_prevu_10j');
    final scores14j = extractScores('risque_prevu_14j');

    // ── Lecture d'une valeur numérique ──────────────────────────────────
    // Accepte "score_X" (format API actuel) OU "X" (ancien format)
    double s(Map<String, dynamic> m, String k) =>
        (m['score_$k'] as num?)?.toDouble() ??
        (m[k]          as num?)?.toDouble() ?? 0.0;

    // ── Calcul du niveau d'alerte global ───────────────────────────────
    String niveau(Map<String, dynamic> m) {
      final best = [s(m, 'inondation'), s(m, 'secheresse'), s(m, 'chaleur')]
          .fold<double>(0.0, (a, b) => a > b ? a : b);
      if (best >= 0.70) return 'ROUGE';
      if (best >= 0.45) return 'ORANGE';
      if (best >= 0.25) return 'JAUNE';
      return 'VERT';
    }

    final zoneLabel = hors_zone
        ? '$zone (${distanceKm.toStringAsFixed(0)} km)'
        : zone;

    // date_collecte et methode_risque peuvent être à la racine ou dans indicateurs
    final dateCollecte  = (json['date_collecte']  as String?) ??
                          (indicateurs['date_collecte']  as String?) ?? '';
    final methodeRisque = (json['methode_risque'] as String?) ??
                          (indicateurs['methode_risque'] as String?) ?? 'ml_gradient_boosting';

    return RiskReport(
      date:          dateCollecte,
      zone:          zoneLabel,
      niveauAlerte:  niveau(scores),
      methodeRisque: methodeRisque,
      actuel: RiskPeriod(
        niveauGlobal: niveau(scores),
        scores: RiskScores(
          inondation: s(scores,   'inondation'),
          secheresse: s(scores,   'secheresse'),
          chaleur:    s(scores,   'chaleur'),
        ),
      ),
      prevu3j: RiskPeriod(
        niveauGlobal: niveau(scores3j),
        scores: RiskScores(
          inondation: s(scores3j, 'inondation'),
          secheresse: s(scores3j, 'secheresse'),
          chaleur:    s(scores3j, 'chaleur'),
        ),
      ),
      prevu7j: RiskPeriod(
        niveauGlobal: niveau(scores7j),
        scores: RiskScores(
          inondation: s(scores7j, 'inondation'),
          secheresse: s(scores7j, 'secheresse'),
          chaleur:    s(scores7j, 'chaleur'),
        ),
      ),
      // J+10/J+14 : absents des anciennes réponses API — marqués INCONNU plutôt
      // que VERT par défaut, pour que l'UI les masque proprement (voir RiskReport.horizons).
      prevu10j: RiskPeriod(
        niveauGlobal: hasHorizon('risque_prevu_10j') ? niveau(scores10j) : 'INCONNU',
        scores: RiskScores(
          inondation: s(scores10j, 'inondation'),
          secheresse: s(scores10j, 'secheresse'),
          chaleur:    s(scores10j, 'chaleur'),
        ),
      ),
      prevu14j: RiskPeriod(
        niveauGlobal: hasHorizon('risque_prevu_14j') ? niveau(scores14j) : 'INCONNU',
        scores: RiskScores(
          inondation: s(scores14j, 'inondation'),
          secheresse: s(scores14j, 'secheresse'),
          chaleur:    s(scores14j, 'chaleur'),
        ),
      ),
      indicateurs: Indicateurs.fromJson(indicateurs),
      meteo: meteo.isNotEmpty
          ? MeteoCourante.fromJson(meteo)
          : MeteoCourante.empty(),
      fromCache: fromCache,
      cachedAt:  cachedAt,
    );
  }
}
