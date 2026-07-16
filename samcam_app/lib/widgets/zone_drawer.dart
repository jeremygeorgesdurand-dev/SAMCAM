import 'package:flutter/material.dart';
import '../l10n/app_localizations.dart';
import '../services/api_service.dart';
import '../services/weather_service.dart';
import '../models/custom_location.dart';
import '../models/weather_forecast.dart' show weatherCodeIcon;

// ── Zones SAMCAM (liste statique = fallback hors-serveur) ──────────────────
const List<Map<String, dynamic>> kSamcamZones = [
  {'name': 'Kribi',        'lat': 2.9399,  'lon': 9.9098 },
  {'name': 'Ebolowa',      'lat': 2.9000,  'lon': 11.1500},
  {'name': 'Kumba',        'lat': 4.6364,  'lon': 9.4469 },
  {'name': 'Bafoussam',    'lat': 5.4765,  'lon': 10.4178},
  {'name': 'Yaounde_peri', 'lat': 3.8480,  'lon': 11.5021},
  {'name': 'Ngaoundere',   'lat': 7.3220,  'lon': 13.5840},
  {'name': 'Garoua',       'lat': 9.3000,  'lon': 13.3900},
  {'name': 'Maroua',       'lat': 10.5910, 'lon': 14.3159},
  // Zones agricoles ajoutées
  {'name': 'Ndop',         'lat': 5.9833,  'lon': 10.4500},
  {'name': 'Foumbot',      'lat': 5.5167,  'lon': 10.6333},
  {'name': 'Kaele',        'lat': 10.1167, 'lon': 14.4500},
  {'name': 'Guider',       'lat': 9.9333,  'lon': 13.9500},
  {'name': 'Meiganga',     'lat': 6.5167,  'lon': 14.3000},
  {'name': 'Mbalmayo',     'lat': 3.5167,  'lon': 11.5000},
  {'name': 'Bafia',        'lat': 4.7500,  'lon': 11.2333},
  {'name': 'Bertoua',      'lat': 4.5833,  'lon': 13.6833},
  {'name': 'Nkongsamba',   'lat': 4.9547,  'lon': 9.9401 },
  {'name': 'Buea',         'lat': 4.1560,  'lon': 9.2420 },
];

String _displayName(String name) {
  if (name == 'Yaounde_peri') return 'Yaoundé (péri.)';
  if (name == 'Kaele') return 'Kaélé';
  return name;
}

// ══════════════════════════════════════════════════════════════════════════════
// ZoneDrawer — volet latéral gauche animé
// ══════════════════════════════════════════════════════════════════════════════
class ZoneDrawer extends StatefulWidget {
  final String currentCity;          // nom de la ville GPS actuelle
  final String? selectedZone;        // zone SAMCAM actuellement affichée
  final String? selectedCustomName;  // endroit personnalisé actuellement affiché
  final double? currentTemp;         // météo actuelle (mode GPS) — température
  final int?    currentWeatherCode;  // météo actuelle (mode GPS) — code WMO
  final void Function(String zoneName) onZoneSelected;
  final void Function(CustomLocation location) onCustomLocationSelected;
  final VoidCallback onCurrentLocationSelected;

  const ZoneDrawer({
    super.key,
    required this.currentCity,
    required this.selectedZone,
    required this.selectedCustomName,
    required this.onZoneSelected,
    required this.onCustomLocationSelected,
    required this.onCurrentLocationSelected,
    this.currentTemp,
    this.currentWeatherCode,
  });

  @override
  State<ZoneDrawer> createState() => _ZoneDrawerState();
}

class _ZoneDrawerState extends State<ZoneDrawer> {
  List<String>? _serverZones;
  List<CustomLocation> _customLocations = [];

  /// nom du lieu → (température, code météo)
  final Map<String, ({double temp, int code})> _weatherSummary = {};

  @override
  void initState() {
    super.initState();
    _tryLoadServerZones();
    _loadCustomLocations();
    _loadWeatherSummaries();
  }

  Future<void> _tryLoadServerZones() async {
    try {
      final zones = await ApiService.listZones();
      if (mounted && zones.isNotEmpty) {
        setState(() => _serverZones = zones);
      }
    } catch (_) {}
  }

  Future<void> _loadCustomLocations() async {
    final locations = await ApiService.getCustomLocations();
    if (mounted) setState(() => _customLocations = locations);
    _loadWeatherSummaries();
  }

  Future<void> _loadWeatherSummaries() async {
    final targets = <String, (double, double)>{
      for (final z in kSamcamZones)
        z['name'] as String: (z['lat'] as double, z['lon'] as double),
      for (final c in _customLocations) c.name: (c.lat, c.lon),
    };
    for (final entry in targets.entries) {
      if (_weatherSummary.containsKey(entry.key)) continue;
      WeatherService.getCurrentLight(entry.value.$1, entry.value.$2).then((w) {
        if (w != null && mounted) {
          setState(() => _weatherSummary[entry.key] = w);
        }
      });
    }
  }

  List<String> get _zones =>
      (_serverZones != null && _serverZones!.isNotEmpty)
          ? _serverZones!
          : kSamcamZones.map((z) => z['name'] as String).toList();

  Future<void> _confirmAndAdd(BuildContext dialogCtx, GeocodeResult result) async {
    final loc = result.toCustomLocation();
    await ApiService.addCustomLocation(loc);
    if (dialogCtx.mounted) Navigator.pop(dialogCtx);
    await _loadCustomLocations();
    widget.onCustomLocationSelected(loc);
  }

  Future<void> _showAddLocationDialog() async {
    final t = AppLocalizations.of(context)!;
    final controller = TextEditingController();
    bool searching = false;
    String? error;
    List<GeocodeResult> results = [];

    await showDialog<void>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) {
          Future<void> runSearch() async {
            final query = controller.text;
            if (query.trim().isEmpty) return;
            setDialogState(() { searching = true; error = null; results = []; });
            final found = await ApiService.searchCity(query);
            setDialogState(() {
              searching = false;
              results    = found;
              error      = found.isEmpty ? t.drawerNoLocationFound(query) : null;
            });
          }

          return AlertDialog(
            backgroundColor: const Color(0xFF0D1A2E),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: Text(t.drawerAddLocationTitle, style: const TextStyle(color: Colors.white)),
            content: SizedBox(
              width: 320,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: controller,
                          autofocus: true,
                          style: const TextStyle(color: Colors.white),
                          decoration: InputDecoration(
                            hintText: t.drawerCityNameHint,
                            hintStyle: const TextStyle(color: Colors.white38),
                            filled: true,
                            fillColor: Colors.white.withOpacity(0.06),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(10),
                              borderSide: BorderSide.none,
                            ),
                          ),
                          onSubmitted: (_) => runSearch(),
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton(
                        onPressed: searching ? null : runSearch,
                        icon: searching
                            ? const SizedBox(
                                width: 16, height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white54))
                            : const Icon(Icons.search, color: Colors.white70),
                      ),
                    ],
                  ),
                  if (error != null) ...[
                    const SizedBox(height: 8),
                    Text(error!, style: const TextStyle(color: Colors.redAccent, fontSize: 12)),
                  ],
                  if (results.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    Text(t.drawerSelectLocationHint,
                      style: const TextStyle(color: Colors.white38, fontSize: 11)),
                    const SizedBox(height: 4),
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxHeight: 260),
                      child: ListView.separated(
                        shrinkWrap: true,
                        itemCount: results.length,
                        separatorBuilder: (_, __) => const Divider(color: Colors.white12, height: 1),
                        itemBuilder: (_, i) {
                          final r = results[i];
                          return InkWell(
                            onTap: () => _confirmAndAdd(ctx, r),
                            child: Padding(
                              padding: const EdgeInsets.symmetric(vertical: 10),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(r.shortName,
                                    style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600)),
                                  const SizedBox(height: 2),
                                  Text(r.fullAddress,
                                    style: const TextStyle(color: Colors.white54, fontSize: 11),
                                    maxLines: 2, overflow: TextOverflow.ellipsis),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: Text(t.drawerCancel, style: const TextStyle(color: Colors.white54)),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _removeCustomLocation(CustomLocation loc) async {
    await ApiService.removeCustomLocation(loc.name);
    await _loadCustomLocations();
  }

  bool get _isGpsMode => widget.selectedZone == null && widget.selectedCustomName == null;

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context)!;
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
                  Text(
                    t.drawerZonesLabel,
                    style: const TextStyle(
                      color: Colors.white38,
                      fontSize: 12,
                      letterSpacing: 0.5,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Text(
                t.drawerLocationSectionLabel,
                style: const TextStyle(
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
                  : t.settingsGpsPosition,
              isSelected: _isGpsMode,
              temp: widget.currentTemp,
              weatherCode: widget.currentWeatherCode,
              onTap: () {
                Navigator.pop(context);
                widget.onCurrentLocationSelected();
              },
            ),
            const SizedBox(height: 20),
            // ── Contenu défilant : zones + endroits personnalisés ─────
            Expanded(
              child: ListView(
                padding: const EdgeInsets.only(bottom: 24),
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    child: Text(
                      t.drawerZonesSamcamLabel,
                      style: const TextStyle(
                        color: Colors.white38,
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 1.2,
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  for (final zoneName in _zones)
                    _ZoneTile(
                      name:        _displayName(zoneName),
                      isSelected:  widget.selectedZone == zoneName,
                      weather:     _weatherSummary[zoneName],
                      onTap: () {
                        Navigator.pop(context);
                        widget.onZoneSelected(zoneName);
                      },
                    ),
                  const SizedBox(height: 20),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    child: Text(
                      t.drawerMyPlacesLabel,
                      style: const TextStyle(
                        color: Colors.white38,
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 1.2,
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  for (final loc in _customLocations)
                    _ZoneTile(
                      name:        loc.name,
                      isSelected:  widget.selectedCustomName == loc.name,
                      weather:     _weatherSummary[loc.name],
                      onTap: () {
                        Navigator.pop(context);
                        widget.onCustomLocationSelected(loc);
                      },
                      onDelete: () => _removeCustomLocation(loc),
                    ),
                  _AddLocationTile(onTap: _showAddLocationDialog, label: t.drawerAddLocationTitle),
                ],
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
              child: Text(
                t.drawerFooterTagline,
                style: const TextStyle(
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

// ── Petit résumé météo (icône + température) réutilisé par les tuiles ──────
Widget _weatherSummaryChip(({double temp, int code})? weather) {
  if (weather == null) return const SizedBox.shrink();
  return Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Text(weatherCodeIcon(weather.code), style: const TextStyle(fontSize: 15)),
      const SizedBox(width: 4),
      Text('${weather.temp.toStringAsFixed(0)}°',
        style: const TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.w500)),
    ],
  );
}

// ── Tuile « Position GPS actuelle » ──────────────────────────────────────────
class _LocationTile extends StatelessWidget {
  final String cityName;
  final bool isSelected;
  final double? temp;
  final int? weatherCode;
  final VoidCallback onTap;

  const _LocationTile({
    required this.cityName,
    required this.isSelected,
    required this.onTap,
    this.temp,
    this.weatherCode,
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
                  child: Text(
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
                ),
                if (temp != null && weatherCode != null) ...[
                  _weatherSummaryChip((temp: temp!, code: weatherCode!)),
                  const SizedBox(width: 8),
                ],
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

// ── Tuile de zone / endroit personnalisé ────────────────────────────────────
class _ZoneTile extends StatelessWidget {
  final String name;
  final bool isSelected;
  final ({double temp, int code})? weather;
  final VoidCallback onTap;
  final VoidCallback? onDelete;

  const _ZoneTile({
    required this.name,
    required this.isSelected,
    required this.onTap,
    this.weather,
    this.onDelete,
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
                Icon(Icons.location_on_outlined,
                  color: isSelected ? Colors.white70 : Colors.white38, size: 16),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    name,
                    style: TextStyle(
                      color: isSelected ? Colors.white : Colors.white70,
                      fontSize: 14,
                      fontWeight: isSelected
                          ? FontWeight.w600
                          : FontWeight.w400,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 6),
                _weatherSummaryChip(weather),
                if (isSelected) ...[
                  const SizedBox(width: 8),
                  const Icon(
                    Icons.check_circle_outline,
                    color: Colors.white54,
                    size: 16,
                  ),
                ],
                if (onDelete != null)
                  IconButton(
                    icon: const Icon(Icons.close, color: Colors.white24, size: 15),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                    visualDensity: VisualDensity.compact,
                    onPressed: onDelete,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ── Tuile « Ajouter un endroit » ─────────────────────────────────────────────
class _AddLocationTile extends StatelessWidget {
  final VoidCallback onTap;
  final String label;
  const _AddLocationTile({required this.onTap, required this.label});

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
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: Colors.white.withOpacity(0.15),
                width: 0.8,
              ),
            ),
            child: Row(
              children: [
                const Icon(Icons.add, color: Colors.white54, size: 16),
                const SizedBox(width: 10),
                Text(
                  label,
                  style: const TextStyle(color: Colors.white54, fontSize: 14),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
