import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';
import '../models/risk_report.dart';

class ApiService {
  static Future<String> getServerUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(Config.prefServerUrl) ?? Config.defaultServerUrl;
  }

  static Future<void> setServerUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(Config.prefServerUrl, url);
  }

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
