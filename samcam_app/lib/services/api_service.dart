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
      // Fallback Kribi
      return const GpsPosition(2.9399, 9.9094);
    }

    final pos = await Geolocator.getCurrentPosition(
      desiredAccuracy: LocationAccuracy.medium,
    );
    return GpsPosition(pos.latitude, pos.longitude);
  }

  // ── GET /api/nearest-live ───────────────────────────────────────────

  /// Météo temps réel + risque ML à la position GPS exacte.
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

  // ── GET /api/risk ──────────────────────────────────────────────────────

  static Future<RiskReport> getRisk() async {
    final base = await getServerUrl();
    final uri  = Uri.parse('$base/api/risk');

    final response = await http
        .get(uri, headers: {'Accept': 'application/json'})
        .timeout(Config.httpTimeout);

    if (response.statusCode == 200) {
      return RiskReport.fromJson(
        jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>,
      );
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
    final uri  = Uri.parse('$base/api/history?limit=$limit');

    final response = await http
        .get(uri, headers: {'Accept': 'application/json'})
        .timeout(Config.httpTimeout);

    if (response.statusCode == 200) {
      final data = jsonDecode(utf8.decode(response.bodyBytes));
      return List<Map<String, dynamic>>.from(data['history'] ?? []);
    }
    throw Exception('Historique indisponible');
  }
}
