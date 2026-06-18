import 'package:flutter/material.dart';
import '../config.dart';
import '../services/api_service.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<Map<String, dynamic>> _history = [];
  bool   _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _fetchHistory();
  }

  Future<void> _fetchHistory() async {
    setState(() { _loading = true; _error = null; });
    try {
      final h = await ApiService.getHistory(limit: 30);
      setState(() { _history = h; _loading = false; });
    } catch (e) {
      setState(() { _error = e.toString(); _loading = false; });
    }
  }

  Color _alertColor(String niveau) =>
      Color(Config.alertColors[niveau] ?? Config.alertColors['INCONNU']!);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161B22),
        title: const Text('Historique',
          style: TextStyle(color: Colors.white)),
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: Colors.white70),
            onPressed: _fetchHistory,
          ),
        ],
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: Color(0xFF01696F)))
          : _error != null
              ? Center(child: Text(_error!,
                  style: const TextStyle(color: Colors.white54)))
              : _history.isEmpty
                  ? const Center(child: Text('Aucun historique disponible',
                      style: TextStyle(color: Colors.white54)))
                  : ListView.separated(
                      padding: const EdgeInsets.all(16),
                      itemCount: _history.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 8),
                      itemBuilder: (_, i) => _buildHistoryItem(_history[i]),
                    ),
    );
  }

  Widget _buildHistoryItem(Map<String, dynamic> item) {
    final niveau = item['niveau_alerte'] ?? 'INCONNU';
    final color  = _alertColor(niveau);
    final scores = (item['risque_actuel'] as Map?) ?? {};

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          Container(
            width: 8, height: 48,
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(4),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item['date'] ?? '',
                  style: const TextStyle(
                      color: Colors.white70, fontSize: 13,
                      fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text(
                  'Inond: ${_pct(scores["inondation"])}  '
                  'Séch: ${_pct(scores["secheresse"])}  '
                  'Chal: ${_pct(scores["chaleur"])}',
                  style: const TextStyle(
                      color: Colors.white38, fontSize: 11)),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(
              color: color.withOpacity(0.2),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: color.withOpacity(0.5)),
            ),
            child: Text(niveau,
              style: TextStyle(
                  color: color,
                  fontWeight: FontWeight.bold,
                  fontSize: 12)),
          ),
        ],
      ),
    );
  }

  String _pct(dynamic v) =>
      '${((v ?? 0.0) * 100).toStringAsFixed(0)}%';
}
