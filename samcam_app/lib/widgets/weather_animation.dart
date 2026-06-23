import 'dart:math';
import 'package:flutter/material.dart';

// ══════════════════════════════════════════════════════════════════
// WeatherAnimationBg — animation météo style Apple Weather
// Entièrement en Flutter pur, compatible Flutter Web
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
  if (code == null || code == 0) return night ? WeatherAnimType.clearNight : WeatherAnimType.clearDay;
  if (code <= 2) return night ? WeatherAnimType.partlyCloudyNight : WeatherAnimType.partlyCloudyDay;
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
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [Color(0xFF1A6DBF), Color(0xFF3D9BE0), Color(0xFF6AB4F0)],
        stops: [0.0, 0.55, 1.0]);
    case WeatherAnimType.clearNight:
      return const LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [Color(0xFF03061A), Color(0xFF08142E), Color(0xFF0D2045)],
        stops: [0.0, 0.5, 1.0]);
    case WeatherAnimType.partlyCloudyDay:
      return const LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [Color(0xFF1F6FA8), Color(0xFF4A8EC4), Color(0xFF7EAEDD)],
        stops: [0.0, 0.5, 1.0]);
    case WeatherAnimType.partlyCloudyNight:
      return const LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [Color(0xFF050D20), Color(0xFF0C1F3D), Color(0xFF152844)]);
    case WeatherAnimType.cloudy:
      return const LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [Color(0xFF3A4F6A), Color(0xFF526780), Color(0xFF6B7E94)]);
    case WeatherAnimType.foggy:
      return const LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [Color(0xFF5A6375), Color(0xFF7A8494), Color(0xFF9BA4AF)]);
    case WeatherAnimType.lightRain:
      return const LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [Color(0xFF1E3450), Color(0xFF2D4D6E), Color(0xFF3D6080)]);
    case WeatherAnimType.heavyRain:
      return const LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [Color(0xFF0F1E30), Color(0xFF1A2E45), Color(0xFF243D55)]);
    case WeatherAnimType.storm:
      return const LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [Color(0xFF0A0F1E), Color(0xFF141C2E), Color(0xFF1E2A3E)]);
    case WeatherAnimType.snow:
      return const LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [Color(0xFF3A5A7A), Color(0xFF5A7A9A), Color(0xFF7A9AB0)]);
  }
}

// ── Widget principal ──────────────────────────────────────────────
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
  late AnimationController _mainCtrl;
  late AnimationController _slowCtrl;
  late AnimationController _lightningCtrl;

  @override
  void initState() {
    super.initState();
    _mainCtrl = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 8),
    )..repeat();
    _slowCtrl = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 20),
    )..repeat();
    _lightningCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 150),
    );
    if (widget.type == WeatherAnimType.storm) {
      _scheduleLightning();
    }
  }

  void _scheduleLightning() async {
    while (mounted) {
      await Future.delayed(Duration(seconds: 2 + Random().nextInt(5)));
      if (!mounted) break;
      await _lightningCtrl.forward();
      await _lightningCtrl.reverse();
    }
  }

  @override
  void dispose() {
    _mainCtrl.dispose();
    _slowCtrl.dispose();
    _lightningCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.width,
      height: widget.height,
      child: AnimatedBuilder(
        animation: Listenable.merge([_mainCtrl, _slowCtrl, _lightningCtrl]),
        builder: (context, _) {
          return CustomPaint(
            painter: _WeatherPainter(
              type: widget.type,
              t: _mainCtrl.value,
              tSlow: _slowCtrl.value,
              lightning: _lightningCtrl.value,
            ),
            size: Size(widget.width, widget.height),
          );
        },
      ),
    );
  }
}

// ── Painter principal ─────────────────────────────────────────────
class _WeatherPainter extends CustomPainter {
  final WeatherAnimType type;
  final double t;
  final double tSlow;
  final double lightning;

  const _WeatherPainter({
    required this.type,
    required this.t,
    required this.tSlow,
    required this.lightning,
  });

  @override
  void paint(Canvas canvas, Size size) {
    switch (type) {
      case WeatherAnimType.clearDay:
        _drawSun(canvas, size);
        _drawHalo(canvas, size);
        _drawAtmosphere(canvas, size, [Colors.white.withOpacity(0.06), Colors.transparent]);
        break;
      case WeatherAnimType.clearNight:
        _drawMoon(canvas, size);
        _drawStars(canvas, size);
        break;
      case WeatherAnimType.partlyCloudyDay:
        _drawSun(canvas, size, small: true);
        _drawClouds(canvas, size, count: 3, baseOpacity: 0.85, white: true);
        break;
      case WeatherAnimType.partlyCloudyNight:
        _drawMoon(canvas, size, small: true);
        _drawStars(canvas, size, count: 30);
        _drawClouds(canvas, size, count: 2, baseOpacity: 0.5, white: false);
        break;
      case WeatherAnimType.cloudy:
        _drawClouds(canvas, size, count: 5, baseOpacity: 0.9, white: true);
        break;
      case WeatherAnimType.foggy:
        _drawFog(canvas, size);
        break;
      case WeatherAnimType.lightRain:
        _drawClouds(canvas, size, count: 4, baseOpacity: 0.8, white: false);
        _drawRain(canvas, size, intensity: 0.4);
        break;
      case WeatherAnimType.heavyRain:
        _drawClouds(canvas, size, count: 5, baseOpacity: 0.95, white: false);
        _drawRain(canvas, size, intensity: 1.0);
        break;
      case WeatherAnimType.storm:
        _drawClouds(canvas, size, count: 5, baseOpacity: 0.98, white: false);
        _drawRain(canvas, size, intensity: 1.5);
        _drawLightning(canvas, size);
        break;
      case WeatherAnimType.snow:
        _drawClouds(canvas, size, count: 4, baseOpacity: 0.85, white: true);
        _drawSnow(canvas, size);
        break;
    }
  }

  // ── SOLEIL ─────────────────────────────────────────────────────
  void _drawSun(Canvas canvas, Size size, {bool small = false}) {
    final cx = size.width * 0.72;
    final cy = size.height * 0.18;
    final r  = small ? size.width * 0.08 : size.width * 0.13;
    final rot = t * 2 * pi;

    // Rayons animés
    final rayPaint = Paint()
      ..color = const Color(0xFFFFD060).withOpacity(0.35)
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    for (int i = 0; i < 12; i++) {
      final angle = rot + i * pi / 6;
      final r1 = r * 1.35;
      final r2 = r * 1.7;
      canvas.drawLine(
        Offset(cx + cos(angle) * r1, cy + sin(angle) * r1),
        Offset(cx + cos(angle) * r2, cy + sin(angle) * r2),
        rayPaint);
    }

    // Lueur externe
    final glowPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          const Color(0xFFFFE080).withOpacity(0.6),
          const Color(0xFFFFD040).withOpacity(0.15),
          Colors.transparent,
        ],
        stops: const [0.0, 0.5, 1.0],
      ).createShader(Rect.fromCircle(center: Offset(cx, cy), radius: r * 2.5));
    canvas.drawCircle(Offset(cx, cy), r * 2.5, glowPaint);

    // Disque solaire
    final sunPaint = Paint()
      ..shader = RadialGradient(
        colors: [const Color(0xFFFFFFCC), const Color(0xFFFFD040)],
      ).createShader(Rect.fromCircle(center: Offset(cx, cy), radius: r));
    canvas.drawCircle(Offset(cx, cy), r, sunPaint);
  }

  void _drawHalo(Canvas canvas, Size size) {
    final cx = size.width * 0.72;
    final cy = size.height * 0.18;
    final pulse = 0.95 + 0.05 * sin(t * 2 * pi);
    final haloPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          Colors.transparent,
          const Color(0xFFFFE066).withOpacity(0.07 * pulse),
          Colors.transparent,
        ],
        stops: const [0.3, 0.6, 1.0],
      ).createShader(Rect.fromCircle(center: Offset(cx, cy), radius: size.width * 0.45));
    canvas.drawCircle(Offset(cx, cy), size.width * 0.45, haloPaint);
  }

  void _drawAtmosphere(Canvas canvas, Size size, List<Color> colors) {
    final paint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: colors,
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));
    canvas.drawRect(Rect.fromLTWH(0, 0, size.width, size.height), paint);
  }

  // ── LUNE ───────────────────────────────────────────────────────
  void _drawMoon(Canvas canvas, Size size, {bool small = false}) {
    final cx = size.width * 0.72;
    final cy = size.height * 0.18;
    final r  = small ? size.width * 0.055 : size.width * 0.09;

    final glowPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          const Color(0xFFD4E8FF).withOpacity(0.35),
          Colors.transparent,
        ],
      ).createShader(Rect.fromCircle(center: Offset(cx, cy), radius: r * 2.5));
    canvas.drawCircle(Offset(cx, cy), r * 2.5, glowPaint);

    final moonPaint = Paint()
      ..shader = RadialGradient(
        colors: [const Color(0xFFEEF4FF), const Color(0xFFB8CDE0)],
        center: const Alignment(-0.3, -0.3),
      ).createShader(Rect.fromCircle(center: Offset(cx, cy), radius: r));
    canvas.drawCircle(Offset(cx, cy), r, moonPaint);

    // Croissant (ombre)
    final shadowPaint = Paint()..color = const Color(0xFF08142E).withOpacity(0.9);
    canvas.drawCircle(Offset(cx + r * 0.35, cy - r * 0.1), r * 0.88, shadowPaint);
  }

  // ── ÉTOILES ────────────────────────────────────────────────────
  void _drawStars(Canvas canvas, Size size, {int count = 60}) {
    final rng = Random(42);
    for (int i = 0; i < count; i++) {
      final sx = rng.nextDouble() * size.width;
      final sy = rng.nextDouble() * size.height * 0.75;
      final sr = rng.nextDouble() * 1.5 + 0.3;
      final twinkle = 0.4 + 0.6 * sin(t * 2 * pi + i * 1.3);
      final starPaint = Paint()
        ..color = Colors.white.withOpacity(twinkle * 0.9);
      canvas.drawCircle(Offset(sx, sy), sr, starPaint);
    }
  }

  // ── NUAGES ─────────────────────────────────────────────────────
  void _drawClouds(Canvas canvas, Size size,
      {required int count, required double baseOpacity, required bool white}) {
    final rng = Random(77);
    final cloudColor = white
        ? Colors.white.withOpacity(baseOpacity)
        : const Color(0xFF4A5E72).withOpacity(baseOpacity);

    final configs = List.generate(count, (i) {
      final speed = 0.015 + rng.nextDouble() * 0.025;
      final yFrac = 0.05 + rng.nextDouble() * 0.45;
      final baseX = rng.nextDouble();
      final scale = 0.5 + rng.nextDouble() * 0.8;
      return (speed: speed, yFrac: yFrac, baseX: baseX, scale: scale);
    });

    for (final cfg in configs) {
      final x = ((cfg.baseX + tSlow * cfg.speed) % 1.4 - 0.2) * size.width;
      final y = cfg.yFrac * size.height;
      _drawCloud(canvas, size, x, y, cfg.scale, cloudColor);
    }
  }

  void _drawCloud(Canvas canvas, Size size,
      double cx, double cy, double scale, Color color) {
    final paint = Paint()..color = color;
    final r = size.width * 0.07 * scale;
    final bubbles = [
      Offset(cx,       cy + r * 0.4),
      Offset(cx + r,   cy),
      Offset(cx + r * 2.0, cy + r * 0.15),
      Offset(cx + r * 3.0, cy + r * 0.4),
      Offset(cx - r * 0.5, cy + r * 0.6),
      Offset(cx + r * 3.5, cy + r * 0.6),
    ];
    final radii = [r * 0.9, r, r * 0.95, r * 0.85, r * 0.6, r * 0.6];
    for (int i = 0; i < bubbles.length; i++) {
      canvas.drawCircle(bubbles[i], radii[i], paint);
    }
    final bodyPaint = Paint()..color = color;
    canvas.drawRect(
      Rect.fromLTRB(cx - r * 0.5, cy + r * 0.3, cx + r * 3.5, cy + r * 1.2),
      bodyPaint);
  }

  // ── PLUIE ──────────────────────────────────────────────────────
  void _drawRain(Canvas canvas, Size size, {required double intensity}) {
    final count = (60 * intensity).toInt();
    final rng   = Random(13);
    final rainPaint = Paint()
      ..color = const Color(0xFFADD8F0).withOpacity(0.6)
      ..strokeWidth = 1.2
      ..strokeCap = StrokeCap.round;

    for (int i = 0; i < count; i++) {
      final ox = rng.nextDouble() * size.width;
      final oy = rng.nextDouble() * size.height;
      final progress = (oy + t * size.height * 1.4) % (size.height * 1.2);
      final x = ox + progress * 0.15;
      final y = progress - size.height * 0.1;
      final len = 8.0 + intensity * 6;
      canvas.drawLine(
        Offset(x, y),
        Offset(x + len * 0.15, y + len),
        rainPaint);
    }
  }

  // ── ÉCLAIR ─────────────────────────────────────────────────────
  void _drawLightning(Canvas canvas, Size size) {
    if (lightning <= 0) return;
    // Flash de fond
    final flashPaint = Paint()..color = Colors.white.withOpacity(lightning * 0.18);
    canvas.drawRect(Rect.fromLTWH(0, 0, size.width, size.height), flashPaint);
    // Éclair
    final boltPaint = Paint()
      ..color = const Color(0xFFFFFF99).withOpacity(lightning)
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..style = PaintingStyle.stroke;
    final cx = size.width * 0.55;
    final path = Path()
      ..moveTo(cx,          size.height * 0.15)
      ..lineTo(cx - 12,     size.height * 0.38)
      ..lineTo(cx + 8,      size.height * 0.38)
      ..lineTo(cx - 18,     size.height * 0.65);
    canvas.drawPath(path, boltPaint);
  }

  // ── BROUILLARD ─────────────────────────────────────────────────
  void _drawFog(Canvas canvas, Size size) {
    for (int i = 0; i < 6; i++) {
      final yFrac = 0.1 + i * 0.14;
      final phase = tSlow + i * 0.17;
      final shift = sin(phase * 2 * pi) * size.width * 0.06;
      final opacity = 0.10 + 0.08 * sin(t * 2 * pi + i);
      final paint = Paint()
        ..shader = LinearGradient(
          colors: [
            Colors.transparent,
            const Color(0xFFBFCDD8).withOpacity(opacity * 2),
            Colors.transparent,
          ],
        ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));
      final y = yFrac * size.height;
      canvas.drawRect(
        Rect.fromLTWH(shift, y, size.width, size.height * 0.06),
        paint);
    }
  }

  // ── NEIGE ──────────────────────────────────────────────────────
  void _drawSnow(Canvas canvas, Size size) {
    final rng = Random(99);
    final snowPaint = Paint()..color = Colors.white.withOpacity(0.85);
    for (int i = 0; i < 50; i++) {
      final ox = rng.nextDouble() * size.width;
      final oy = rng.nextDouble() * size.height;
      final r  = rng.nextDouble() * 2.5 + 1.0;
      final drift = sin((t + i * 0.1) * 2 * pi) * 12;
      final progress = (oy + t * size.height * 0.4) % (size.height * 1.1);
      canvas.drawCircle(
        Offset(ox + drift, progress - size.height * 0.05), r, snowPaint);
    }
  }

  @override
  bool shouldRepaint(_WeatherPainter old) =>
      old.t != t || old.tSlow != tSlow || old.lightning != lightning || old.type != type;
}
