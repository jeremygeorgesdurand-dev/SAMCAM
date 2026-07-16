import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'l10n/app_localizations.dart';
import 'screens/home_screen.dart';
import 'services/locale_controller.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await LocaleController.load();
  runApp(const SamcamApp());
}

class SamcamApp extends StatelessWidget {
  const SamcamApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<Locale>(
      valueListenable: LocaleController.locale,
      builder: (context, locale, _) => MaterialApp(
        title: 'SAMCAM',
        debugShowCheckedModeBanner: false,
        // ── Langue choisie dans les réglages, persistée (LocaleController) ────
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: const [
          Locale('fr', 'FR'),
          Locale('en', 'US'),
        ],
        locale: locale,
        // ──────────────────────────────────────────────────────────────────────
        theme: ThemeData(
          colorScheme: ColorScheme.dark(
            primary:   const Color(0xFF01696F),
            secondary: const Color(0xFF4F98A3),
            surface:   const Color(0xFF161B22),
            error:     const Color(0xFFC62828),
          ),
          scaffoldBackgroundColor: const Color(0xFF0D1117),
          fontFamily: 'Roboto',
          useMaterial3: true,
        ),
        home: const HomeScreen(),
      ),
    );
  }
}
