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

class _HomeScreenState extends State<HomeScreen> {
  RiskReport? _report;
  bool        _loading = true;
  String?     _error;

  @override
  void initState() {
    super.initState();
    _fetchRisk();
  }

  Future<void> _fetchRisk() async {
    setState(() { _loading = true; _error = null; });
    try {
      final report = await ApiService.getRisk();
      setState(() { _report = report; _loading = false; });
    } catch (e) {
      setState(() {
        _error   = 'Impossible de joindre le serveur SAMCAM.\n$e';
        _loading = false;
      });
    }
  }

  // Couleurs dégradé selon alerte
  List<Color> _bgGradient(String niveau) {
    switch (niveau) {
      case 'VERT':   return [const Color(0xFF1B4332), const Color(0xFF081C15)];
      case 'JAUNE':  return [const Color(0xFF3D2C00), const Color(0xFF1A1200)];
      case 'ORANGE': return [const Color(0xFF3D1A00), const Color(0xFF1A0A00)];
      case 'ROUGE':  return [const Color(0xFF3D0000), const Color(0xFF1A0000)];
      default:       return [const Color(0xFF0D2137), const Color(0xFF0D1117)];
    }
  }

  Color _alertColor(String niveau) =>
      Color(Config.alertColors[niveau] ?? Config.alertColors['INCONNU']!);

  @override
  Widget build(BuildContext context) {
    final niveau  = _report?.niveauAlerte ?? 'INCONNU';
    final colors  = _bgGradient(niveau);

    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: colors,
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ),
        ),
        child: SafeArea(
          child: _loading
              ? const Center(child: CircularProgressIndicator(
                  color: Colors.white70))
              : _error != null
                  ? _buildError()
                  : _buildContent(),
        ),
      ),
    );
  }

  // ── Error state ────────────────────────────────────────────────────
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
              style: TextStyle(color: Colors.white,
                  fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(_error!,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white54, fontSize: 13)),
            const SizedBox(height: 28),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _glassButton('Réessayer', Icons.refresh, _fetchRisk),
                const SizedBox(width: 12),
                _glassButton('Réglages', Icons.settings_outlined, () async {
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

  // ── Contenu principal ────────────────────────────────────────────────
  Widget _buildContent() {
    final r = _report!;
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
                  color: Colors.white,
                  fontWeight: FontWeight.w600,
                  fontSize: 17)),
            centerTitle: true,
            actions: [
              IconButton(
                icon: const Icon(Icons.history, color: Colors.white70),
                onPressed: () => Navigator.push(context,
                  MaterialPageRoute(builder: (_) => const HistoryScreen())),
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
                // ── Hero météo Apple-style ───────────────────────────────
                _buildHero(r),

                // ── Alerte SAMCAM ────────────────────────────────────────
                _buildAlerteBanner(r),

                const SizedBox(height: 12),

                // ── Prévisions horaires (scroll horizontal) ─────────────
                if (r.meteo.heures.isNotEmpty)
                  _buildHeures(r.meteo)
                else
                  _buildHeuresFallback(r),

                const SizedBox(height: 12),

                // ── Prévisions 7 jours ─────────────────────────────────
                if (r.meteo.jours.isNotEmpty)
                  _buildJours(r.meteo)
                else
                  _buildJoursFallback(r),

                const SizedBox(height: 12),

                // ── Détails météo (vent, humidité, pluie, NDVI) ──────
                _buildDetails(r),

                const SizedBox(height: 12),

                // ── Scores de risque SAMCAM ───────────────────────────
                _buildRisques(r),

                const SizedBox(height: 40),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── Hero : grande température + condition ─────────────────────────
  Widget _buildHero(RiskReport r) {
    final meteo = r.meteo;
    final tempDisplay = meteo.temperature > 0
        ? '${meteo.temperature.round()}°'
        : r.indicateurs.temperatureMax > 0
            ? '${r.indicateurs.temperatureMax.round()}°'
            : '--°';
    final condition = meteo.temperature > 0
        ? meteo.condition
        : _conditionFromAlerte(r.niveauAlerte);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
      child: Column(
        children: [
          Text(meteo.emoji.isNotEmpty ? meteo.emoji : '🌤️',
            style: const TextStyle(fontSize: 72)),
          Text(tempDisplay,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 96,
              fontWeight: FontWeight.w200,
              height: 1.0,
              letterSpacing: -4,
            )),
          const SizedBox(height: 4),
          Text(condition,
            style: const TextStyle(
                color: Colors.white70,
                fontSize: 22,
                fontWeight: FontWeight.w300)),
          const SizedBox(height: 8),
          if (meteo.tempMax > 0 || meteo.tempMin > 0)
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text('↑ ${meteo.tempMax.round()}°',
                  style: const TextStyle(
                      color: Colors.white70, fontSize: 16)),
                const SizedBox(width: 12),
                Text('↓ ${meteo.tempMin.round()}°',
                  style: const TextStyle(
                      color: Colors.white54, fontSize: 16)),
              ],
            )
          else if (r.indicateurs.temperatureMax > 0)
            Text('Max ${r.indicateurs.temperatureMax.round()}°',
              style: const TextStyle(
                  color: Colors.white70, fontSize: 16)),
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  String _conditionFromAlerte(String niveau) {
    switch (niveau) {
      case 'VERT':   return 'Conditions normales';
      case 'JAUNE':  return 'Vigilance requise';
      case 'ORANGE': return 'Risque modéré';
      case 'ROUGE':  return 'Risque élevé';
      default:       return 'Données indisponibles';
    }
  }

  // ── Bannière alerte ────────────────────────────────────────────────
  Widget _buildAlerteBanner(RiskReport r) {
    final color = _alertColor(r.niveauAlerte);
    final label = Config.alertLabels[r.niveauAlerte] ?? r.niveauAlerte;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: _glassCard(
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(r.niveauAlerte,
                style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 13,
                    letterSpacing: 1)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Alerte SAMCAM — Kribi',
                    style: const TextStyle(
                        color: Colors.white54,
                        fontSize: 11,
                        letterSpacing: 0.5)),
                  Text(label,
                    style: TextStyle(
                        color: color,
                        fontWeight: FontWeight.w600,
                        fontSize: 15)),
                ],
              ),
            ),
            Text(r.date,
              style: const TextStyle(
                  color: Colors.white38, fontSize: 11)),
          ],
        ),
      ),
    );
  }

  // ── Prévisions horaires (données serveur) ───────────────────────
  Widget _buildHeures(MeteoCourante meteo) {
    return _glassSection(
      label: 'PRÉVISIONS HORAIRES',
      icon: Icons.schedule_outlined,
      child: SizedBox(
        height: 100,
        child: ListView.builder(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 8),
          itemCount: meteo.heures.length,
          itemBuilder: (_, i) {
            final h = meteo.heures[i];
            return Container(
              width: 60,
              margin: const EdgeInsets.symmetric(horizontal: 4),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  Text(h.heure,
                    style: const TextStyle(
                        color: Colors.white60, fontSize: 12)),
                  Text(h.emoji,
                    style: const TextStyle(fontSize: 22)),
                  Text('${h.temperature.round()}°',
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w600)),
                  if (h.humidite > 0)
                    Text('${h.humidite.round()}%',
                      style: const TextStyle(
                          color: Colors.lightBlueAccent,
                          fontSize: 10)),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  // Fallback si pas de données horaires du serveur
  Widget _buildHeuresFallback(RiskReport r) {
    return _glassSection(
      label: 'APERÇU',
      icon: Icons.schedule_outlined,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            _miniStat('Pluie 7j',
                '${r.indicateurs.pluie7j.toStringAsFixed(0)} mm',
                '💧'),
            _miniStat('Prévue',
                '${r.indicateurs.pluiePrevue7j.toStringAsFixed(0)} mm',
                '☔'),
            _miniStat('NDVI',
                r.indicateurs.ndviMoyen.toStringAsFixed(2),
                '🌿'),
          ],
        ),
      ),
    );
  }

  // ── Prévisions 7 jours (données serveur) ────────────────────────
  Widget _buildJours(MeteoCourante meteo) {
    final allMax = meteo.jours.map((j) => j.tempMax).reduce(
        (a, b) => a > b ? a : b);
    final allMin = meteo.jours.map((j) => j.tempMin).reduce(
        (a, b) => a < b ? a : b);
    final range  = (allMax - allMin).clamp(1.0, double.infinity);

    return _glassSection(
      label: 'PRÉVISIONS 7 JOURS',
      icon: Icons.calendar_today_outlined,
      child: Column(
        children: meteo.jours.map((j) {
          final leftFrac  = ((j.tempMin - allMin) / range).clamp(0.0, 1.0);
          final widthFrac = ((j.tempMax - j.tempMin) / range).clamp(0.0, 1.0);
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 4),
            child: Row(
              children: [
                SizedBox(width: 36,
                  child: Text(j.jour,
                    style: const TextStyle(
                        color: Colors.white70,
                        fontSize: 14,
                        fontWeight: FontWeight.w500))),
                Text(j.emoji,
                  style: const TextStyle(fontSize: 18)),
                const SizedBox(width: 8),
                Text('${j.tempMin.round()}°',
                  style: const TextStyle(
                      color: Colors.white54, fontSize: 13)),
                const SizedBox(width: 6),
                Expanded(
                  child: LayoutBuilder(builder: (ctx, cst) {
                    return Stack(
                      children: [
                        Container(
                          height: 5,
                          decoration: BoxDecoration(
                            color: Colors.white12,
                            borderRadius: BorderRadius.circular(3),
                          ),
                        ),
                        Positioned(
                          left: leftFrac * cst.maxWidth,
                          width: widthFrac * cst.maxWidth,
                          top: 0, bottom: 0,
                          child: Container(
                            decoration: BoxDecoration(
                              gradient: const LinearGradient(
                                colors: [
                                  Color(0xFF4FC3F7),
                                  Color(0xFFFF8A65)
                                ],
                              ),
                              borderRadius: BorderRadius.circular(3),
                            ),
                          ),
                        ),
                      ],
                    );
                  }),
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

  // Fallback si pas de données journalières
  Widget _buildJoursFallback(RiskReport r) {
    return _glassSection(
      label: 'PRÉVISIONS',
      icon: Icons.calendar_today_outlined,
      child: Row(
        children: [
          Expanded(child: _prevCard2('J+3', r.prevu3j.niveauGlobal)),
          const SizedBox(width: 8),
          Expanded(child: _prevCard2('J+7', r.prevu7j.niveauGlobal)),
        ],
      ),
    );
  }

  // ── Détails météo : grille 2x2 ───────────────────────────────────────
  Widget _buildDetails(RiskReport r) {
    final m = r.meteo;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: GridView.count(
        crossAxisCount: 2,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        crossAxisSpacing: 10,
        mainAxisSpacing: 10,
        childAspectRatio: 1.6,
        children: [
          _detailCard('💧', 'Humidité',
            m.humidite > 0
                ? '${m.humidite.round()}%'
                : '--',
            'Taux d\'humidité actuel'),
          _detailCard('🌬️', 'Vent',
            m.vent > 0
                ? '${m.vent.round()} km/h'
                : '--',
            'Vitesse du vent'),
          _detailCard('🌧️', 'Pluie 24h',
            m.pluie24h > 0
                ? '${m.pluie24h.toStringAsFixed(1)} mm'
                : '${r.indicateurs.pluie7j.toStringAsFixed(0)} mm (7j)',
            'Précipitations'),
          _detailCard('🌿', 'NDVI',
            r.indicateurs.ndviMoyen.toStringAsFixed(3),
            'Indice végétation'),
        ],
      ),
    );
  }

  // ── Risques SAMCAM ───────────────────────────────────────────────────
  Widget _buildRisques(RiskReport r) {
    return _glassSection(
      label: 'RISQUES CLIMATIQUES • SAMCAM',
      icon: Icons.warning_amber_outlined,
      child: Column(
        children: [
          _riskRow('🚰 Inondation', r.actuel.scores.inondation,
              const Color(0xFF4FC3F7)),
          const SizedBox(height: 10),
          _riskRow('🏜️ Sécheresse', r.actuel.scores.secheresse,
              const Color(0xFFFFB74D)),
          const SizedBox(height: 10),
          _riskRow('🔥 Chaleur', r.actuel.scores.chaleur,
              const Color(0xFFEF5350)),
        ],
      ),
    );
  }

  // ── Widgets helpers ──────────────────────────────────────────────────

  Widget _glassCard({required Widget child}) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.1),
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
          color: Colors.white.withOpacity(0.08),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Colors.white.withOpacity(0.12)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 12, color: Colors.white54),
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

  Widget _detailCard(String emoji, String label,
      String value, String subtitle) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.08),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withOpacity(0.12)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Text(emoji, style: const TextStyle(fontSize: 16)),
              const SizedBox(width: 6),
              Text(subtitle,
                style: const TextStyle(
                    color: Colors.white54, fontSize: 10)),
            ],
          ),
          Text(value,
            style: const TextStyle(
                color: Colors.white,
                fontSize: 22,
                fontWeight: FontWeight.w300)),
          Text(label,
            style: const TextStyle(
                color: Colors.white60, fontSize: 11)),
        ],
      ),
    );
  }

  Widget _riskRow(String label, double score, Color color) {
    return Row(
      children: [
        SizedBox(width: 110,
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
              minHeight: 7,
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(width: 36,
          child: Text('${(score * 100).round()}%',
            textAlign: TextAlign.right,
            style: TextStyle(
                color: color,
                fontWeight: FontWeight.bold,
                fontSize: 13))),
      ],
    );
  }

  Widget _prevCard2(String horizon, String niveau) {
    final color = _alertColor(niveau);
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Column(
        children: [
          Text(horizon,
            style: const TextStyle(color: Colors.white54, fontSize: 12)),
          const SizedBox(height: 6),
          Text(niveau,
            style: TextStyle(
                color: color, fontWeight: FontWeight.bold,
                fontSize: 15, letterSpacing: 1)),
        ],
      ),
    );
  }

  Widget _miniStat(String label, String value, String emoji) {
    return Column(
      children: [
        Text(emoji, style: const TextStyle(fontSize: 20)),
        const SizedBox(height: 4),
        Text(value,
          style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w600,
              fontSize: 14)),
        Text(label,
          style: const TextStyle(
              color: Colors.white54, fontSize: 11)),
      ],
    );
  }

  Widget _glassButton(String label, IconData icon, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.15),
          borderRadius: BorderRadius.circular(20),
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
