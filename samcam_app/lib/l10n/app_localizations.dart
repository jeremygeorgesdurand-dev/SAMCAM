import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_fr.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
      : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations? of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations);
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('fr')
  ];

  /// No description provided for @settingsTitle.
  ///
  /// In fr, this message translates to:
  /// **'Réglages'**
  String get settingsTitle;

  /// No description provided for @settingsDemoMode.
  ///
  /// In fr, this message translates to:
  /// **'Mode Démo'**
  String get settingsDemoMode;

  /// No description provided for @settingsDemoModeCardTitle.
  ///
  /// In fr, this message translates to:
  /// **'Mode Démo météo'**
  String get settingsDemoModeCardTitle;

  /// No description provided for @settingsDemoModeCardSubtitle.
  ///
  /// In fr, this message translates to:
  /// **'9 conditions météo • Animations premium • Auto 5 s'**
  String get settingsDemoModeCardSubtitle;

  /// No description provided for @settingsFavoriteZone.
  ///
  /// In fr, this message translates to:
  /// **'Zone par défaut'**
  String get settingsFavoriteZone;

  /// No description provided for @settingsFavoriteZoneHint.
  ///
  /// In fr, this message translates to:
  /// **'Zone affichée au démarrage de l\'app, à la place du mode GPS automatique.'**
  String get settingsFavoriteZoneHint;

  /// No description provided for @settingsGpsPosition.
  ///
  /// In fr, this message translates to:
  /// **'Position GPS'**
  String get settingsGpsPosition;

  /// No description provided for @settingsAlerts.
  ///
  /// In fr, this message translates to:
  /// **'Alertes personnalisées'**
  String get settingsAlerts;

  /// No description provided for @settingsNotificationsEnabled.
  ///
  /// In fr, this message translates to:
  /// **'Notifications activées'**
  String get settingsNotificationsEnabled;

  /// No description provided for @settingsNotificationsHint.
  ///
  /// In fr, this message translates to:
  /// **'Recevoir une notification quand un risque dépasse votre seuil'**
  String get settingsNotificationsHint;

  /// No description provided for @settingsNotificationsCheckedHint.
  ///
  /// In fr, this message translates to:
  /// **'Vérifiées à chaque ouverture/rafraîchissement de l\'app (pas en tâche de fond).'**
  String get settingsNotificationsCheckedHint;

  /// No description provided for @riskFlood.
  ///
  /// In fr, this message translates to:
  /// **'Inondation'**
  String get riskFlood;

  /// No description provided for @riskDrought.
  ///
  /// In fr, this message translates to:
  /// **'Sécheresse'**
  String get riskDrought;

  /// No description provided for @riskHeat.
  ///
  /// In fr, this message translates to:
  /// **'Chaleur'**
  String get riskHeat;

  /// No description provided for @settingsServer.
  ///
  /// In fr, this message translates to:
  /// **'Connexion serveur'**
  String get settingsServer;

  /// No description provided for @settingsServerUrlLabel.
  ///
  /// In fr, this message translates to:
  /// **'URL du serveur SAMCAM'**
  String get settingsServerUrlLabel;

  /// No description provided for @settingsServerUrlExample.
  ///
  /// In fr, this message translates to:
  /// **'Exemple réseau local : http://192.168.1.42:8000'**
  String get settingsServerUrlExample;

  /// No description provided for @settingsSave.
  ///
  /// In fr, this message translates to:
  /// **'Sauvegarder'**
  String get settingsSave;

  /// No description provided for @settingsTest.
  ///
  /// In fr, this message translates to:
  /// **'Tester'**
  String get settingsTest;

  /// No description provided for @settingsUrlSaved.
  ///
  /// In fr, this message translates to:
  /// **'URL sauvegardée'**
  String get settingsUrlSaved;

  /// No description provided for @settingsUrlSavedInsecure.
  ///
  /// In fr, this message translates to:
  /// **'URL sauvegardée — ⚠️ connexion non chiffrée (http)'**
  String get settingsUrlSavedInsecure;

  /// No description provided for @settingsUrlInvalid.
  ///
  /// In fr, this message translates to:
  /// **'URL invalide — doit commencer par http:// ou https://'**
  String get settingsUrlInvalid;

  /// No description provided for @settingsTestSuccess.
  ///
  /// In fr, this message translates to:
  /// **'✅ Connecté — Version {version} | Dernière MAJ : {lastUpdate}'**
  String settingsTestSuccess(String version, String lastUpdate);

  /// No description provided for @settingsTestFailure.
  ///
  /// In fr, this message translates to:
  /// **'❌ Connexion échouée : {error}'**
  String settingsTestFailure(String error);

  /// No description provided for @settingsLanguage.
  ///
  /// In fr, this message translates to:
  /// **'Langue'**
  String get settingsLanguage;

  /// No description provided for @settingsLanguageFrench.
  ///
  /// In fr, this message translates to:
  /// **'Français'**
  String get settingsLanguageFrench;

  /// No description provided for @settingsLanguageEnglish.
  ///
  /// In fr, this message translates to:
  /// **'English'**
  String get settingsLanguageEnglish;

  /// No description provided for @yaoundePeri.
  ///
  /// In fr, this message translates to:
  /// **'Yaoundé (péri.)'**
  String get yaoundePeri;

  /// No description provided for @homeServerUnreachable.
  ///
  /// In fr, this message translates to:
  /// **'Serveur SAMCAM inaccessible'**
  String get homeServerUnreachable;

  /// No description provided for @homeOverviewTooltip.
  ///
  /// In fr, this message translates to:
  /// **'Vue d\'ensemble'**
  String get homeOverviewTooltip;

  /// No description provided for @homeRetry.
  ///
  /// In fr, this message translates to:
  /// **'Réessayer'**
  String get homeRetry;

  /// No description provided for @homeOfflineBanner.
  ///
  /// In fr, this message translates to:
  /// **'Mode hors-ligne — données{suffix}'**
  String homeOfflineBanner(String suffix);

  /// No description provided for @homeOfflineSince.
  ///
  /// In fr, this message translates to:
  /// **' du {date}'**
  String homeOfflineSince(String date);

  /// No description provided for @homeWindStat.
  ///
  /// In fr, this message translates to:
  /// **'Vent'**
  String get homeWindStat;

  /// No description provided for @homeHumidityStat.
  ///
  /// In fr, this message translates to:
  /// **'Humidité'**
  String get homeHumidityStat;

  /// No description provided for @homeHourlyForecastTitle.
  ///
  /// In fr, this message translates to:
  /// **'PRÉVISIONS PAR HEURE'**
  String get homeHourlyForecastTitle;

  /// No description provided for @homeDailyForecastTitle.
  ///
  /// In fr, this message translates to:
  /// **'PRÉVISIONS 7 JOURS'**
  String get homeDailyForecastTitle;

  /// No description provided for @homeToday.
  ///
  /// In fr, this message translates to:
  /// **'Aujourd\'hui'**
  String get homeToday;

  /// No description provided for @homeTodayShort.
  ///
  /// In fr, this message translates to:
  /// **'Auj.'**
  String get homeTodayShort;

  /// No description provided for @homeWeekdaySun.
  ///
  /// In fr, this message translates to:
  /// **'Dim'**
  String get homeWeekdaySun;

  /// No description provided for @homeWeekdayMon.
  ///
  /// In fr, this message translates to:
  /// **'Lun'**
  String get homeWeekdayMon;

  /// No description provided for @homeWeekdayTue.
  ///
  /// In fr, this message translates to:
  /// **'Mar'**
  String get homeWeekdayTue;

  /// No description provided for @homeWeekdayWed.
  ///
  /// In fr, this message translates to:
  /// **'Mer'**
  String get homeWeekdayWed;

  /// No description provided for @homeWeekdayThu.
  ///
  /// In fr, this message translates to:
  /// **'Jeu'**
  String get homeWeekdayThu;

  /// No description provided for @homeWeekdayFri.
  ///
  /// In fr, this message translates to:
  /// **'Ven'**
  String get homeWeekdayFri;

  /// No description provided for @homeWeekdaySat.
  ///
  /// In fr, this message translates to:
  /// **'Sam'**
  String get homeWeekdaySat;

  /// No description provided for @homeUvIndexLabel.
  ///
  /// In fr, this message translates to:
  /// **'INDICE UV'**
  String get homeUvIndexLabel;

  /// No description provided for @homeUvProtectionUntil.
  ///
  /// In fr, this message translates to:
  /// **'Protection jusqu\'à {time}.'**
  String homeUvProtectionUntil(String time);

  /// No description provided for @homeSunSectionLabel.
  ///
  /// In fr, this message translates to:
  /// **'SOLEIL'**
  String get homeSunSectionLabel;

  /// No description provided for @homeSunsetLabel.
  ///
  /// In fr, this message translates to:
  /// **'Coucher'**
  String get homeSunsetLabel;

  /// No description provided for @homeSunriseAt.
  ///
  /// In fr, this message translates to:
  /// **'Lever : {time}'**
  String homeSunriseAt(String time);

  /// No description provided for @homeWindSectionLabel.
  ///
  /// In fr, this message translates to:
  /// **'VENT'**
  String get homeWindSectionLabel;

  /// No description provided for @homeGusts.
  ///
  /// In fr, this message translates to:
  /// **'Rafales : {value} km/h'**
  String homeGusts(String value);

  /// No description provided for @homeWindAvgSurface.
  ///
  /// In fr, this message translates to:
  /// **'Vent moyen en surface.'**
  String get homeWindAvgSurface;

  /// No description provided for @homePrecipitationLabel.
  ///
  /// In fr, this message translates to:
  /// **'PRÉCIPITATIONS'**
  String get homePrecipitationLabel;

  /// No description provided for @homePrecipTomorrow.
  ///
  /// In fr, this message translates to:
  /// **'{value} mm demain.'**
  String homePrecipTomorrow(String value);

  /// No description provided for @homeFeelsLikeLabel.
  ///
  /// In fr, this message translates to:
  /// **'RESSENTI'**
  String get homeFeelsLikeLabel;

  /// No description provided for @homeFeelsHigher.
  ///
  /// In fr, this message translates to:
  /// **'Ressenti plus élevé que la réalité.'**
  String get homeFeelsHigher;

  /// No description provided for @homeFeelsSimilar.
  ///
  /// In fr, this message translates to:
  /// **'Similaire à la température réelle.'**
  String get homeFeelsSimilar;

  /// No description provided for @homePressureLabel.
  ///
  /// In fr, this message translates to:
  /// **'PRESSION'**
  String get homePressureLabel;

  /// No description provided for @homePressureLow.
  ///
  /// In fr, this message translates to:
  /// **'Pression basse.'**
  String get homePressureLow;

  /// No description provided for @homePressureHigh.
  ///
  /// In fr, this message translates to:
  /// **'Pression haute.'**
  String get homePressureHigh;

  /// No description provided for @homePressureNormal.
  ///
  /// In fr, this message translates to:
  /// **'Pression normale.'**
  String get homePressureNormal;

  /// No description provided for @homeVisibilityLabel.
  ///
  /// In fr, this message translates to:
  /// **'VISIBILITÉ'**
  String get homeVisibilityLabel;

  /// No description provided for @homeVisibilityClear.
  ///
  /// In fr, this message translates to:
  /// **'Vue parfaitement dégagée.'**
  String get homeVisibilityClear;

  /// No description provided for @homeVisibilityReduced.
  ///
  /// In fr, this message translates to:
  /// **'Visibilité réduite.'**
  String get homeVisibilityReduced;

  /// No description provided for @homeVisibilityFog.
  ///
  /// In fr, this message translates to:
  /// **'Brouillard possible.'**
  String get homeVisibilityFog;

  /// No description provided for @homeHumidityLabel.
  ///
  /// In fr, this message translates to:
  /// **'HUMIDITÉ'**
  String get homeHumidityLabel;

  /// No description provided for @homeHumidityVeryHigh.
  ///
  /// In fr, this message translates to:
  /// **'Humidité très élevée.'**
  String get homeHumidityVeryHigh;

  /// No description provided for @homeHumidityModerate.
  ///
  /// In fr, this message translates to:
  /// **'Humidité modérée.'**
  String get homeHumidityModerate;

  /// No description provided for @homeHumidityDry.
  ///
  /// In fr, this message translates to:
  /// **'Air relativement sec.'**
  String get homeHumidityDry;

  /// No description provided for @homeRainReceived7d.
  ///
  /// In fr, this message translates to:
  /// **'Pluie reçue (7j)'**
  String get homeRainReceived7d;

  /// No description provided for @homeRainReceivedTooltip.
  ///
  /// In fr, this message translates to:
  /// **'Quantité totale de pluie tombée ces 7 derniers jours'**
  String get homeRainReceivedTooltip;

  /// No description provided for @homeRainExpected7d.
  ///
  /// In fr, this message translates to:
  /// **'Pluie prévue (7j)'**
  String get homeRainExpected7d;

  /// No description provided for @homeRainExpectedTooltip.
  ///
  /// In fr, this message translates to:
  /// **'Précipitations attendues dans les 7 prochains jours'**
  String get homeRainExpectedTooltip;

  /// No description provided for @homeClimateRisksTitle.
  ///
  /// In fr, this message translates to:
  /// **'RISQUES CLIMATIQUES'**
  String get homeClimateRisksTitle;

  /// No description provided for @homeMethodAiRf.
  ///
  /// In fr, this message translates to:
  /// **'IA + RF'**
  String get homeMethodAiRf;

  /// No description provided for @homeMethodRules.
  ///
  /// In fr, this message translates to:
  /// **'Règles'**
  String get homeMethodRules;

  /// No description provided for @homeRiskTrendTitle.
  ///
  /// In fr, this message translates to:
  /// **'TENDANCE DES RISQUES'**
  String get homeRiskTrendTitle;

  /// No description provided for @homeRiskTrendSubtitle.
  ///
  /// In fr, this message translates to:
  /// **'Comment les risques évoluent-ils dans les prochains jours ?'**
  String get homeRiskTrendSubtitle;

  /// No description provided for @homeReportThanks.
  ///
  /// In fr, this message translates to:
  /// **'Merci ! Votre signalement a été enregistré.'**
  String get homeReportThanks;

  /// No description provided for @homeReportButton.
  ///
  /// In fr, this message translates to:
  /// **'Signaler un événement observé'**
  String get homeReportButton;

  /// No description provided for @homeFloodNone.
  ///
  /// In fr, this message translates to:
  /// **'Pas de risque d\'inondation en ce moment.'**
  String get homeFloodNone;

  /// No description provided for @homeFloodHeavyRain.
  ///
  /// In fr, this message translates to:
  /// **'Beaucoup de pluie : {value} mm en 7 jours.'**
  String homeFloodHeavyRain(String value);

  /// No description provided for @homeFloodMonitoring.
  ///
  /// In fr, this message translates to:
  /// **'Surveillance active des précipitations.'**
  String get homeFloodMonitoring;

  /// No description provided for @homeDroughtHydrated.
  ///
  /// In fr, this message translates to:
  /// **'La végétation est bien hydratée.'**
  String get homeDroughtHydrated;

  /// No description provided for @homeDroughtSevere.
  ///
  /// In fr, this message translates to:
  /// **'Végétation {state} — le sol manque significativement d\'eau.'**
  String homeDroughtSevere(String state);

  /// No description provided for @homeDroughtMild.
  ///
  /// In fr, this message translates to:
  /// **'Végétation {state} — légère sécheresse détectée.'**
  String homeDroughtMild(String state);

  /// No description provided for @homeHeatNormal.
  ///
  /// In fr, this message translates to:
  /// **'Températures normales pour la saison.'**
  String get homeHeatNormal;

  /// No description provided for @homeHeatWarning.
  ///
  /// In fr, this message translates to:
  /// **'Attention : {value}°C relevés, restez à l\'ombre.'**
  String homeHeatWarning(String value);

  /// No description provided for @homeHeatHydrate.
  ///
  /// In fr, this message translates to:
  /// **'Températures élevées, pensez à bien vous hydrater.'**
  String get homeHeatHydrate;

  /// No description provided for @homeDataUnavailable.
  ///
  /// In fr, this message translates to:
  /// **'Données indisponibles'**
  String get homeDataUnavailable;

  /// No description provided for @homeRiskLevelNone.
  ///
  /// In fr, this message translates to:
  /// **'Nul'**
  String get homeRiskLevelNone;

  /// No description provided for @homeRiskLevelLow.
  ///
  /// In fr, this message translates to:
  /// **'Faible'**
  String get homeRiskLevelLow;

  /// No description provided for @homeRiskLevelModerate.
  ///
  /// In fr, this message translates to:
  /// **'Modéré'**
  String get homeRiskLevelModerate;

  /// No description provided for @homeRiskLevelHigh.
  ///
  /// In fr, this message translates to:
  /// **'Élevé'**
  String get homeRiskLevelHigh;

  /// No description provided for @homeRiskLevelCritical.
  ///
  /// In fr, this message translates to:
  /// **'Critique'**
  String get homeRiskLevelCritical;

  /// No description provided for @homeAlertNormal.
  ///
  /// In fr, this message translates to:
  /// **'Normal'**
  String get homeAlertNormal;

  /// No description provided for @homeAlertVigilance.
  ///
  /// In fr, this message translates to:
  /// **'Vigilance'**
  String get homeAlertVigilance;

  /// No description provided for @homeAlertModerate.
  ///
  /// In fr, this message translates to:
  /// **'Modéré'**
  String get homeAlertModerate;

  /// No description provided for @homeAlertHigh.
  ///
  /// In fr, this message translates to:
  /// **'Élevé'**
  String get homeAlertHigh;

  /// No description provided for @homeAlertUnknown.
  ///
  /// In fr, this message translates to:
  /// **'Inconnu'**
  String get homeAlertUnknown;

  /// No description provided for @overviewTitle.
  ///
  /// In fr, this message translates to:
  /// **'Vue d\'ensemble'**
  String get overviewTitle;

  /// No description provided for @overviewGridViewTooltip.
  ///
  /// In fr, this message translates to:
  /// **'Vue grille'**
  String get overviewGridViewTooltip;

  /// No description provided for @overviewMapViewTooltip.
  ///
  /// In fr, this message translates to:
  /// **'Vue carte'**
  String get overviewMapViewTooltip;

  /// No description provided for @historyTitle.
  ///
  /// In fr, this message translates to:
  /// **'Historique'**
  String get historyTitle;

  /// No description provided for @historyEmptyState.
  ///
  /// In fr, this message translates to:
  /// **'Aucun historique disponible'**
  String get historyEmptyState;

  /// No description provided for @drawerNoLocationFound.
  ///
  /// In fr, this message translates to:
  /// **'Aucun lieu trouvé pour \"{query}\"'**
  String drawerNoLocationFound(String query);

  /// No description provided for @drawerAddLocationTitle.
  ///
  /// In fr, this message translates to:
  /// **'Ajouter un endroit'**
  String get drawerAddLocationTitle;

  /// No description provided for @drawerCityNameHint.
  ///
  /// In fr, this message translates to:
  /// **'Nom de la ville'**
  String get drawerCityNameHint;

  /// No description provided for @drawerSelectLocationHint.
  ///
  /// In fr, this message translates to:
  /// **'Sélectionnez le lieu correspondant :'**
  String get drawerSelectLocationHint;

  /// No description provided for @drawerCancel.
  ///
  /// In fr, this message translates to:
  /// **'Annuler'**
  String get drawerCancel;

  /// No description provided for @drawerZonesLabel.
  ///
  /// In fr, this message translates to:
  /// **'Zones'**
  String get drawerZonesLabel;

  /// No description provided for @drawerLocationSectionLabel.
  ///
  /// In fr, this message translates to:
  /// **'LOCALISATION'**
  String get drawerLocationSectionLabel;

  /// No description provided for @drawerZonesSamcamLabel.
  ///
  /// In fr, this message translates to:
  /// **'ZONES SAMCAM'**
  String get drawerZonesSamcamLabel;

  /// No description provided for @drawerMyPlacesLabel.
  ///
  /// In fr, this message translates to:
  /// **'MES ENDROITS'**
  String get drawerMyPlacesLabel;

  /// No description provided for @drawerFooterTagline.
  ///
  /// In fr, this message translates to:
  /// **'Système d\'Alerte Météo Cameroun'**
  String get drawerFooterTagline;

  /// No description provided for @signalementTitle.
  ///
  /// In fr, this message translates to:
  /// **'Signaler un événement observé'**
  String get signalementTitle;

  /// No description provided for @signalementZoneLabel.
  ///
  /// In fr, this message translates to:
  /// **'Zone : {zone}'**
  String signalementZoneLabel(String zone);

  /// No description provided for @signalementTypeOther.
  ///
  /// In fr, this message translates to:
  /// **'Autre'**
  String get signalementTypeOther;

  /// No description provided for @signalementDescriptionHint.
  ///
  /// In fr, this message translates to:
  /// **'Décrivez ce que vous observez (lieu, ampleur…)'**
  String get signalementDescriptionHint;

  /// No description provided for @signalementSendError.
  ///
  /// In fr, this message translates to:
  /// **'Envoi impossible — vérifiez votre connexion.'**
  String get signalementSendError;

  /// No description provided for @signalementSending.
  ///
  /// In fr, this message translates to:
  /// **'Envoi…'**
  String get signalementSending;

  /// No description provided for @signalementSendButton.
  ///
  /// In fr, this message translates to:
  /// **'Envoyer le signalement'**
  String get signalementSendButton;

  /// No description provided for @assistantTitle.
  ///
  /// In fr, this message translates to:
  /// **'Assistant SAMCAM'**
  String get assistantTitle;

  /// No description provided for @assistantError.
  ///
  /// In fr, this message translates to:
  /// **'L\'assistant est indisponible pour le moment (le modèle local peut mettre du temps à démarrer — réessayez).'**
  String get assistantError;

  /// No description provided for @assistantLoading.
  ///
  /// In fr, this message translates to:
  /// **'Analyse en cours (peut prendre jusqu\'à une minute)…'**
  String get assistantLoading;

  /// No description provided for @assistantQuestionHint.
  ///
  /// In fr, this message translates to:
  /// **'Posez une question (ex. puis-je semer ?)'**
  String get assistantQuestionHint;

  /// No description provided for @demoAutoCountdown.
  ///
  /// In fr, this message translates to:
  /// **'Auto  {countdown} s'**
  String demoAutoCountdown(String countdown);

  /// No description provided for @demoManualLabel.
  ///
  /// In fr, this message translates to:
  /// **'Manuel'**
  String get demoManualLabel;

  /// No description provided for @demoBadgeLabel.
  ///
  /// In fr, this message translates to:
  /// **'DÉMO'**
  String get demoBadgeLabel;

  /// No description provided for @demoAvgDayLabel.
  ///
  /// In fr, this message translates to:
  /// **'Moy. jour'**
  String get demoAvgDayLabel;

  /// No description provided for @demoScenarioClearDayLabel.
  ///
  /// In fr, this message translates to:
  /// **'Ciel dégagé — Jour'**
  String get demoScenarioClearDayLabel;

  /// No description provided for @demoScenarioClearDayDescription.
  ///
  /// In fr, this message translates to:
  /// **'Beau temps, ensoleillement maximal'**
  String get demoScenarioClearDayDescription;

  /// No description provided for @demoScenarioClearDayCondition.
  ///
  /// In fr, this message translates to:
  /// **'Ensoleillé'**
  String get demoScenarioClearDayCondition;

  /// No description provided for @demoScenarioClearNightLabel.
  ///
  /// In fr, this message translates to:
  /// **'Ciel dégagé — Nuit'**
  String get demoScenarioClearNightLabel;

  /// No description provided for @demoScenarioClearNightDescription.
  ///
  /// In fr, this message translates to:
  /// **'Nuit claire, étoiles visibles'**
  String get demoScenarioClearNightDescription;

  /// No description provided for @demoScenarioClearNightCondition.
  ///
  /// In fr, this message translates to:
  /// **'Nuit claire'**
  String get demoScenarioClearNightCondition;

  /// No description provided for @demoScenarioPartlyCloudyLabel.
  ///
  /// In fr, this message translates to:
  /// **'Partiellement nuageux'**
  String get demoScenarioPartlyCloudyLabel;

  /// No description provided for @demoScenarioPartlyCloudyDescription.
  ///
  /// In fr, this message translates to:
  /// **'Alternance soleil et nuages'**
  String get demoScenarioPartlyCloudyDescription;

  /// No description provided for @demoScenarioPartlyCloudyCondition.
  ///
  /// In fr, this message translates to:
  /// **'Peu nuageux'**
  String get demoScenarioPartlyCloudyCondition;

  /// No description provided for @demoScenarioCloudyLabel.
  ///
  /// In fr, this message translates to:
  /// **'Nuageux'**
  String get demoScenarioCloudyLabel;

  /// No description provided for @demoScenarioCloudyDescription.
  ///
  /// In fr, this message translates to:
  /// **'Couverture nuageuse totale'**
  String get demoScenarioCloudyDescription;

  /// No description provided for @demoScenarioCloudyCondition.
  ///
  /// In fr, this message translates to:
  /// **'Très nuageux'**
  String get demoScenarioCloudyCondition;

  /// No description provided for @demoScenarioLightRainLabel.
  ///
  /// In fr, this message translates to:
  /// **'Pluie légère'**
  String get demoScenarioLightRainLabel;

  /// No description provided for @demoScenarioLightRainDescription.
  ///
  /// In fr, this message translates to:
  /// **'Bruine intermittente'**
  String get demoScenarioLightRainDescription;

  /// No description provided for @demoScenarioLightRainCondition.
  ///
  /// In fr, this message translates to:
  /// **'Pluie légère'**
  String get demoScenarioLightRainCondition;

  /// No description provided for @demoScenarioHeavyRainLabel.
  ///
  /// In fr, this message translates to:
  /// **'Forte pluie'**
  String get demoScenarioHeavyRainLabel;

  /// No description provided for @demoScenarioHeavyRainDescription.
  ///
  /// In fr, this message translates to:
  /// **'Averses intenses'**
  String get demoScenarioHeavyRainDescription;

  /// No description provided for @demoScenarioHeavyRainCondition.
  ///
  /// In fr, this message translates to:
  /// **'Pluie forte'**
  String get demoScenarioHeavyRainCondition;

  /// No description provided for @demoScenarioStormLabel.
  ///
  /// In fr, this message translates to:
  /// **'Orage'**
  String get demoScenarioStormLabel;

  /// No description provided for @demoScenarioStormDescription.
  ///
  /// In fr, this message translates to:
  /// **'Orages violents, éclairs'**
  String get demoScenarioStormDescription;

  /// No description provided for @demoScenarioStormCondition.
  ///
  /// In fr, this message translates to:
  /// **'Orage violent'**
  String get demoScenarioStormCondition;

  /// No description provided for @demoScenarioFoggyLabel.
  ///
  /// In fr, this message translates to:
  /// **'Brouillard'**
  String get demoScenarioFoggyLabel;

  /// No description provided for @demoScenarioFoggyDescription.
  ///
  /// In fr, this message translates to:
  /// **'Visibilité réduite'**
  String get demoScenarioFoggyDescription;

  /// No description provided for @demoScenarioFoggyCondition.
  ///
  /// In fr, this message translates to:
  /// **'Brouillard dense'**
  String get demoScenarioFoggyCondition;

  /// No description provided for @demoScenarioSnowLabel.
  ///
  /// In fr, this message translates to:
  /// **'Neige'**
  String get demoScenarioSnowLabel;

  /// No description provided for @demoScenarioSnowDescription.
  ///
  /// In fr, this message translates to:
  /// **'Chutes de neige modérées'**
  String get demoScenarioSnowDescription;

  /// No description provided for @demoScenarioSnowCondition.
  ///
  /// In fr, this message translates to:
  /// **'Neige modérée'**
  String get demoScenarioSnowCondition;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'fr'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
    case 'fr':
      return AppLocalizationsFr();
  }

  throw FlutterError(
      'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
      'an issue with the localizations generation tool. Please file an issue '
      'on GitHub with a reproducible sample app and the gen-l10n configuration '
      'that was used.');
}
