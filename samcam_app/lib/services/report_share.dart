// SAMCAM — Génération et partage d'un bulletin de risque en texte brut.
//
// Le format texte est volontaire : il passe partout (WhatsApp, SMS,
// e-mail) sans pièce jointe, y compris sur des connexions très lentes —
// contrairement à un PDF ou une image.

import 'package:intl/intl.dart';
import 'package:share_plus/share_plus.dart';
import '../config.dart';
import '../models/risk_report.dart';

class ReportShare {
  /// Construit le bulletin texte à partir d'un rapport de risque.
  static String buildText(RiskReport r) {
    final now = DateTime.now();
    String dateStr;
    try {
      dateStr = DateFormat('EEEE d MMMM yyyy, HH:mm', 'fr_FR').format(now);
    } catch (_) {
      dateStr = DateFormat('yyyy-MM-dd HH:mm').format(now);
    }

    String pct(double v) => '${(v * 100).toStringAsFixed(0)}%';
    String niveauLabel(String n) => Config.alertLabels[n] ?? n;

    final b = StringBuffer();
    b.writeln('BULLETIN DE RISQUE CLIMATIQUE — SAMCAM');
    b.writeln('Zone : ${r.zone}');
    b.writeln('Édité le : $dateStr');
    if (r.fromCache && r.cachedAt != null) {
      b.writeln('(données hors-ligne du '
          '${DateFormat('dd/MM à HH:mm').format(r.cachedAt!)})');
    }
    b.writeln('');
    b.writeln('NIVEAU D\'ALERTE : ${r.niveauAlerte} '
        '(${niveauLabel(r.niveauAlerte)})');
    b.writeln('');
    b.writeln('Risques aujourd\'hui :');
    b.writeln('  • Inondation : ${pct(r.actuel.scores.inondation)}');
    b.writeln('  • Sécheresse : ${pct(r.actuel.scores.secheresse)}');
    b.writeln('  • Chaleur    : ${pct(r.actuel.scores.chaleur)}');
    b.writeln('');
    b.writeln('Prévisions (niveau global) :');
    for (final h in r.horizons) {
      if (h.label == 'Aujourd\'hui') continue;
      b.writeln('  • ${h.label.replaceAll('J+', '')} jours : '
          '${h.periode.niveauGlobal} '
          '(${niveauLabel(h.periode.niveauGlobal)})');
    }
    b.writeln('');
    b.writeln('Indicateurs :');
    b.writeln('  • Pluie reçue (7j)  : '
        '${r.indicateurs.pluie7j.toStringAsFixed(0)} mm');
    b.writeln('  • Pluie prévue (7j) : '
        '${r.indicateurs.pluiePrevue7j.toStringAsFixed(0)} mm');
    if (r.indicateurs.ndviMoyen > 0) {
      b.writeln('  • Végétation        : ${r.indicateurs.etatVegetation}');
    }
    b.writeln('');
    b.writeln('— Bulletin généré par l\'application SAMCAM');
    b.writeln('  (surveillance climatique du Cameroun, données météo '
        'et satellitaires)');
    return b.toString();
  }

  /// Ouvre la feuille de partage native avec le bulletin.
  static Future<void> share(RiskReport r) async {
    await Share.share(
      buildText(r),
      subject: 'Bulletin SAMCAM — ${r.zone} (${r.niveauAlerte})',
    );
  }
}
