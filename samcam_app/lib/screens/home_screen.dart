import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../config.dart';
import '../models/risk_report.dart';
import '../services/api_service.dart';
import 'settings_screen.dart';
import 'history_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen>
    with SingleTickerProviderStateMixin {
  RiskReport? _report;
  bool _loading = true;
  String? _error;
  late AnimationController _animCtrl;

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(
      vsync: this, duration: const Duration(seconds: 8))
      ..repeat();
    _fetchRisk();
  }

  @override
  void dispose() {
    _animCtrl.dispose();
    super.dispose();
  }

  Future<void> _fetchRisk() async {
    setState(() { _loading = true; _error = null; });
    try {
      final r = await ApiService.getRisk();
      setState(() { _report = r; _loading = false; });
    } catch (e) {
      setState(() { _error = '$e'; _loading = false; });
    }
  }

  // Couleurs fond selon condition météo
  List<Color> _skyGradient(int wmoCode, String niveau) {
    // Priorité au code WMO si dispo
    if (wmoCode > 0) {
      if (wmoCode == 0) return [const Color(0xFF1E90FF), const Color(0xFF87CEEB), const Color(0xFFB0D8F5)];
      if (wmoCode <= 2) return [const Color(0xFF4682B4), const Color(0xFF87CEEB), const Color(0xFFB8D4E8)];
      if (wmoCode == 3) return [const Color(0xFF4A5568), const Color(0xFF718096), const Color(0xFF8FA3B1)];
      if (wmoCode >= 51 && wmoCode <= 67) return [const Color(0xFF2D3748), const Color(0xFF4A6073), const Color(0xFF6B8A9E)];
      if (wmoCode >= 80 && wmoCode <= 82) return [const Color(0xFF2C3E50), const Color(0xFF3B5068), const Color(0xFF5A7A8E)];
      if (wmoCode >= 95) return [const Color(0xFF1A1A2E), const Color(0xFF16213E), const Color(0xFF0F3460)];
    }
    // Fallback sur le niveau d'alerte
    switch (niveau) {
      case 'VERT':   return [const Color(0xFF0D4F3C), const Color(0xFF1B6B52), const Color(0xFF2A8A68)];
      case 'JAUNE':  return [const Color(0xFF4A3B00), const Color(0xFF6B5500), const Color(0xFF8A7000)];
      case 'ORANGE': return [const Color(0xFF5C2A00), const Color(0xFF7A3800), const Color(0xFF8F4A10)];
      case 'ROUGE':  return [const Color(0xFF5C0000), const Color(0xFF7A0000), const Color(0xFF8F1010)];
      default:       return [const Color(0xFF1A2744), const Color(0xFF263A5E), const Color(0xFF344D7A)];
    }
  }

  @override
  Widget build(BuildContext context) {
    final r      = _report;
    final wmo    = r?.meteo.codeMeteo ?? 0;
    final niveau = r?.niveauAlerte ?? 'INCONNU';
    final colors = _skyGradient(wmo, niveau);

    return Scaffold(
      body: Stack(
        children: [
          // Fond dégradé animé
          AnimatedBuilder(
            animation: _animCtrl,
            builder: (_, __) => CustomPaint(
              size: MediaQuery.of(context).size,
              painter: _SkyPainter(
                wmoCode:   wmo,
                colors:    colors,
                animValue: _animCtrl.value,
              ),
            ),
          ),
          // Contenu
          SafeArea(
            child: _loading
                ? const Center(child: CircularProgressIndicator(color: Colors.white70))
                : _error != null
                    ? _buildError()
                    : _buildContent(r!),
          ),
        ],
      ),
    );
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  Widget _buildError() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('🌧️', style: TextStyle(fontSize: 64)),
            const SizedBox(height: 16),
            const Text('Serveur inaccessible',
              style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(_error!, textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white54, fontSize: 12)),
            const SizedBox(height: 28),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _pillBtn('Réessayer', Icons.refresh, _fetchRisk),
                const SizedBox(width: 12),
                _pillBtn('Réglages', Icons.settings_outlined, () async {
                  await Navigator.push(context,
                    MaterialPageRoute(builder: (_) => const SettingsScreen()));
                  _fetchRisk();
                }),
              ],
            ),
          ],
        ),
      ),
    );
  }

  // ── Contenu principal ─────────────────────────────────────────────────────
  Widget _buildContent(RiskReport r) {
    return RefreshIndicator(
      onRefresh: _fetchRisk,
      color: Colors.white,
      backgroundColor: Colors.white24,
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          // AppBar transparent
          SliverAppBar(
            backgroundColor: Colors.transparent,
            elevation: 0,
            floating: true,
            title: Text(r.zone,
              style: const TextStyle(
                  color: Colors.white, fontWeight: FontWeight.w600, fontSize: 17)),
            centerTitle: true,
            actions: [
              IconButton(
                icon: const Icon(Icons.history, color: Colors.white70),
                onPressed: () => Navigator.push(context,
                  MaterialPageRoute(builder: (_) => const HistoryScreen())),
              ),
              IconButton(
                icon: const Icon(Icons.settings_outlined, color: Colors.white70),
                onPressed: () async {
                  await Navigator.push(context,
                    MaterialPageRoute(builder: (_) => const SettingsScreen()));
                  _fetchRisk();
                },
              ),
            ],
          ),

          SliverToBoxAdapter(
            child: Column(
              children: [
                _buildHero(r),
                _buildAlerteBanner(r),
                const SizedBox(height: 10),
                if (r.meteo.heures.isNotEmpty) _buildHeures(r.meteo),
                const SizedBox(height: 10),
                if (r.meteo.jours.isNotEmpty)
                  _buildJours(r.meteo)
                else
                  _buildPrevFallback(r),
                const SizedBox(height: 10),
                _buildRisques(r),
                const SizedBox(height: 40),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── Hero : grande température ─────────────────────────────────────────────
  Widget _buildHero(RiskReport r) {
    final m = r.meteo;
    final temp = m.temperature > 0
        ? '${m.temperature.round()}°'
        : r.indicateurs.temperatureMax > 0
            ? '${r.indicateurs.temperatureMax.round()}°'
            : '--°';
    final condition = m.temperature > 0 ? m.condition : _conditionFromAlerte(r.niveauAlerte);
    final hasMinMax = m.tempMax > 0 || m.tempMin > 0;

    return Padding(
      padding: const EdgeInsets.fromLTRB(0, 4, 0, 16),
      child: Column(
        children: [
          // Température
          Text(temp,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 88,
              fontWeight: FontWeight.w100,
              height: 1.0,
              letterSpacing: -4,
            )),
          const SizedBox(height: 4),
          Text(condition,
            style: const TextStyle(
                color: Colors.white70, fontSize: 20, fontWeight: FontWeight.w300)),
          const SizedBox(height: 6),
          if (hasMinMax)
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text('↑ ${m.tempMax.round()}°',
                  style: const TextStyle(color: Colors.white70, fontSize: 15)),
                const SizedBox(width: 14),
                Text('↓ ${m.tempMin.round()}°',
                  style: const TextStyle(color: Colors.white54, fontSize: 15)),
              ],
            )
          else if (r.indicateurs.temperatureMax > 0)
            Text('Max ${r.indicateurs.temperatureMax.round()}°',
              style: const TextStyle(color: Colors.white60, fontSize: 15)),
        ],
      ),
    );
  }

  String _conditionFromAlerte(String n) {
    switch (n) {
      case 'VERT':   return 'Conditions normales';
      case 'JAUNE':  return 'Vigilance requise';
      case 'ORANGE': return 'Risque modéré';
      case 'ROUGE':  return 'Risque élevé';
      default:       return 'En attente…';
    }
  }

  // ── Bannière alerte compacte ──────────────────────────────────────────────
  Widget _buildAlerteBanner(RiskReport r) {
    final color = Color(Config.alertColors[r.niveauAlerte] ?? Config.alertColors['INCONNU']!);
    final label = Config.alertLabels[r.niveauAlerte] ?? r.niveauAlerte;
    // N'afficher que si pas VERT (pas d'alerte = pas besoin d'alerter)
    if (r.niveauAlerte == 'VERT') {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: _glassCard(
          child: Row(
            children: [
              const Icon(Icons.check_circle_outline, color: Colors.greenAccent, size: 18),
              const SizedBox(width: 10),
              const Text('Aucune alerte climatique active',
                style: TextStyle(color: Colors.white70, fontSize: 13)),
            ],
          ),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: color.withOpacity(0.18),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: color.withOpacity(0.5), width: 1),
        ),
        child: Row(
          children: [
            Icon(Icons.warning_amber_rounded, color: color, size: 20),
            const SizedBox(width: 10),
            Expanded(
              child: Text(label,
                style: TextStyle(
                    color: color, fontWeight: FontWeight.w600, fontSize: 15)),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(r.niveauAlerte,
                style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 11,
                    letterSpacing: 0.5)),
            ),
          ],
        ),
      ),
    );
  }

  // ── Prévisions horaires ───────────────────────────────────────────────────
  Widget _buildHeures(MeteoCourante m) {
    return _glassSection(
      label: 'PRÉVISIONS HORAIRES',
      icon: Icons.schedule_outlined,
      child: SizedBox(
        height: 90,
        child: ListView.builder(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 4),
          itemCount: m.heures.length,
          itemBuilder: (_, i) {
            final h   = m.heures[i];
            final now = i == 0;
            return SizedBox(
              width: 58,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  Text(now ? 'Maint.' : h.heure,
                    style: TextStyle(
                        color: now ? Colors.white : Colors.white60,
                        fontSize: 11,
                        fontWeight: now ? FontWeight.w600 : FontWeight.normal)),
                  Text(h.emoji, style: const TextStyle(fontSize: 22)),
                  Text('${h.temperature.round()}°',
                    style: const TextStyle(
                        color: Colors.white, fontSize: 15,
                        fontWeight: FontWeight.w500)),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  // ── Prévisions 7 jours ────────────────────────────────────────────────────
  Widget _buildJours(MeteoCourante m) {
    final allMax = m.jours.map((j) => j.tempMax).reduce((a, b) => a > b ? a : b);
    final allMin = m.jours.map((j) => j.tempMin).reduce((a, b) => a < b ? a : b);
    final range  = (allMax - allMin).clamp(1.0, double.infinity);

    return _glassSection(
      label: 'PRÉVISIONS 7 JOURS',
      icon: Icons.calendar_today_outlined,
      child: Column(
        children: m.jours.map((j) {
          final leftFrac  = ((j.tempMin - allMin) / range).clamp(0.0, 1.0);
          final widthFrac = ((j.tempMax - j.tempMin) / range).clamp(0.05, 1.0);
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 5),
            child: Row(
              children: [
                SizedBox(width: 38,
                  child: Text(j.jour,
                    style: const TextStyle(
                        color: Colors.white70, fontSize: 14,
                        fontWeight: FontWeight.w500))),
                Text(j.emoji, style: const TextStyle(fontSize: 18)),
                const SizedBox(width: 10),
                Text('${j.tempMin.round()}°',
                  style: const TextStyle(color: Colors.white54, fontSize: 13)),
                const SizedBox(width: 6),
                Expanded(
                  child: LayoutBuilder(builder: (_, cst) => Stack(
                    children: [
                      Container(
                        height: 5,
                        decoration: BoxDecoration(
                          color: Colors.white12,
                          borderRadius: BorderRadius.circular(3)),
                      ),
                      Positioned(
                        left:  leftFrac  * cst.maxWidth,
                        width: widthFrac * cst.maxWidth,
                        top: 0, bottom: 0,
                        child: Container(
                          decoration: BoxDecoration(
                            gradient: const LinearGradient(colors: [
                              Color(0xFF4FC3F7), Color(0xFFFF8A65)
                            ]),
                            borderRadius: BorderRadius.circular(3)),
                        ),
                      ),
                    ],
                  )),
                ),
                const SizedBox(width: 6),
                Text('${j.tempMax.round()}°',
                  style: const TextStyle(
                      color: Colors.white, fontSize: 13,
                      fontWeight: FontWeight.w600)),
              ],
            ),
          );
        }).toList(),
      ),
    );
  }

  // Fallback prévisions si pas de données meteo.jours
  Widget _buildPrevFallback(RiskReport r) {
    return _glassSection(
      label: 'PRÉVISIONS',
      icon: Icons.calendar_today_outlined,
      child: Row(
        children: [
          Expanded(child: _prevPill('J+3', r.prevu3j.niveauGlobal)),
          const SizedBox(width: 10),
          Expanded(child: _prevPill('J+7', r.prevu7j.niveauGlobal)),
        ],
      ),
    );
  }

  // ── Risques SAMCAM compacts ───────────────────────────────────────────────
  Widget _buildRisques(RiskReport r) {
    return _glassSection(
      label: 'RISQUES SAMCAM',
      icon: Icons.shield_outlined,
      child: Column(
        children: [
          _riskRow('💧 Inondation', r.actuel.scores.inondation, const Color(0xFF4FC3F7)),
          const SizedBox(height: 8),
          _riskRow('🏜️ Sécheresse', r.actuel.scores.secheresse, const Color(0xFFFFB74D)),
          const SizedBox(height: 8),
          _riskRow('🔥 Chaleur',    r.actuel.scores.chaleur,    const Color(0xFFEF5350)),
        ],
      ),
    );
  }

  // ── Widgets helpers ───────────────────────────────────────────────────────
  Widget _glassCard({required Widget child}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.12),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withOpacity(0.15)),
      ),
      child: child,
    );
  }

  Widget _glassSection({
    required String label,
    required IconData icon,
    required Widget child,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Container(
        padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.1),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Colors.white.withOpacity(0.15)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 11, color: Colors.white54),
                const SizedBox(width: 5),
                Text(label,
                  style: const TextStyle(
                      color: Colors.white54,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.8)),
              ],
            ),
            const SizedBox(height: 10),
            child,
          ],
        ),
      ),
    );
  }

  Widget _riskRow(String label, double score, Color color) {
    return Row(
      children: [
        SizedBox(width: 100,
          child: Text(label,
            style: const TextStyle(color: Colors.white70, fontSize: 13))),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: score.clamp(0.0, 1.0),
              backgroundColor: Colors.white12,
              valueColor: AlwaysStoppedAnimation<Color>(color),
              minHeight: 6,
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(width: 34,
          child: Text('${(score * 100).round()}%',
            textAlign: TextAlign.right,
            style: TextStyle(
                color: color, fontWeight: FontWeight.bold, fontSize: 12))),
      ],
    );
  }

  Widget _prevPill(String horizon, String niveau) {
    final color = Color(Config.alertColors[niveau] ?? Config.alertColors['INCONNU']!);
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.4)),
      ),
      child: Column(
        children: [
          Text(horizon, style: const TextStyle(color: Colors.white54, fontSize: 12)),
          const SizedBox(height: 5),
          Text(niveau,
            style: TextStyle(
                color: color, fontWeight: FontWeight.bold,
                fontSize: 15, letterSpacing: 0.5)),
        ],
      ),
    );
  }

  Widget _pillBtn(String label, IconData icon, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.15),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: Colors.white24),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: Colors.white, size: 16),
            const SizedBox(width: 6),
            Text(label, style: const TextStyle(color: Colors.white, fontSize: 14)),
          ],
        ),
      ),
    );
  }
}

// ════════════════════════════════════════════════════════════════════════════
// CustomPainter : fond météo animé
// ════════════════════════════════════════════════════════════════════════════

class _SkyPainter extends CustomPainter {
  final int wmoCode;
  final List<Color> colors;
  final double animValue; // 0.0 → 1.0 en boucle

  _SkyPainter({
    required this.wmoCode,
    required this.colors,
    required this.animValue,
  });

  @override
  void paint(Canvas canvas, Size size) {
    // Dégradé de fond
    final bgPaint = Paint()
      ..shader = LinearGradient(
          colors: colors,
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter)
        .createShader(Rect.fromLTWH(0, 0, size.width, size.height));
    canvas.drawRect(Rect.fromLTWH(0, 0, size.width, size.height), bgPaint);

    if (wmoCode == 0) {
      // ☀️ Ciel ensoleillé : soleil + rayons
      _paintSun(canvas, size);
    } else if (wmoCode <= 2) {
      // ⛅ Quelques nuages
      _paintSun(canvas, size, small: true);
      _paintClouds(canvas, size, count: 2, opacity: 0.7);
    } else if (wmoCode == 3) {
      // ☁️ Couvert
      _paintClouds(canvas, size, count: 4, opacity: 0.9);
    } else if (wmoCode >= 51 && wmoCode <= 82) {
      // 🌧️ Pluie / averses
      _paintClouds(canvas, size, count: 3, opacity: 0.85, dark: true);
      _paintRain(canvas, size);
    } else if (wmoCode >= 95) {
      // ⛈️ Orage
      _paintClouds(canvas, size, count: 4, opacity: 0.95, dark: true);
      _paintRain(canvas, size, heavy: true);
      _paintLightning(canvas, size);
    } else {
      // Par défaut : quelques nuages
      _paintClouds(canvas, size, count: 2, opacity: 0.6);
    }
  }

  void _paintSun(Canvas canvas, Size size, {bool small = false}) {
    final cx = size.width * 0.72;
    final cy = size.height * 0.12;
    final r  = small ? size.width * 0.08 : size.width * 0.14;
    final halo = r * 1.6;

    // Halo extérieur
    final haloPaint = Paint()
      ..color = Colors.white.withOpacity(0.15)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 30);
    canvas.drawCircle(Offset(cx, cy), halo, haloPaint);

    // Rayons animés
    final rayPaint = Paint()
      ..color = Colors.white.withOpacity(0.35)
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round;
    for (int i = 0; i < 8; i++) {
      final angle  = (i / 8) * math.pi * 2 + animValue * math.pi * 2;
      final inner  = r * 1.25;
      final outer  = r * 1.9;
      canvas.drawLine(
        Offset(cx + math.cos(angle) * inner, cy + math.sin(angle) * inner),
        Offset(cx + math.cos(angle) * outer, cy + math.sin(angle) * outer),
        rayPaint,
      );
    }

    // Corps du soleil
    final sunPaint = Paint()
      ..shader = RadialGradient(
          colors: [Colors.white.withOpacity(0.95), Colors.yellow.withOpacity(0.6)])
        .createShader(Rect.fromCircle(center: Offset(cx, cy), radius: r));
    canvas.drawCircle(Offset(cx, cy), r, sunPaint);
  }

  void _paintClouds(Canvas canvas, Size size,
      {int count = 3, double opacity = 0.7, bool dark = false}) {
    final baseColor = dark
        ? Colors.blueGrey.shade700.withOpacity(opacity)
        : Colors.white.withOpacity(opacity);
    final cloudPaint = Paint()..color = baseColor;

    // Positions et tailles des nuages (décalage animé horizontal)
    final configs = [
      [0.1,  0.08, 0.38, 0.10],
      [0.45, 0.13, 0.30, 0.08],
      [0.65, 0.07, 0.28, 0.07],
      [0.20, 0.22, 0.22, 0.06],
    ];

    for (int i = 0; i < count.clamp(0, configs.length); i++) {
      final cfg    = configs[i];
      final speed  = 0.04 + i * 0.015;
      final xBase  = (cfg[0] + animValue * speed) % 1.0;
      final cx     = xBase * size.width;
      final cy     = cfg[1] * size.height;
      final rw     = cfg[2] * size.width;
      final rh     = cfg[3] * size.height;
      _drawCloud(canvas, cloudPaint, cx, cy, rw, rh);
    }
  }

  void _drawCloud(Canvas canvas, Paint p,
      double cx, double cy, double rw, double rh) {
    canvas.drawOval(
        Rect.fromCenter(center: Offset(cx, cy), width: rw, height: rh), p);
    canvas.drawOval(
        Rect.fromCenter(
            center: Offset(cx - rw * 0.25, cy + rh * 0.1),
            width: rw * 0.55, height: rh * 0.85),
        p);
    canvas.drawOval(
        Rect.fromCenter(
            center: Offset(cx + rw * 0.3, cy + rh * 0.15),
            width: rw * 0.5, height: rh * 0.8),
        p);
  }

  void _paintRain(Canvas canvas, Size size, {bool heavy = false}) {
    final drops   = heavy ? 60 : 30;
    final rng     = math.Random(42);
    final paint   = Paint()
      ..color = Colors.lightBlueAccent.withOpacity(0.4)
      ..strokeWidth = 1.2
      ..strokeCap = StrokeCap.round;

    for (int i = 0; i < drops; i++) {
      final x   = rng.nextDouble() * size.width;
      // offset vertical animé
      final yRaw = (rng.nextDouble() + animValue) % 1.0;
      final y    = yRaw * size.height;
      canvas.drawLine(
        Offset(x - 2, y),
        Offset(x + 2, y + 14),
        paint,
      );
    }
  }

  void _paintLightning(Canvas canvas, Size size) {
    // Éclair visible 20% du temps
    final phase = (animValue * 3) % 1.0;
    if (phase < 0.2) {
      final flash = Paint()
        ..color = Colors.yellowAccent.withOpacity(0.85)
        ..strokeWidth = 2
        ..strokeCap = StrokeCap.round;
      final bx = size.width * 0.5;
      final by = size.height * 0.2;
      final path = Path()
        ..moveTo(bx,        by)
        ..lineTo(bx - 14,  by + 28)
        ..lineTo(bx - 4,   by + 28)
        ..lineTo(bx - 20,  by + 60)
        ..lineTo(bx + 4,   by + 34)
        ..lineTo(bx - 6,   by + 34)
        ..close();
      canvas.drawPath(path, flash);
    }
  }

  @override
  bool shouldRepaint(_SkyPainter old) =>
      old.animValue != animValue || old.wmoCode != wmoCode;
}
