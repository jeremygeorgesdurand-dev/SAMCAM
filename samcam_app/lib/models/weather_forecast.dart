// SAMCAM — Modèle météo pour prévisions horaires et 7 jours
// Utilise Open-Meteo (gratuit, sans clé API)

class HourlyForecast {
  final DateTime time;
  final double temperature;
  final double feelsLike;
  final double precipitation;
  final int weatherCode;
  final double windSpeed;
  final int humidity;

  HourlyForecast({
    required this.time,
    required this.temperature,
    required this.feelsLike,
    required this.precipitation,
    required this.weatherCode,
    required this.windSpeed,
    required this.humidity,
  });
}

class DailyForecast {
  final DateTime date;
  final double tempMin;
  final double tempMax;
  final double precipitationSum;
  final int weatherCode;
  final double windSpeedMax;
  final double uvIndexMax;
  final DateTime? sunrise;
  final DateTime? sunset;
  final double precipitationProbMax;

  DailyForecast({
    required this.date,
    required this.tempMin,
    required this.tempMax,
    required this.precipitationSum,
    required this.weatherCode,
    required this.windSpeedMax,
    this.uvIndexMax = 0,
    this.sunrise,
    this.sunset,
    this.precipitationProbMax = 0,
  });
}

class CurrentConditions {
  final double temperature;
  final double feelsLike;
  final double pressure;
  final double visibility;
  final int uvIndex;
  final int humidity;
  final double windSpeed;
  final double windGusts;
  final int weatherCode;

  CurrentConditions({
    required this.temperature,
    required this.feelsLike,
    required this.pressure,
    required this.visibility,
    required this.uvIndex,
    required this.humidity,
    required this.windSpeed,
    required this.windGusts,
    this.weatherCode = 0,
  });

  factory CurrentConditions.empty() => CurrentConditions(
    temperature: 0, feelsLike: 0, pressure: 1013,
    visibility: 10, uvIndex: 0, humidity: 0,
    windSpeed: 0, windGusts: 0, weatherCode: 0,
  );
}

class WeatherData {
  final List<HourlyForecast> hourly;
  final List<DailyForecast> daily;
  final CurrentConditions? current;

  WeatherData({
    required this.hourly,
    required this.daily,
    this.current,
  });
}

/// Retourne une icône pour un code météo WMO
String weatherCodeIcon(int code) {
  if (code == 0)  return '☀️';
  if (code <= 2)  return '⛅';
  if (code == 3)  return '☁️';
  if (code <= 49) return '🌫️';
  if (code <= 59) return '🌦️';
  if (code <= 69) return '🌧️';
  if (code <= 79) return '🌨️';
  if (code <= 84) return '🌦️';
  if (code <= 99) return '⛈️';
  return '🌡️';
}

String weatherCodeLabel(int code) {
  if (code == 0)  return 'Ensoleillé';
  if (code <= 2)  return 'Peu nuageux';
  if (code == 3)  return 'Couvert';
  if (code <= 49) return 'Brouillard';
  if (code <= 59) return 'Bruine';
  if (code <= 69) return 'Pluie';
  if (code <= 79) return 'Neige';
  if (code <= 84) return 'Averses';
  if (code <= 99) return 'Orage';
  return 'Inconnu';
}

String uvLabel(int uv) {
  if (uv <= 2)  return 'Faible';
  if (uv <= 5)  return 'Modéré';
  if (uv <= 7)  return 'Élevé';
  if (uv <= 10) return 'Très élevé';
  return 'Extrême';
}
