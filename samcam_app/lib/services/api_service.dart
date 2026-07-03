import 'dart:convert';
import 'package:flutter/foundation.dart' show kDebugMode, kIsWeb;
import 'package:http/http.dart' as http;
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';
import '../models/risk_report.dart';

class ApiService {
  // ── URL serveur ──────────────────────────────────────────────────────────

  static Future<String> getServerUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(Config.prefServerUrl) ?? Config.defaultServerUrl;
  }

  static Future<void> setServerUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(Config.prefServerUrl, url);
  }

  // ── Position GPS (ou debug via URL params en mode web) ───────────────────

  /// Retourne (latitude, longitude) de l'utilisateur.
  /// En debug web, lit ?lat=...&lon=... depuis l'URL du navigateur.
  static Future<(double, double)> getPosition() async {
    if (kDebugMode && kIsWeb) {
      final uri = Uri.base;
      final lat = double.tryParse(uri.queryParameters['lat'] ?? '');
      final lon = double.tryParse(uri.queryParameters['lon'] ?? '');
      if (lat != null && lon != null) return (lat, lon);
    }

    LocationPermission perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      perm = await Geolocator.requestPermission();
    }
    if (perm == LocationPermission.deniedForever) {
      // Fallback sur Kribi si GPS refusé
      return (2.9399, 9.9094);
    }

    final pos = await Geolocator.getCurrentPosition(
      desiredAccuracy: LocationAccuracy.medium,
    );
    return (pos.latitude, pos.longitude);
  }

  // ── GET /api/nearest-live — météo temps réel à la position GPS ───────────

  /// Retourne la météo en temps réel et le risque ML pour la position
  /// GPS exacte de l'utilisateur.
  static Future<Map<String, dynamic>> getNearestLive() async {
    final base        = await getServerUrl();
    final (lat, lon)  = await getPosition();
    final uri         = Uri.parse('$base/api/nearest-live?lat=$lat&lon=$lon');

    final response = await http
        .get(uri, headers: {'Accept': 'application/json'})
        .timeout(Config.httpTimeout);

    if (response.statusCode == 200) {
      return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    }
    throw Exception('Erreur serveur : ${response.statusCode}');
  }

  // ── GET /api/risk ────────────────────────────────────────────────────────

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

  // ── GET /health ──────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> getHealth() async {
    final base = await getServerUrl();
    final uri  = Uri.parse('$base/health');

    final response = await http
        .get(uri)
        .timeout(Config.httpTimeout);

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Serveur inaccessible');
  }

  // ── GET /api/history ─────────────────────────────────────────────────────

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
