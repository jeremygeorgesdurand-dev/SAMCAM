// SAMCAM — Modèle de données enrichi (météo + risque)

class RiskScores {
  final double inondation;
  final double secheresse;
  final double chaleur;

  RiskScores({
    required this.inondation,
    required this.secheresse,
    required this.chaleur,
  });

  factory RiskScores.fromJson(Map<String, dynamic> json) => RiskScores(
    inondation: (json['inondation'] ?? 0.0).toDouble(),
    secheresse: (json['secheresse'] ?? 0.0).toDouble(),
    chaleur:    (json['chaleur']    ?? 0.0).toDouble(),
  );

  factory RiskScores.empty() =>
      RiskScores(inondation: 0, secheresse: 0, chaleur: 0);
}

class RiskPeriod {
  final String niveauGlobal;
  final RiskScores scores;

  RiskPeriod({required this.niveauGlobal, required this.scores});

  factory RiskPeriod.fromJson(Map<String, dynamic> json) => RiskPeriod(
    niveauGlobal: json['niveau_global'] ?? 'INCONNU',
    scores: RiskScores.fromJson(
        (json['scores'] as Map<String, dynamic>?) ?? {}),
  );

  factory RiskPeriod.empty() =>
      RiskPeriod(niveauGlobal: 'INCONNU', scores: RiskScores.empty());
}

// ── Données météo horaires ───────────────────────────────────────

class MeteoHeure {
  final String heure;        // "08:00"
  final double temperature;  // °C
  final double pluie;        // mm
  final double humidite;     // %
  final int    codeMeteo;    // WMO code

  MeteoHeure({
    required this.heure,
    required this.temperature,
    required this.pluie,
    required this.humidite,
    required this.codeMeteo,
  });

  factory MeteoHeure.fromJson(Map<String, dynamic> json) => MeteoHeure(
    heure:       json['heure']       ?? '00:00',
    temperature: (json['temperature'] ?? 0.0).toDouble(),
    pluie:       (json['pluie']       ?? 0.0).toDouble(),
    humidite:    (json['humidite']    ?? 0.0).toDouble(),
    codeMeteo:   (json['code_meteo']  ?? 0) as int,
  );

  /// Emoji selon code WMO
  String get emoji {
    if (codeMeteo == 0)                     return '☀️';
    if (codeMeteo <= 2)                     return '🌤️';
    if (codeMeteo == 3)                     return '☁️';
    if (codeMeteo >= 45 && codeMeteo <= 48) return '🌫️';
    if (codeMeteo >= 51 && codeMeteo <= 67) return '🌧️';
    if (codeMeteo >= 71 && codeMeteo <= 77) return '❄️';
    if (codeMeteo >= 80 && codeMeteo <= 82) return '🌦️';
    if (codeMeteo >= 95)                    return '⚡';
    return '🌤️';
  }

  String get condition {
    if (codeMeteo == 0)                     return 'Ensoleillé';
    if (codeMeteo <= 2)                     return 'Peu nuageux';
    if (codeMeteo == 3)                     return 'Couvert';
    if (codeMeteo >= 45 && codeMeteo <= 48) return 'Brouillard';
    if (codeMeteo >= 51 && codeMeteo <= 67) return 'Pluie';
    if (codeMeteo >= 71 && codeMeteo <= 77) return 'Neige';
    if (codeMeteo >= 80 && codeMeteo <= 82) return 'Averses';
    if (codeMeteo >= 95)                    return 'Orage';
    return 'Nuageux';
  }
}

// ── Prévision journalière ───────────────────────────────────────────────

class MeteoJour {
  final String jour;         // "Lun", "Mar"...
  final double tempMin;
  final double tempMax;
  final double pluie;
  final int    codeMeteo;

  MeteoJour({
    required this.jour,
    required this.tempMin,
    required this.tempMax,
    required this.pluie,
    required this.codeMeteo,
  });

  factory MeteoJour.fromJson(Map<String, dynamic> json) => MeteoJour(
    jour:      json['jour']       ?? '--',
    tempMin:   (json['temp_min']  ?? 0.0).toDouble(),
    tempMax:   (json['temp_max']  ?? 0.0).toDouble(),
    pluie:     (json['pluie']     ?? 0.0).toDouble(),
    codeMeteo: (json['code_meteo'] ?? 0) as int,
  );

  String get emoji {
    if (codeMeteo == 0)  return '☀️';
    if (codeMeteo <= 2)  return '🌤️';
    if (codeMeteo == 3)  return '☁️';
    if (codeMeteo >= 51 && codeMeteo <= 67) return '🌧️';
    if (codeMeteo >= 80 && codeMeteo <= 82) return '🌦️';
    if (codeMeteo >= 95) return '⚡';
    return '🌤️';
  }
}

// ── Météo courante ────────────────────────────────────────────────────

class MeteoCourante {
  final double temperature;
  final double tempMin;
  final double tempMax;
  final double humidite;
  final double vent;         // km/h
  final double pluie24h;
  final int    codeMeteo;
  final List<MeteoHeure> heures;
  final List<MeteoJour>  jours;

  MeteoCourante({
    required this.temperature,
    required this.tempMin,
    required this.tempMax,
    required this.humidite,
    required this.vent,
    required this.pluie24h,
    required this.codeMeteo,
    required this.heures,
    required this.jours,
  });

  factory MeteoCourante.fromJson(Map<String, dynamic> json) => MeteoCourante(
    temperature: (json['temperature']   ?? 0.0).toDouble(),
    tempMin:     (json['temp_min']       ?? 0.0).toDouble(),
    tempMax:     (json['temp_max']       ?? 0.0).toDouble(),
    humidite:    (json['humidite']       ?? 0.0).toDouble(),
    vent:        (json['vent_kmh']       ?? 0.0).toDouble(),
    pluie24h:    (json['pluie_24h_mm']   ?? 0.0).toDouble(),
    codeMeteo:   (json['code_meteo']     ?? 0) as int,
    heures: ((json['heures'] as List?) ?? [])
        .map((h) => MeteoHeure.fromJson(h as Map<String, dynamic>))
        .toList(),
    jours: ((json['jours'] as List?) ?? [])
        .map((j) => MeteoJour.fromJson(j as Map<String, dynamic>))
        .toList(),
  );

  factory MeteoCourante.empty() => MeteoCourante(
    temperature: 0, tempMin: 0, tempMax: 0,
    humidite: 0, vent: 0, pluie24h: 0, codeMeteo: 0,
    heures: [], jours: [],
  );

  String get emoji {
    if (codeMeteo == 0)  return '☀️';
    if (codeMeteo <= 2)  return '🌤️';
    if (codeMeteo == 3)  return '☁️';
    if (codeMeteo >= 51 && codeMeteo <= 67) return '🌧️';
    if (codeMeteo >= 80 && codeMeteo <= 82) return '🌦️';
    if (codeMeteo >= 95) return '⚡';
    return '🌤️';
  }

  String get condition {
    if (codeMeteo == 0)  return 'Ensoleillé';
    if (codeMeteo <= 2)  return 'Peu nuageux';
    if (codeMeteo == 3)  return 'Couvert';
    if (codeMeteo >= 51 && codeMeteo <= 67) return 'Pluie';
    if (codeMeteo >= 80 && codeMeteo <= 82) return 'Averses';
    if (codeMeteo >= 95) return 'Orage';
    return 'Nuageux';
  }
}

// ── Indicateurs climatiques ───────────────────────────────────────────

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

  factory Indicateurs.fromJson(Map<String, dynamic> json) => Indicateurs(
    pluie7j:        (json['pluie_cumulee_7j_mm']  ?? 0.0).toDouble(),
    pluiePrevue7j:  (json['pluie_prevue_7j_mm']   ?? 0.0).toDouble(),
    ndviMoyen:      (json['ndvi_moyen']            ?? 0.0).toDouble(),
    temperatureMax: (json['temperature_max_c']     ?? 0.0).toDouble(),
  );

  factory Indicateurs.empty() => Indicateurs(
    pluie7j: 0, pluiePrevue7j: 0, ndviMoyen: 0, temperatureMax: 0,
  );

  /// Traduit le NDVI en état lisible pour le grand public.
  /// NDVI > 0.5 : végétation saine
  /// NDVI 0.3–0.5 : stress hydrique modéré
  /// NDVI < 0.3 : végétation en état critique
  String get etatVegetation {
    if (ndviMoyen <= 0.0) return 'Données indisponibles';
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

// ── Rapport complet ──────────────────────────────────────────────────────────

class RiskReport {
  final String date;
  final String zone;
  final String niveauAlerte;
  final String methodeRisque;
  final RiskPeriod  actuel;
  final RiskPeriod  prevu3j;
  final RiskPeriod  prevu7j;
  final RiskPeriod  prevu10j;
  final RiskPeriod  prevu14j;
  final Indicateurs indicateurs;
  final MeteoCourante meteo;

  /// true si ce rapport provient du cache hors-ligne (échec réseau),
  /// auquel cas [cachedAt] donne la date de la dernière mise à jour réussie.
  final bool fromCache;
  final DateTime? cachedAt;

  RiskReport({
    required this.date,
    required this.zone,
    required this.niveauAlerte,
    required this.methodeRisque,
    required this.actuel,
    required this.prevu3j,
    required this.prevu7j,
    required this.prevu10j,
    required this.prevu14j,
    required this.indicateurs,
    required this.meteo,
    this.fromCache = false,
    this.cachedAt,
  });

  /// Horizons de prévision disponibles, dans l'ordre chronologique.
  /// Les entrées "vides" (backend legacy sans J+10/J+14) sont filtrées.
  List<({String label, RiskPeriod periode})> get horizons => [
        (label: 'Aujourd\'hui', periode: actuel),
        (label: 'J+3',  periode: prevu3j),
        (label: 'J+7',  periode: prevu7j),
        (label: 'J+10', periode: prevu10j),
        (label: 'J+14', periode: prevu14j),
      ].where((h) => h.periode.niveauGlobal != 'INCONNU' || h.label == 'Aujourd\'hui').toList();

  factory RiskReport.fromJson(Map<String, dynamic> json) => RiskReport(
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
    prevu10j: RiskPeriod.fromJson(
        (json['risque_prevu_10j'] as Map<String, dynamic>?) ?? {}),
    prevu14j: RiskPeriod.fromJson(
        (json['risque_prevu_14j'] as Map<String, dynamic>?) ?? {}),
    indicateurs: Indicateurs.fromJson(
        (json['indicateurs'] as Map<String, dynamic>?) ?? {}),
    meteo: json['meteo'] != null
        ? MeteoCourante.fromJson(json['meteo'] as Map<String, dynamic>)
        : MeteoCourante.empty(),
  );
}
