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
  void initState() {
    super.initState();
    _fetchAll();
  }

  Future<void> _fetchAll() async {
    setState(() { _loading = true; _error = null; });

    // Météo en parallèle avec SAMCAM — la météo a toujours un fallback
    final weatherFuture = WeatherService.getForecast();

    try {
      final risk = await ApiService.getRisk();
      final weather = await weatherFuture;
      setState(() {
        _report  = risk;
        _weather = weather;
        _loading = false;
      });
    } catch (e) {
      // Serveur SAMCAM inaccessible mais météo disponible (fallback mocké)
      final weather = await weatherFuture.catchError((_) => WeatherService.getForecast());
      setState(() {
        _weather = weather;
        _error   = 'Serveur SAMCAM inaccessible';
        _loading = false;
      });
    }
  }

  Color _alertColor(String niveau) =>
      Color(Config.alertColors[niveau] ?? Config.alertColors['INCONNU']!);

  String _alertLabel(String niveau) =>
      Config.alertLabels[niveau] ?? niveau;

  LinearGradient _skyGradient() {
    // Heure locale WAT (UTC+1) — fonctionne correctement sur Web
    final h = DateTime.now().toLocal().hour;
    if (h >= 6 && h < 12) {
      return const LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [Color(0xFF1A7FC1), Color(0xFF5BAFE0)],
      );
    } else if (h >= 12 && h < 18) {
      return const LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [Color(0xFF0D5FA3), Color(0xFF4A9FD0)],
      );
    } else if (h >= 18 && h < 21) {
      return const LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [Color(0xFF1A3A6B), Color(0xFFD4721A)],
      );
    } else {
      return const LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [Color(0xFF0A1628), Color(0xFF1A2E4A)],
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('SAMCAM',
          style: TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.bold,
            letterSpacing: 1.5,
            fontSize: 18,
          )),
        actions: [
          IconButton(
            icon: const Icon(Icons.history, color: Colors.white70),
            tooltip: 'Historique',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const HistoryScreen()),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined, color: Colors.white70),
            tooltip: 'Réglages',
            onPressed: () async {
              await Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const SettingsScreen()),
              );
              _fetchAll();
            },
          ),
          IconButton(
            icon: const Icon(Icons.refresh, color: Colors.white70),
            tooltip: 'Actualiser',
            onPressed: _fetchAll,
          ),
        ],
      ),
      body: Container(
        decoration: BoxDecoration(gradient: _skyGradient()),
        child: SafeArea(
          // Sur Web, évite que le contenu soit coupé sous la barre de navigation
          top: true,
          bottom: false,
          child: RefreshIndicator(
            onRefresh: _fetchAll,
            color: Colors.white,
            child: _buildBody(),
          ),
        ),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
        children: [
          _buildSkeletonHeader(),
          const SizedBox(height: 20),
          _buildSkeletonCard(height: 130),
          const SizedBox(height: 12),
          _buildSkeletonCard(height: 220),
        ],
      );
    }

    // Météo disponible (API ou fallback mocké)
    final weather = _weather ?? WeatherData(hourly: [], daily: []);

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      children: [
        _buildWeatherHeader(weather),
        const SizedBox(height: 20),
        _buildHourlySection(weather),
        const SizedBox(height: 12),
        _buildDailySection(weather),
        const SizedBox(height: 20),
        if (_report != null) _buildAlertBanner(_report!),
        if (_error != null) _buildErrorBanner(),
        const SizedBox(height: 12),
        if (_report != null) ..._buildRiskSection(_report!),
      ],
    );
  }

  // ── SQUELETTES DE CHARGEMENT ───────────────────────────────────────────────
  Widget _buildSkeletonHeader() {
    return Column(
      children: [
        _skeletonBox(width: 120, height: 28, radius: 8),
        const SizedBox(height: 8),
        _skeletonBox(width: 80, height: 14, radius: 6),
        const SizedBox(height: 20),
        _skeletonBox(width: 160, height: 80, radius: 12),
        const SizedBox(height: 12),
        _skeletonBox(width: 100, height: 16, radius: 6),
      ],
    );
  }

  Widget _buildSkeletonCard({required double height}) {
    return Container(
      height: height,
      decoration: BoxDecoration(
        color: Colors.white10,
        borderRadius: BorderRadius.circular(20),
      ),
      child: const Center(
        child: CircularProgressIndicator(color: Colors.white30, strokeWidth: 2),
      ),
    );
  }

  Widget _skeletonBox({double? width, required double height, double radius = 4}) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: Colors.white12,
        borderRadius: BorderRadius.circular(radius),
      ),
    );
  }

  // ── EN-TÊTE MÉTÉO ──────────────────────────────────────────────────────────
  Widget _buildWeatherHeader(WeatherData weather) {
    final now  = DateTime.now();
    // Formatage sécurisé — ne plante pas si les locales ne sont pas chargées
    String dateStr;
    try {
      dateStr = DateFormat('EEEE d MMMM', 'fr_FR').format(now);
    } catch (_) {
      dateStr = DateFormat('yyyy-MM-dd').format(now);
    }

    final city = _report?.zone ?? 'Kribi';

    String currentTemp = '--';
    String currentIcon = '🌡️';
    String currentDesc = '';
    int    humidity    = 0;
    double wind        = 0;

    if (weather.hourly.isNotEmpty) {
      final h = weather.hourly.first;
      currentTemp = h.temperature.toStringAsFixed(0);
      currentIcon = weatherCodeIcon(h.weatherCode);
      currentDesc = weatherCodeLabel(h.weatherCode);
      humidity    = h.humidity;
      wind        = h.windSpeed;
    } else if (weather.daily.isNotEmpty) {
      final d = weather.daily.first;
      currentTemp = '${d.tempMin.toStringAsFixed(0)}-${d.tempMax.toStringAsFixed(0)}';
      currentIcon = weatherCodeIcon(d.weatherCode);
      currentDesc = weatherCodeLabel(d.weatherCode);
    }

    return Column(
      children: [
        Text(city,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 26,
            fontWeight: FontWeight.w300,
            letterSpacing: 1,
          )),
        Text(dateStr,
          style: const TextStyle(color: Colors.white60, fontSize: 13)),
        const SizedBox(height: 12),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(currentIcon, style: const TextStyle(fontSize: 64)),
            const SizedBox(width: 8),
            Text('$currentTemp°',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 80,
                fontWeight: FontWeight.w200,
                height: 1,
              )),
          ],
        ),
        Text(currentDesc,
          style: const TextStyle(
            color: Colors.white70,
            fontSize: 16,
            fontWeight: FontWeight.w400,
          )),
        const SizedBox(height: 12),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _headerStat('💧', '$humidity %', 'Humidité'),
            const SizedBox(width: 32),
            _headerStat('💨', '${wind.toStringAsFixed(0)} km/h', 'Vent'),
          ],
        ),
      ],
    );
  }

  Widget _headerStat(String icon, String value, String label) {
    return Column(
      children: [
        Text('$icon $value',
          style: const TextStyle(
            color: Colors.white,
            fontSize: 15,
            fontWeight: FontWeight.w500,
          )),
        Text(label,
          style: const TextStyle(color: Colors.white54, fontSize: 11)),
      ],
    );
  }

  // ── PRÉVISIONS HORAIRES (déroulant) ────────────────────────────────────────
  Widget _buildHourlySection(WeatherData weather) {
    return _glassCard(
      child: Column(
        children: [
          _expandableHeader(
            icon: Icons.access_time,
            title: 'PRÉVISIONS PAR HEURE',
            expanded: _hourlyExpanded,
            onTap: () => setState(() => _hourlyExpanded = !_hourlyExpanded),
          ),
          if (_hourlyExpanded) ..._buildHourlyContent(weather),
        ],
      ),
    );
  }

  List<Widget> _buildHourlyContent(WeatherData weather) {
    if (weather.hourly.isEmpty) {
      return [const Padding(
        padding: EdgeInsets.all(16),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.cloud_off, color: Colors.white38, size: 16),
            SizedBox(width: 8),
            Text('Données indisponibles',
              style: TextStyle(color: Colors.white54, fontSize: 13)),
          ],
        ),
      )];
    }
    return [
      const Divider(color: Colors.white12, height: 1),
      SizedBox(
        height: 110,
        child: ListView.builder(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          itemCount: weather.hourly.length,
          itemBuilder: (ctx, i) => _hourlyItem(weather.hourly[i]),
        ),
      ),
    ];
  }

  Widget _hourlyItem(HourlyForecast h) {
    String timeStr;
    try {
      timeStr = DateFormat('HH:mm').format(h.time);
    } catch (_) {
      timeStr = '${h.time.hour.toString().padLeft(2, '0')}:00';
    }
    return Container(
      width: 64,
      margin: const EdgeInsets.symmetric(horizontal: 4),
      decoration: BoxDecoration(
        color: Colors.white10,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(timeStr,
            style: const TextStyle(color: Colors.white54, fontSize: 11)),
          const SizedBox(height: 4),
          Text(weatherCodeIcon(h.weatherCode),
            style: const TextStyle(fontSize: 22)),
          const SizedBox(height: 4),
          Text('${h.temperature.toStringAsFixed(0)}°',
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w600,
              fontSize: 14,
            )),
          if (h.precipitation > 0)
            Text('${h.precipitation.toStringAsFixed(1)}mm',
              style: const TextStyle(
                color: Color(0xFF7EC8E3),
                fontSize: 10,
              )),
        ],
      ),
    );
  }

  // ── PRÉVISIONS 7 JOURS (déroulant) ─────────────────────────────────────────
  Widget _buildDailySection(WeatherData weather) {
    return _glassCard(
      child: Column(
        children: [
          _expandableHeader(
            icon: Icons.calendar_today,
            title: 'PRÉVISIONS 7 JOURS',
            expanded: _dailyExpanded,
            onTap: () => setState(() => _dailyExpanded = !_dailyExpanded),
          ),
          if (_dailyExpanded) ..._buildDailyContent(weather),
        ],
      ),
    );
  }

  List<Widget> _buildDailyContent(WeatherData weather) {
    if (weather.daily.isEmpty) {
      return [const Padding(
        padding: EdgeInsets.all(16),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.cloud_off, color: Colors.white38, size: 16),
            SizedBox(width: 8),
            Text('Données indisponibles',
              style: TextStyle(color: Colors.white54, fontSize: 13)),
          ],
        ),
      )];
    }
    return List.generate(
      weather.daily.length,
      (i) => _dailyRow(weather.daily[i], i == 0),
    );
  }

  Widget _dailyRow(DailyForecast d, bool isToday) {
    String dayLabel;
    try {
      final raw = DateFormat('EEEE', 'fr_FR').format(d.date);
      dayLabel = isToday ? "Aujourd'hui" : _capitalize(raw);
    } catch (_) {
      final days = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
      dayLabel = isToday ? "Aujourd'hui" : days[d.date.weekday % 7];
    }

    const double minRange = 15.0;
    const double maxRange = 45.0;
    final double barStart =
        ((d.tempMin - minRange) / (maxRange - minRange)).clamp(0.0, 1.0);
    final double barWidth =
        ((d.tempMax - d.tempMin) / (maxRange - minRange)).clamp(0.0, 1.0 - barStart);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(
        children: [
          SizedBox(
            width: 100,
            child: Text(dayLabel,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              )),
          ),
          Text(weatherCodeIcon(d.weatherCode),
            style: const TextStyle(fontSize: 20)),
          const SizedBox(width: 8),
          SizedBox(
            width: 36,
            child: d.precipitationSum > 0
              ? Text('${d.precipitationSum.toStringAsFixed(0)}mm',
                  style: const TextStyle(
                    color: Color(0xFF7EC8E3),
                    fontSize: 11,
                  ))
              : const SizedBox(),
          ),
          SizedBox(
            width: 30,
            child: Text('${d.tempMin.toStringAsFixed(0)}°',
              style: const TextStyle(color: Colors.white54, fontSize: 13)),
          ),
          const SizedBox(width: 4),
          Expanded(
            child: LayoutBuilder(
              builder: (ctx, constraints) {
                return Container(
                  height: 6,
                  decoration: BoxDecoration(
                    color: Colors.white12,
                    borderRadius: BorderRadius.circular(3),
                  ),
                  child: Stack(
                    children: [
                      Positioned(
                        left: constraints.maxWidth * barStart,
                        width: (constraints.maxWidth * barWidth)
                            .clamp(4.0, constraints.maxWidth),
                        top: 0, bottom: 0,
                        child: Container(
                          decoration: BoxDecoration(
                            gradient: const LinearGradient(
                              colors: [Color(0xFF7EC8E3), Color(0xFFFF9500)],
                            ),
                            borderRadius: BorderRadius.circular(3),
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
          const SizedBox(width: 4),
          SizedBox(
            width: 30,
            child: Text('${d.tempMax.toStringAsFixed(0)}°',
              textAlign: TextAlign.right,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              )),
          ),
        ],
      ),
    );
  }

  // ── BANNIÈRE ALERTE SAMCAM ─────────────────────────────────────────────────
  Widget _buildAlertBanner(RiskReport r) {
    final color = _alertColor(r.niveauAlerte);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withOpacity(0.5), width: 1.5),
      ),
      child: Row(
        children: [
          Icon(Icons.warning_amber_rounded, color: color, size: 28),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${r.zone}  •  ${r.date}',
                  style: const TextStyle(color: Colors.white54, fontSize: 11)),
                Text(_alertLabel(r.niveauAlerte),
                  style: TextStyle(
                    color: color,
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  )),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text(r.niveauAlerte,
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
                letterSpacing: 1,
                fontSize: 12,
              )),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorBanner() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: Colors.white10,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.white12),
        ),
        child: Row(
          children: [
            const Icon(Icons.cloud_off, color: Colors.white38, size: 18),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                '${_error ?? 'Serveur SAMCAM inaccessible'} — météo en mode local',
                style: const TextStyle(color: Colors.white54, fontSize: 12),
              ),
            ),
            TextButton(
              onPressed: _fetchAll,
              style: TextButton.styleFrom(padding: EdgeInsets.zero),
              child: const Text('Réessayer',
                style: TextStyle(color: Colors.white70, fontSize: 12)),
            ),
          ],
        ),
      ),
    );
  }

  // ── INDICATEURS & RISQUES SAMCAM ───────────────────────────────────────────
  List<Widget> _buildRiskSection(RiskReport r) {
    return [
      _glassCard(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _sectionLabel('APERÇU DU JOUR'),
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _indicItem('💧', '${r.indicateurs.pluie7j.toStringAsFixed(0)} mm', 'Pluie 7j'),
                  _indicItem('☂️', '${r.indicateurs.pluiePrevue7j.toStringAsFixed(0)} mm', 'Prévue'),
                  _indicItem('🌡️', '${r.indicateurs.temperatureMax.toStringAsFixed(0)}°', 'Temp. max'),
                ],
              ),
            ],
          ),
        ),
      ),
      const SizedBox(height: 12),
      _glassCard(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _sectionLabel('PRÉVISIONS'),
              const SizedBox(height: 12),
              Row(
                children: [
                  _prevCard('J+3', r.prevu3j.niveauGlobal),
                  const SizedBox(width: 10),
                  _prevCard('J+7', r.prevu7j.niveauGlobal),
                ],
              ),
            ],
          ),
        ),
      ),
      const SizedBox(height: 12),
      _glassCard(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _sectionLabel('RISQUES SAMCAM'),
              const SizedBox(height: 12),
              _riskBar('💧 Inondation', r.actuel.scores.inondation, const Color(0xFF1565C0)),
              _riskBar('🌿 Sécheresse', r.actuel.scores.secheresse, const Color(0xFFE65100)),
              _riskBar('🔥 Chaleur',    r.actuel.scores.chaleur,    const Color(0xFFC62828)),
            ],
          ),
        ),
      ),
    ];
  }

  Widget _indicItem(String icon, String value, String label) {
    return Column(
      children: [
        Text(icon, style: const TextStyle(fontSize: 26)),
        const SizedBox(height: 4),
        Text(value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 15,
            fontWeight: FontWeight.w600,
          )),
        Text(label,
          style: const TextStyle(color: Colors.white54, fontSize: 11)),
      ],
    );
  }

  Widget _riskBar(String label, double score, Color color) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label,
                style: const TextStyle(color: Colors.white70, fontSize: 13)),
              Text('${(score * 100).toStringAsFixed(0)}%',
                style: TextStyle(
                  color: color,
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                )),
            ],
          ),
          const SizedBox(height: 6),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: score.clamp(0.0, 1.0),
              backgroundColor: Colors.white12,
              valueColor: AlwaysStoppedAnimation<Color>(color),
              minHeight: 8,
            ),
          ),
        ],
      ),
    );
  }

  Widget _prevCard(String horizon, String niveau) {
    final color = _alertColor(niveau);
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: BoxDecoration(
          color: color.withOpacity(0.15),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withOpacity(0.4)),
        ),
        child: Column(
          children: [
            Text(horizon,
              style: const TextStyle(color: Colors.white54, fontSize: 12)),
            const SizedBox(height: 8),
            Text(niveau,
              style: TextStyle(
                color: color,
                fontWeight: FontWeight.bold,
                fontSize: 16,
                letterSpacing: 1,
              )),
          ],
        ),
      ),
    );
  }

  // ── UTILITAIRES UI ─────────────────────────────────────────────────────────
  Widget _glassCard({required Widget child}) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white24, width: 0.8),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: child,
      ),
    );
  }

  Widget _expandableHeader({
    required IconData icon,
    required String title,
    required bool expanded,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            Icon(icon, color: Colors.white54, size: 14),
            const SizedBox(width: 6),
            Text(title,
              style: const TextStyle(
                color: Colors.white54,
                fontSize: 11,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.8,
              )),
            const Spacer(),
            AnimatedRotation(
              turns: expanded ? 0 : -0.25,
              duration: const Duration(milliseconds: 200),
              child: const Icon(Icons.expand_more,
                color: Colors.white38, size: 18),
            ),
          ],
        ),
      ),
    );
  }

  Widget _sectionLabel(String text) => Text(text,
    style: const TextStyle(
      color: Colors.white54,
      fontSize: 11,
      fontWeight: FontWeight.w600,
      letterSpacing: 0.8,
    ));

  String _capitalize(String s) =>
      s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
}
