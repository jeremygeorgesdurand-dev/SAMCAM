import 'package:flutter/material.dart';
import '../config.dart';
import '../services/api_service.dart';
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

  @override
  void initState() {
    super.initState();
    _loadUrl();
  }

  Future<void> _loadUrl() async {
    final url = await ApiService.getServerUrl();
    _controller.text = url;
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
