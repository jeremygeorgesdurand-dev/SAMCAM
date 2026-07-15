// SAMCAM — Carte "Assistant SAMCAM" : commentaire en langage naturel du
// bulletin de risque, généré par un LLM local (Ollama) mais ancré sur les
// scores RÉELS déjà calculés par les modèles ML (le LLM reformule, il ne
// calcule jamais de risque lui-même).

import 'package:flutter/material.dart';
import '../services/api_service.dart';

class AssistantCard extends StatefulWidget {
  final String zone;
  const AssistantCard({super.key, required this.zone});

  @override
  State<AssistantCard> createState() => _AssistantCardState();
}

class _AssistantCardState extends State<AssistantCard> {
  final _questionCtrl = TextEditingController();
  String? _reponse;
  String? _error;
  bool _loading = false;
  bool _ouvert = false;

  @override
  void didUpdateWidget(covariant AssistantCard old) {
    super.didUpdateWidget(old);
    // Nouvelle zone sélectionnée → la réponse précédente n'a plus de sens
    if (old.zone != widget.zone) {
      setState(() { _reponse = null; _error = null; });
    }
  }

  @override
  void dispose() {
    _questionCtrl.dispose();
    super.dispose();
  }

  Future<void> _demander({String? question}) async {
    setState(() { _loading = true; _error = null; });
    try {
      final reponse = await ApiService.askAssistant(
        zone: widget.zone, question: question);
      if (!mounted) return;
      setState(() { _reponse = reponse; _loading = false; });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = "L'assistant est indisponible pour le moment "
            "(le modèle local peut mettre du temps à démarrer — réessayez).";
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFB39DDB).withOpacity(0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            borderRadius: BorderRadius.circular(16),
            onTap: () {
              setState(() => _ouvert = !_ouvert);
              if (_ouvert && _reponse == null && !_loading) _demander();
            },
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
              child: Row(
                children: [
                  const Icon(Icons.auto_awesome_outlined,
                    color: Color(0xFFB39DDB), size: 18),
                  const SizedBox(width: 10),
                  const Expanded(
                    child: Text('Assistant SAMCAM',
                      style: TextStyle(
                        color: Colors.white, fontSize: 14, fontWeight: FontWeight.w700)),
                  ),
                  Icon(_ouvert ? Icons.expand_less : Icons.expand_more,
                    color: Colors.white38, size: 20),
                ],
              ),
            ),
          ),
          if (_ouvert)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (_loading)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 8),
                      child: Row(
                        children: [
                          SizedBox(
                            width: 14, height: 14,
                            child: CircularProgressIndicator(
                              strokeWidth: 2, color: Color(0xFFB39DDB))),
                          SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              "Analyse en cours (peut prendre jusqu'à une minute)…",
                              style: TextStyle(color: Colors.white54, fontSize: 12)),
                          ),
                        ],
                      ),
                    )
                  else if (_error != null)
                    Text(_error!,
                      style: const TextStyle(color: Color(0xFFEF5350), fontSize: 12))
                  else if (_reponse != null)
                    Text(_reponse!,
                      style: const TextStyle(
                        color: Colors.white70, fontSize: 13, height: 1.5)),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _questionCtrl,
                          enabled: !_loading,
                          style: const TextStyle(color: Colors.white, fontSize: 13),
                          decoration: InputDecoration(
                            hintText: 'Posez une question (ex. puis-je semer ?)',
                            hintStyle: const TextStyle(color: Colors.white38, fontSize: 12),
                            isDense: true,
                            filled: true,
                            fillColor: const Color(0xFF21262D),
                            contentPadding: const EdgeInsets.symmetric(
                              horizontal: 12, vertical: 10),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(10),
                              borderSide: BorderSide.none),
                          ),
                          onSubmitted: (q) {
                            if (q.trim().isNotEmpty && !_loading) {
                              _demander(question: q);
                              _questionCtrl.clear();
                            }
                          },
                        ),
                      ),
                      const SizedBox(width: 8),
                      InkWell(
                        borderRadius: BorderRadius.circular(10),
                        onTap: _loading ? null : () {
                          final q = _questionCtrl.text.trim();
                          if (q.isNotEmpty) {
                            _demander(question: q);
                            _questionCtrl.clear();
                          }
                        },
                        child: Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: const Color(0xFFB39DDB).withOpacity(_loading ? 0.1 : 0.18),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Icon(Icons.send_outlined,
                            size: 16,
                            color: _loading ? Colors.white24 : const Color(0xFFB39DDB)),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
