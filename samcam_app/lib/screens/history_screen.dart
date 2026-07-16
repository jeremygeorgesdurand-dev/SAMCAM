import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../config.dart';
import '../l10n/app_localizations.dart';
import '../services/api_service.dart';
import '../widgets/zone_drawer.dart' show kSamcamZones;

class HistoryScreen extends StatefulWidget {
  final String? initialZone;
  const HistoryScreen({super.key, this.initialZone});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  late String _zone;
  List<Map<String, dynamic>> _history = [];
  bool    _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _zone = widget.initialZone ?? (kSamcamZones.first['name'] as String);
    _fetchHistory();
  }

  Future<void> _fetchHistory() async {
    setState(() { _loading = true; _error = null; });
    try {
      final h = await ApiService.getHistory(zone: _zone, days: 14);
      // Ordre antéchronologique (le plus récent en premier) pour la liste.
      setState(() { _history = h.reversed.toList(); _loading = false; });
    } catch (e) {
      setState(() { _error = e.toString(); _loading = false; });
    }
  }

  void _onZoneSelected(String zone) {
    if (zone == _zone) return;
    setState(() => _zone = zone);
    _fetchHistory();
  }

  Color _alertColor(String niveau) =>
      Color(Config.alertColors[niveau] ?? Config.alertColors['INCONNU']!);

  Color _riskColor(double score) {
    if (score < 0.25) return const Color(0xFF66BB6A);
    if (score < 0.50) return const Color(0xFFFFEE58);
    if (score < 0.75) return const Color(0xFFFFB74D);
    return const Color(0xFFEF5350);
  }

  late AppLocalizations t;

  String _displayZoneName(String name) {
    if (name == 'Yaounde_peri') return t.yaoundePeri;
    if (name == 'Kaele') return 'Kaélé';
    return name;
  }

  String _formatDate(String? iso) {
    if (iso == null) return '--';
    try {
      final d = DateTime.parse(iso);
      return _capitalize(DateFormat('EEEE d MMMM', 'fr_FR').format(d));
    } catch (_) {
      return iso;
    }
  }

  String _capitalize(String s) => s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);

  @override
  Widget build(BuildContext context) {
    t = AppLocalizations.of(context)!;
    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161B22),
        title: Text(t.historyTitle,
          style: const TextStyle(color: Colors.white)),
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: Colors.white70),
            onPressed: _fetchHistory,
          ),
        ],
      ),
      body: Column(
        children: [
          _buildZoneSelector(),
          const Divider(color: Colors.white12, height: 1),
          Expanded(
            child: _loading
                ? const Center(
                    child: CircularProgressIndicator(color: Color(0xFF01696F)))
                : _error != null
                    ? Center(child: Text(_error!,
                        style: const TextStyle(color: Colors.white54)))
                    : _history.isEmpty
                        ? Center(child: Text(t.historyEmptyState,
                            style: const TextStyle(color: Colors.white54)))
                        : ListView.builder(
                            padding: const EdgeInsets.all(16),
                            itemCount: _history.length,
                            itemBuilder: (_, i) => Padding(
                              padding: const EdgeInsets.only(bottom: 10),
                              child: _buildHistoryItem(_history[i]),
                            ),
                          ),
          ),
        ],
      ),
    );
  }

  Widget _buildZoneSelector() {
    return SizedBox(
      height: 52,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        children: [
          for (final z in kSamcamZones)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: _ZoneChip(
                label: _displayZoneName(z['name'] as String),
                selected: _zone == z['name'],
                onTap: () => _onZoneSelected(z['name'] as String),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildHistoryItem(Map<String, dynamic> item) {
    final niveau = item['niveau_alerte'] ?? 'INCONNU';
    final color  = _alertColor(niveau);
    final scores = (item['risque_actuel'] as Map?) ?? {};

    double score(String key) => ((scores[key] ?? 0.0) as num).toDouble();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(_formatDate(item['date'] as String?),
                  style: const TextStyle(
                    color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
                  overflow: TextOverflow.ellipsis),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: color.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: color.withOpacity(0.5))),
                child: Text(niveau,
                  style: TextStyle(
                    color: color, fontWeight: FontWeight.bold, fontSize: 12)),
              ),
            ],
          ),
          const SizedBox(height: 14),
          _miniRiskRow(Icons.water_outlined, t.riskFlood, score('score_inondation')),
          const SizedBox(height: 9),
          _miniRiskRow(Icons.grass_outlined, t.riskDrought, score('score_secheresse')),
          const SizedBox(height: 9),
          _miniRiskRow(Icons.local_fire_department_outlined, t.riskHeat, score('score_chaleur')),
        ],
      ),
    );
  }

  Widget _miniRiskRow(IconData icon, String label, double score) {
    final color = _riskColor(score);
    return Row(
      children: [
        Icon(icon, color: Colors.white38, size: 15),
        const SizedBox(width: 8),
        SizedBox(width: 82,
          child: Text(label, style: const TextStyle(color: Colors.white60, fontSize: 12))),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(3),
            child: LinearProgressIndicator(
              value: score.clamp(0.0, 1.0),
              backgroundColor: Colors.white12,
              valueColor: AlwaysStoppedAnimation<Color>(color),
              minHeight: 6)),
        ),
        const SizedBox(width: 10),
        SizedBox(
          width: 42,
          child: Text('${(score * 100).toStringAsFixed(0)}%',
            textAlign: TextAlign.right,
            style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 12)),
        ),
      ],
    );
  }
}

class _ZoneChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _ZoneChip({required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: selected ? const Color(0xFF01696F) : Colors.white.withOpacity(0.06),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: selected ? const Color(0xFF01696F) : Colors.white24,
              width: 1),
          ),
          child: Text(label,
            style: TextStyle(
              color: selected ? Colors.white : Colors.white60,
              fontSize: 13,
              fontWeight: selected ? FontWeight.w700 : FontWeight.w400)),
        ),
      ),
    );
  }
}
