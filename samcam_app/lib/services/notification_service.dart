// SAMCAM — Notifications locales d'alerte climatique
//
// Note d'implémentation : ceci déclenche des notifications LOCALES, vérifiées
// quand l'app est ouverte/reprise (pas de push serveur type Firebase — ça
// demanderait un projet Firebase + des identifiants APNs/FCM à provisionner
// séparément). Suffisant pour alerter l'utilisateur pendant qu'il utilise
// l'app ou juste après l'avoir rouverte, mais ça ne réveille pas l'app en
// tâche de fond.

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';
import '../models/risk_report.dart';

class NotificationService {
  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  static bool _initialized = false;

  static Future<void> init() async {
    if (_initialized || kIsWeb) return;
    const androidInit = AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosInit = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
    );
    await _plugin.initialize(
      const InitializationSettings(android: androidInit, iOS: iosInit),
    );

    final androidImpl = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    await androidImpl?.requestNotificationsPermission();

    _initialized = true;
  }

  static Future<bool> isEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(Config.prefNotificationsEnabled) ?? false;
  }

  static Future<void> setEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(Config.prefNotificationsEnabled, enabled);
  }

  static Future<double> getThreshold(String risk) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getDouble('${Config.prefThresholdPrefix}$risk')
        ?? Config.defaultAlertThreshold;
  }

  static Future<void> setThreshold(String risk, double value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setDouble('${Config.prefThresholdPrefix}$risk', value);
  }

  /// Vérifie les scores actuels contre les seuils personnalisés de l'utilisateur
  /// et déclenche une notification locale si un risque vient de dépasser son
  /// seuil (dédupliqué : ne renotifie pas tant que le risque reste au-dessus).
  static Future<void> checkAndNotify(String zoneName, RiskReport report) async {
    if (kIsWeb) return;
    if (!await isEnabled()) return;
    await init();

    final scores = {
      'inondation': report.actuel.scores.inondation,
      'secheresse': report.actuel.scores.secheresse,
      'chaleur':    report.actuel.scores.chaleur,
    };
    final labels = {
      'inondation': 'inondation',
      'secheresse': 'sécheresse',
      'chaleur':    'chaleur',
    };

    final prefs = await SharedPreferences.getInstance();

    for (final risk in scores.keys) {
      final score     = scores[risk]!;
      final threshold = await getThreshold(risk);
      final key       = '${Config.prefLastNotifiedPrefix}${zoneName}_$risk';
      final wasAbove  = prefs.getBool(key) ?? false;
      final isAbove   = score >= threshold;

      if (isAbove && !wasAbove) {
        await _show(
          id: '$zoneName-$risk'.hashCode,
          title: 'SAMCAM — Alerte ${labels[risk]}',
          body: '$zoneName : risque de ${labels[risk]} à ${(score * 100).toStringAsFixed(0)}% '
                '(seuil personnel : ${(threshold * 100).toStringAsFixed(0)}%)',
        );
      }
      await prefs.setBool(key, isAbove);
    }
  }

  static Future<void> _show({
    required int id,
    required String title,
    required String body,
  }) async {
    const androidDetails = AndroidNotificationDetails(
      'samcam_alerts',
      'Alertes climatiques SAMCAM',
      channelDescription: 'Alertes de risque inondation/sécheresse/chaleur',
      importance: Importance.high,
      priority: Priority.high,
    );
    const iosDetails = DarwinNotificationDetails();
    await _plugin.show(
      id, title, body,
      const NotificationDetails(android: androidDetails, iOS: iosDetails),
    );
  }
}
