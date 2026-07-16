// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for French (`fr`).
class AppLocalizationsFr extends AppLocalizations {
  AppLocalizationsFr([String locale = 'fr']) : super(locale);

  @override
  String get settingsTitle => 'Réglages';

  @override
  String get settingsDemoMode => 'Mode Démo';

  @override
  String get settingsDemoModeCardTitle => 'Mode Démo météo';

  @override
  String get settingsDemoModeCardSubtitle =>
      '9 conditions météo • Animations premium • Auto 5 s';

  @override
  String get settingsFavoriteZone => 'Zone par défaut';

  @override
  String get settingsFavoriteZoneHint =>
      'Zone affichée au démarrage de l\'app, à la place du mode GPS automatique.';

  @override
  String get settingsGpsPosition => 'Position GPS';

  @override
  String get settingsAlerts => 'Alertes personnalisées';

  @override
  String get settingsNotificationsEnabled => 'Notifications activées';

  @override
  String get settingsNotificationsHint =>
      'Recevoir une notification quand un risque dépasse votre seuil';

  @override
  String get settingsNotificationsCheckedHint =>
      'Vérifiées à chaque ouverture/rafraîchissement de l\'app (pas en tâche de fond).';

  @override
  String get riskFlood => 'Inondation';

  @override
  String get riskDrought => 'Sécheresse';

  @override
  String get riskHeat => 'Chaleur';

  @override
  String get settingsServer => 'Connexion serveur';

  @override
  String get settingsServerUrlLabel => 'URL du serveur SAMCAM';

  @override
  String get settingsServerUrlExample =>
      'Exemple réseau local : http://192.168.1.42:8000';

  @override
  String get settingsSave => 'Sauvegarder';

  @override
  String get settingsTest => 'Tester';

  @override
  String get settingsUrlSaved => 'URL sauvegardée';

  @override
  String settingsTestSuccess(String version, String lastUpdate) {
    return '✅ Connecté — Version $version | Dernière MAJ : $lastUpdate';
  }

  @override
  String settingsTestFailure(String error) {
    return '❌ Connexion échouée : $error';
  }

  @override
  String get settingsLanguage => 'Langue';

  @override
  String get settingsLanguageFrench => 'Français';

  @override
  String get settingsLanguageEnglish => 'English';

  @override
  String get yaoundePeri => 'Yaoundé (péri.)';

  @override
  String get homeServerUnreachable => 'Serveur SAMCAM inaccessible';

  @override
  String get homeOverviewTooltip => 'Vue d\'ensemble';

  @override
  String get homeRetry => 'Réessayer';

  @override
  String homeOfflineBanner(String suffix) {
    return 'Mode hors-ligne — données$suffix';
  }

  @override
  String homeOfflineSince(String date) {
    return ' du $date';
  }

  @override
  String get homeWindStat => 'Vent';

  @override
  String get homeHumidityStat => 'Humidité';

  @override
  String get homeHourlyForecastTitle => 'PRÉVISIONS PAR HEURE';

  @override
  String get homeDailyForecastTitle => 'PRÉVISIONS 7 JOURS';

  @override
  String get homeToday => 'Aujourd\'hui';

  @override
  String get homeTodayShort => 'Auj.';

  @override
  String get homeWeekdaySun => 'Dim';

  @override
  String get homeWeekdayMon => 'Lun';

  @override
  String get homeWeekdayTue => 'Mar';

  @override
  String get homeWeekdayWed => 'Mer';

  @override
  String get homeWeekdayThu => 'Jeu';

  @override
  String get homeWeekdayFri => 'Ven';

  @override
  String get homeWeekdaySat => 'Sam';

  @override
  String get homeUvIndexLabel => 'INDICE UV';

  @override
  String homeUvProtectionUntil(String time) {
    return 'Protection jusqu\'à $time.';
  }

  @override
  String get homeSunSectionLabel => 'SOLEIL';

  @override
  String get homeSunsetLabel => 'Coucher';

  @override
  String homeSunriseAt(String time) {
    return 'Lever : $time';
  }

  @override
  String get homeWindSectionLabel => 'VENT';

  @override
  String homeGusts(String value) {
    return 'Rafales : $value km/h';
  }

  @override
  String get homeWindAvgSurface => 'Vent moyen en surface.';

  @override
  String get homePrecipitationLabel => 'PRÉCIPITATIONS';

  @override
  String homePrecipTomorrow(String value) {
    return '$value mm demain.';
  }

  @override
  String get homeFeelsLikeLabel => 'RESSENTI';

  @override
  String get homeFeelsHigher => 'Ressenti plus élevé que la réalité.';

  @override
  String get homeFeelsSimilar => 'Similaire à la température réelle.';

  @override
  String get homePressureLabel => 'PRESSION';

  @override
  String get homePressureLow => 'Pression basse.';

  @override
  String get homePressureHigh => 'Pression haute.';

  @override
  String get homePressureNormal => 'Pression normale.';

  @override
  String get homeVisibilityLabel => 'VISIBILITÉ';

  @override
  String get homeVisibilityClear => 'Vue parfaitement dégagée.';

  @override
  String get homeVisibilityReduced => 'Visibilité réduite.';

  @override
  String get homeVisibilityFog => 'Brouillard possible.';

  @override
  String get homeHumidityLabel => 'HUMIDITÉ';

  @override
  String get homeHumidityVeryHigh => 'Humidité très élevée.';

  @override
  String get homeHumidityModerate => 'Humidité modérée.';

  @override
  String get homeHumidityDry => 'Air relativement sec.';

  @override
  String get homeRainReceived7d => 'Pluie reçue (7j)';

  @override
  String get homeRainReceivedTooltip =>
      'Quantité totale de pluie tombée ces 7 derniers jours';

  @override
  String get homeRainExpected7d => 'Pluie prévue (7j)';

  @override
  String get homeRainExpectedTooltip =>
      'Précipitations attendues dans les 7 prochains jours';

  @override
  String get homeClimateRisksTitle => 'RISQUES CLIMATIQUES';

  @override
  String get homeMethodAiRf => 'IA + RF';

  @override
  String get homeMethodRules => 'Règles';

  @override
  String get homeRiskTrendTitle => 'TENDANCE DES RISQUES';

  @override
  String get homeRiskTrendSubtitle =>
      'Comment les risques évoluent-ils dans les prochains jours ?';

  @override
  String get homeReportThanks => 'Merci ! Votre signalement a été enregistré.';

  @override
  String get homeReportButton => 'Signaler un événement observé';

  @override
  String get homeFloodNone => 'Pas de risque d\'inondation en ce moment.';

  @override
  String homeFloodHeavyRain(String value) {
    return 'Beaucoup de pluie : $value mm en 7 jours.';
  }

  @override
  String get homeFloodMonitoring => 'Surveillance active des précipitations.';

  @override
  String get homeDroughtHydrated => 'La végétation est bien hydratée.';

  @override
  String homeDroughtSevere(String state) {
    return 'Végétation $state — le sol manque significativement d\'eau.';
  }

  @override
  String homeDroughtMild(String state) {
    return 'Végétation $state — légère sécheresse détectée.';
  }

  @override
  String get homeHeatNormal => 'Températures normales pour la saison.';

  @override
  String homeHeatWarning(String value) {
    return 'Attention : $value°C relevés, restez à l\'ombre.';
  }

  @override
  String get homeHeatHydrate =>
      'Températures élevées, pensez à bien vous hydrater.';

  @override
  String get homeDataUnavailable => 'Données indisponibles';

  @override
  String get homeRiskLevelNone => 'Nul';

  @override
  String get homeRiskLevelLow => 'Faible';

  @override
  String get homeRiskLevelModerate => 'Modéré';

  @override
  String get homeRiskLevelHigh => 'Élevé';

  @override
  String get homeRiskLevelCritical => 'Critique';

  @override
  String get homeAlertNormal => 'Normal';

  @override
  String get homeAlertVigilance => 'Vigilance';

  @override
  String get homeAlertModerate => 'Modéré';

  @override
  String get homeAlertHigh => 'Élevé';

  @override
  String get homeAlertUnknown => 'Inconnu';

  @override
  String get overviewTitle => 'Vue d\'ensemble';

  @override
  String get overviewGridViewTooltip => 'Vue grille';

  @override
  String get overviewMapViewTooltip => 'Vue carte';

  @override
  String get historyTitle => 'Historique';

  @override
  String get historyEmptyState => 'Aucun historique disponible';

  @override
  String drawerNoLocationFound(String query) {
    return 'Aucun lieu trouvé pour \"$query\"';
  }

  @override
  String get drawerAddLocationTitle => 'Ajouter un endroit';

  @override
  String get drawerCityNameHint => 'Nom de la ville';

  @override
  String get drawerSelectLocationHint => 'Sélectionnez le lieu correspondant :';

  @override
  String get drawerCancel => 'Annuler';

  @override
  String get drawerZonesLabel => 'Zones';

  @override
  String get drawerLocationSectionLabel => 'LOCALISATION';

  @override
  String get drawerZonesSamcamLabel => 'ZONES SAMCAM';

  @override
  String get drawerMyPlacesLabel => 'MES ENDROITS';

  @override
  String get drawerFooterTagline => 'Système d\'Alerte Météo Cameroun';

  @override
  String get signalementTitle => 'Signaler un événement observé';

  @override
  String signalementZoneLabel(String zone) {
    return 'Zone : $zone';
  }

  @override
  String get signalementTypeOther => 'Autre';

  @override
  String get signalementDescriptionHint =>
      'Décrivez ce que vous observez (lieu, ampleur…)';

  @override
  String get signalementSendError =>
      'Envoi impossible — vérifiez votre connexion.';

  @override
  String get signalementSending => 'Envoi…';

  @override
  String get signalementSendButton => 'Envoyer le signalement';

  @override
  String get assistantTitle => 'Assistant SAMCAM';

  @override
  String get assistantError =>
      'L\'assistant est indisponible pour le moment (le modèle local peut mettre du temps à démarrer — réessayez).';

  @override
  String get assistantLoading =>
      'Analyse en cours (peut prendre jusqu\'à une minute)…';

  @override
  String get assistantQuestionHint =>
      'Posez une question (ex. puis-je semer ?)';

  @override
  String demoAutoCountdown(String countdown) {
    return 'Auto  $countdown s';
  }

  @override
  String get demoManualLabel => 'Manuel';

  @override
  String get demoBadgeLabel => 'DÉMO';

  @override
  String get demoAvgDayLabel => 'Moy. jour';

  @override
  String get demoScenarioClearDayLabel => 'Ciel dégagé — Jour';

  @override
  String get demoScenarioClearDayDescription =>
      'Beau temps, ensoleillement maximal';

  @override
  String get demoScenarioClearDayCondition => 'Ensoleillé';

  @override
  String get demoScenarioClearNightLabel => 'Ciel dégagé — Nuit';

  @override
  String get demoScenarioClearNightDescription =>
      'Nuit claire, étoiles visibles';

  @override
  String get demoScenarioClearNightCondition => 'Nuit claire';

  @override
  String get demoScenarioPartlyCloudyLabel => 'Partiellement nuageux';

  @override
  String get demoScenarioPartlyCloudyDescription =>
      'Alternance soleil et nuages';

  @override
  String get demoScenarioPartlyCloudyCondition => 'Peu nuageux';

  @override
  String get demoScenarioCloudyLabel => 'Nuageux';

  @override
  String get demoScenarioCloudyDescription => 'Couverture nuageuse totale';

  @override
  String get demoScenarioCloudyCondition => 'Très nuageux';

  @override
  String get demoScenarioLightRainLabel => 'Pluie légère';

  @override
  String get demoScenarioLightRainDescription => 'Bruine intermittente';

  @override
  String get demoScenarioLightRainCondition => 'Pluie légère';

  @override
  String get demoScenarioHeavyRainLabel => 'Forte pluie';

  @override
  String get demoScenarioHeavyRainDescription => 'Averses intenses';

  @override
  String get demoScenarioHeavyRainCondition => 'Pluie forte';

  @override
  String get demoScenarioStormLabel => 'Orage';

  @override
  String get demoScenarioStormDescription => 'Orages violents, éclairs';

  @override
  String get demoScenarioStormCondition => 'Orage violent';

  @override
  String get demoScenarioFoggyLabel => 'Brouillard';

  @override
  String get demoScenarioFoggyDescription => 'Visibilité réduite';

  @override
  String get demoScenarioFoggyCondition => 'Brouillard dense';

  @override
  String get demoScenarioSnowLabel => 'Neige';

  @override
  String get demoScenarioSnowDescription => 'Chutes de neige modérées';

  @override
  String get demoScenarioSnowCondition => 'Neige modérée';
}
