// SAMCAM — Vue d'ensemble : niveau de risque des 8 zones en un coup d'œil.
// Taper une carte sélectionne la zone et revient à l'écran principal.

import 'package:flutter/material.dart';
import '../config.dart';
import '../services/api_service.dart';
import '../widgets/cameroon_map.dart';

class OverviewScreen extends StatefulWidget {
  const OverviewScreen({super.key});

  @override
  State<OverviewScreen> createState() => _OverviewScreenState();
}

class _OverviewScreenState extends State<OverviewScreen> {
  List<Map<String, dynamic>> _zones = [];
  bool    _loading = true;
  bool    _showMap = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _fetch();
  }

  Future<void> _fetch() async {
    setState(() { _loading = true; _error = null; });
    try {
      final zones = await ApiService.getOverview();
      setState(() { _zones = zones; _loading = false; });
    } catch (e) {
      setState(() { _error = e.toString(); _loading = false; });
    }
  }

  Color _alertColor(String niveau) =>
      Color(Config.alertColors[niveau] ?? Config.alertColors['INCONNU']!);

  String _displayZoneName(String name) =>
      name == 'Yaounde_peri' ? 'Yaoundé (péri.)' : name;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161B22),
        title: const Text("Vue d'ensemble",
          style: TextStyle(color: Colors.white)),
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          IconButton(
            tooltip: _showMap ? 'Vue grille' : 'Vue carte',
            icon: Icon(_showMap ? Icons.grid_view_rounded : Icons.map_outlined,
              color: Colors.white70),
            onPressed: () => setState(() => _showMap = !_showMap),
          ),
          IconButton(
            icon: const Icon(Icons.refresh, color: Colors.white70),
            onPressed: _fetch,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFF01696F)))
          : _error != null
              ? Center(child: Text(_error!, style: const TextStyle(color: Colors.white54)))
              : _showMap
                  ? _buildMapView()
                  : RefreshIndicator(
                      onRefresh: _fetch,
                      color: Colors.white,
                      child: GridView.builder(
                        padding: const EdgeInsets.all(16),
                        // Hauteur FIXE (mainAxisExtent) plutôt qu'un ratio largeur/hauteur —
                        // sur un écran large (tablette/web), un childAspectRatio étire les
                        // cartes à une hauteur énorme puisque leur largeur suit le nombre de
                        // colonnes. maxCrossAxisExtent adapte aussi le nombre de colonnes à
                        // la largeur d'écran au lieu de le figer à 2.
                        gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                          maxCrossAxisExtent: 260,
                          crossAxisSpacing: 12,
                          mainAxisSpacing: 12,
                          mainAxisExtent: 192,
                        ),
                        itemCount: _zones.length,
                        itemBuilder: (_, i) => _buildZoneCard(_zones[i]),
                      ),
                    ),
    );
  }

  /// Coordonnées des 8 zones SAMCAM (mêmes valeurs que kSamcamZones).
  static const Map<String, (double, double)> _zoneCoords = {
    'Kribi':        (2.9399, 9.9098),
    'Ebolowa':      (2.9000, 11.1500),
    'Kumba':        (4.6364, 9.4469),
    'Bafoussam':    (5.4765, 10.4178),
    'Yaounde_peri': (3.8480, 11.5021),
    'Ngaoundere':   (7.3220, 13.5840),
    'Garoua':       (9.3000, 13.3900),
    'Maroua':       (10.5910, 14.3159),
  };

  Widget _buildMapView() {
    final mapZones = _zones.map((z) {
      final name = (z['zone'] as String?) ?? '';
      final coords = _zoneCoords[name];
      if (coords == null) return null;
      return MapZone(
        name: name,
        lat: coords.$1,
        lon: coords.$2,
        niveauAlerte: (z['niveau_alerte'] as String?) ?? 'INCONNU',
      );
    }).whereType<MapZone>().toList();

    return Column(
      children: [
        Expanded(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: CameroonMap(
              zones: mapZones,
              onZoneTap: (name) => Navigator.pop(context, name),
            ),
          ),
        ),
        // Légende des niveaux d'alerte
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: Wrap(
            spacing: 14,
            runSpacing: 6,
            alignment: WrapAlignment.center,
            children: [
              for (final niveau in const ['VERT', 'JAUNE', 'ORANGE', 'ROUGE'])
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 10, height: 10,
                      decoration: BoxDecoration(
                        color: _alertColor(niveau), shape: BoxShape.circle),
                    ),
                    const SizedBox(width: 5),
                    Text(Config.alertLabels[niveau] ?? niveau,
                      style: const TextStyle(color: Colors.white60, fontSize: 11)),
                  ],
                ),
            ],
          ),
        ),
      ],
    );
  }

  Color _riskColor(double score) {
    if (score < 0.25) return const Color(0xFF66BB6A);
    if (score < 0.50) return const Color(0xFFFFEE58);
    if (score < 0.75) return const Color(0xFFFFB74D);
    return const Color(0xFFEF5350);
  }

  Widget _buildZoneCard(Map<String, dynamic> z) {
    final niveau = (z['niveau_alerte'] as String?) ?? 'INCONNU';
    final color  = _alertColor(niveau);
    final scores = (z['scores'] as Map?) ?? {};

    double score(String key) => ((scores[key] ?? 0.0) as num).toDouble();

    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => Navigator.pop(context, z['zone'] as String),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: const Color(0xFF161B22),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: color.withOpacity(0.35)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(_displayZoneName(z['zone'] as String? ?? ''),
                      style: const TextStyle(
                        color: Colors.white, fontSize: 15, fontWeight: FontWeight.w700),
                      maxLines: 1, overflow: TextOverflow.ellipsis),
                  ),
                  Container(
                    width: 10, height: 10,
                    decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                  ),
                ],
              ),
              const SizedBox(height: 3),
              Text(niveau,
                style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.bold)),
              const SizedBox(height: 14),
              _miniRiskRow(Icons.water_outlined, score('score_inondation')),
              const SizedBox(height: 8),
              _miniRiskRow(Icons.grass_outlined, score('score_secheresse')),
              const SizedBox(height: 8),
              _miniRiskRow(Icons.local_fire_department_outlined, score('score_chaleur')),
            ],
          ),
        ),
      ),
    );
  }

  Widget _miniRiskRow(IconData icon, double score) {
    final color = _riskColor(score);
    return Row(
      children: [
        Icon(icon, color: Colors.white38, size: 13),
        const SizedBox(width: 6),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(3),
            child: LinearProgressIndicator(
              value: score.clamp(0.0, 1.0),
              backgroundColor: Colors.white12,
              valueColor: AlwaysStoppedAnimation<Color>(color),
              minHeight: 5)),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 34,
          child: Text('${(score * 100).toStringAsFixed(0)}%',
            textAlign: TextAlign.right,
            style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w700)),
        ),
      ],
    );
  }
}
