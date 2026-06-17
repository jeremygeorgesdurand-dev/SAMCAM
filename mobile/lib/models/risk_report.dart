// SAMCAM — Modèle de données pour /api/risk

class RiskScores {
  final double inondation;
  final double secheresse;
  final double chaleur;

  RiskScores({
    required this.inondation,
    required this.secheresse,
    required this.chaleur,
  });

  factory RiskScores.fromJson(Map<String, dynamic> json) {
    return RiskScores(
      inondation: (json['inondation'] ?? 0.0).toDouble(),
      secheresse: (json['secheresse'] ?? 0.0).toDouble(),
      chaleur:    (json['chaleur']    ?? 0.0).toDouble(),
    );
  }

  factory RiskScores.empty() =>
      RiskScores(inondation: 0, secheresse: 0, chaleur: 0);
}


class RiskPeriod {
  final String niveauGlobal;
  final RiskScores scores;

  RiskPeriod({required this.niveauGlobal, required this.scores});

  factory RiskPeriod.fromJson(Map<String, dynamic> json) {
    return RiskPeriod(
      niveauGlobal: json['niveau_global'] ?? 'INCONNU',
      scores: RiskScores.fromJson(
        (json['scores'] as Map<String, dynamic>?) ?? {},
      ),
    );
  }

  factory RiskPeriod.empty() =>
      RiskPeriod(niveauGlobal: 'INCONNU', scores: RiskScores.empty());
}


class Indicateurs {
  final double pluie7j;
  final double pluiePrevue7j;
  final double ndviMoyen;
  final double temperatureMax;

  Indicateurs({
    required this.pluie7j,
    required this.pluiePrevue7j,
    required this.ndviMoyen,
    required this.temperatureMax,
  });

  factory Indicateurs.fromJson(Map<String, dynamic> json) {
    return Indicateurs(
      pluie7j:        (json['pluie_cumulee_7j_mm']  ?? 0.0).toDouble(),
      pluiePrevue7j:  (json['pluie_prevue_7j_mm']   ?? 0.0).toDouble(),
      ndviMoyen:      (json['ndvi_moyen']            ?? 0.0).toDouble(),
      temperatureMax: (json['temperature_max_c']     ?? 0.0).toDouble(),
    );
  }

  factory Indicateurs.empty() => Indicateurs(
    pluie7j: 0, pluiePrevue7j: 0, ndviMoyen: 0, temperatureMax: 0,
  );

  /// Traduit le NDVI en état lisible pour le grand public.
  /// NDVI > 0.5  : végétation saine
  /// NDVI 0.3-0.5: stress hydrique modéré
  /// NDVI < 0.3  : végétation en état critique
  String get etatVegetation {
    if (ndviMoyen <= 0.0) return 'Indisponible';
    if (ndviMoyen >= 0.50) return 'Bonne';
    if (ndviMoyen >= 0.30) return 'Stressée';
    return 'Critique';
  }

  String get etatVegetationEmoji {
    if (ndviMoyen <= 0.0) return '❓';
    if (ndviMoyen >= 0.50) return '🌿';
    if (ndviMoyen >= 0.30) return '🍂';
    return '🏜️';
  }
}


class RiskReport {
  final String date;
  final String zone;
  final String niveauAlerte;
  final String methodeRisque;
  final RiskPeriod actuel;
  final RiskPeriod prevu3j;
  final RiskPeriod prevu7j;
  final Indicateurs indicateurs;

  RiskReport({
    required this.date,
    required this.zone,
    required this.niveauAlerte,
    required this.methodeRisque,
    required this.actuel,
    required this.prevu3j,
    required this.prevu7j,
    required this.indicateurs,
  });

  factory RiskReport.fromJson(Map<String, dynamic> json) {
    return RiskReport(
      date:          json['date']           ?? '',
      zone:          json['zone']           ?? 'Kribi',
      niveauAlerte:  json['niveau_alerte']  ?? 'INCONNU',
      methodeRisque: json['methode_risque'] ?? 'regles_physiques',
      actuel:  RiskPeriod.fromJson(
          (json['risque_actuel']   as Map<String, dynamic>?) ?? {}),
      prevu3j: RiskPeriod.fromJson(
          (json['risque_prevu_3j'] as Map<String, dynamic>?) ?? {}),
      prevu7j: RiskPeriod.fromJson(
          (json['risque_prevu_7j'] as Map<String, dynamic>?) ?? {}),
      indicateurs: Indicateurs.fromJson(
          (json['indicateurs'] as Map<String, dynamic>?) ?? {}),
    );
  }
}
