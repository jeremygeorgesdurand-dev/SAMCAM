import 'dart:convert';
import 'package:flutter/foundation.dart' show kDebugMode, kIsWeb;
import 'package:http/http.dart' as http;
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';
import '../models/risk_report.dart';

/// Coordonnées GPS retournées par getPosition()
class GpsPosition {
  final double lat;
  final double lon;
  const GpsPosition(this.lat, this.lon);
}

class ApiService {
  // ── URL serveur ──────────────────────────────────────────────────────

  static Future<String> getServerUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(Config.prefServerUrl) ?? Config.defaultServerUrl;
  }

  static Future<void> setServerUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(Config.prefServerUrl, url);
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

    // Vérifier les permissions GPS
    LocationPermission perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      perm = await Geolocator.requestPermission();
    }
    if (perm == LocationPermission.deniedForever) {
      return const GpsPosition(2.9399, 9.9094); // Fallback Kribi
    }

    final pos = await Geolocator.getCurrentPosition(
      desiredAccuracy: LocationAccuracy.medium,
    );
    return GpsPosition(pos.latitude, pos.longitude);
  }

  // ── GET /api/risk — GPS-aware ──────────────────────────────────────
  //
  // Stratégie :
  //   1. Récupère la position GPS de l'utilisateur
  //   2. Appelle /api/nearest?lat=X&lon=Y  → données de la zone agricole
  //      la plus proche (collectées chaque jour par le scheduler)
  //   3. Si le serveur est inaccessible → Exception (home_screen gère le fallback)
  //
  // Réponse /api/nearest :
  //   { zone, distance_km, hors_zone, indicateurs, meteo, … }
  // On reconstitue un RiskReport compatible avec l'existant.

  static Future<RiskReport> getRisk() async {
    final base = await getServerUrl();
    final pos  = await getPosition();

    // Appel zone la plus proche avec les données pré-collectées (< 50 ms)
    final uri = Uri.parse('$base/api/nearest?lat=${pos.lat}&lon=${pos.lon}');
    final response = await http
        .get(uri, headers: {'Accept': 'application/json'})
        .timeout(Config.httpTimeout);

    if (response.statusCode != 200) {
      throw Exception('Erreur serveur : ${response.statusCode}');
    }

    final json = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    return _nearestToRiskReport(json, pos);
  }

  // ── GET /api/nearest-live ───────────────────────────────────────────
  //
  // Météo Open-Meteo temps réel à la position exacte + risque ML zone proche.
  // Plus lent (~1-2 s) — à appeler uniquement si l'utilisateur veut rafraîchir.

  static Future<Map<String, dynamic>> getNearestLive() async {
    final base = await getServerUrl();
    final pos  = await getPosition();
    final uri  = Uri.parse('$base/api/nearest-live?lat=${pos.lat}&lon=${pos.lon}');

    final response = await http
        .get(uri, headers: {'Accept': 'application/json'})
        .timeout(Config.httpTimeout);

    if (response.statusCode == 200) {
      return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    }
    throw Exception('Erreur serveur : ${response.statusCode}');
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

  static Future<List<Map<String, dynamic>>> getHistory({
    int limit = 30,
  }) async {
    final base = await getServerUrl();
    final pos  = await getPosition();

    // Historique de la zone la plus proche de l'utilisateur
    final uri = Uri.parse('$base/api/history'
        '?limit=$limit'
        '&zone=${Uri.encodeQueryComponent(await _nearestZoneName(base, pos))}');

    final response = await http
        .get(uri, headers: {'Accept': 'application/json'})
        .timeout(Config.httpTimeout);

    if (response.statusCode == 200) {
      final data = jsonDecode(utf8.decode(response.bodyBytes));
      return List<Map<String, dynamic>>.from(data['history'] ?? []);
    }
    throw Exception('Historique indisponible');
  }

  // ── Helpers privés ─────────────────────────────────────────────────

  /// Interroge /api/nearest pour obtenir le nom de la zone la plus proche.
  static Future<String> _nearestZoneName(String base, GpsPosition pos) async {
    try {
      final uri = Uri.parse('$base/api/nearest?lat=${pos.lat}&lon=${pos.lon}');
      final r = await http.get(uri).timeout(Config.httpTimeout);
      if (r.statusCode == 200) {
        final j = jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
        return (j['zone'] as String?) ?? 'Kribi';
      }
    } catch (_) {}
    return 'Kribi';
  }

  /// Convertit la réponse de /api/nearest en RiskReport.
  /// /api/nearest retourne les données pré-collectées de la zone la plus proche.
  /// Le modèle ML n'est PAS réexécuté ici — on lit les scores stockés dans le JSON.
  static RiskReport _nearestToRiskReport(
    Map<String, dynamic> json,
    GpsPosition pos,
  ) {
    final zone        = (json['zone']        as String?) ?? 'Kribi';
    final distanceKm  = (json['distance_km'] as num?)?.toDouble() ?? 0.0;
    final hors_zone   = json['hors_zone'] as bool? ?? false;
    final indicateurs = (json['indicateurs'] as Map<String, dynamic>?) ?? {};
    final meteo       = (json['meteo']       as Map<String, dynamic>?) ?? {};

    // Les scores de risque sont dans indicateurs (champ pré-calculé lors de
    // la collecte quotidienne). Si absents, on retourne des scores nuls.
    final scores = (indicateurs['risque_actuel']   as Map<String, dynamic>?) ??
                   (indicateurs['scores']           as Map<String, dynamic>?) ??
                   {};
    final scores3j = (indicateurs['risque_prevu_3j'] as Map<String, dynamic>?) ?? {};
    final scores7j = (indicateurs['risque_prevu_7j'] as Map<String, dynamic>?) ?? {};

    double s(Map<String, dynamic> m, String k) =>
        (m[k] as num?)?.toDouble() ?? 0.0;

    String niveau(Map<String, dynamic> m) {
      final best = [s(m, 'inondation'), s(m, 'secheresse'), s(m, 'chaleur')]
          .fold<double>(0.0, (a, b) => a > b ? a : b);
      if (best >= 0.70) return 'ROUGE';
      if (best >= 0.45) return 'ORANGE';
      if (best >= 0.25) return 'JAUNE';
      return 'VERT';
    }

    // Note de distance affichée dans la zone si hors-zone
    final zoneLabel = hors_zone
        ? '$zone (${distanceKm.toStringAsFixed(0)} km)'
        : zone;

    return RiskReport(
      date:          indicateurs['date_collecte']   as String? ?? '',
      zone:          zoneLabel,
      niveauAlerte:  niveau(scores),
      methodeRisque: indicateurs['methode_risque']  as String? ?? 'ml_gradient_boosting',
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
      indicateurs: Indicateurs.fromJson(indicateurs),
      meteo: meteo.isNotEmpty
          ? MeteoCourante.fromJson(meteo)
          : MeteoCourante.empty(),
    );
  }
}
