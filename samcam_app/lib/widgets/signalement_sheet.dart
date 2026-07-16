// SAMCAM — Feuille de signalement communautaire.
//
// Permet à un utilisateur de signaler un événement climatique observé sur
// le terrain (inondation, sécheresse, chaleur). Ces observations servent
// de vérité terrain pour recalibrer les modèles côté serveur.

import 'package:flutter/material.dart';
import '../l10n/app_localizations.dart';
import '../services/api_service.dart';

/// Ouvre la feuille de signalement pour [zone] (nom de zone SAMCAM, sans
/// suffixe de distance). Retourne true si un signalement a été envoyé.
Future<bool?> showSignalementSheet(BuildContext context, String zone) {
  return showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    backgroundColor: const Color(0xFF161B22),
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => _SignalementSheet(zone: zone),
  );
}

class _SignalementSheet extends StatefulWidget {
  final String zone;
  const _SignalementSheet({required this.zone});

  @override
  State<_SignalementSheet> createState() => _SignalementSheetState();
}

class _SignalementSheetState extends State<_SignalementSheet> {
  static const _typeKeys = [
    ('inondation', Icons.water_outlined),
    ('secheresse', Icons.grass_outlined),
    ('chaleur',    Icons.local_fire_department_outlined),
    ('autre',      Icons.report_problem_outlined),
  ];

  String _typeLabel(AppLocalizations t, String key) {
    switch (key) {
      case 'inondation': return t.riskFlood;
      case 'secheresse': return t.riskDrought;
      case 'chaleur':    return t.riskHeat;
      default:           return t.signalementTypeOther;
    }
  }

  String _type = 'inondation';
  final _descCtrl = TextEditingController();
  bool _sending = false;
  String? _error;
  late AppLocalizations t;

  @override
  void dispose() {
    _descCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() { _sending = true; _error = null; });
    try {
      // Position GPS jointe si disponible (aide à localiser l'événement
      // dans la zone) — non bloquant si refusée.
      double? lat, lon;
      try {
        final pos = await ApiService.getPosition();
        lat = pos.lat;
        lon = pos.lon;
      } catch (_) {}

      await ApiService.submitSignalement(
        zone:          widget.zone,
        typeEvenement: _type,
        description:   _descCtrl.text.trim(),
        lat: lat,
        lon: lon,
      );
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      setState(() {
        _sending = false;
        _error = t.signalementSendError;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    t = AppLocalizations.of(context)!;
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 16, 20, 20 + bottomInset),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 36, height: 4,
              decoration: BoxDecoration(
                color: Colors.white24,
                borderRadius: BorderRadius.circular(2)),
            ),
          ),
          const SizedBox(height: 16),
          Text(t.signalementTitle,
            style: const TextStyle(
              color: Colors.white, fontSize: 17, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text(t.signalementZoneLabel(widget.zone),
            style: const TextStyle(color: Colors.white54, fontSize: 13)),
          const SizedBox(height: 16),

          // Type d'événement
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final (key, icon) in _typeKeys)
                ChoiceChip(
                  selected: _type == key,
                  onSelected: (_) => setState(() => _type = key),
                  avatar: Icon(icon, size: 16,
                    color: _type == key ? Colors.white : Colors.white54),
                  label: Text(_typeLabel(t, key)),
                  labelStyle: TextStyle(
                    color: _type == key ? Colors.white : Colors.white70,
                    fontSize: 13),
                  selectedColor: const Color(0xFF01696F),
                  backgroundColor: const Color(0xFF21262D),
                  side: BorderSide(
                    color: _type == key ? const Color(0xFF01696F) : Colors.white12),
                ),
            ],
          ),
          const SizedBox(height: 14),

          // Description libre
          TextField(
            controller: _descCtrl,
            maxLines: 3,
            maxLength: 500,
            style: const TextStyle(color: Colors.white, fontSize: 14),
            decoration: InputDecoration(
              hintText: t.signalementDescriptionHint,
              hintStyle: const TextStyle(color: Colors.white38, fontSize: 13),
              counterStyle: const TextStyle(color: Colors.white38, fontSize: 11),
              filled: true,
              fillColor: const Color(0xFF21262D),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide.none),
            ),
          ),

          if (_error != null) ...[
            const SizedBox(height: 4),
            Text(_error!,
              style: const TextStyle(color: Color(0xFFEF5350), fontSize: 12)),
          ],
          const SizedBox(height: 12),

          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: _sending ? null : _submit,
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF01696F),
                padding: const EdgeInsets.symmetric(vertical: 14)),
              icon: _sending
                  ? const SizedBox(
                      width: 16, height: 16,
                      child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white))
                  : const Icon(Icons.send_outlined, size: 17),
              label: Text(_sending ? t.signalementSending : t.signalementSendButton),
            ),
          ),
        ],
      ),
    );
  }
}
