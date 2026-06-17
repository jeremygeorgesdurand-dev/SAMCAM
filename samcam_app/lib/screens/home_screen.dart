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
  bool        _loading = true;
  String?     _error;
  late AnimationController _animCtrl;

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(
        vsync: this, duration: const Duration(seconds: 12))
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

  // ── Palette ciel selon code WMO ──────────────────────────────────────
  _SkyTheme _skyTheme(int wmo) {
    if (wmo == 0) {
      return _SkyTheme(
        top:    const Color(0xFF0A74DA),
        mid:    const Color(0xFF3B9EE8),
        bottom: const Color(0xFF87CEEB),
        sky:    _SkyType.sunny,
      );
    }
    if (wmo <= 2) {
      return _SkyTheme(
        top:    const Color(0xFF2C6FAC),
        mid:    const Color(0xFF5B9BD5),
        bottom: const Color(0xFFA8C8E8),
        sky:    _SkyType.partlyCloudy,
      );
    }
    if (wmo == 3) {
      return _SkyTheme(
        top:    const Color(0xFF3D5A73),
        mid:    const Color(0xFF5E7A91),
        bottom: const Color(0xFF8AA4B5),
        sky:    _SkyType.overcast,
      );
    }
    if (wmo >= 45 && wmo <= 48) {
      return _SkyTheme(
        top:    const Color(0xFF4A5568),
        mid:    const Color(0xFF718096),
        bottom: const Color(0xFFA0AEC0),
        sky:    _SkyType.fog,
      );
    }
    if (wmo >= 51 && wmo <= 67) {
      return _SkyTheme(
        top:    const Color(0xFF1A2F3F),
        mid:    const Color(0xFF2D4F66),
        bottom: const Color(0xFF3D6880),
        sky:    _SkyType.rainy,
      );
    }
    if (wmo >= 80 && wmo <= 82) {
      return _SkyTheme(
        top:    const Color(0xFF162232),
        mid:    const Color(0xFF253B4D),
        bottom: const Color(0xFF3A5468),
        sky:    _SkyType.rainy,
      );
    }
    if (wmo >= 95) {
      return _SkyTheme(
        top:    const Color(0xFF0D1B2A),
        mid:    const Color(0xFF1A2D3E),
        bottom: const Color(0xFF253D52),
        sky:    _SkyType.storm,
      );
    }
    return _SkyTheme(
      top:    const Color(0xFF3D5A73),
      mid:    const Color(0xFF5E7A91),
      bottom: const Color(0xFF8AA4B5),
      sky:    _SkyType.overcast,
    );
  }

  @override
  Widget build(BuildContext context) {
    final wmo   = _report?.meteo.codeMeteo ?? 0;
    final theme = _skyTheme(wmo);

    return Scaffold(
      body: Stack(
        children: [
          AnimatedBuilder(
            animation: _animCtrl,
            builder: (_, __) => CustomPaint(
              size: MediaQuery.of(context).size,
              painter: _SkyPainter(
                theme:     theme,
                animValue: _animCtrl.value,
              ),
            ),
          ),
          SafeArea(
            child: _loading
                ? const Center(child: CircularProgressIndicator(
                    color: Colors.white70))
                : _error != null
                    ? _buildError()
                    : _buildContent(_report!),
          ),
        ],
      ),
    );
  }

  // ── Error ────────────────────────────────────────────────────────────
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
              style: TextStyle(
                  color: Colors.white, fontSize: 20,
                  fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(_error!,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white54, fontSize: 12)),
            const SizedBox(height: 28),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _pillBtn('Réessayer', Icons.refresh, _fetchRisk),
                const SizedBox(width: 12),
                _pillBtn('Réglages', Icons.settings_outlined, () async {
                  await Navigator.push(context,
                    MaterialPageRoute(
                        builder: (_) => const SettingsScreen()));
                  _fetchRisk();
                }),
              ],
            ),
          ],
        ),
      ),
    );
  }

  // ── Contenu principal ───────────────────────────────────────────────
  Widget _buildContent(RiskReport r) {
    return RefreshIndicator(
      onRefresh: _fetchRisk,
      color: Colors.white,
      backgroundColor: Colors.white24,
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverAppBar(
            backgroundColor: Colors.transparent,
            elevation: 0,
            floating: true,
            title: Column(
              children: [
                Text(r.zone,
                  style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w600,
                      fontSize: 17)),
                if (r.date.isNotEmpty)
                  Text(r.date,
                    style: const TextStyle(
                        color: Colors.white54, fontSize: 11)),
              ],
            ),
            centerTitle: true,
            actions: [
              IconButton(
                icon: const Icon(Icons.history, color: Colors.white70),
                onPressed: () => Navigator.push(context,
                  MaterialPageRoute(
                      builder: (_) => const HistoryScreen())),
              ),
              IconButton(
                icon: const Icon(Icons.settings_outlined,
                    color: Colors.white70),
                onPressed: () async {
                  await Navigator.push(context,
                    MaterialPageRoute(
                        builder: (_) => const SettingsScreen()));
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
                const SizedBox(height: 12),
                if (r.meteo.heures.isNotEmpty)
                  _buildHeures(r.meteo)
                else
                  _buildHeuresFallback(r),
                const SizedBox(height: 12),
                if (r.meteo.jours.isNotEmpty)
                  _buildJours(r.meteo)
                else
                  _buildJoursFallback(r),
                const SizedBox(height: 12),
                _buildRisques(r),
                const SizedBox(height: 40),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── 1. Hero ──────────────────────────────────────────────────────────
  Widget _buildHero(RiskReport r) {
    final m    = r.meteo;
    final temp = m.temperature > 0
        ? '${m.temperature.round()}°'
        : r.indicateurs.temperatureMax > 0
            ? '${r.indicateurs.temperatureMax.round()}°'
            : '--°';
    final condition = m.temperature > 0
        ? m.condition
        : _conditionFromAlerte(r.niveauAlerte);

    return Padding(
      padding: const EdgeInsets.fromLTRB(0, 8, 0, 20),
      child: Column(
        children: [
          Text(temp,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 96,
              fontWeight: FontWeight.w100,
              height: 1.0,
              letterSpacing: -6,
            )),
          const SizedBox(height: 4),
          Text(condition,
            style: const TextStyle(
                color: Colors.white,
                fontSize: 20,
                fontWeight: FontWeight.w300)),
          const SizedBox(height: 8),
          if (m.tempMax > 0 || m.tempMin > 0)
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text('↑ ${m.tempMax.round()}°',
                  style: const TextStyle(
                      color: Colors.white70, fontSize: 16)),
                const SizedBox(width: 16),
                Text('↓ ${m.tempMin.round()}°',
                  style: const TextStyle(
                      color: Colors.white60, fontSize: 16)),
              ],
            )
          else if (r.indicateurs.temperatureMax > 0)
            Text('Max ${r.indicateurs.temperatureMax.round()}°',
              style: const TextStyle(
                  color: Colors.white70, fontSize: 16)),
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
      default:       return 'Chargement…';
    }
  }

  // ── 2. Bannière alerte ───────────────────────────────────────────────
  Widget _buildAlerteBanner(RiskReport r) {
    final color =
        Color(Config.alertColors[r.niveauAlerte] ?? Config.alertColors['INCONNU']!);
    final label = Config.alertLabels[r.niveauAlerte] ?? r.niveauAlerte;

    if (r.niveauAlerte == 'VERT') {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: _glassCard(
          child: Row(
            children: [
              const Icon(Icons.check_circle_outline,
                  color: Colors.greenAccent, size: 16),
              const SizedBox(width: 8),
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
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
        decoration: BoxDecoration(
          color: color.withOpacity(0.18),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: color.withOpacity(0.55)),
        ),
        child: Row(
          children: [
            Icon(Icons.warning_amber_rounded, color: color, size: 20),
            const SizedBox(width: 10),
            Expanded(
              child: Text(label,
                style: TextStyle(
                    color: color,
                    fontWeight: FontWeight.w600,
                    fontSize: 14)),
            ),
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
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

  // ── 3. Prévisions horaires ───────────────────────────────────────────
  Widget _buildHeures(MeteoCourante m) {
    final hasRain = m.heures.any((h) => h.pluie > 0.5);
    final desc = hasRain
        ? 'Pluie attendue au cours de la journée.'
        : 'Temps dégagé toute la journée.';

    return _glassSection(
      label: 'PRÉVISIONS HORAIRES',
      icon: Icons.schedule_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(desc,
            style: const TextStyle(color: Colors.white70, fontSize: 13)),
          const SizedBox(height: 8),
          const Divider(color: Colors.white12, height: 1),
          const SizedBox(height: 8),
          SizedBox(
            height: 90,
            child: ListView.builder(
              scrollDirection: Axis.horizontal,
              itemCount: m.heures.length,
              itemBuilder: (_, i) {
                final h   = m.heures[i];
                final now = i == 0;
                return SizedBox(
                  width: 62,
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      Text(now ? 'Maint.' : h.heure,
                        style: TextStyle(
                            color: now ? Colors.white : Colors.white60,
                            fontSize: 11,
                            fontWeight: now
                                ? FontWeight.w600
                                : FontWeight.normal)),
                      Text(h.emoji,
                          style: const TextStyle(fontSize: 22)),
                      Text('${h.temperature.round()}°',
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                            fontWeight: FontWeight.w500)),
                    ],
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  // ── Fallback indicateurs ────────────────────────────────────────────
  // Pluie 7j   = cumul réel des 7 derniers jours (données satellite + pluvio)
  // Pluie prévu = cumul prévu sur les 7 prochains jours (modèle météo)
  // Végétation  = état traduit depuis l'indice satellitaire (NDVI interne)
  Widget _buildHeuresFallback(RiskReport r) {
    return _glassSection(
      label: 'APERÇU DU JOUR',
      icon: Icons.schedule_outlined,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          _miniStat(
            'Pluie reçue (7j)',
            '${r.indicateurs.pluie7j.toStringAsFixed(0)} mm',
            '💧',
          ),
          _miniStat(
            'Pluie prévue (7j)',
            '${r.indicateurs.pluiePrevue7j.toStringAsFixed(0)} mm',
            '☂️',
          ),
          _miniStat(
            'Végétation',
            r.indicateurs.etatVegetation,
            r.indicateurs.etatVegetationEmoji,
          ),
        ],
      ),
    );
  }

  // ── 4. Prévisions 7 jours ────────────────────────────────────────────
  Widget _buildJours(MeteoCourante m) {
    final allMax = m.jours.map((j) => j.tempMax)
        .reduce((a, b) => a > b ? a : b);
    final allMin = m.jours.map((j) => j.tempMin)
        .reduce((a, b) => a < b ? a : b);
    final range = (allMax - allMin).clamp(1.0, double.infinity);

    return _glassSection(
      label: 'PRÉVISIONS 7 JOURS',
      icon: Icons.calendar_today_outlined,
      child: Column(
        children: List.generate(m.jours.length, (i) {
          final j  = m.jours[i];
          final lf = ((j.tempMin - allMin) / range).clamp(0.0, 1.0);
          final wf = ((j.tempMax - j.tempMin) / range).clamp(0.04, 1.0);
          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 5),
                child: Row(
                  children: [
                    SizedBox(
                      width: 40,
                      child: Text(j.jour,
                        style: TextStyle(
                          color: i == 0 ? Colors.white : Colors.white70,
                          fontSize: 15,
                          fontWeight: i == 0
                              ? FontWeight.w600
                              : FontWeight.w400)),
                    ),
                    Text(j.emoji,
                        style: const TextStyle(fontSize: 20)),
                    const SizedBox(width: 10),
                    SizedBox(
                      width: 28,
                      child: Text('${j.tempMin.round()}°',
                        textAlign: TextAlign.right,
                        style: const TextStyle(
                            color: Colors.white54, fontSize: 13)),
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: LayoutBuilder(
                        builder: (_, cst) => Stack(
                          children: [
                            Container(
                              height: 5,
                              decoration: BoxDecoration(
                                color: Colors.white12,
                                borderRadius: BorderRadius.circular(3)),
                            ),
                            Positioned(
                              left:  lf * cst.maxWidth,
                              width: wf * cst.maxWidth,
                              top: 0, bottom: 0,
                              child: Container(
                                decoration: BoxDecoration(
                                  gradient: const LinearGradient(
                                    colors: [
                                      Color(0xFF64B5F6),
                                      Color(0xFFFFCC80),
                                    ]),
                                  borderRadius: BorderRadius.circular(3)),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(width: 6),
                    SizedBox(
                      width: 30,
                      child: Text('${j.tempMax.round()}°',
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 13,
                            fontWeight: FontWeight.w600)),
                    ),
                  ],
                ),
              ),
              if (i < m.jours.length - 1)
                const Divider(color: Colors.white10, height: 1),
            ],
          );
        }),
      ),
    );
  }

  Widget _buildJoursFallback(RiskReport r) {
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

  // ── 5. Risques SAMCAM ────────────────────────────────────────────────
  // Les scores sont des probabilités continues (0–100%), calculées par
  // des règles physiques calibrées ou le modèle RandomForest entraîné,
  // puis affinées par Phi-3 mini pour la génération du résumé textuel.
  Widget _buildRisques(RiskReport r) {
    // Sous-titre méthode IA
    final bool iaActive = r.methodeRisque == 'modele_ml';
    final String methodeLabel = iaActive
        ? '✦ Analyse Phi-3 mini + RandomForest'
        : '⚙ Règles physiques calibrées';

    return _glassSection(
      label: 'RISQUES SAMCAM',
      icon: Icons.shield_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Méthode d'analyse
          Text(
            methodeLabel,
            style: TextStyle(
              color: iaActive
                  ? const Color(0xFFB39DDB)
                  : Colors.white38,
              fontSize: 11,
              fontWeight: FontWeight.w500,
              letterSpacing: 0.3,
            ),
          ),
          const SizedBox(height: 10),
          const Divider(color: Colors.white10, height: 1),
          const SizedBox(height: 10),
          _riskRow(
            '💧 Inondation',
            r.actuel.scores.inondation,
            _riskDescription('inondation', r.actuel.scores.inondation),
          ),
          const SizedBox(height: 10),
          _riskRow(
            '🏜️ Sécheresse',
            r.actuel.scores.secheresse,
            _riskDescription('secheresse', r.actuel.scores.secheresse),
          ),
          const SizedBox(height: 10),
          _riskRow(
            '🔥 Chaleur',
            r.actuel.scores.chaleur,
            _riskDescription('chaleur', r.actuel.scores.chaleur),
          ),
        ],
      ),
    );
  }

  /// Retourne une description textuelle du niveau de risque.
  /// Les scores sont graduels (0–100%), pas binaires :
  ///   < 25% → risque faible / normal
  ///   25–50% → risque modéré, vigilance conseillée
  ///   50–75% → risque élevé, attention requise
  ///   > 75% → risque critique
  String _riskDescription(String type, double score) {
    final pct = score * 100;
    if (type == 'inondation') {
      if (pct < 10)  return 'Aucun risque d\'inondation détecté.';
      if (pct < 25)  return 'Risque faible — sol peu saturé.';
      if (pct < 50)  return 'Risque modéré — surveiller les cumuls.';
      if (pct < 75)  return 'Risque élevé — zones basses à éviter.';
      return 'Risque critique — inondations probables.';
    } else if (type == 'secheresse') {
      if (pct < 10)  return 'Aucun stress hydrique détecté.';
      if (pct < 25)  return 'Légère sécheresse — situation normale.';
      if (pct < 50)  return 'Stress hydrique modéré — végétation sous tension.';
      if (pct < 75)  return 'Sécheresse marquée — irrigation conseillée.';
      return 'Sécheresse sévère — cultures en danger.';
    } else {
      if (pct < 10)  return 'Températures dans les normales.';
      if (pct < 25)  return 'Légère chaleur — rester hydraté.';
      if (pct < 50)  return 'Chaleur modérée — limiter l\'effort physique.';
      if (pct < 75)  return 'Forte chaleur — populations vulnérables à risque.';
      return 'Canicule — danger pour la santé.';
    }
  }

  // ── Widgets helpers ──────────────────────────────────────────────────

  Widget _glassCard({required Widget child}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.12),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withOpacity(0.15)),
      ),
      child: child,
    );
  }

  Widget _glassSection({
    required String   label,
    required IconData icon,
    required Widget   child,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Container(
        padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.1),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Colors.white.withOpacity(0.14)),
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

  /// Barre de risque avec couleur dynamique selon le score,
  /// et description textuelle sous la barre (non binaire).
  Widget _riskRow(String label, double score, String description) {
    // Couleur dynamique : vert → jaune → orange → rouge
    final Color color;
    if (score < 0.25) {
      color = const Color(0xFF66BB6A);        // vert
    } else if (score < 0.50) {
      color = const Color(0xFFFFEE58);        // jaune
    } else if (score < 0.75) {
      color = const Color(0xFFFFB74D);        // orange
    } else {
      color = const Color(0xFFEF5350);        // rouge
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            SizedBox(
              width: 110,
              child: Text(label,
                style: const TextStyle(
                    color: Colors.white70, fontSize: 13))),
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
            SizedBox(
              width: 36,
              child: Text('${(score * 100).round()}%',
                textAlign: TextAlign.right,
                style: TextStyle(
                    color: color,
                    fontWeight: FontWeight.bold,
                    fontSize: 12))),
          ],
        ),
        const SizedBox(height: 3),
        Padding(
          padding: const EdgeInsets.only(left: 2),
          child: Text(
            description,
            style: const TextStyle(
                color: Colors.white38,
                fontSize: 11,
                fontStyle: FontStyle.italic),
          ),
        ),
      ],
    );
  }

  Widget _prevPill(String horizon, String niveau) {
    final color =
        Color(Config.alertColors[niveau] ?? Config.alertColors['INCONNU']!);
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.4)),
      ),
      child: Column(
        children: [
          Text(horizon,
            style: const TextStyle(
                color: Colors.white54, fontSize: 12)),
          const SizedBox(height: 5),
          Text(niveau,
            style: TextStyle(
                color: color,
                fontWeight: FontWeight.bold,
                fontSize: 15,
                letterSpacing: 0.5)),
        ],
      ),
    );
  }

  Widget _miniStat(String label, String value, String emoji) {
    return Column(
      children: [
        Text(emoji, style: const TextStyle(fontSize: 22)),
        const SizedBox(height: 4),
        Text(value,
          style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w500,
              fontSize: 14)),
        Text(label,
          textAlign: TextAlign.center,
          style: const TextStyle(
              color: Colors.white54, fontSize: 11)),
      ],
    );
  }

  Widget _pillBtn(String label, IconData icon, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding:
            const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
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
            Text(label,
              style: const TextStyle(
                  color: Colors.white, fontSize: 14)),
          ],
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// SkyTheme — données de palette + type de ciel
// ═══════════════════════════════════════════════════════════════════════════

enum _SkyType { sunny, partlyCloudy, overcast, fog, rainy, storm }

class _SkyTheme {
  final Color    top;
  final Color    mid;
  final Color    bottom;
  final _SkyType sky;
  const _SkyTheme({
    required this.top, required this.mid,
    required this.bottom, required this.sky});
}

// ═══════════════════════════════════════════════════════════════════════════
// SkyPainter — fond météo réaliste
// ═══════════════════════════════════════════════════════════════════════════

class _SkyPainter extends CustomPainter {
  final _SkyTheme theme;
  final double   animValue;

  _SkyPainter({required this.theme, required this.animValue});

  @override
  void paint(Canvas canvas, Size size) {
    final bgPaint = Paint()
      ..shader = LinearGradient(
          colors: [theme.top, theme.mid, theme.bottom],
          stops: const [0.0, 0.5, 1.0],
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter)
        .createShader(Rect.fromLTWH(0, 0, size.width, size.height));
    canvas.drawRect(
        Rect.fromLTWH(0, 0, size.width, size.height), bgPaint);

    switch (theme.sky) {
      case _SkyType.sunny:
        _paintSun(canvas, size, full: true);
        break;
      case _SkyType.partlyCloudy:
        _paintSun(canvas, size, full: false);
        _paintClouds(canvas, size, count: 3, white: true, opacity: 0.85);
        break;
      case _SkyType.overcast:
        _paintClouds(canvas, size, count: 5, white: false, opacity: 0.75);
        break;
      case _SkyType.fog:
        _paintFog(canvas, size);
        break;
      case _SkyType.rainy:
        _paintClouds(canvas, size, count: 4, white: false, opacity: 0.9);
        _paintRain(canvas, size, heavy: false);
        break;
      case _SkyType.storm:
        _paintClouds(canvas, size, count: 5, white: false, opacity: 1.0);
        _paintRain(canvas, size, heavy: true);
        _paintLightning(canvas, size);
        break;
    }
  }

  void _paintSun(Canvas canvas, Size size, {required bool full}) {
    final heroH  = size.height * 0.40;
    final cx     = size.width  * 0.78;
    final cy     = size.height * 0.12;
    final r      = full
        ? math.min(size.width * 0.13, heroH * 0.55)
        : math.min(size.width * 0.09, heroH * 0.40);

    for (final haloR in [r * 3.5, r * 2.5, r * 1.8]) {
      final alpha = full
          ? (haloR == r * 3.5 ? 0.06 : haloR == r * 2.5 ? 0.10 : 0.14)
          : 0.06;
      canvas.drawCircle(
        Offset(cx, cy),
        haloR,
        Paint()
          ..color = Colors.white.withOpacity(alpha)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 20),
      );
    }

    if (full) {
      final rayPaint = Paint()
        ..strokeWidth = 1.5
        ..strokeCap   = StrokeCap.round;
      for (int i = 0; i < 8; i++) {
        final angle = (i / 8) * math.pi * 2
            + animValue * math.pi * 0.25;
        final inner = r * 1.35;
        final outer = r * 2.20;
        final alpha = 0.25 + 0.15 * math.sin(animValue * math.pi * 2 + i);
        rayPaint.color = Colors.white.withOpacity(alpha);
        canvas.drawLine(
          Offset(cx + math.cos(angle) * inner,
              cy + math.sin(angle) * inner),
          Offset(cx + math.cos(angle) * outer,
              cy + math.sin(angle) * outer),
          rayPaint,
        );
      }
    }

    canvas.drawCircle(
      Offset(cx, cy),
      r,
      Paint()
        ..shader = RadialGradient(
            colors: [
              const Color(0xFFFFF9C4),
              const Color(0xFFFFF176),
              const Color(0xFFFFD54F),
              const Color(0xFFFFB300),
            ],
            stops: const [0.0, 0.35, 0.70, 1.0],
          )
          .createShader(
              Rect.fromCircle(center: Offset(cx, cy), radius: r)),
    );

    canvas.drawCircle(
      Offset(cx - r * 0.25, cy - r * 0.25),
      r * 0.35,
      Paint()
        ..color = Colors.white.withOpacity(0.25)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8),
    );
  }

  void _paintClouds(Canvas canvas, Size size,
      {required int count, required bool white, required double opacity}) {
    final baseColor = white
        ? Colors.white.withOpacity(opacity)
        : const Color(0xFF5F6B7A).withOpacity(opacity);

    final configs = [
      [0.05, 0.07, 0.45, 0.10, 1.0],
      [0.50, 0.12, 0.38, 0.08, 0.7],
      [0.70, 0.05, 0.28, 0.07, 1.2],
      [0.15, 0.19, 0.33, 0.08, 0.9],
      [0.40, 0.22, 0.25, 0.06, 1.1],
    ];

    for (int i = 0; i < count.clamp(0, configs.length); i++) {
      final cfg   = configs[i];
      final speed = 0.03 * cfg[4];
      final xBase = (cfg[0] + animValue * speed) % 1.2 - 0.1;
      final cx    = xBase    * size.width;
      final cy    = cfg[1]   * size.height;
      final rw    = cfg[2]   * size.width;
      final rh    = cfg[3]   * size.height;

      if (!white) {
        _drawCloud(
          canvas,
          Paint()..color = Colors.black.withOpacity(0.08),
          cx + rw * 0.02, cy + rh * 0.15, rw, rh * 0.9,
        );
      }
      _drawCloud(canvas, Paint()..color = baseColor, cx, cy, rw, rh);
    }
  }

  void _drawCloud(Canvas canvas, Paint p,
      double cx, double cy, double rw, double rh) {
    canvas.drawOval(
        Rect.fromCenter(
            center: Offset(cx, cy), width: rw, height: rh), p);
    canvas.drawOval(
        Rect.fromCenter(
            center: Offset(cx - rw * 0.28, cy + rh * 0.08),
            width: rw * 0.55, height: rh * 0.85), p);
    canvas.drawOval(
        Rect.fromCenter(
            center: Offset(cx + rw * 0.28, cy + rh * 0.10),
            width: rw * 0.48, height: rh * 0.78), p);
    canvas.drawOval(
        Rect.fromCenter(
            center: Offset(cx + rw * 0.08, cy - rh * 0.18),
            width: rw * 0.40, height: rh * 0.70), p);
  }

  void _paintRain(Canvas canvas, Size size, {required bool heavy}) {
    final drops = heavy ? 80 : 40;
    final rng   = math.Random(17);
    final paint = Paint()
      ..color      = Colors.lightBlueAccent.withOpacity(0.35)
      ..strokeWidth = heavy ? 1.4 : 1.0
      ..strokeCap  = StrokeCap.round;

    for (int i = 0; i < drops; i++) {
      final x    = rng.nextDouble() * size.width;
      final yRaw = (rng.nextDouble() + animValue * 1.5) % 1.0;
      final y    = yRaw * size.height;
      canvas.drawLine(
        Offset(x - 2, y),
        Offset(x + 3, y + 16),
        paint,
      );
    }
  }

  void _paintFog(Canvas canvas, Size size) {
    for (int i = 0; i < 4; i++) {
      final yFrac  = 0.08 + i * 0.08;
      final offset = math.sin(animValue * math.pi * 2 + i) * 20;
      canvas.drawRect(
        Rect.fromLTWH(0, yFrac * size.height + offset,
            size.width, size.height * 0.04),
        Paint()
          ..color = Colors.white.withOpacity(0.12)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 12),
      );
    }
  }

  void _paintLightning(Canvas canvas, Size size) {
    final phase = (animValue * 4) % 1.0;
    if (phase < 0.18) {
      final bx = size.width * 0.48;
      final by = size.height * 0.18;
      final path = Path()
        ..moveTo(bx,        by)
        ..lineTo(bx - 12,  by + 30)
        ..lineTo(bx - 3,   by + 30)
        ..lineTo(bx - 18,  by + 64)
        ..lineTo(bx + 6,   by + 36)
        ..lineTo(bx - 4,   by + 36)
        ..close();
      canvas.drawPath(
        path,
        Paint()..color = Colors.yellowAccent.withOpacity(0.9),
      );
      canvas.drawPath(
        path,
        Paint()
          ..color = Colors.yellowAccent.withOpacity(0.25)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6),
      );
    }
  }

  @override
  bool shouldRepaint(_SkyPainter old) =>
      old.animValue != animValue || old.theme.sky != theme.sky;
}
