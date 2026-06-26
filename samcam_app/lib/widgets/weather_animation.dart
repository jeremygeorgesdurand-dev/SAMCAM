import 'dart:math';
import 'package:flutter/material.dart';

// ══════════════════════════════════════════════════════════════════
// WeatherAnimationBg — animation météo premium style Apple/iOS 17
// Nuages 3D multicouches, soleil avec lens-flare, parallaxe
// Défilement infini droite → gauche, répartition harmonieuse
// ══════════════════════════════════════════════════════════════════

enum WeatherAnimType {
  clearDay,
  clearNight,
  partlyCloudyDay,
  partlyCloudyNight,
  cloudy,
  foggy,
  lightRain,
  heavyRain,
  storm,
  snow,
}

WeatherAnimType weatherAnimTypeFromCode(int? code, int hour) {
  final night = hour < 6 || hour >= 21;
  if (code == null || code == 0)
    return night ? WeatherAnimType.clearNight : WeatherAnimType.clearDay;
  if (code <= 2)
    return night ? WeatherAnimType.partlyCloudyNight : WeatherAnimType.partlyCloudyDay;
  if (code == 3) return WeatherAnimType.cloudy;
  if (code >= 45 && code <= 48) return WeatherAnimType.foggy;
  if (code >= 51 && code <= 57) return WeatherAnimType.lightRain;
  if (code >= 61 && code <= 67) return WeatherAnimType.heavyRain;
  if (code >= 71 && code <= 79) return WeatherAnimType.snow;
  if (code >= 80 && code <= 82) return WeatherAnimType.heavyRain;
  if (code >= 85 && code <= 86) return WeatherAnimType.snow;
  if (code >= 95) return WeatherAnimType.storm;
  return night ? WeatherAnimType.clearNight : WeatherAnimType.clearDay;
}

LinearGradient weatherGradient(WeatherAnimType type) {
  switch (type) {
    case WeatherAnimType.clearDay:
      return const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF0A4FA8), Color(0xFF1A7FD4), Color(0xFF4EB3E8)],
          stops: [0.0, 0.5, 1.0]);
    case WeatherAnimType.clearNight:
      return const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF020818), Color(0xFF060F26), Color(0xFF0C1A3A)],
          stops: [0.0, 0.5, 1.0]);
    case WeatherAnimType.partlyCloudyDay:
      return const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF1460A8), Color(0xFF3A88C8), Color(0xFF6AAEDD),
                   Color(0xFF8DC4E6)],
          stops: [0.0, 0.35, 0.7, 1.0]);
    case WeatherAnimType.partlyCloudyNight:
      return const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF030A1E), Color(0xFF081528), Color(0xFF0F2040)]);
    case WeatherAnimType.cloudy:
      return const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF2E4560), Color(0xFF445E78), Color(0xFF5E7A8E)]);
    case WeatherAnimType.foggy:
      return const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF5A6475), Color(0xFF7A8494), Color(0xFF9EA8B0)]);
    case WeatherAnimType.lightRain:
      return const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF182E48), Color(0xFF244260), Color(0xFF2E506E)]);
    case WeatherAnimType.heavyRain:
      return const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF0C1828), Color(0xFF162436), Color(0xFF1E3045)]);
    case WeatherAnimType.storm:
      return const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF080C18), Color(0xFF0E1424), Color(0xFF161E30)]);
    case WeatherAnimType.snow:
      return const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF304E6A), Color(0xFF506E88), Color(0xFF7090A8)]);
  }
}

// ─── Widget principal ──────────────────────────────────────────────
class WeatherAnimationBg extends StatefulWidget {
  final WeatherAnimType type;
  final double width;
  final double height;

  const WeatherAnimationBg({
    super.key,
    required this.type,
    required this.width,
    required this.height,
  });

  @override
  State<WeatherAnimationBg> createState() => _WeatherAnimationBgState();
}

class _WeatherAnimationBgState extends State<WeatherAnimationBg>
    with TickerProviderStateMixin {
  late AnimationController _mainCtrl;   // 10s  — pluie, neige, étoiles
  late AnimationController _cloudCtrl;  // 60s  — nuages lents (fond)
  late AnimationController _cloud2Ctrl; // 36s  — nuages rapides (avant)
  late AnimationController _sunCtrl;    // 12s  — rotation soleil
  late AnimationController _pulseCtrl;  // 3s   — halo pulsant
  late AnimationController _ltCtrl;     // 120ms — éclair

  @override
  void initState() {
    super.initState();
    _mainCtrl   = AnimationController(vsync: this, duration: const Duration(seconds: 10))..repeat();
    // Durées allonges : le cycle correspond au temps pour parcourir
    // tout le bandeau (2.4x largeur) — pas de saut visible car
    // la position est calculée en continu par modulo sur le bandeau.
    _cloudCtrl  = AnimationController(vsync: this, duration: const Duration(seconds: 60))..repeat();
    _cloud2Ctrl = AnimationController(vsync: this, duration: const Duration(seconds: 36))..repeat();
    _sunCtrl    = AnimationController(vsync: this, duration: const Duration(seconds: 12))..repeat();
    _pulseCtrl  = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat(reverse: true);
    _ltCtrl     = AnimationController(vsync: this, duration: const Duration(milliseconds: 120));
    if (widget.type == WeatherAnimType.storm) _scheduleLightning();
  }

  void _scheduleLightning() async {
    final rng = Random();
    while (mounted) {
      await Future.delayed(Duration(milliseconds: 1800 + rng.nextInt(4000)));
      if (!mounted) break;
      await _ltCtrl.forward();
      await _ltCtrl.reverse();
      if (rng.nextBool()) {
        await Future.delayed(const Duration(milliseconds: 80));
        await _ltCtrl.forward(from: 0.5);
        await _ltCtrl.reverse();
      }
    }
  }

  @override
  void dispose() {
    _mainCtrl.dispose();
    _cloudCtrl.dispose();
    _cloud2Ctrl.dispose();
    _sunCtrl.dispose();
    _pulseCtrl.dispose();
    _ltCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.width,
      height: widget.height,
      child: AnimatedBuilder(
        animation: Listenable.merge(
            [_mainCtrl, _cloudCtrl, _cloud2Ctrl, _sunCtrl, _pulseCtrl, _ltCtrl]),
        builder: (_, __) => CustomPaint(
          painter: _WeatherPainter(
            type:    widget.type,
            t:       _mainCtrl.value,
            tCloud:  _cloudCtrl.value,
            tCloud2: _cloud2Ctrl.value,
            tSun:    _sunCtrl.value,
            tPulse:  _pulseCtrl.value,
            lightning: _ltCtrl.value,
          ),
          size: Size(widget.width, widget.height),
        ),
      ),
    );
  }
}

// ─── Painter ───────────────────────────────────────────────────────
class _WeatherPainter extends CustomPainter {
  final WeatherAnimType type;
  final double t, tCloud, tCloud2, tSun, tPulse, lightning;
  const _WeatherPainter({
    required this.type, required this.t, required this.tCloud,
    required this.tCloud2, required this.tSun, required this.tPulse,
    required this.lightning,
  });

  @override
  void paint(Canvas canvas, Size size) {
    switch (type) {
      case WeatherAnimType.clearDay:
        _drawSun(canvas, size);
        _drawAtmosphericHaze(canvas, size);
        break;
      case WeatherAnimType.clearNight:
        _drawMilkyWay(canvas, size);
        _drawStars(canvas, size, 70);
        _drawMoon(canvas, size);
        break;
      case WeatherAnimType.partlyCloudyDay:
        _drawSun(canvas, size, xFrac: 0.78, yFrac: 0.20, scale: 0.85);
        _drawAtmosphericHaze(canvas, size, opacity: 0.4);
        _drawCloudLayer(canvas, size, tCloud,  layer: 0);
        _drawCloudLayer(canvas, size, tCloud2, layer: 1);
        break;
      case WeatherAnimType.partlyCloudyNight:
        _drawStars(canvas, size, 45);
        _drawMoon(canvas, size, xFrac: 0.76, yFrac: 0.17);
        _drawCloudLayer(canvas, size, tCloud,  layer: 0, night: true);
        _drawCloudLayer(canvas, size, tCloud2, layer: 1, night: true);
        break;
      case WeatherAnimType.cloudy:
        _drawCloudLayer(canvas, size, tCloud,  layer: 0, dense: true);
        _drawCloudLayer(canvas, size, tCloud2, layer: 1, dense: true);
        _drawCloudLayer(canvas, size, tCloud,  layer: 2, dense: true);
        break;
      case WeatherAnimType.foggy:
        _drawFog(canvas, size);
        break;
      case WeatherAnimType.lightRain:
        _drawCloudLayer(canvas, size, tCloud,  layer: 0, dark: true, dense: true);
        _drawCloudLayer(canvas, size, tCloud2, layer: 1, dark: true);
        _drawRain(canvas, size, intensity: 0.45, wind: 0.12);
        _drawRainSplash(canvas, size, t);
        break;
      case WeatherAnimType.heavyRain:
        _drawCloudLayer(canvas, size, tCloud,  layer: 0, dark: true, dense: true);
        _drawCloudLayer(canvas, size, tCloud2, layer: 1, dark: true, dense: true);
        _drawRain(canvas, size, intensity: 1.0, wind: 0.18);
        _drawRain(canvas, size, intensity: 0.5, wind: 0.08, seed: 77);
        _drawRainSplash(canvas, size, t);
        break;
      case WeatherAnimType.storm:
        _drawCloudLayer(canvas, size, tCloud,  layer: 0, dark: true, dense: true, storm: true);
        _drawCloudLayer(canvas, size, tCloud2, layer: 1, dark: true, dense: true, storm: true);
        _drawRain(canvas, size, intensity: 1.4, wind: 0.25);
        _drawRain(canvas, size, intensity: 0.7, wind: 0.14, seed: 55);
        _drawLightning(canvas, size);
        break;
      case WeatherAnimType.snow:
        _drawCloudLayer(canvas, size, tCloud,  layer: 0, dense: true);
        _drawCloudLayer(canvas, size, tCloud2, layer: 1);
        _drawSnow(canvas, size);
        break;
    }
  }

  // ══ SOLEIL PREMIUM ═══════════════════════════════════════════════
  void _drawSun(Canvas canvas, Size size, {
    double xFrac = 0.75, double yFrac = 0.22, double scale = 1.0,
  }) {
    final cx = size.width  * xFrac;
    final cy = size.height * yFrac;
    final r  = size.width  * 0.11 * scale;
    final rot = tSun * 2 * pi;

    final outerGlow = Paint()
      ..shader = RadialGradient(colors: [
        const Color(0xFFFFE580).withOpacity(0.18),
        const Color(0xFFFFCC40).withOpacity(0.06),
        Colors.transparent,
      ], stops: const [0.0, 0.45, 1.0])
      .createShader(Rect.fromCircle(center: Offset(cx, cy), radius: r * 4.0));
    canvas.drawCircle(Offset(cx, cy), r * 4.0, outerGlow);

    final pulse = 0.96 + 0.04 * tPulse;
    final corona = Paint()
      ..shader = RadialGradient(colors: [
        const Color(0xFFFFEB80).withOpacity(0.55 * pulse),
        const Color(0xFFFFD040).withOpacity(0.20 * pulse),
        Colors.transparent,
      ], stops: const [0.0, 0.5, 1.0])
      .createShader(Rect.fromCircle(center: Offset(cx, cy), radius: r * 2.2));
    canvas.drawCircle(Offset(cx, cy), r * 2.2, corona);

    final longRayPaint = Paint()
      ..color = const Color(0xFFFFE060).withOpacity(0.22)
      ..strokeWidth = 1.2
      ..strokeCap = StrokeCap.round;
    for (int i = 0; i < 16; i++) {
      final angle = rot * 0.5 + i * pi / 8;
      canvas.drawLine(
        Offset(cx + cos(angle) * r * 1.55, cy + sin(angle) * r * 1.55),
        Offset(cx + cos(angle) * r * 2.8,  cy + sin(angle) * r * 2.8),
        longRayPaint);
    }

    final shortRayPaint = Paint()
      ..color = const Color(0xFFFFEA70).withOpacity(0.45)
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;
    for (int i = 0; i < 8; i++) {
      final angle = rot + i * pi / 4;
      canvas.drawLine(
        Offset(cx + cos(angle) * r * 1.25, cy + sin(angle) * r * 1.25),
        Offset(cx + cos(angle) * r * 1.65, cy + sin(angle) * r * 1.65),
        shortRayPaint);
    }

    final sunPaint = Paint()
      ..shader = RadialGradient(
        center: const Alignment(-0.3, -0.35),
        colors: [
          const Color(0xFFFFFFCC),
          const Color(0xFFFFEE80),
          const Color(0xFFFFCC30),
          const Color(0xFFFFAA00),
        ],
        stops: const [0.0, 0.35, 0.70, 1.0],
      ).createShader(Rect.fromCircle(center: Offset(cx, cy), radius: r));
    canvas.drawCircle(Offset(cx, cy), r, sunPaint);

    final streakPaint = Paint()
      ..color = Colors.white.withOpacity(0.14)
      ..strokeWidth = r * 0.5
      ..strokeCap = StrokeCap.round
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8);
    canvas.drawLine(
      Offset(cx - r * 3.5, cy + r * 1.2),
      Offset(cx + r * 2.5, cy - r * 0.8),
      streakPaint);
  }

  void _drawAtmosphericHaze(Canvas canvas, Size size, {double opacity = 0.7}) {
    final paint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          Colors.transparent,
          const Color(0xFF90C8F0).withOpacity(0.12 * opacity),
          const Color(0xFFB8DCF4).withOpacity(0.20 * opacity),
        ],
        stops: const [0.0, 0.5, 1.0],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));
    canvas.drawRect(Rect.fromLTWH(0, 0, size.width, size.height), paint);
  }

  // ══ LUNE ══════════════════════════════════════════════════════════
  void _drawMoon(Canvas canvas, Size size,
      {double xFrac = 0.74, double yFrac = 0.20}) {
    final cx = size.width  * xFrac;
    final cy = size.height * yFrac;
    final r  = size.width  * 0.075;

    final halo = Paint()
      ..shader = RadialGradient(colors: [
        const Color(0xFFCCDFFF).withOpacity(0.22),
        const Color(0xFF99BBEE).withOpacity(0.08),
        Colors.transparent,
      ]).createShader(Rect.fromCircle(center: Offset(cx, cy), radius: r * 3.0));
    canvas.drawCircle(Offset(cx, cy), r * 3.0, halo);

    final moonPaint = Paint()
      ..shader = RadialGradient(
        center: const Alignment(-0.3, -0.4),
        colors: [
          const Color(0xFFEEF6FF),
          const Color(0xFFD4E8FA),
          const Color(0xFFB0CAE0),
        ],
        stops: const [0.0, 0.5, 1.0],
      ).createShader(Rect.fromCircle(center: Offset(cx, cy), radius: r));
    canvas.drawCircle(Offset(cx, cy), r, moonPaint);

    final bg = Paint()..color = const Color(0xFF060F26).withOpacity(0.92);
    canvas.drawCircle(Offset(cx + r * 0.22, cy - r * 0.06), r * 0.88, bg);

    final craterPaint = Paint()..color = Colors.black.withOpacity(0.06);
    canvas.drawCircle(Offset(cx - r * 0.22, cy + r * 0.15), r * 0.12, craterPaint);
    canvas.drawCircle(Offset(cx - r * 0.08, cy - r * 0.30), r * 0.08, craterPaint);
    canvas.drawCircle(Offset(cx - r * 0.38, cy - r * 0.05), r * 0.07, craterPaint);
  }

  // ══ VOIE LACTÉE + ÉTOILES ═════════════════════════════════════════
  void _drawMilkyWay(Canvas canvas, Size size) {
    final paint = Paint()
      ..shader = LinearGradient(
        begin: const Alignment(-1.0, 0.2),
        end:   const Alignment(1.0, -0.2),
        colors: [
          Colors.transparent,
          const Color(0xFF8899CC).withOpacity(0.06),
          const Color(0xFFAABBDD).withOpacity(0.10),
          const Color(0xFF8899CC).withOpacity(0.06),
          Colors.transparent,
        ],
        stops: const [0.0, 0.25, 0.5, 0.75, 1.0],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));
    canvas.drawRect(Rect.fromLTWH(0, 0, size.width, size.height), paint);
  }

  void _drawStars(Canvas canvas, Size size, int count) {
    final rng = Random(42);
    for (int i = 0; i < count; i++) {
      final sx = rng.nextDouble() * size.width;
      final sy = rng.nextDouble() * size.height * 0.80;
      final sr = rng.nextDouble() * 1.3 + 0.2;
      final bright = rng.nextDouble();
      final twinkle = 0.35 + 0.65 * (0.5 + 0.5 * sin(t * 2 * pi * (0.7 + bright * 0.6) + i * 1.7));
      if (bright > 0.75) {
        final starGlow = Paint()
          ..color = Colors.white.withOpacity(twinkle * 0.18)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 3);
        canvas.drawCircle(Offset(sx, sy), sr * 2.5, starGlow);
      }
      final starPaint = Paint()..color = Colors.white.withOpacity(twinkle * 0.92);
      canvas.drawCircle(Offset(sx, sy), sr, starPaint);
    }
  }

  // ══ NUAGES 3D MULTICOUCHES — DÉFILEMENT INFINI ═══════════════════════
  //
  //  Principe du tiling infini (comme un fond de jeu 2D) :
  //  -------------------------------------------------------
  //  On définit un « bandeau » virtuel de largeur BAND = 2.4 * width.
  //  Chaque nuage i occupe une « case » de largeur BAND/count
  //  dans ce bandeau, avec un décalage aléatoire à l'intérieur
  //  de sa case (± 30 % de la largeur de case) pour éviter la
  //  régularité métronome.
  //
  //  Position dans le bandeau = slot_center + jitter - offset_anime
  //  offset_animé = anim * BAND  (croissant de 0 à BAND sur la durée
  //                               du controller, puis repart à 0).
  //
  //  On projette ensuite la position avec modulo BAND, ce qui crée
  //  un recyclage parfaitement invisible : quand un nuage sort à
  //  gauche, son « clone » arrive depuis la droite dans la même case.
  //  Le saut se produit hors écran (dans la zone > width ou < -marge).
  //
  //  layer 0 = fond  (petits, lents, transparents)
  //  layer 1 = milieu
  //  layer 2 = avant (grands, rapides, opaques)
  void _drawCloudLayer(Canvas canvas, Size size, double anim, {
    required int layer,
    bool night = false,
    bool dark  = false,
    bool dense = false,
    bool storm = false,
  }) {
    final int count = layer == 2 ? 4 : (dense ? 6 : 5);

    // Largeur du bandeau virtuel (en pixels logiques normalisés sur [0..1])
    // On travaille en fractions de width pour rester indépendant de la taille.
    const double band = 2.4; // = 2.4 * size.width

    // Vitesse du layer : fraction du bandeau parcourue par cycle du controller
    // Le controller boucle indéfiniment, donc anim ∈ [0, 1[ en permanence.
    // En multipliant par band, on parcourt le bandeau entier en 1 cycle.
    final double layerSpeed = layer == 0 ? 1.0 : layer == 1 ? 1.0 : 1.0;
    // (la vitesse réelle est contrôlée par la durée du controller :
    //  layer 0 : 60s, layer 1 & 2 : 36s — layer 2 défile 60/36 = 1.67x plus vite)

    final double slotWidth = band / count; // largeur d'une case

    for (int i = 0; i < count; i++) {
      final rng = Random(layer * 41 + i * 19 + 3);

      // Centre de la case i dans le bandeau
      final double slotCenter = (i + 0.5) * slotWidth;

      // Jitter aléatoire à l'intérieur de la case (± 30 % de slotWidth)
      // Seed fixe ⇒ position stable entre les frames
      final double jitter = (rng.nextDouble() - 0.5) * slotWidth * 0.60;

      // Variation de vitesse individuelle (± 15 %) pour éviter le « peloton »
      final double speedVar = 0.85 + rng.nextDouble() * 0.30;

      // Offset animé : progresse de 0 à band sur un cycle, puis repart
      // On ajoute i*0.07 pour déphaser les nuages d'une même couche
      final double offset = (anim * band * layerSpeed * speedVar + i * 0.07 * band) % band;

      // Position brute dans le bandeau (D→G : on soustrait l'offset)
      double rawPos = slotCenter + jitter - offset;

      // Recyclage : on ramène rawPos dans [-0.35*band .. band]
      // pour que le nuage soit toujours à portail de l'écran ou juste après
      rawPos = rawPos % band;
      if (rawPos < -0.35 * band) rawPos += band;

      // Conversion en pixels : [-0.3*width .. 2.1*width]
      // Les nuages hors écran (< -large_nuage ou > width+marge) sont
      // dessinés mais invisibles — coût négligeable.
      final double x = (rawPos - 0.3) * size.width;

      // Position Y aléatoire fixée par seed
      final double yFrac = layer == 0
          ? 0.03 + rng.nextDouble() * 0.20
          : layer == 1
              ? 0.08 + rng.nextDouble() * 0.32
              : 0.05 + rng.nextDouble() * 0.42;
      final double y = yFrac * size.height;

      // Taille
      final double cloudScale = layer == 0
          ? 0.30 + rng.nextDouble() * 0.38
          : layer == 1
              ? 0.50 + rng.nextDouble() * 0.50
              : 0.70 + rng.nextDouble() * 0.60;

      final double opacity = layer == 0 ? 0.52 : layer == 1 ? 0.74 : 0.91;

      _drawRealisticCloud(
        canvas, size, x, y, cloudScale,
        layer: layer,
        night: night,
        dark: dark || storm,
        baseOpacity: opacity * (dense ? 1.0 : 0.88),
      );
    }
  }

  void _drawRealisticCloud(Canvas canvas, Size size,
      double cx, double cy, double scale, {
    required int layer,
    bool night = false,
    bool dark  = false,
    double baseOpacity = 0.85,
  }) {
    final r = size.width * 0.065 * scale;

    Color topColor, midColor, bottomColor;
    if (dark) {
      topColor    = const Color(0xFF404860);
      midColor    = const Color(0xFF303548);
      bottomColor = const Color(0xFF202430);
    } else if (night) {
      topColor    = const Color(0xFF3A4868);
      midColor    = const Color(0xFF283450);
      bottomColor = const Color(0xFF1A2238);
    } else {
      topColor    = const Color(0xFFF8FCFF);
      midColor    = const Color(0xFFE8F4FE);
      bottomColor = const Color(0xFFCCDEF0);
    }

    // Ombre portée
    final shadowPaint = Paint()
      ..color = (dark
            ? const Color(0xFF0A1020)
            : night
                ? const Color(0xFF0A1530)
                : const Color(0xFF90A8C0))
          .withOpacity(baseOpacity * 0.28)
      ..maskFilter = MaskFilter.blur(BlurStyle.normal, r * 0.55);
    canvas.drawOval(
      Rect.fromCenter(
          center: Offset(cx + r * 1.5, cy + r * 1.50),
          width: r * 4.2, height: r * 0.62),
      shadowPaint);

    // Bulles du nuage — forme cumuliforme organique
    // Rayon COMPLET (non pondéré par baseOpacity) pour éviter l'effet croissant.
    // L'opacité est appliquée sur les couleurs du gradient.
    const bubbles = [
      // rangee basse (base large et stable)
      (-0.40, 0.70, 0.60),
      ( 0.30, 0.62, 0.82),
      ( 1.50, 0.58, 0.80),
      ( 2.70, 0.62, 0.78),
      ( 3.40, 0.70, 0.58),
      // rangee intermediaire
      ( 0.55, 0.20, 0.92),
      ( 1.55, 0.13, 1.02),
      ( 2.50, 0.18, 0.88),
      // bosses superieures
      ( 0.95,-0.06, 0.96),
      ( 1.88,-0.20, 1.10),  // pic central
      ( 2.82,-0.10, 0.91),
    ];

    final effectiveOpacity = baseOpacity.clamp(0.0, 1.0);
    for (final b in bubbles) {
      final bx = b[0] as double;
      final by = b[1] as double;
      final br = b[2] as double;
      final bCx = cx + bx * r;
      final bCy = cy + by * r;
      final bR  = br * r;
      final highlight = by < 0.0;

      final bubblePaint = Paint()
        ..shader = RadialGradient(
          center: Alignment(-0.25, highlight ? -0.55 : -0.30),
          colors: [
            (highlight ? topColor : midColor).withOpacity(effectiveOpacity),
            midColor.withOpacity(effectiveOpacity * 0.95),
            bottomColor.withOpacity(effectiveOpacity * 0.78),
          ],
          stops: const [0.0, 0.45, 1.0],
        ).createShader(Rect.fromCircle(center: Offset(bCx, bCy), radius: bR))
        ..style = PaintingStyle.fill;
      canvas.drawCircle(Offset(bCx, bCy), bR, bubblePaint);
    }

    // Reflet spéculaire haut-gauche
    if (!dark) {
      final specPaint = Paint()
        ..color = Colors.white.withOpacity(baseOpacity * (night ? 0.10 : 0.27))
        ..maskFilter = MaskFilter.blur(BlurStyle.normal, r * 0.35);
      canvas.drawCircle(Offset(cx + r * 1.0, cy - r * 0.05), r * 0.50, specPaint);
    }
  }

  // ══ PLUIE RÉALISTE ════════════════════════════════════════════════
  void _drawRain(Canvas canvas, Size size, {
    required double intensity,
    required double wind,
    int seed = 13,
  }) {
    final count  = (70 * intensity).toInt();
    final rng    = Random(seed);
    for (int i = 0; i < count; i++) {
      final ox    = rng.nextDouble() * size.width * 1.2 - size.width * 0.1;
      final oy    = rng.nextDouble() * size.height;
      final speed = 0.8 + rng.nextDouble() * 0.6;
      final prog  = (oy + t * size.height * 1.6 * speed) % (size.height * 1.25);
      final x     = ox + prog * wind * 1.3;
      final y     = prog - size.height * 0.12;
      final len   = (10.0 + intensity * 8) * speed;
      final alpha = 0.35 + rng.nextDouble() * 0.45;
      final thick = 0.8 + rng.nextDouble() * 0.7;

      final rainPaint = Paint()
        ..color = const Color(0xFFB8DCF5).withOpacity(alpha)
        ..strokeWidth = thick
        ..strokeCap = StrokeCap.round;
      canvas.drawLine(
        Offset(x, y),
        Offset(x + len * wind * 0.8, y + len),
        rainPaint);
    }
  }

  void _drawRainSplash(Canvas canvas, Size size, double t) {
    final rng = Random(88);
    for (int i = 0; i < 12; i++) {
      final sx = rng.nextDouble() * size.width;
      final phase = (t + i * 0.083) % 1.0;
      if (phase > 0.6) continue;
      final progress = phase / 0.6;
      final splashR  = progress * 4.0;
      final splashA  = (1 - progress) * 0.3;
      canvas.drawCircle(
        Offset(sx, size.height * (0.85 + rng.nextDouble() * 0.12)),
        splashR,
        Paint()
          ..color = const Color(0xFF90C8E8).withOpacity(splashA)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 0.8);
    }
  }

  // ══ ÉCLAIR ════════════════════════════════════════════════════════
  void _drawLightning(Canvas canvas, Size size) {
    if (lightning <= 0) return;
    final rng = Random(42);
    final xBase = size.width * (0.35 + rng.nextDouble() * 0.30);

    final flashPaint = Paint()
      ..shader = RadialGradient(
        center: Alignment(xBase / size.width * 2 - 1, -0.8),
        colors: [
          Colors.white.withOpacity(lightning * 0.35),
          const Color(0xFFDDE8FF).withOpacity(lightning * 0.12),
          Colors.transparent,
        ],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));
    canvas.drawRect(Rect.fromLTWH(0, 0, size.width, size.height), flashPaint);
    _drawBolt(canvas, size, xBase, lightning);
  }

  void _drawBolt(Canvas canvas, Size size, double x, double alpha) {
    final rng   = Random(7);
    final path  = Path();
    double cx   = x;
    double cy   = size.height * 0.08;
    path.moveTo(cx, cy);
    for (int i = 0; i < 6; i++) {
      cx += (rng.nextDouble() - 0.45) * 28;
      cy += size.height * 0.55 / 6;
      path.lineTo(cx, cy);
    }
    canvas.drawPath(path, Paint()
      ..color = const Color(0xFF88BBFF).withOpacity(alpha * 0.55)
      ..strokeWidth = 8
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 10));
    canvas.drawPath(path, Paint()
      ..color = Colors.white.withOpacity(alpha * 0.9)
      ..strokeWidth = 2.0
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round);
  }

  // ══ BROUILLARD ════════════════════════════════════════════════════
  void _drawFog(Canvas canvas, Size size) {
    for (int i = 0; i < 8; i++) {
      final yFrac   = 0.05 + i * 0.12;
      final phase   = tCloud + i * 0.13;
      final shift   = sin(phase * 2 * pi) * size.width * 0.05
                    + cos(phase * pi * 1.3) * size.width * 0.02;
      final opacity = 0.06 + 0.05 * sin(t * 2 * pi + i * 0.9);
      final grad    = Paint()
        ..shader = LinearGradient(colors: [
          Colors.transparent,
          const Color(0xFFCED6DF).withOpacity(opacity * 2.2),
          const Color(0xFFD8E0E8).withOpacity(opacity * 2.8),
          const Color(0xFFCED6DF).withOpacity(opacity * 2.2),
          Colors.transparent,
        ], stops: const [0.0, 0.2, 0.5, 0.8, 1.0]).createShader(
            Rect.fromLTWH(shift, 0, size.width, size.height));
      final y = yFrac * size.height;
      canvas.drawRect(
          Rect.fromLTWH(shift, y, size.width * 1.1, size.height * 0.08), grad);
    }
  }

  // ══ NEIGE ═════════════════════════════════════════════════════════
  void _drawSnow(Canvas canvas, Size size) {
    final rng = Random(99);
    for (int i = 0; i < 60; i++) {
      final ox    = rng.nextDouble() * size.width;
      final oy    = rng.nextDouble() * size.height;
      final r     = rng.nextDouble() * 2.8 + 0.8;
      final speed = 0.25 + rng.nextDouble() * 0.4;
      final drift = sin((t * (0.8 + speed) + i * 0.21) * 2 * pi) * 14;
      final prog  = (oy + t * size.height * 0.55 * speed) % (size.height * 1.08);
      final y     = prog - size.height * 0.04;
      final alpha = 0.5 + rng.nextDouble() * 0.45;

      if (r > 2.2) {
        canvas.drawCircle(
          Offset(ox + drift, y),
          r * 2.0,
          Paint()
            ..color = Colors.white.withOpacity(alpha * 0.18)
            ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 3));
      }
      canvas.drawCircle(
        Offset(ox + drift, y), r,
        Paint()..color = Colors.white.withOpacity(alpha));
    }
  }

  @override
  bool shouldRepaint(_WeatherPainter old) =>
      old.t != t || old.tCloud != tCloud || old.tCloud2 != tCloud2 ||
      old.tSun != tSun || old.tPulse != tPulse || old.lightning != lightning ||
      old.type != type;
}
