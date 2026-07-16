import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Langue de l'app, persistée et observable globalement (pas de rebuild manuel
/// à câbler écran par écran : main.dart écoute ce ValueNotifier une seule fois).
class LocaleController {
  static const _prefKey = 'samcam_locale';
  static final ValueNotifier<Locale> locale = ValueNotifier(const Locale('fr', 'FR'));

  static Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    final code = prefs.getString(_prefKey);
    if (code == 'en') locale.value = const Locale('en', 'US');
  }

  static Future<void> setLocale(Locale newLocale) async {
    locale.value = newLocale;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefKey, newLocale.languageCode);
  }
}
