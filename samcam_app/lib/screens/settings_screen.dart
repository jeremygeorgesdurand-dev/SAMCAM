import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';
import '../services/api_service.dart';
import '../services/notification_service.dart';
import '../widgets/zone_drawer.dart' show kSamcamZones;
import 'demo_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _controller = TextEditingController();
  bool   _testing  = false;
  String? _testResult;
  bool   _testOk   = false;

  String? _favoriteZone;
  bool    _notificationsEnabled = false;
  final Map<String, double> _thresholds = {
    'inondation': Config.defaultAlertThreshold,
    'secheresse': Config.defaultAlertThreshold,
    'chaleur':    Config.defaultAlertThreshold,
  };

  @override
  void initState() {
    super.initState();
    _loadUrl();
    _loadFavoriteZone();
    _loadNotificationSettings();
  }

  Future<void> _loadUrl() async {
    final url = await ApiService.getServerUrl();
    _controller.text = url;
  }

  Future<void> _loadFavoriteZone() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() => _favoriteZone = prefs.getString(Config.prefFavoriteZone));
  }

  Future<void> _setFavoriteZone(String? zone) async {
    final prefs = await SharedPreferences.getInstance();
    if (zone == null) {
      await prefs.remove(Config.prefFavoriteZone);
    } else {
      await prefs.setString(Config.prefFavoriteZone, zone);
    }
    setState(() => _favoriteZone = zone);
  }

  Future<void> _loadNotificationSettings() async {
    final enabled = await NotificationService.isEnabled();
    final vals = <String, double>{};
    for (final risk in _thresholds.keys) {
      vals[risk] = await NotificationService.getThreshold(risk);
    }
    setState(() {
      _notificationsEnabled = enabled;
      _thresholds.addAll(vals);
    });
  }

  Future<void> _toggleNotifications(bool value) async {
    if (value) await NotificationService.init();
    await NotificationService.setEnabled(value);
    setState(() => _notificationsEnabled = value);
  }

  Future<void> _setThreshold(String risk, double value) async {
    setState(() => _thresholds[risk] = value);
    await NotificationService.setThreshold(risk, value);
  }

  Future<void> _saveUrl() async {
    final url = _controller.text.trim();
    if (url.isEmpty) return;
    await ApiService.setServerUrl(url);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('URL sauvegardée'),
          backgroundColor: Color(0xFF01696F),
        ),
      );
    }
  }

  Future<void> _testConnection() async {
    setState(() { _testing = true; _testResult = null; });
    final url = _controller.text.trim();
    await ApiService.setServerUrl(url);
    try {
      final health = await ApiService.getHealth();
      setState(() {
        _testOk     = true;
        _testResult = '✅ Connecté — Version ${health["version"]} '
            '| Dernière MAJ : ${health["derniere_maj"] ?? "N/A"}';
        _testing    = false;
      });
    } catch (e) {
      setState(() {
        _testOk     = false;
        _testResult = '❌ Connexion échouée : $e';
        _testing    = false;
      });
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161B22),
        title: const Text('Réglages',
          style: TextStyle(color: Colors.white)),
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [

            // ══ Section : Mode Démo ══════════════════════════════════════════
            _SectionHeader(icon: Icons.play_circle_outline_rounded,
                label: 'Mode Démo'),
            const SizedBox(height: 12),
            _DemoCard(
              onTap: () => Navigator.push(
                context,
                PageRouteBuilder(
                  pageBuilder: (_, a, __) => const DemoScreen(),
                  transitionsBuilder: (_, anim, __, child) =>
                    FadeTransition(opacity: anim, child: child),
                  transitionDuration: const Duration(milliseconds: 350),
                ),
              ),
            ),

            const SizedBox(height: 32),

            // ══ Section : Zone favorite ══════════════════════════════════════
            _SectionHeader(icon: Icons.star_outline_rounded, label: 'Zone par défaut'),
            const SizedBox(height: 12),
            const Text(
              "Zone affichée au démarrage de l'app, à la place du mode GPS automatique.",
              style: TextStyle(color: Colors.white54, fontSize: 12)),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8, runSpacing: 8,
              children: [
                _FavoriteChip(
                  label: 'Position GPS',
                  selected: _favoriteZone == null,
                  onTap: () => _setFavoriteZone(null),
                ),
                for (final z in kSamcamZones)
                  _FavoriteChip(
                    label: (z['name'] as String) == 'Yaounde_peri'
                        ? 'Yaoundé (péri.)' : z['name'] as String,
                    selected: _favoriteZone == z['name'],
                    onTap: () => _setFavoriteZone(z['name'] as String),
                  ),
              ],
            ),

            const SizedBox(height: 32),

            // ══ Section : Alertes ════════════════════════════════════════════
            _SectionHeader(icon: Icons.notifications_active_outlined, label: 'Alertes personnalisées'),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: Text(
                    _notificationsEnabled
                        ? 'Notifications activées'
                        : 'Recevoir une notification quand un risque dépasse votre seuil',
                    style: const TextStyle(color: Colors.white70, fontSize: 13)),
                ),
                Switch(
                  value: _notificationsEnabled,
                  activeThumbColor: const Color(0xFF01696F),
                  onChanged: _toggleNotifications,
                ),
              ],
            ),
            if (_notificationsEnabled) ...[
              const SizedBox(height: 8),
              const Text(
                "Vérifiées à chaque ouverture/rafraîchissement de l'app (pas en tâche de fond).",
                style: TextStyle(color: Colors.white38, fontSize: 11)),
              const SizedBox(height: 16),
              _ThresholdSlider(
                icon: Icons.water_outlined, label: 'Inondation',
                value: _thresholds['inondation']!,
                onChanged: (v) => _setThreshold('inondation', v)),
              const SizedBox(height: 12),
              _ThresholdSlider(
                icon: Icons.grass_outlined, label: 'Sécheresse',
                value: _thresholds['secheresse']!,
                onChanged: (v) => _setThreshold('secheresse', v)),
              const SizedBox(height: 12),
              _ThresholdSlider(
                icon: Icons.local_fire_department_outlined, label: 'Chaleur',
                value: _thresholds['chaleur']!,
                onChanged: (v) => _setThreshold('chaleur', v)),
            ],

            const SizedBox(height: 32),

            // ══ Section : Serveur ════════════════════════════════════════════
            _SectionHeader(icon: Icons.dns_rounded, label: 'Connexion serveur'),
            const SizedBox(height: 12),

            const Text('URL du serveur SAMCAM',
              style: TextStyle(
                  color: Colors.white70,
                  fontSize: 13,
                  fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            TextField(
              controller: _controller,
              style: const TextStyle(color: Colors.white),
              decoration: InputDecoration(
                hintText: Config.defaultServerUrl,
                hintStyle: const TextStyle(color: Colors.white38),
                filled: true,
                fillColor: const Color(0xFF161B22),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: const BorderSide(color: Colors.white12),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: const BorderSide(color: Colors.white12),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: const BorderSide(
                      color: Color(0xFF01696F), width: 2),
                ),
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Exemple réseau local : http://192.168.1.42:8000',
              style: TextStyle(color: Colors.white38, fontSize: 11),
            ),
            const SizedBox(height: 20),
            Row(
              children: [
                Expanded(
                  child: ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF01696F),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(10)),
                    ),
                    onPressed: _saveUrl,
                    child: const Text('Sauvegarder'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: const Color(0xFF4F98A3),
                      side: const BorderSide(color: Color(0xFF4F98A3)),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(10)),
                    ),
                    onPressed: _testing ? null : _testConnection,
                    child: _testing
                        ? const SizedBox(
                            width: 18, height: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Color(0xFF4F98A3),
                            ))
                        : const Text('Tester'),
                  ),
                ),
              ],
            ),
            if (_testResult != null) ...
            [
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: _testOk
                      ? const Color(0xFF01696F).withOpacity(0.15)
                      : Colors.red.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: _testOk
                        ? const Color(0xFF01696F).withOpacity(0.5)
                        : Colors.red.withOpacity(0.5),
                  ),
                ),
                child: Text(_testResult!,
                  style: TextStyle(
                      color: _testOk ? const Color(0xFF4F98A3) : Colors.redAccent,
                      fontSize: 12)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ── Widgets utilitaires ──────────────────────────────────────────────────────

class _SectionHeader extends StatelessWidget {
  final IconData icon;
  final String   label;
  const _SectionHeader({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: const Color(0xFF4F98A3), size: 18),
        const SizedBox(width: 8),
        Text(label,
          style: const TextStyle(
            color: Color(0xFF4F98A3),
            fontSize: 12,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.2,
          )),
        const SizedBox(width: 8),
        Expanded(child: Divider(
            color: Colors.white.withOpacity(0.08), height: 1)),
      ],
    );
  }
}

class _FavoriteChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _FavoriteChip({required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
          decoration: BoxDecoration(
            color: selected ? const Color(0xFF01696F) : const Color(0xFF161B22),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: selected ? const Color(0xFF01696F) : Colors.white12),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (selected) ...[
                const Icon(Icons.check, color: Colors.white, size: 14),
                const SizedBox(width: 5),
              ],
              Text(label,
                style: TextStyle(
                  color: selected ? Colors.white : Colors.white60,
                  fontSize: 13,
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w400)),
            ],
          ),
        ),
      ),
    );
  }
}

class _ThresholdSlider extends StatelessWidget {
  final IconData icon;
  final String label;
  final double value;
  final ValueChanged<double> onChanged;
  const _ThresholdSlider({
    required this.icon, required this.label,
    required this.value, required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: Colors.white38, size: 16),
        const SizedBox(width: 8),
        SizedBox(width: 84,
          child: Text(label, style: const TextStyle(color: Colors.white70, fontSize: 12))),
        Expanded(
          child: SliderTheme(
            data: SliderTheme.of(context).copyWith(
              activeTrackColor: const Color(0xFF01696F),
              inactiveTrackColor: Colors.white12,
              thumbColor: const Color(0xFF4F98A3),
              overlayColor: const Color(0xFF01696F).withOpacity(0.2),
              trackHeight: 3,
            ),
            child: Slider(
              value: value,
              min: 0.1, max: 0.9, divisions: 16,
              onChanged: onChanged,
            ),
          ),
        ),
        SizedBox(
          width: 40,
          child: Text('${(value * 100).toStringAsFixed(0)}%',
            textAlign: TextAlign.right,
            style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600)),
        ),
      ],
    );
  }
}

class _DemoCard extends StatelessWidget {
  final VoidCallback onTap;
  const _DemoCard({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF1A2A4A), Color(0xFF0D1A30)],
          ),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: const Color(0xFF4F98A3).withOpacity(0.35),
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(
                color: const Color(0xFF01696F).withOpacity(0.20),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                    color: const Color(0xFF4F98A3).withOpacity(0.40)),
              ),
              child: const Center(
                child: Text('🌤️', style: TextStyle(fontSize: 26)),
              ),
            ),
            const SizedBox(width: 14),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Mode Démo météo',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                    )),
                  SizedBox(height: 3),
                  Text(
                    '9 conditions météo • Animations premium • Auto 5 s',
                    style: TextStyle(
                      color: Colors.white54,
                      fontSize: 12,
                    )),
                ],
              ),
            ),
            const Icon(Icons.chevron_right_rounded,
                color: Colors.white38, size: 22),
          ],
        ),
      ),
    );
  }
}
