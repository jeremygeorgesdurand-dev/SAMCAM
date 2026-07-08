import 'package:flutter/material.dart';
import '../services/api_service.dart';

// ── Zones SAMCAM (liste statique = fallback hors-serveur) ──────────────────
const List<Map<String, dynamic>> kSamcamZones = [
  {'name': 'Kribi',        'lat': 2.9399,  'lon': 9.9098,  'climate': 'Équatorial côtier'},
  {'name': 'Ebolowa',      'lat': 2.9000,  'lon': 11.1500, 'climate': 'Équatorial'},
  {'name': 'Kumba',        'lat': 4.6364,  'lon': 9.4469,  'climate': 'Équatorial'},
  {'name': 'Bafoussam',    'lat': 5.4765,  'lon': 10.4178, 'climate': 'Tropical montagnard'},
  {'name': 'Yaounde_peri', 'lat': 3.8480,  'lon': 11.5021, 'climate': 'Équatorial'},
  {'name': 'Ngaoundere',   'lat': 7.3220,  'lon': 13.5840, 'climate': 'Tropical montagnard'},
  {'name': 'Garoua',       'lat': 9.3000,  'lon': 13.3900, 'climate': 'Sahélien'},
  {'name': 'Maroua',       'lat': 10.5910, 'lon': 14.3159, 'climate': 'Sahélien'},
];

String _climateEmoji(String climate) {
  if (climate.contains('côtier'))     return '🌊';
  if (climate.contains('montagnard')) return '⛰️';
  if (climate.contains('Sahélien'))   return '🏜️';
  return '🌿';
}

String _displayName(String name) {
  if (name == 'Yaounde_peri') return 'Yaoundé (péri.)';
  return name;
}

// ══════════════════════════════════════════════════════════════════════════════
// ZoneDrawer — volet latéral gauche animé
// ══════════════════════════════════════════════════════════════════════════════
class ZoneDrawer extends StatefulWidget {
  final String currentCity;          // nom de la ville GPS actuelle
  final String? selectedZone;        // zone actuellement affichée (null = GPS auto)
  final void Function(String zoneName) onZoneSelected;
  final VoidCallback onCurrentLocationSelected;

  const ZoneDrawer({
    super.key,
    required this.currentCity,
    required this.selectedZone,
    required this.onZoneSelected,
    required this.onCurrentLocationSelected,
  });

  @override
  State<ZoneDrawer> createState() => _ZoneDrawerState();
}

class _ZoneDrawerState extends State<ZoneDrawer> {
  List<String>? _serverZones;

  @override
  void initState() {
    super.initState();
    _tryLoadServerZones();
  }

  Future<void> _tryLoadServerZones() async {
    try {
      final zones = await ApiService.listZones();
      if (mounted && zones.isNotEmpty) {
        setState(() => _serverZones = zones);
      }
    } catch (_) {}
  }

  List<String> get _zones =>
      (_serverZones != null && _serverZones!.isNotEmpty)
          ? _serverZones!
          : kSamcamZones.map((z) => z['name'] as String).toList();

  Map<String, dynamic>? _zoneInfo(String name) {
    try {
      return kSamcamZones.firstWhere((z) => z['name'] == name);
    } catch (_) {
      return null;
    }
  }

  bool get _isGpsMode => widget.selectedZone == null;

  @override
  Widget build(BuildContext context) {
    final topPadding = MediaQuery.of(context).padding.top;

    return Drawer(
      width: 300,
      backgroundColor: Colors.transparent,
      child: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              const Color(0xFF0D1A2E).withOpacity(0.97),
              const Color(0xFF0A2438).withOpacity(0.97),
            ],
          ),
          border: Border(
            right: BorderSide(
              color: Colors.white.withOpacity(0.12),
              width: 0.8,
            ),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ── En-tête ──────────────────────────────────────────────
            SizedBox(height: topPadding + 12),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.08),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: Colors.white.withOpacity(0.15)),
                    ),
                    child: const Text(
                      'SAMCAM',
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 2,
                        fontSize: 14,
                      ),
                    ),
                  ),
                  const Spacer(),
                  const Text(
                    'Zones',
                    style: TextStyle(
                      color: Colors.white38,
                      fontSize: 12,
                      letterSpacing: 0.5,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 20),
              child: Text(
                'LOCALISATION',
                style: TextStyle(
                  color: Colors.white38,
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.2,
                ),
              ),
            ),
            const SizedBox(height: 8),
            // ── Tuile position GPS actuelle ───────────────────────────
            _LocationTile(
              cityName: widget.currentCity.isNotEmpty
                  ? widget.currentCity
                  : 'Position GPS',
              isSelected: _isGpsMode,
              onTap: () {
                Navigator.pop(context);
                widget.onCurrentLocationSelected();
              },
            ),
            const SizedBox(height: 20),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 20),
              child: Text(
                'ZONES SAMCAM',
                style: TextStyle(
                  color: Colors.white38,
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.2,
                ),
              ),
            ),
            const SizedBox(height: 8),
            // ── Liste des 8 zones ─────────────────────────────────────
            Expanded(
              child: ListView.builder(
                padding: const EdgeInsets.only(bottom: 24),
                itemCount: _zones.length,
                itemBuilder: (ctx, i) {
                  final zoneName = _zones[i];
                  final info     = _zoneInfo(zoneName);
                  final isSelected = widget.selectedZone == zoneName;
                  return _ZoneTile(
                    name:       _displayName(zoneName),
                    rawName:    zoneName,
                    climate:    info?['climate'] as String? ?? '',
                    emoji:      info != null ? _climateEmoji(info['climate'] as String) : '📍',
                    isSelected: isSelected,
                    onTap: () {
                      Navigator.pop(context);
                      widget.onZoneSelected(zoneName);
                    },
                  );
                },
              ),
            ),
            // ── Pied de volet ─────────────────────────────────────────
            Container(
              padding: EdgeInsets.fromLTRB(
                  20, 12, 20, MediaQuery.of(context).padding.bottom + 12),
              decoration: BoxDecoration(
                border: Border(
                  top: BorderSide(color: Colors.white.withOpacity(0.08)),
                ),
              ),
              child: const Text(
                'Système d\'Alerte Météo Cameroun',
                style: TextStyle(
                  color: Colors.white24,
                  fontSize: 10,
                  letterSpacing: 0.3,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Tuile « Position GPS actuelle » ──────────────────────────────────────────
class _LocationTile extends StatelessWidget {
  final String cityName;
  final bool isSelected;
  final VoidCallback onTap;

  const _LocationTile({
    required this.cityName,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
            decoration: BoxDecoration(
              color: isSelected
                  ? Colors.white.withOpacity(0.14)
                  : Colors.white.withOpacity(0.05),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: isSelected
                    ? Colors.white.withOpacity(0.30)
                    : Colors.white.withOpacity(0.08),
                width: isSelected ? 1.0 : 0.6,
              ),
            ),
            child: Row(
              children: [
                Icon(
                  Icons.my_location,
                  color: isSelected ? Colors.white : Colors.white54,
                  size: 18,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        cityName,
                        style: TextStyle(
                          color: isSelected ? Colors.white : Colors.white70,
                          fontSize: 14,
                          fontWeight: isSelected
                              ? FontWeight.w600
                              : FontWeight.w400,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 2),
                      const Text(
                        'Ma position actuelle',
                        style: TextStyle(
                          color: Colors.white38,
                          fontSize: 11,
                        ),
                      ),
                    ],
                  ),
                ),
                if (isSelected)
                  const Icon(
                    Icons.check_circle_outline,
                    color: Colors.white54,
                    size: 16,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ── Tuile de zone ─────────────────────────────────────────────────────────────
class _ZoneTile extends StatelessWidget {
  final String name;
  final String rawName;
  final String climate;
  final String emoji;
  final bool isSelected;
  final VoidCallback onTap;

  const _ZoneTile({
    required this.name,
    required this.rawName,
    required this.climate,
    required this.emoji,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 3),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              color: isSelected
                  ? Colors.white.withOpacity(0.14)
                  : Colors.transparent,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: isSelected
                    ? Colors.white.withOpacity(0.28)
                    : Colors.transparent,
                width: 0.8,
              ),
            ),
            child: Row(
              children: [
                Text(emoji, style: const TextStyle(fontSize: 20)),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name,
                        style: TextStyle(
                          color: isSelected ? Colors.white : Colors.white70,
                          fontSize: 14,
                          fontWeight: isSelected
                              ? FontWeight.w600
                              : FontWeight.w400,
                        ),
                      ),
                      if (climate.isNotEmpty) ...[  
                        const SizedBox(height: 2),
                        Text(
                          climate,
                          style: const TextStyle(
                            color: Colors.white38,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                if (isSelected)
                  const Icon(
                    Icons.check_circle_outline,
                    color: Colors.white54,
                    size: 16,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
