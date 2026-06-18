// SAMCAM — Service météo via Open-Meteo (gratuit, sans clé)
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/weather_forecast.dart';

class WeatherService {
  static const double _lat = 2.9399;
  static const double _lon = 9.9094;

  static Future<WeatherData> getForecast() async {
    try {
      final uri = Uri.parse(
        'https://api.open-meteo.com/v1/forecast'
        '?latitude=$_lat&longitude=$_lon'
        '&hourly=temperature_2m,apparent_temperature,precipitation,weathercode,windspeed_10m,relativehumidity_2m'
        '&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max'
        ',uv_index_max,sunrise,sunset,precipitation_probability_max'
        '&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m'
        ',wind_gusts_10m,surface_pressure,visibility,uv_index'
        '&timezone=Africa%2FDouala'
        '&forecast_days=7',
      );

      final response = await http.get(uri).timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) throw Exception('HTTP \${response.statusCode}');
      return _parse(jsonDecode(response.body) as Map<String, dynamic>);
    } catch (_) {
      return _mockKribi();
    }
  }

  // ── Mock Kribi (fallback) ────────────────────────────────────────────────
  static WeatherData _mockKribi() {
    final now = DateTime.now();
    final hourly = List.generate(24, (i) {
      final t = now.add(Duration(hours: i + 1));
      final isRaining = (i % 6 == 0 || i % 6 == 1);
      return HourlyForecast(
        time:          t,
        temperature:   26.0 + (i % 4) * 1.5 - (i > 14 ? 2.0 : 0.0),
        feelsLike:     29.0 + (i % 3),
        precipitation: isRaining ? 4.5 : 0.0,
        weatherCode:   isRaining ? 61 : 2,
        windSpeed:     12.0 + (i % 3) * 2.0,
        humidity:      78 + (i % 5),
      );
    });
    final daily = List.generate(7, (i) {
      final d = now.add(Duration(days: i));
      final rainy = (i == 0 || i == 2 || i == 5);
      return DailyForecast(
        date:                  d,
        tempMin:               24.0 + i * 0.3,
        tempMax:               31.0 + i * 0.2,
        precipitationSum:      rainy ? 18.0 + i * 2.0 : 0.0,
        weatherCode:           rainy ? 61 : 1,
        windSpeedMax:          18.0,
        uvIndexMax:            4.5,
        sunrise:               DateTime(d.year, d.month, d.day, 6, 12),
        sunset:                DateTime(d.year, d.month, d.day, 18, 30),
        precipitationProbMax:  rainy ? 75.0 : 20.0,
      );
    });
    return WeatherData(
      hourly: hourly,
      daily: daily,
      current: CurrentConditions(
        temperature: 28, feelsLike: 31, pressure: 1012,
        visibility: 17, uvIndex: 3, humidity: 76,
        windSpeed: 11, windGusts: 19,
      ),
    );
  }

  // ── Parsing ────────────────────────────────────────────────────────────
  static WeatherData _parse(Map<String, dynamic> json) {
    CurrentConditions? current;
    if (json['current'] != null) {
      final c = json['current'] as Map<String, dynamic>;
      current = CurrentConditions(
        temperature: (c['temperature_2m']        ?? 0).toDouble(),
        feelsLike:   (c['apparent_temperature']  ?? 0).toDouble(),
        pressure:    (c['surface_pressure']      ?? 1013).toDouble(),
        visibility:  ((c['visibility']           ?? 10000) / 1000.0),
        uvIndex:     (c['uv_index']              ?? 0).toInt(),
        humidity:    (c['relative_humidity_2m']  ?? 0).toInt(),
        windSpeed:   (c['wind_speed_10m']        ?? 0).toDouble(),
        windGusts:   (c['wind_gusts_10m']        ?? 0).toDouble(),
      );
    }

    final h      = json['hourly'] as Map<String, dynamic>;
    final times  = (h['time']                  as List).cast<String>();
    final temps  = (h['temperature_2m']        as List).map((v) => (v as num).toDouble()).toList();
    final feels  = (h['apparent_temperature']  as List).map((v) => (v as num).toDouble()).toList();
    final precip = (h['precipitation']         as List).map((v) => (v as num).toDouble()).toList();
    final wcH    = (h['weathercode']           as List).map((v) => (v as num).toInt()).toList();
    final windH  = (h['windspeed_10m']         as List).map((v) => (v as num).toDouble()).toList();
    final humH   = (h['relativehumidity_2m']   as List).map((v) => (v as num).toInt()).toList();

    final now    = DateTime.now();
    final hourly = <HourlyForecast>[];
    for (int i = 0; i < times.length; i++) {
      final t = DateTime.parse(times[i]);
      if (t.isAfter(now) && t.isBefore(now.add(const Duration(hours: 25)))) {
        hourly.add(HourlyForecast(
          time:          t,
          temperature:   temps[i],
          feelsLike:     feels[i],
          precipitation: precip[i],
          weatherCode:   wcH[i],
          windSpeed:     windH[i],
          humidity:      humH[i],
        ));
      }
    }

    final d    = json['daily'] as Map<String, dynamic>;
    final dates = (d['time']              as List).cast<String>();
    final wcD   = (d['weathercode']       as List).map((v) => (v as num).toInt()).toList();
    final tMax  = (d['temperature_2m_max'] as List).map((v) => (v as num).toDouble()).toList();
    final tMin  = (d['temperature_2m_min'] as List).map((v) => (v as num).toDouble()).toList();
    final precD = (d['precipitation_sum'] as List).map((v) => (v as num).toDouble()).toList();
    final windD = (d['windspeed_10m_max'] as List).map((v) => (v as num).toDouble()).toList();
    final uvD   = (d['uv_index_max']      as List).map((v) => (v as num).toDouble()).toList();
    final srD   = (d['sunrise']           as List).cast<String>();
    final ssD   = (d['sunset']            as List).cast<String>();
    final ppD   = (d['precipitation_probability_max'] as List)
                  .map((v) => v != null ? (v as num).toDouble() : 0.0).toList();

    final daily = List.generate(dates.length, (i) => DailyForecast(
      date:                 DateTime.parse(dates[i]),
      tempMin:              tMin[i],
      tempMax:              tMax[i],
      precipitationSum:     precD[i],
      weatherCode:          wcD[i],
      windSpeedMax:         windD[i],
      uvIndexMax:           uvD[i],
      sunrise:              DateTime.tryParse(srD[i]),
      sunset:               DateTime.tryParse(ssD[i]),
      precipitationProbMax: ppD[i],
    ));

    return WeatherData(hourly: hourly, daily: daily, current: current);
  }
}
