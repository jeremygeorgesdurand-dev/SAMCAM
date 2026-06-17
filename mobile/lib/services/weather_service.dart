// SAMCAM — Service météo via Open-Meteo (gratuit, sans clé)
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/weather_forecast.dart';

class WeatherService {
  // Coordonnées de Kribi, Cameroun
  static const double _lat  = 2.9399;
  static const double _lon  = 9.9094;

  static Future<WeatherData> getForecast() async {
    final uri = Uri.parse(
      'https://api.open-meteo.com/v1/forecast'
      '?latitude=$_lat&longitude=$_lon'
      '&hourly=temperature_2m,precipitation,weathercode,windspeed_10m,relativehumidity_2m'
      '&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max'
      '&timezone=Africa%2FDouala'
      '&forecast_days=7',
    );

    final response = await http.get(uri).timeout(const Duration(seconds: 10));
    if (response.statusCode != 200) {
      throw Exception('Erreur Open-Meteo : ${response.statusCode}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return _parse(json);
  }

  static WeatherData _parse(Map<String, dynamic> json) {
    final h      = json['hourly'] as Map<String, dynamic>;
    final times  = (h['time']                   as List).cast<String>();
    final temps  = (h['temperature_2m']          as List).map((v) => (v as num).toDouble()).toList();
    final precip = (h['precipitation']           as List).map((v) => (v as num).toDouble()).toList();
    final wcH    = (h['weathercode']             as List).map((v) => (v as num).toInt()).toList();
    final windH  = (h['windspeed_10m']           as List).map((v) => (v as num).toDouble()).toList();
    final humH   = (h['relativehumidity_2m']     as List).map((v) => (v as num).toInt()).toList();

    final now = DateTime.now();
    final hourly = <HourlyForecast>[];
    for (int i = 0; i < times.length; i++) {
      final t = DateTime.parse(times[i]);
      if (t.isAfter(now) && t.isBefore(now.add(const Duration(hours: 25)))) {
        hourly.add(HourlyForecast(
          time:          t,
          temperature:   temps[i],
          precipitation: precip[i],
          weatherCode:   wcH[i],
          windSpeed:     windH[i],
          humidity:      humH[i],
        ));
      }
    }

    final d      = json['daily'] as Map<String, dynamic>;
    final dates  = (d['time']                    as List).cast<String>();
    final wcD    = (d['weathercode']             as List).map((v) => (v as num).toInt()).toList();
    final tMax   = (d['temperature_2m_max']      as List).map((v) => (v as num).toDouble()).toList();
    final tMin   = (d['temperature_2m_min']      as List).map((v) => (v as num).toDouble()).toList();
    final precD  = (d['precipitation_sum']       as List).map((v) => (v as num).toDouble()).toList();
    final windD  = (d['windspeed_10m_max']       as List).map((v) => (v as num).toDouble()).toList();

    final daily = <DailyForecast>[];
    for (int i = 0; i < dates.length; i++) {
      daily.add(DailyForecast(
        date:              DateTime.parse(dates[i]),
        tempMin:           tMin[i],
        tempMax:           tMax[i],
        precipitationSum:  precD[i],
        weatherCode:       wcD[i],
        windSpeedMax:      windD[i],
      ));
    }

    return WeatherData(hourly: hourly, daily: daily);
  }
}
