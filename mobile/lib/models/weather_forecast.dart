// SAMCAM — Modèle météo pour prévisions horaires et 7 jours
// Utilise Open-Meteo (gratuit, sans clé API)

class HourlyForecast {
  final DateTime time;
  final double temperature;
  final double precipitation;
  final int weatherCode;
  final double windSpeed;
  final int humidity;

  HourlyForecast({
    required this.time,
    required this.temperature,
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

  DailyForecast({
    required this.date,
    required this.tempMin,
    required this.tempMax,
    required this.precipitationSum,
    required this.weatherCode,
    required this.windSpeedMax,
  });
}

class WeatherData {
  final List<HourlyForecast> hourly;
  final List<DailyForecast> daily;

  WeatherData({required this.hourly, required this.daily});
}

/// Retourne une icône pour un code météo WMO
String weatherCodeIcon(int code) {
  if (code == 0) return '☀️';
  if (code <= 2) return '🌤️';
  if (code == 3) return '☁️';
  if (code <= 49) return '🌫️';
  if (code <= 59) return '🌦️';
  if (code <= 69) return '🌧️';
  if (code <= 79) return '🌨️';
  if (code <= 84) return '🌦️';
  if (code <= 99) return '⛈️';
  return '🌡️';
}

String weatherCodeLabel(int code) {
  if (code == 0) return 'Ensoleillé';
  if (code <= 2) return 'Peu nuageux';
  if (code == 3) return 'Couvert';
  if (code <= 49) return 'Brouillard';
  if (code <= 59) return 'Bruine';
  if (code <= 69) return 'Pluie';
  if (code <= 79) return 'Neige';
  if (code <= 84) return 'Averses';
  if (code <= 99) return 'Orage';
  return 'Inconnu';
}
