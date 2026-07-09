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

  // ── GET /api/risk — GPS-aware ou zone explicite ───────────────────
  //
  // Si [zone] est fourni : appelle /api/risk?zone=<zone>
  // Sinon               : appelle /api/nearest?lat=X&lon=Y  (GPS auto)

  static Future<RiskReport> getRisk({String? zone}) async {
    final base = await getServerUrl();

    if (zone != null) {
      // Mode zone explicite → endpoint dédié
      final uri = Uri.parse('$base/api/risk?zone=' + Uri.encodeQueryComponent(zone));
      final response = await http
          .get(uri, headers: {'Accept': 'application/json'})
          .timeout(Config.httpTimeout);

      if (response.statusCode != 200) {
        throw Exception('Erreur serveur : ' + response.statusCode.toString());
      }

      final json =
          jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
      // /api/risk retourne directement un objet compatible _nearestToRiskReport
      return _nearestToRiskReport(json, null);
    }

    // Mode GPS automatique
    final pos = await getPosition();
    final uri = Uri.parse('$base/api/nearest').replace(
      queryParameters: {
        'lat': pos.lat.toString(),
        'lon': pos.lon.toString(),
      },
    );
    final response = await http
        .get(uri, headers: {'Accept': 'application/json'})
        .timeout(Config.httpTimeout);

    if (response.statusCode != 200) {
      throw Exception('Erreur serveur : ' + response.statusCode.toString());
    }

    final json =
        jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    return _nearestToRiskReport(json, pos);
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

  static Future<List<Map<String, dynamic>>> getHistory({
    int limit = 30,
  }) async {
    final base = await getServerUrl();
    final pos  = await getPosition();

    final uri = Uri.parse('$base/api/history'
        '?limit=$limit'
        + '&zone=' + Uri.encodeQueryComponent(await _nearestZoneName(base, pos)));


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
  static RiskReport _nearestToRiskReport(
    Map<String, dynamic> json,
    GpsPosition? pos,
  ) {
    final zone        = (json['zone']        as String?) ?? 'Kribi';
    final distanceKm  = (json['distance_km'] as num?)?.toDouble() ?? 0.0;
    final hors_zone   = json['hors_zone'] as bool? ?? false;
    final indicateurs = (json['indicateurs'] as Map<String, dynamic>?) ?? {};
    final meteo       = (json['meteo']       as Map<String, dynamic>?) ?? {};

    final scores   = (indicateurs['risque_actuel']   as Map<String, dynamic>?) ??
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

    final zoneLabel = hors_zone
        ? '$zone (\${distanceKm.toStringAsFixed(0)} km)'
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
