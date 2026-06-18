import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'screens/home_screen.dart';

void main() {
  runApp(const SamcamApp());
}

class SamcamApp extends StatelessWidget {
  const SamcamApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SAMCAM',
      debugShowCheckedModeBanner: false,
      // ── Localisation française (obligatoire pour DateFormat fr_FR) ─────────
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [
        Locale('fr', 'FR'),
        Locale('en', 'US'),
      ],
      locale: const Locale('fr', 'FR'),
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
    );
  }
}
