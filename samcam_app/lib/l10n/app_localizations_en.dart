// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get settingsTitle => 'Settings';

  @override
  String get settingsDemoMode => 'Demo Mode';

  @override
  String get settingsDemoModeCardTitle => 'Weather Demo Mode';

  @override
  String get settingsDemoModeCardSubtitle =>
      '9 weather conditions • Premium animations • Auto 5s';

  @override
  String get settingsFavoriteZone => 'Default zone';

  @override
  String get settingsFavoriteZoneHint =>
      'Zone shown at app startup, instead of automatic GPS mode.';

  @override
  String get settingsGpsPosition => 'GPS position';

  @override
  String get settingsAlerts => 'Custom alerts';

  @override
  String get settingsNotificationsEnabled => 'Notifications enabled';

  @override
  String get settingsNotificationsHint =>
      'Get notified when a risk exceeds your threshold';

  @override
  String get settingsNotificationsCheckedHint =>
      'Checked on every app open/refresh (not in the background).';

  @override
  String get riskFlood => 'Flood';

  @override
  String get riskDrought => 'Drought';

  @override
  String get riskHeat => 'Heat';

  @override
  String get settingsServer => 'Server connection';

  @override
  String get settingsServerUrlLabel => 'SAMCAM server URL';

  @override
  String get settingsServerUrlExample =>
      'Local network example: http://192.168.1.42:8000';

  @override
  String get settingsSave => 'Save';

  @override
  String get settingsTest => 'Test';

  @override
  String get settingsUrlSaved => 'URL saved';

  @override
  String get settingsUrlCleared =>
      'URL cleared — automatic detection re-enabled';

  @override
  String get settingsUrlSavedInsecure =>
      'URL saved — ⚠️ unencrypted connection (http)';

  @override
  String get settingsUrlInvalid =>
      'Invalid URL — must start with http:// or https://';

  @override
  String settingsTestSuccess(String version, String lastUpdate) {
    return '✅ Connected — Version $version | Last update: $lastUpdate';
  }

  @override
  String settingsTestFailure(String error) {
    return '❌ Connection failed: $error';
  }

  @override
  String get settingsLanguage => 'Language';

  @override
  String get settingsLanguageFrench => 'Français';

  @override
  String get settingsLanguageEnglish => 'English';

  @override
  String get yaoundePeri => 'Yaoundé (peri.)';

  @override
  String get homeServerUnreachable => 'SAMCAM server unreachable';

  @override
  String get homeOverviewTooltip => 'Overview';

  @override
  String get homeRetry => 'Retry';

  @override
  String homeOfflineBanner(String suffix) {
    return 'Offline mode — data$suffix';
  }

  @override
  String homeOfflineSince(String date) {
    return ' from $date';
  }

  @override
  String get homeWindStat => 'Wind';

  @override
  String get homeHumidityStat => 'Humidity';

  @override
  String get homeHourlyForecastTitle => 'HOURLY FORECAST';

  @override
  String get homeDailyForecastTitle => '7-DAY FORECAST';

  @override
  String get homeToday => 'Today';

  @override
  String get homeTodayShort => 'Today';

  @override
  String get homeWeekdaySun => 'Sun';

  @override
  String get homeWeekdayMon => 'Mon';

  @override
  String get homeWeekdayTue => 'Tue';

  @override
  String get homeWeekdayWed => 'Wed';

  @override
  String get homeWeekdayThu => 'Thu';

  @override
  String get homeWeekdayFri => 'Fri';

  @override
  String get homeWeekdaySat => 'Sat';

  @override
  String get homeUvIndexLabel => 'UV INDEX';

  @override
  String homeUvProtectionUntil(String time) {
    return 'Protection needed until $time.';
  }

  @override
  String get homeSunSectionLabel => 'SUN';

  @override
  String get homeSunsetLabel => 'Sunset';

  @override
  String homeSunriseAt(String time) {
    return 'Sunrise: $time';
  }

  @override
  String get homeWindSectionLabel => 'WIND';

  @override
  String homeGusts(String value) {
    return 'Gusts: $value km/h';
  }

  @override
  String get homeWindAvgSurface => 'Average surface wind.';

  @override
  String get homePrecipitationLabel => 'PRECIPITATION';

  @override
  String homePrecipTomorrow(String value) {
    return '$value mm tomorrow.';
  }

  @override
  String get homeFeelsLikeLabel => 'FEELS LIKE';

  @override
  String get homeFeelsHigher => 'Feels warmer than the actual temperature.';

  @override
  String get homeFeelsSimilar => 'Similar to the actual temperature.';

  @override
  String get homePressureLabel => 'PRESSURE';

  @override
  String get homePressureLow => 'Low pressure.';

  @override
  String get homePressureHigh => 'High pressure.';

  @override
  String get homePressureNormal => 'Normal pressure.';

  @override
  String get homeVisibilityLabel => 'VISIBILITY';

  @override
  String get homeVisibilityClear => 'Perfectly clear visibility.';

  @override
  String get homeVisibilityReduced => 'Reduced visibility.';

  @override
  String get homeVisibilityFog => 'Fog possible.';

  @override
  String get homeHumidityLabel => 'HUMIDITY';

  @override
  String get homeHumidityVeryHigh => 'Very high humidity.';

  @override
  String get homeHumidityModerate => 'Moderate humidity.';

  @override
  String get homeHumidityDry => 'Relatively dry air.';

  @override
  String get homeRainReceived7d => 'Rain received (7d)';

  @override
  String get homeRainReceivedTooltip => 'Total rainfall over the last 7 days';

  @override
  String get homeRainExpected7d => 'Rain expected (7d)';

  @override
  String get homeRainExpectedTooltip =>
      'Rainfall expected over the next 7 days';

  @override
  String get homeClimateRisksTitle => 'CLIMATE RISKS';

  @override
  String get homeMethodAiRf => 'AI + RF';

  @override
  String get homeMethodRules => 'Rules';

  @override
  String get homeRiskTrendTitle => 'RISK TREND';

  @override
  String get homeRiskTrendSubtitle =>
      'How will risks evolve over the coming days?';

  @override
  String get homeReportThanks => 'Thank you! Your report has been recorded.';

  @override
  String get homeReportButton => 'Report an observed event';

  @override
  String get homeFloodNone => 'No flood risk at the moment.';

  @override
  String homeFloodHeavyRain(String value) {
    return 'Heavy rainfall: $value mm over 7 days.';
  }

  @override
  String get homeFloodMonitoring => 'Actively monitoring rainfall.';

  @override
  String get homeDroughtHydrated => 'Vegetation is well hydrated.';

  @override
  String homeDroughtSevere(String state) {
    return 'Vegetation $state — the soil is significantly short of water.';
  }

  @override
  String homeDroughtMild(String state) {
    return 'Vegetation $state — mild drought detected.';
  }

  @override
  String get homeHeatNormal => 'Normal temperatures for the season.';

  @override
  String homeHeatWarning(String value) {
    return 'Warning: $value°C recorded, stay in the shade.';
  }

  @override
  String get homeHeatHydrate => 'High temperatures, remember to stay hydrated.';

  @override
  String get homeDataUnavailable => 'Data unavailable';

  @override
  String get homeRiskLevelNone => 'None';

  @override
  String get homeRiskLevelLow => 'Low';

  @override
  String get homeRiskLevelModerate => 'Moderate';

  @override
  String get homeRiskLevelHigh => 'High';

  @override
  String get homeRiskLevelCritical => 'Critical';

  @override
  String get homeAlertNormal => 'Normal';

  @override
  String get homeAlertVigilance => 'Watch';

  @override
  String get homeAlertModerate => 'Moderate';

  @override
  String get homeAlertHigh => 'High';

  @override
  String get homeAlertUnknown => 'Unknown';

  @override
  String get overviewTitle => 'Overview';

  @override
  String get overviewGridViewTooltip => 'Grid view';

  @override
  String get overviewMapViewTooltip => 'Map view';

  @override
  String get historyTitle => 'History';

  @override
  String get historyEmptyState => 'No history available';

  @override
  String drawerNoLocationFound(String query) {
    return 'No location found for \"$query\"';
  }

  @override
  String get drawerAddLocationTitle => 'Add a place';

  @override
  String get drawerCityNameHint => 'City name';

  @override
  String get drawerSelectLocationHint => 'Select the matching location:';

  @override
  String get drawerCancel => 'Cancel';

  @override
  String get drawerZonesLabel => 'Zones';

  @override
  String get drawerLocationSectionLabel => 'LOCATION';

  @override
  String get drawerZonesSamcamLabel => 'SAMCAM ZONES';

  @override
  String get drawerMyPlacesLabel => 'MY PLACES';

  @override
  String get drawerFooterTagline => 'Cameroon Weather Alert System';

  @override
  String get signalementTitle => 'Report an observed event';

  @override
  String signalementZoneLabel(String zone) {
    return 'Zone: $zone';
  }

  @override
  String get signalementTypeOther => 'Other';

  @override
  String get signalementDescriptionHint =>
      'Describe what you\'re observing (location, extent…)';

  @override
  String get signalementSendError => 'Could not send — check your connection.';

  @override
  String get signalementSending => 'Sending…';

  @override
  String get signalementSendButton => 'Send report';

  @override
  String get assistantTitle => 'SAMCAM Assistant';

  @override
  String get assistantError =>
      'The assistant is currently unavailable (the local model may take a moment to start — please try again).';

  @override
  String get assistantLoading => 'Analyzing (this can take up to a minute)…';

  @override
  String get assistantQuestionHint => 'Ask a question (e.g. can I plant now?)';

  @override
  String demoAutoCountdown(String countdown) {
    return 'Auto  ${countdown}s';
  }

  @override
  String get demoManualLabel => 'Manual';

  @override
  String get demoBadgeLabel => 'DEMO';

  @override
  String get demoAvgDayLabel => 'Day avg.';

  @override
  String get demoScenarioClearDayLabel => 'Clear sky — Day';

  @override
  String get demoScenarioClearDayDescription =>
      'Fine weather, maximum sunshine';

  @override
  String get demoScenarioClearDayCondition => 'Sunny';

  @override
  String get demoScenarioClearNightLabel => 'Clear sky — Night';

  @override
  String get demoScenarioClearNightDescription => 'Clear night, stars visible';

  @override
  String get demoScenarioClearNightCondition => 'Clear night';

  @override
  String get demoScenarioPartlyCloudyLabel => 'Partly cloudy';

  @override
  String get demoScenarioPartlyCloudyDescription =>
      'Alternating sun and clouds';

  @override
  String get demoScenarioPartlyCloudyCondition => 'Partly cloudy';

  @override
  String get demoScenarioCloudyLabel => 'Cloudy';

  @override
  String get demoScenarioCloudyDescription => 'Full cloud cover';

  @override
  String get demoScenarioCloudyCondition => 'Overcast';

  @override
  String get demoScenarioLightRainLabel => 'Light rain';

  @override
  String get demoScenarioLightRainDescription => 'Intermittent drizzle';

  @override
  String get demoScenarioLightRainCondition => 'Light rain';

  @override
  String get demoScenarioHeavyRainLabel => 'Heavy rain';

  @override
  String get demoScenarioHeavyRainDescription => 'Intense showers';

  @override
  String get demoScenarioHeavyRainCondition => 'Heavy rain';

  @override
  String get demoScenarioStormLabel => 'Storm';

  @override
  String get demoScenarioStormDescription => 'Violent storms, lightning';

  @override
  String get demoScenarioStormCondition => 'Severe storm';

  @override
  String get demoScenarioFoggyLabel => 'Fog';

  @override
  String get demoScenarioFoggyDescription => 'Reduced visibility';

  @override
  String get demoScenarioFoggyCondition => 'Dense fog';

  @override
  String get demoScenarioSnowLabel => 'Snow';

  @override
  String get demoScenarioSnowDescription => 'Moderate snowfall';

  @override
  String get demoScenarioSnowCondition => 'Moderate snow';
}
