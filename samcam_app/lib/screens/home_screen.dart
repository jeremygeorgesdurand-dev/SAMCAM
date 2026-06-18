import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../config.dart';
import '../models/risk_report.dart';
import '../models/weather_forecast.dart';
import '../services/api_service.dart';
import '../services/weather_service.dart';
import 'settings_screen.dart';
import 'history_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  RiskReport?  _report;
  WeatherData? _weather;
  bool         _loading = true;
  String?      _error;
  bool _hourlyExpanded = true;
  bool _dailyExpanded  = true;

  @override
  void initState() { super.initState(); _fetchAll(); }

  Future<void> _fetchAll() async {
    setState(() { _loading = true; _error = null; });
    final weatherFuture = WeatherService.getForecast();
    try {
      final risk    = await ApiService.getRisk();
      final weather = await weatherFuture;
      setState(() { _report = risk; _weather = weather; _loading = false; });
    } catch (e) {
      final weather = await weatherFuture.catchError((_) => WeatherService.getForecast());
      setState(() { _weather = weather; _error = 'Serveur SAMCAM inaccessible'; _loading = false; });
    }
  }

  Color _alertColor(String niveau) =>
      Color(Config.alertColors[niveau] ?? Config.alertColors['INCONNU']!);

  /// Libellé court pour les badges (évite le débordement)
  String _alertShort(String niveau) {
    const short = {
      'VERT':    'Normal',
      'JAUNE':   'Vigilance',
      'ORANGE':  'Modéré',
      'ROUGE':   'Élevé',
      'INCONNU': 'Inconnu',
    };
    return short[niveau] ?? niveau;
  }

  /// Libellé long pour la bannière principale
  String _alertLabel(String niveau) =>
      Config.alertLabels[niveau] ?? niveau;

  LinearGradient _skyGradient() {
    final h = DateTime.now().toLocal().hour;
    if (h >= 6 && h < 12) return const LinearGradient(
      begin: Alignment.topCenter, end: Alignment.bottomCenter,
      colors: [Color(0xFF1A7FC1), Color(0xFF5BAFE0)]);
    if (h >= 12 && h < 18) return const LinearGradient(
      begin: Alignment.topCenter, end: Alignment.bottomCenter,
      colors: [Color(0xFF0D5FA3), Color(0xFF4A9FD0)]);
    if (h >= 18 && h < 21) return const LinearGradient(
      begin: Alignment.topCenter, end: Alignment.bottomCenter,
      colors: [Color(0xFF1A3A6B), Color(0xFFD4721A)]);
    return const LinearGradient(
      begin: Alignment.topCenter, end: Alignment.bottomCenter,
      colors: [Color(0xFF0A1628), Color(0xFF1A2E4A)]);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent, elevation: 0,
        title: const Text('SAMCAM', style: TextStyle(
          color: Colors.white, fontWeight: FontWeight.bold,
          letterSpacing: 1.5, fontSize: 18)),
        actions: [
          IconButton(
            icon: const Icon(Icons.history, color: Colors.white70),
            onPressed: () => Navigator.push(context,
              MaterialPageRoute(builder: (_) => const HistoryScreen()))),
          IconButton(
            icon: const Icon(Icons.settings_outlined, color: Colors.white70),
            onPressed: () async {
              await Navigator.push(context,
                MaterialPageRoute(builder: (_) => const SettingsScreen()));
              _fetchAll();
            }),
          IconButton(
            icon: const Icon(Icons.refresh, color: Colors.white70),
            onPressed: _fetchAll),
        ],
      ),
      body: Container(
        decoration: BoxDecoration(gradient: _skyGradient()),
        child: SafeArea(
          top: true, bottom: false,
          child: RefreshIndicator(
            onRefresh: _fetchAll, color: Colors.white,
            child: _buildBody()),
        ),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
        children: [
          _buildSkeletonBanner(),
          const SizedBox(height: 12),
          _buildSkeletonHeader(),
          const SizedBox(height: 20),
          _buildSkeletonCard(height: 130),
          const SizedBox(height: 12),
          _buildSkeletonCard(height: 220),
        ],
      );
    }
    final weather = _weather ?? WeatherData(hourly: [], daily: []);
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      children: [
        // ── BANDEAU ALERTE ──────────────────────────────────────────
        if (_report != null) _buildAlertBanner(_report!),
        if (_error != null) _buildErrorBanner(),
        if (_report != null || _error != null) const SizedBox(height: 16),
        // ── MÉTÉO ───────────────────────────────────────────────────
        _buildWeatherHeader(weather),
        const SizedBox(height: 20),
        _buildHourlySection(weather),
        const SizedBox(height: 12),
        _buildDailySection(weather),
        const SizedBox(height: 20),
        _buildWeatherTiles(weather),
        const SizedBox(height: 12),
        if (_report != null) ..._buildRiskSection(_report!),
      ],
    );
  }

  // ── SQUELETTES ──────────────────────────────────────────────────
  Widget _buildSkeletonBanner() => Container(
    height: 52,
    decoration: BoxDecoration(
      color: Colors.white10, borderRadius: BorderRadius.circular(18)));

  Widget _buildSkeletonHeader() => Column(children: [
    _skeletonBox(width: 120, height: 28, radius: 8),
    const SizedBox(height: 8),
    _skeletonBox(width: 80, height: 14, radius: 6),
    const SizedBox(height: 20),
    _skeletonBox(width: 160, height: 80, radius: 12),
    const SizedBox(height: 12),
    _skeletonBox(width: 100, height: 16, radius: 6),
  ]);

  Widget _buildSkeletonCard({required double height}) => Container(
    height: height,
    decoration: BoxDecoration(
      color: Colors.white10, borderRadius: BorderRadius.circular(20)),
    child: const Center(
      child: CircularProgressIndicator(color: Colors.white30, strokeWidth: 2)));

  Widget _skeletonBox({double? width, required double height, double radius = 4}) =>
    Container(
      width: width, height: height,
      decoration: BoxDecoration(
        color: Colors.white12, borderRadius: BorderRadius.circular(radius)));

  // ── BANNIÈRE ALERTE ─────────────────────────────────────────────
  Widget _buildAlertBanner(RiskReport r) {
    final color = _alertColor(r.niveauAlerte);
    final isOk  = r.niveauAlerte == 'VERT';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: color.withOpacity(0.18),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withOpacity(0.45), width: 1)),
      child: Row(children: [
        Icon(
          isOk ? Icons.check_circle_outline : Icons.warning_amber_rounded,
          color: color, size: 20),
        const SizedBox(width: 10),
        Expanded(child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(_alertLabel(r.niveauAlerte), style: TextStyle(
              color: color, fontSize: 14, fontWeight: FontWeight.w700)),
            Text('${r.zone}  •  ${r.date}',
              style: const TextStyle(color: Colors.white54, fontSize: 11)),
          ])),
        const SizedBox(width: 8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: color.withOpacity(0.25),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: color.withOpacity(0.6))),
          child: Text(r.niveauAlerte, style: TextStyle(
            color: color, fontWeight: FontWeight.bold,
            letterSpacing: 0.8, fontSize: 11))),
      ]),
    );
  }

  Widget _buildErrorBanner() => Container(
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
    decoration: BoxDecoration(
      color: Colors.white.withOpacity(0.08),
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: Colors.white12)),
    child: Row(children: [
      const Icon(Icons.cloud_off_outlined, color: Colors.white38, size: 16),
      const SizedBox(width: 8),
      Expanded(child: Text(
        '${_error ?? 'Serveur SAMCAM inaccessible'} — météo locale',
        style: const TextStyle(color: Colors.white54, fontSize: 12))),
      TextButton(
        onPressed: _fetchAll,
        style: TextButton.styleFrom(padding: EdgeInsets.zero,
          minimumSize: Size.zero,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap),
        child: const Text('Réessayer',
          style: TextStyle(color: Colors.white60, fontSize: 12))),
    ]));

  // ── EN-TÊTE MÉTÉO ────────────────────────────────────────────────
  Widget _buildWeatherHeader(WeatherData weather) {
    final now = DateTime.now();
    String dateStr;
    try { dateStr = DateFormat('EEEE d MMMM', 'fr_FR').format(now); }
    catch (_) { dateStr = DateFormat('yyyy-MM-dd').format(now); }

    final city = _report?.zone ?? 'Kribi';
    final cur  = weather.current;

    String currentTemp = '--';
    String currentIcon = '';
    String currentDesc = '';
    int    humidity    = 0;
    double wind        = 0;

    if (cur != null) {
      currentTemp = cur.temperature.toStringAsFixed(0);
      humidity    = cur.humidity;
      wind        = cur.windSpeed;
      currentIcon = weatherCodeIcon(cur.weatherCode);
      currentDesc = weatherCodeLabel(cur.weatherCode);
    }
    if (weather.hourly.isNotEmpty) {
      final h = weather.hourly.first;
      if (cur == null) {
        currentTemp = h.temperature.toStringAsFixed(0);
        currentIcon = weatherCodeIcon(h.weatherCode);
        currentDesc = weatherCodeLabel(h.weatherCode);
        humidity    = h.humidity;
        wind        = h.windSpeed;
      }
    } else if (weather.daily.isNotEmpty) {
      final d = weather.daily.first;
      if (cur == null) {
        currentTemp = d.tempMax.toStringAsFixed(0);
        currentIcon = weatherCodeIcon(d.weatherCode);
        currentDesc = weatherCodeLabel(d.weatherCode);
      }
    }

    String minMax = '';
    if (weather.daily.isNotEmpty) {
      final d = weather.daily.first;
      minMax = '↑ ${d.tempMax.toStringAsFixed(0)}°  ↓ ${d.tempMin.toStringAsFixed(0)}°';
    }

    return Column(children: [
      Text(city, style: const TextStyle(
        color: Colors.white, fontSize: 26,
        fontWeight: FontWeight.w300, letterSpacing: 1)),
      Text(dateStr, style: const TextStyle(color: Colors.white60, fontSize: 13)),
      const SizedBox(height: 12),
      Row(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(currentIcon, style: const TextStyle(fontSize: 64)),
          const SizedBox(width: 8),
          Text('$currentTemp°', style: const TextStyle(
            color: Colors.white, fontSize: 80,
            fontWeight: FontWeight.w200, height: 1)),
        ],
      ),
      Text(currentDesc, style: const TextStyle(
        color: Colors.white70, fontSize: 16, fontWeight: FontWeight.w400)),
      const SizedBox(height: 4),
      if (minMax.isNotEmpty)
        Text(minMax, style: const TextStyle(color: Colors.white54, fontSize: 13)),
      const SizedBox(height: 14),
      Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          _headerStat(Icons.water_drop_outlined, '$humidity %', 'Humidité'),
          Container(width: 1, height: 28, margin: const EdgeInsets.symmetric(horizontal: 24), color: Colors.white24),
          _headerStat(Icons.air, '${wind.toStringAsFixed(0)} km/h', 'Vent'),
        ],
      ),
    ]);
  }

  Widget _headerStat(IconData icon, String value, String label) =>
    Row(children: [
      Icon(icon, color: Colors.white60, size: 16),
      const SizedBox(width: 6),
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(value, style: const TextStyle(
          color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500)),
        Text(label, style: const TextStyle(color: Colors.white54, fontSize: 11)),
      ]),
    ]);

  // ── PRÉVISIONS HORAIRES ──────────────────────────────────────────
  Widget _buildHourlySection(WeatherData weather) => _glassCard(
    child: Column(children: [
      _expandableHeader(
        icon: Icons.access_time_outlined,
        title: 'PRÉVISIONS PAR HEURE',
        expanded: _hourlyExpanded,
        onTap: () => setState(() => _hourlyExpanded = !_hourlyExpanded)),
      if (_hourlyExpanded) ..._buildHourlyContent(weather),
    ]),
  );

  List<Widget> _buildHourlyContent(WeatherData weather) {
    if (weather.hourly.isEmpty) return [_emptyState()];
    return [
      const Divider(color: Colors.white12, height: 1),
      SizedBox(
        height: 110,
        child: ListView.builder(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          itemCount: weather.hourly.length,
          itemBuilder: (ctx, i) => _hourlyItem(weather.hourly[i]))),
    ];
  }

  Widget _hourlyItem(HourlyForecast h) {
    String timeStr;
    try { timeStr = DateFormat('HH:mm').format(h.time); }
    catch (_) { timeStr = '${h.time.hour.toString().padLeft(2, '0')}:00'; }
    return Container(
      width: 64,
      margin: const EdgeInsets.symmetric(horizontal: 4),
      decoration: BoxDecoration(
        color: Colors.white10, borderRadius: BorderRadius.circular(12)),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(timeStr, style: const TextStyle(color: Colors.white54, fontSize: 11)),
          const SizedBox(height: 4),
          Text(weatherCodeIcon(h.weatherCode), style: const TextStyle(fontSize: 22)),
          const SizedBox(height: 4),
          Text('${h.temperature.toStringAsFixed(0)}°', style: const TextStyle(
            color: Colors.white, fontWeight: FontWeight.w600, fontSize: 14)),
          if (h.precipitation > 0)
            Text('${h.precipitation.toStringAsFixed(1)} mm',
              style: const TextStyle(color: Color(0xFF7EC8E3), fontSize: 10)),
        ],
      ),
    );
  }

  // ── PRÉVISIONS 7 JOURS ───────────────────────────────────────────
  Widget _buildDailySection(WeatherData weather) => _glassCard(
    child: Column(children: [
      _expandableHeader(
        icon: Icons.calendar_month_outlined,
        title: 'PRÉVISIONS 7 JOURS',
        expanded: _dailyExpanded,
        onTap: () => setState(() => _dailyExpanded = !_dailyExpanded)),
      if (_dailyExpanded) ..._buildDailyContent(weather),
    ]),
  );

  List<Widget> _buildDailyContent(WeatherData weather) {
    if (weather.daily.isEmpty) return [_emptyState()];
    return List.generate(weather.daily.length, (i) => _dailyRow(weather.daily[i], i == 0));
  }

  Widget _dailyRow(DailyForecast d, bool isToday) {
    String dayLabel;
    try {
      final raw = DateFormat('EEEE', 'fr_FR').format(d.date);
      dayLabel = isToday ? "Aujourd'hui" : _capitalize(raw);
    } catch (_) {
      const days = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
      dayLabel = isToday ? "Auj." : days[d.date.weekday % 7];
    }
    const double minR = 15.0, maxR = 45.0;
    final double barStart = ((d.tempMin - minR) / (maxR - minR)).clamp(0.0, 1.0);
    final double barWidth  = ((d.tempMax - d.tempMin) / (maxR - minR)).clamp(0.05, 1.0 - barStart);

    return Column(children: [
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
        child: Row(children: [
          SizedBox(width: 96, child: Text(dayLabel, style: TextStyle(
            color: isToday ? Colors.white : Colors.white70,
            fontSize: 14,
            fontWeight: isToday ? FontWeight.w600 : FontWeight.w400))),
          Text(weatherCodeIcon(d.weatherCode), style: const TextStyle(fontSize: 18)),
          const SizedBox(width: 6),
          SizedBox(
            width: 36,
            child: d.precipitationProbMax > 5
              ? Text('${d.precipitationProbMax.toStringAsFixed(0)} %',
                  style: const TextStyle(color: Color(0xFF7EC8E3), fontSize: 11))
              : const SizedBox()),
          SizedBox(width: 28, child: Text('${d.tempMin.toStringAsFixed(0)}°',
            style: const TextStyle(color: Colors.white38, fontSize: 13))),
          const SizedBox(width: 6),
          Expanded(child: LayoutBuilder(builder: (ctx, constraints) =>
            Container(
              height: 5,
              decoration: BoxDecoration(
                color: Colors.white12, borderRadius: BorderRadius.circular(3)),
              child: Stack(children: [
                Positioned(
                  left: constraints.maxWidth * barStart,
                  width: (constraints.maxWidth * barWidth).clamp(6.0, constraints.maxWidth),
                  top: 0, bottom: 0,
                  child: Container(decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFF5BAFE0), Color(0xFFFF9500)]),
                    borderRadius: BorderRadius.circular(3)))),
              ]),
            ))),
          const SizedBox(width: 6),
          SizedBox(width: 28, child: Text('${d.tempMax.toStringAsFixed(0)}°',
            textAlign: TextAlign.right,
            style: const TextStyle(
              color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600))),
        ]),
      ),
      if (!isToday || d != (_weather?.daily.last))
        const Divider(color: Colors.white10, height: 1, indent: 16, endIndent: 16),
    ]);
  }

  // ── TUILES MÉTÉO (2 colonnes max) ────────────────────────────────
  Widget _buildWeatherTiles(WeatherData weather) {
    final cur   = weather.current;
    final today = weather.daily.isNotEmpty ? weather.daily.first : null;

    final uv         = cur?.uvIndex ?? (today?.uvIndexMax.toInt() ?? 0);
    final feelsLike  = cur?.feelsLike ?? (weather.hourly.isNotEmpty ? weather.hourly.first.feelsLike : 0.0);
    final pressure   = cur?.pressure ?? 1013.0;
    final visibility = cur?.visibility ?? 10.0;
    final gusts      = cur?.windGusts ?? 0.0;
    final windSpeed  = cur?.windSpeed ?? (weather.hourly.isNotEmpty ? weather.hourly.first.windSpeed : 0.0);
    final precipToday    = today?.precipitationSum ?? 0.0;
    final precipTomorrow = weather.daily.length > 1 ? weather.daily[1].precipitationSum : 0.0;

    String sunriseStr = '--';
    String sunsetStr  = '--';
    if (today?.sunrise != null) {
      try { sunriseStr = DateFormat('HH:mm').format(today!.sunrise!); } catch (_) {}
    }
    if (today?.sunset != null) {
      try { sunsetStr = DateFormat('HH:mm').format(today!.sunset!); } catch (_) {}
    }

    // Toutes les tuiles en 2 colonnes pour éviter le débordement mobile
    return Column(children: [
      Row(children: [
        _appleCard(
          icon: Icons.wb_sunny_outlined, label: 'INDICE UV',
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('$uv', style: const TextStyle(
              color: Colors.white, fontSize: 36,
              fontWeight: FontWeight.w200, height: 1.1)),
            Text(uvLabel(uv), style: const TextStyle(
              color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500)),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(3),
              child: Container(
                height: 5,
                decoration: const BoxDecoration(
                  gradient: LinearGradient(colors: [
                    Color(0xFF4CAF50), Color(0xFFFFEB3B),
                    Color(0xFFFF9800), Color(0xFFF44336), Color(0xFF9C27B0),
                  ])),
                child: Align(
                  alignment: Alignment(((uv / 11.0) * 2 - 1).clamp(-1.0, 1.0), 0),
                  child: Container(
                    width: 8, height: 8,
                    decoration: const BoxDecoration(
                      color: Colors.white, shape: BoxShape.circle,
                      boxShadow: [BoxShadow(color: Colors.black38, blurRadius: 2)])),
                ),
              ),
            ),
            const SizedBox(height: 8),
            if (today?.sunset != null)
              Text('Protection jusqu\'à $sunsetStr.',
                style: const TextStyle(color: Colors.white60, fontSize: 12)),
          ]),
        ),
        const SizedBox(width: 10),
        _appleCard(
          icon: Icons.wb_twilight_outlined, label: 'SOLEIL',
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Coucher', style: TextStyle(color: Colors.white60, fontSize: 13)),
            Text(sunsetStr, style: const TextStyle(
              color: Colors.white, fontSize: 36,
              fontWeight: FontWeight.w200, height: 1.1)),
            const SizedBox(height: 8),
            _sunArc(sunriseStr, sunsetStr),
            const SizedBox(height: 6),
            Text('Lever : $sunriseStr', style: const TextStyle(
              color: Colors.white60, fontSize: 12)),
          ]),
        ),
      ]),
      const SizedBox(height: 10),
      Row(children: [
        _appleCard(
          icon: Icons.air, label: 'VENT',
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${windSpeed.toStringAsFixed(0)} km/h', style: const TextStyle(
              color: Colors.white, fontSize: 30,
              fontWeight: FontWeight.w200, height: 1.1)),
            const SizedBox(height: 4),
            if (gusts > 0)
              Text('Rafales : ${gusts.toStringAsFixed(0)} km/h',
                style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500)),
            const SizedBox(height: 8),
            const Text('Vent moyen en surface.',
              style: TextStyle(color: Colors.white60, fontSize: 12)),
          ]),
        ),
        const SizedBox(width: 10),
        _appleCard(
          icon: Icons.water_drop_outlined, label: 'PRÉCIPITATIONS',
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Text('${precipToday.toStringAsFixed(0)}', style: const TextStyle(
                color: Colors.white, fontSize: 36,
                fontWeight: FontWeight.w200, height: 1)),
              const Padding(
                padding: EdgeInsets.only(bottom: 6, left: 3),
                child: Text('mm', style: TextStyle(color: Colors.white70, fontSize: 16))),
            ]),
            const Text("Aujourd'hui", style: TextStyle(
              color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500)),
            const SizedBox(height: 8),
            Text('${precipTomorrow.toStringAsFixed(0)} mm demain.',
              style: const TextStyle(color: Colors.white60, fontSize: 12)),
          ]),
        ),
      ]),
      const SizedBox(height: 10),
      // Ressenti + Pression : 2 colonnes (plus de place pour les chiffres)
      Row(children: [
        _appleCard(
          icon: Icons.thermostat_outlined, label: 'RESSENTI',
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${feelsLike.toStringAsFixed(0)}°', style: const TextStyle(
              color: Colors.white, fontSize: 36,
              fontWeight: FontWeight.w200, height: 1.1)),
            const SizedBox(height: 8),
            Text(
              feelsLike > (cur?.temperature ?? feelsLike)
                ? 'Ressenti plus élevé que la réalité.'
                : 'Similaire à la température réelle.',
              style: const TextStyle(color: Colors.white60, fontSize: 12)),
          ]),
        ),
        const SizedBox(width: 10),
        _appleCard(
          icon: Icons.compress, label: 'PRESSION',
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            // Affichage compact : valeur + unité sur une ligne
            Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Text(pressure.toStringAsFixed(0), style: const TextStyle(
                color: Colors.white, fontSize: 32,
                fontWeight: FontWeight.w200, height: 1.1)),
              const Padding(
                padding: EdgeInsets.only(bottom: 4, left: 4),
                child: Text('hPa', style: TextStyle(color: Colors.white60, fontSize: 13))),
            ]),
            const SizedBox(height: 8),
            Text(
              pressure < 1005 ? 'Pression basse.' :
              pressure > 1020 ? 'Pression haute.' : 'Pression normale.',
              style: const TextStyle(color: Colors.white60, fontSize: 12)),
          ]),
        ),
      ]),
      const SizedBox(height: 10),
      // Visibilité seule sur sa ligne (ou avec une 2e tuile si besoin futur)
      Row(children: [
        _appleCard(
          icon: Icons.visibility_outlined, label: 'VISIBILITÉ',
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Text(visibility.toStringAsFixed(0), style: const TextStyle(
                color: Colors.white, fontSize: 36,
                fontWeight: FontWeight.w200, height: 1.1)),
              const Padding(
                padding: EdgeInsets.only(bottom: 6, left: 4),
                child: Text('km', style: TextStyle(color: Colors.white60, fontSize: 14))),
            ]),
            const SizedBox(height: 8),
            Text(
              visibility >= 10 ? 'Vue parfaitement dégagée.' :
              visibility >= 5  ? 'Visibilité réduite.' : 'Brouillard possible.',
              style: const TextStyle(color: Colors.white60, fontSize: 12)),
          ]),
        ),
        const SizedBox(width: 10),
        // Tuile vide pour équilibrer la grille
        Expanded(child: const SizedBox()),
      ]),
    ]);
  }

  // ── ARC SOLAIRE ──────────────────────────────────────────────────
  Widget _sunArc(String sunriseStr, String sunsetStr) {
    final now     = TimeOfDay.now();
    final nowMins = now.hour * 60 + now.minute;
    int parseMins(String s) {
      final parts = s.split(':');
      if (parts.length != 2) return 0;
      return (int.tryParse(parts[0]) ?? 0) * 60 + (int.tryParse(parts[1]) ?? 0);
    }
    final rise  = parseMins(sunriseStr);
    final set   = parseMins(sunsetStr);
    final total = (set - rise).clamp(1, 1440);
    final prog  = ((nowMins - rise) / total).clamp(0.0, 1.0);
    return SizedBox(
      height: 36,
      child: CustomPaint(painter: _SunArcPainter(progress: prog)),
    );
  }

  // ── SECTION RISQUES SAMCAM ───────────────────────────────────────
  List<Widget> _buildRiskSection(RiskReport r) {
    final isML = r.methodeRisque.toLowerCase().contains('ia') ||
                 r.methodeRisque.toLowerCase().contains('ai') ||
                 r.methodeRisque.toLowerCase().contains('ml') ||
                 r.methodeRisque == 'modele_ml';

    return [
      // Tuiles indicateurs
      Row(children: [
        _numericTile(
          icon: Icons.water_drop_outlined,
          value: '${r.indicateurs.pluie7j.toStringAsFixed(0)} mm',
          label: 'Pluie reçue (7j)',
          tooltip: 'Quantité totale de pluie tombée ces 7 derniers jours',
        ),
        const SizedBox(width: 10),
        _numericTile(
          icon: Icons.umbrella_outlined,
          value: '${r.indicateurs.pluiePrevue7j.toStringAsFixed(0)} mm',
          label: 'Pluie prévue (7j)',
          tooltip: 'Précipitations attendues dans les 7 prochains jours',
        ),
        const SizedBox(width: 10),
        _numericTile(
          icon: Icons.eco_outlined,
          value: '${r.indicateurs.etatVegetationEmoji} ${r.indicateurs.etatVegetation}',
          label: 'État végétation',
          tooltip: 'Indice NDVI — mesure la santé et la verdure de la végétation',
          highlight: _vegetationColor(r.indicateurs.ndviMoyen),
        ),
      ]),
      const SizedBox(height: 10),
      // Prévisions J+3 / J+7 — libellés courts pour éviter le débordement
      Row(children: [
        _prevCard('Dans 3 jours', r.prevu3j.niveauGlobal),
        const SizedBox(width: 10),
        _prevCard('Dans 7 jours', r.prevu7j.niveauGlobal),
      ]),
      const SizedBox(height: 10),
      // Barres de risques
      _glassCard(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 6),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                _sectionLabel('RISQUES CLIMATIQUES'),
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: isML
                      ? const Color(0xFFB39DDB).withOpacity(0.18)
                      : Colors.white10,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: isML
                        ? const Color(0xFFB39DDB).withOpacity(0.5)
                        : Colors.white24)),
                  child: Row(children: [
                    Icon(
                      isML ? Icons.auto_awesome_outlined : Icons.rule_outlined,
                      color: isML ? const Color(0xFFB39DDB) : Colors.white38,
                      size: 11),
                    const SizedBox(width: 4),
                    Text(
                      isML ? 'IA + RF' : 'Règles',
                      style: TextStyle(
                        color: isML ? const Color(0xFFB39DDB) : Colors.white38,
                        fontSize: 10, fontWeight: FontWeight.w600)),
                  ]),
                ),
              ]),
              const SizedBox(height: 14),
              _riskBar(
                icon: Icons.water_outlined, label: 'Inondation',
                score: r.actuel.scores.inondation, detail: _floodDetail(r)),
              _riskBar(
                icon: Icons.grass_outlined, label: 'Sécheresse',
                score: r.actuel.scores.secheresse, detail: _droughtDetail(r)),
              _riskBar(
                icon: Icons.local_fire_department_outlined, label: 'Chaleur',
                score: r.actuel.scores.chaleur, detail: _heatDetail(r)),
            ],
          ),
        ),
      ),
      const SizedBox(height: 10),
      // Évolution
      _glassCard(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _sectionLabel('TENDANCE DES RISQUES'),
              const SizedBox(height: 6),
              const Text(
                'Comment les risques évoluent-ils dans les prochains jours ?',
                style: TextStyle(color: Colors.white38, fontSize: 11)),
              const SizedBox(height: 14),
              _riskEvolutionRow(
                'Inondation', Icons.water_outlined,
                r.actuel.scores.inondation, r.prevu3j.scores.inondation, r.prevu7j.scores.inondation,
                _riskColor(r.actuel.scores.inondation)),
              const SizedBox(height: 10),
              _riskEvolutionRow(
                'Sécheresse', Icons.grass_outlined,
                r.actuel.scores.secheresse, r.prevu3j.scores.secheresse, r.prevu7j.scores.secheresse,
                _riskColor(r.actuel.scores.secheresse)),
              const SizedBox(height: 10),
              _riskEvolutionRow(
                'Chaleur', Icons.local_fire_department_outlined,
                r.actuel.scores.chaleur, r.prevu3j.scores.chaleur, r.prevu7j.scores.chaleur,
                _riskColor(r.actuel.scores.chaleur)),
            ],
          ),
        ),
      ),
    ];
  }

  Widget _riskEvolutionRow(String label, IconData icon,
      double now, double j3, double j7, Color color) {
    Widget dot(double v) => Column(children: [
      Text('${(v * 100).toStringAsFixed(0)} %',
        style: TextStyle(
          color: v > 0.01 ? _riskColor(v) : Colors.white38,
          fontSize: 13, fontWeight: FontWeight.w600)),
      const SizedBox(height: 2),
      Container(
        width: 8, height: 8,
        decoration: BoxDecoration(
          color: v > 0.01 ? _riskColor(v) : Colors.white24,
          shape: BoxShape.circle)),
    ]);

    Widget col(String lbl, double v) => Column(children: [
      dot(v),
      const SizedBox(height: 4),
      Text(lbl, style: const TextStyle(color: Colors.white38, fontSize: 10)),
    ]);

    return Row(children: [
      Icon(icon, color: Colors.white38, size: 15),
      const SizedBox(width: 8),
      SizedBox(width: 72,
        child: Text(label, style: const TextStyle(color: Colors.white70, fontSize: 13))),
      Expanded(child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          col('Auj.', now),
          _evolutionArrow(now, j3, color),
          col('J+3', j3),
          _evolutionArrow(j3, j7, color),
          col('J+7', j7),
        ],
      )),
    ]);
  }

  Widget _evolutionArrow(double from, double to, Color color) {
    final diff = to - from;
    if (diff.abs() < 0.02) return const Icon(Icons.remove, color: Colors.white24, size: 14);
    if (diff > 0) return Icon(Icons.trending_up, color: color, size: 14);
    return Icon(Icons.trending_down, color: Colors.greenAccent.shade200, size: 14);
  }

  String _floodDetail(RiskReport r) {
    final p = r.indicateurs.pluie7j;
    if (r.actuel.scores.inondation < 0.05) return 'Pas de risque d\'inondation en ce moment.';
    if (p > 80) return 'Beaucoup de pluie : ${p.toStringAsFixed(0)} mm en 7 jours.';
    return 'Surveillance active des précipitations.';
  }

  String _droughtDetail(RiskReport r) {
    if (r.actuel.scores.secheresse < 0.1) return 'La végétation est bien hydratée.';
    final etat = r.indicateurs.etatVegetation;
    if (r.actuel.scores.secheresse >= 0.5)
      return 'Végétation $etat — le sol manque significativement d\'eau.';
    return 'Végétation $etat — légère sécheresse détectée.';
  }

  String _heatDetail(RiskReport r) {
    final t = r.indicateurs.temperatureMax;
    if (r.actuel.scores.chaleur < 0.05) return 'Températures normales pour la saison.';
    if (t > 35) return 'Attention : ${t.toStringAsFixed(0)}°C relevés, restez à l\'ombre.';
    return 'Températures élevées, pensez à bien vous hydrater.';
  }

  Color _riskColor(double score) {
    if (score < 0.25) return const Color(0xFF66BB6A);
    if (score < 0.50) return const Color(0xFFFFEE58);
    if (score < 0.75) return const Color(0xFFFFB74D);
    return const Color(0xFFEF5350);
  }

  Color _vegetationColor(double ndvi) {
    if (ndvi <= 0.0) return Colors.white38;
    if (ndvi >= 0.5) return const Color(0xFF66BB6A);
    if (ndvi >= 0.3) return const Color(0xFFFFB74D);
    return const Color(0xFFEF5350);
  }

  Widget _appleCard({required IconData icon, required String label, required Widget child}) =>
    Expanded(
      child: Container(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.12),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Colors.white24, width: 0.8)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(icon, color: Colors.white54, size: 13),
              const SizedBox(width: 5),
              Text(label, style: const TextStyle(
                color: Colors.white54, fontSize: 11,
                fontWeight: FontWeight.w600, letterSpacing: 0.6)),
            ]),
            const SizedBox(height: 10),
            child,
          ],
        ),
      ),
    );

  Widget _numericTile({
    required IconData icon,
    required String value,
    required String label,
    Color? highlight,
    String? tooltip,
  }) =>
    Expanded(
      child: Tooltip(
        message: tooltip ?? '',
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(0.12),
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: Colors.white24, width: 0.8)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: highlight ?? Colors.white54, size: 18),
              const SizedBox(height: 10),
              Text(value, style: TextStyle(
                color: highlight ?? Colors.white,
                fontSize: 14, fontWeight: FontWeight.w400, height: 1.2)),
              const SizedBox(height: 4),
              Text(label, style: const TextStyle(
                color: Colors.white54, fontSize: 11)),
            ],
          ),
        ),
      ),
    );

  Widget _riskBar({required IconData icon, required String label,
      required double score, String detail = ''}) {
    final color = _riskColor(score);
    final pct   = (score * 100).toStringAsFixed(0);
    final String levelLabel = score < 0.05 ? 'Nul'
      : score < 0.25 ? 'Faible'
      : score < 0.50 ? 'Modéré'
      : score < 0.75 ? 'Élevé' : 'Critique';
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(icon, color: Colors.white38, size: 15),
            const SizedBox(width: 8),
            SizedBox(width: 80,
              child: Text(label, style: const TextStyle(
                color: Colors.white70, fontSize: 13))),
            Expanded(child: ClipRRect(
              borderRadius: BorderRadius.circular(3),
              child: LinearProgressIndicator(
                value: score.clamp(0.0, 1.0),
                backgroundColor: Colors.white12,
                valueColor: AlwaysStoppedAnimation<Color>(color),
                minHeight: 5))),
            const SizedBox(width: 10),
            SizedBox(
              width: 64,
              child: Text(
                score < 0.05 ? levelLabel : '$levelLabel ($pct %)',
                textAlign: TextAlign.right,
                style: TextStyle(
                  color: score > 0.01 ? color : Colors.white38,
                  fontWeight: FontWeight.w600, fontSize: 11))),
          ]),
          if (detail.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(left: 23, top: 3),
              child: Text(detail, style: const TextStyle(
                color: Colors.white54, fontSize: 11))),
        ],
      ),
    );
  }

  /// Badge dans les cartes J+3 / J+7
  /// Utilise _alertShort() pour un libellé court qui ne déborde pas
  Widget _prevCard(String horizon, String niveau) {
    final color = _alertColor(niveau);
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 14),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.12),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Colors.white24, width: 0.8)),
        child: Row(
          children: [
            Expanded(
              child: Text(horizon,
                style: const TextStyle(
                  color: Colors.white70, fontSize: 13, fontWeight: FontWeight.w500),
                overflow: TextOverflow.ellipsis,
                maxLines: 1)),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: color.withOpacity(0.2),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: color.withOpacity(0.5))),
              // Libellé court : 'Modéré' au lieu de 'Risque modéré'
              child: Text(_alertShort(niveau), style: TextStyle(
                color: color, fontWeight: FontWeight.bold,
                fontSize: 12, letterSpacing: 0.3))),
          ],
        ),
      ),
    );
  }

  Widget _glassCard({required Widget child}) => Container(
    width: double.infinity,
    decoration: BoxDecoration(
      color: Colors.white.withOpacity(0.12),
      borderRadius: BorderRadius.circular(20),
      border: Border.all(color: Colors.white24, width: 0.8)),
    child: ClipRRect(borderRadius: BorderRadius.circular(20), child: child));

  Widget _expandableHeader({
    required IconData icon,
    required String title,
    required bool expanded,
    required VoidCallback onTap,
  }) => InkWell(
    onTap: onTap,
    borderRadius: BorderRadius.circular(20),
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(children: [
        Icon(icon, color: Colors.white54, size: 14),
        const SizedBox(width: 6),
        Text(title, style: const TextStyle(
          color: Colors.white54, fontSize: 11,
          fontWeight: FontWeight.w600, letterSpacing: 0.8)),
        const Spacer(),
        AnimatedRotation(
          turns: expanded ? 0 : -0.25,
          duration: const Duration(milliseconds: 200),
          child: const Icon(Icons.expand_more, color: Colors.white38, size: 18)),
      ])
    ),
  );

  Widget _emptyState() => const Padding(
    padding: EdgeInsets.symmetric(vertical: 16, horizontal: 16),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(Icons.cloud_off_outlined, color: Colors.white38, size: 15),
        SizedBox(width: 8),
        Text('Données indisponibles',
          style: TextStyle(color: Colors.white54, fontSize: 13)),
      ],
    ),
  );

  Widget _sectionLabel(String text) => Text(text,
    style: const TextStyle(
      color: Colors.white54, fontSize: 11,
      fontWeight: FontWeight.w600, letterSpacing: 0.8));

  String _capitalize(String s) => s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
}

class _SunArcPainter extends CustomPainter {
  final double progress;
  const _SunArcPainter({required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white24
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;
    final path = Path();
    path.moveTo(0, size.height);
    path.quadraticBezierTo(
      size.width / 2, -size.height * 0.3, size.width, size.height);
    canvas.drawPath(path, paint);
    final t  = progress.clamp(0.0, 1.0);
    final cx = size.width * t;
    final cy = size.height - (size.height + size.height * 0.3) * 4 * t * (1 - t);
    canvas.drawCircle(
      Offset(cx, cy.clamp(-4.0, size.height + 4.0)), 5,
      Paint()..color = Colors.white);
  }

  @override
  bool shouldRepaint(_SunArcPainter old) => old.progress != progress;
}
