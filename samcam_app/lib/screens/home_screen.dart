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

  Color _alertColor(String niveau) =>
      Color(Config.alertColors[niveau] ?? Config.alertColors['INCONNU']!);

  String _alertLabel(String niveau) =>
      Config.alertLabels[niveau] ?? niveau;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161B22),
        title: Row(
          children: [
            Container(
              width: 32, height: 32,
              decoration: BoxDecoration(
                color: const Color(0xFF01696F),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(Icons.water_drop, color: Colors.white, size: 18),
            ),
            const SizedBox(width: 10),
            const Text('SAMCAM',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
                letterSpacing: 1.5,
              )),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.history, color: Colors.white70),
            tooltip: 'Historique',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const HistoryScreen()),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined, color: Colors.white70),
            tooltip: 'Réglages',
            onPressed: () async {
              await Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const SettingsScreen()),
              );
              _fetchRisk();
            },
          ),
          IconButton(
            icon: const Icon(Icons.refresh, color: Colors.white70),
            tooltip: 'Actualiser',
            onPressed: _fetchRisk,
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _fetchRisk,
        color: const Color(0xFF01696F),
        child: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(
        child: CircularProgressIndicator(color: Color(0xFF01696F)),
      );
    }
    if (_error != null) return _buildError();
    if (_report == null) {
      return const Center(
        child: Text('Aucune donnée', style: TextStyle(color: Colors.white54)),
      );
    }
    return _buildReport(_report!);
  }

  Widget _buildError() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, color: Colors.white38, size: 64),
            const SizedBox(height: 16),
            const Text('Serveur inaccessible',
              style: TextStyle(color: Colors.white,
                  fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(_error!,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white54, fontSize: 13)),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF01696F)),
              onPressed: _fetchRisk,
              icon: const Icon(Icons.refresh),
              label: const Text('Réessayer'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildReport(RiskReport r) {
    final color = _alertColor(r.niveauAlerte);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // ── Niveau d'alerte global ─────────────────────────────────────────
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: color.withOpacity(0.15),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: color.withOpacity(0.5), width: 1.5),
          ),
          child: Column(
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(r.zone,
                        style: const TextStyle(
                            color: Colors.white70, fontSize: 13)),
                      const SizedBox(height: 4),
                      Text(r.date,
                        style: const TextStyle(
                            color: Colors.white38, fontSize: 12)),
                    ],
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 8),
                    decoration: BoxDecoration(
                      color: color,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(r.niveauAlerte,
                      style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                          letterSpacing: 1)),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Text(_alertLabel(r.niveauAlerte),
                style: TextStyle(
                    color: color, fontSize: 20,
                    fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Text('Modèle : ${r.methodeRisque}',
                style: const TextStyle(
                    color: Colors.white38, fontSize: 11)),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // ── Indicateurs météo ──────────────────────────────────────────────
        _sectionTitle('Indicateurs'),
        const SizedBox(height: 8),
        Row(
          children: [
            _indicCard('Pluie 7j',
                '${r.indicateurs.pluie7j.toStringAsFixed(1)} mm',
                Icons.water_drop_outlined),
            const SizedBox(width: 10),
            _indicCard('Prévue 7j',
                '${r.indicateurs.pluiePrevue7j.toStringAsFixed(1)} mm',
                Icons.umbrella_outlined),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            _indicCard('Temp. max',
                '${r.indicateurs.temperatureMax.toStringAsFixed(1)} °C',
                Icons.thermostat_outlined),
            const SizedBox(width: 10),
            _indicCard('NDVI',
                r.indicateurs.ndviMoyen.toStringAsFixed(3),
                Icons.eco_outlined),
          ],
        ),
        const SizedBox(height: 20),

        // ── Scores de risque ───────────────────────────────────────────────
        _sectionTitle('Risques actuels'),
        const SizedBox(height: 8),
        _riskBar('Inondation', r.actuel.scores.inondation,
            const Color(0xFF1565C0)),
        _riskBar('Sécheresse', r.actuel.scores.secheresse,
            const Color(0xFFE65100)),
        _riskBar('Chaleur',    r.actuel.scores.chaleur,
            const Color(0xFFC62828)),
        const SizedBox(height: 20),

        // ── Prévisions J+3 / J+7 ──────────────────────────────────────────
        _sectionTitle('Prévisions'),
        const SizedBox(height: 8),
        Row(
          children: [
            _prevCard('J+3', r.prevu3j.niveauGlobal),
            const SizedBox(width: 10),
            _prevCard('J+7', r.prevu7j.niveauGlobal),
          ],
        ),
        const SizedBox(height: 32),
      ],
    );
  }

  Widget _sectionTitle(String title) => Text(title,
    style: const TextStyle(
        color: Colors.white70, fontSize: 13,
        fontWeight: FontWeight.w600, letterSpacing: 0.8));

  Widget _indicCard(String label, String value, IconData icon) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: const Color(0xFF161B22),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.white12),
        ),
        child: Row(
          children: [
            Icon(icon, color: const Color(0xFF4F98A3), size: 22),
            const SizedBox(width: 10),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label,
                  style: const TextStyle(
                      color: Colors.white54, fontSize: 11)),
                Text(value,
                  style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                      fontSize: 15)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _riskBar(String label, double score, Color color) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label,
                style: const TextStyle(
                    color: Colors.white70, fontSize: 13)),
              Text('${(score * 100).toStringAsFixed(0)}%',
                style: TextStyle(
                    color: color,
                    fontWeight: FontWeight.bold,
                    fontSize: 13)),
            ],
          ),
          const SizedBox(height: 6),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: score.clamp(0.0, 1.0),
              backgroundColor: Colors.white12,
              valueColor: AlwaysStoppedAnimation<Color>(color),
              minHeight: 8,
            ),
          ),
        ],
      ),
    );
  }

  Widget _prevCard(String horizon, String niveau) {
    final color = _alertColor(niveau);
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: color.withOpacity(0.12),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withOpacity(0.4)),
        ),
        child: Column(
          children: [
            Text(horizon,
              style: const TextStyle(
                  color: Colors.white54, fontSize: 12)),
            const SizedBox(height: 8),
            Text(niveau,
              style: TextStyle(
                  color: color,
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                  letterSpacing: 1)),
          ],
        ),
      ),
    );
  }
}
