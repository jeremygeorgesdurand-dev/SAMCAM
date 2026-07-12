import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';
import '../models/risk_report.dart';
import '../models/weather_forecast.dart';
import '../models/custom_location.dart';
import '../services/api_service.dart';
import '../services/weather_service.dart';
import '../services/notification_service.dart';
import '../services/report_share.dart';
import '../widgets/signalement_sheet.dart';
import '../widgets/weather_animation.dart';
import '../widgets/zone_drawer.dart';
import 'settings_screen.dart';
import 'history_screen.dart';
import 'overview_screen.dart';

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
  String       _cityName = '';
  String       _gpsCity  = '';
  bool _hourlyExpanded = true;
  bool _dailyExpanded  = true;

  /// null = mode GPS automatique ; sinon = zone SAMCAM forcée
  String? _selectedZone;
  /// endroit personnalisé sélectionné (prioritaire sur _selectedZone/GPS)
  CustomLocation? _selectedCustom;

  final _scrollCtrl  = ScrollController();
  final _drawerKey   = GlobalKey<ScaffoldState>();
  double _scrollOffset = 0;

  @override
  void initState() {
    super.initState();
    _loadFavoriteZoneThenFetch();
    _scrollCtrl.addListener(() {
      setState(() => _scrollOffset = _scrollCtrl.offset);
    });
  }

  Future<void> _loadFavoriteZoneThenFetch() async {
    final prefs = await SharedPreferences.getInstance();
    final favorite = prefs.getString(Config.prefFavoriteZone);
    if (favorite != null) _selectedZone = favorite;
    _fetchAll();
  }

  @override
  void dispose() {
    _scrollCtrl.dispose();
    super.dispose();
  }

  // ── Chargement données ────────────────────────────────────────────────────

  Future<void> _fetchAll() async {
    setState(() { _loading = true; _error = null; });
    final custom = _selectedCustom;
    final weatherFuture = custom != null
        ? WeatherService.getForecast(lat: custom.lat, lon: custom.lon)
        : WeatherService.getForecast(zone: _selectedZone);
    final cityFuture = custom != null
        ? Future.value(custom.name)
        : _selectedZone != null
            ? Future.value(_selectedZone!)
            : ApiService.getPosition().then(
                (pos) => WeatherService.getCityName(pos.lat, pos.lon));
    try {
      final risk    = custom != null
          ? await ApiService.getRisk(lat: custom.lat, lon: custom.lon)
          : await ApiService.getRisk(zone: _selectedZone);
      final weather = await weatherFuture;
      final city    = await cityFuture;
      setState(() {
        _report   = risk;
        _weather  = weather;
        _cityName = city;
        if (_selectedZone == null && custom == null) _gpsCity = city;
        _loading  = false;
      });
      NotificationService.checkAndNotify(risk.zone.split(' (').first, risk);
    } catch (e) {
      final weather = await weatherFuture.catchError((_) => WeatherService.getForecast());
      final city    = await cityFuture.catchError((_) async => custom?.name ?? _selectedZone ?? '');
      setState(() {
        _weather  = weather;
        _cityName = city;
        if (_selectedZone == null && custom == null) _gpsCity = city;
        _error    = 'Serveur SAMCAM inaccessible';
        _loading  = false;
      });
    }
  }

  void _onZoneSelected(String zoneName) {
    setState(() {
      _selectedZone   = zoneName;
      _selectedCustom = null;
    });
    _fetchAll();
  }

  void _onCustomLocationSelected(CustomLocation location) {
    setState(() {
      _selectedZone   = null;
      _selectedCustom = location;
    });
    _fetchAll();
  }

  void _onGpsSelected() {
    setState(() {
      _selectedZone   = null;
      _selectedCustom = null;
      _report = null;    // vide l'affichage de l'ancienne zone
      _error  = null;    // efface l'éventuel message d'erreur
    });
    _fetchAll();
  }


  // ── Helpers couleurs / labels ─────────────────────────────────────────────

  Color _alertColor(String niveau) =>
      Color(Config.alertColors[niveau] ?? Config.alertColors['INCONNU']!);

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

  String _alertLabel(String niveau) =>
      Config.alertLabels[niveau] ?? niveau;

  int get _currentCode {
    final cur = _weather?.current;
    if (cur != null) return cur.weatherCode;
    if (_weather?.hourly.isNotEmpty == true) return _weather!.hourly.first.weatherCode;
    return 0;
  }

  bool get _hasAlert => _report != null || _error != null;
  double get _alertBannerHeight => _hasAlert ? 36.0 : 0.0;

  // ── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final hour     = DateTime.now().hour;
    final animType = _loading
        ? (hour < 6 || hour >= 21 ? WeatherAnimType.clearNight : WeatherAnimType.clearDay)
        : weatherAnimTypeFromCode(_currentCode, hour);
    final gradient = weatherGradient(animType);

    return Scaffold(
      key: _drawerKey,
      extendBodyBehindAppBar: true,
      // ── Volet latéral gauche ─────────────────────────────────────────
      drawer: ZoneDrawer(
        currentCity:               _gpsCity,
        selectedZone:              _selectedZone,
        selectedCustomName:        _selectedCustom?.name,
        currentTemp:               _selectedZone == null && _selectedCustom == null
                                        ? _weather?.current?.temperature
                                        : null,
        currentWeatherCode:        _selectedZone == null && _selectedCustom == null
                                        ? _weather?.current?.weatherCode
                                        : null,
        onZoneSelected:            _onZoneSelected,
        onCustomLocationSelected:  _onCustomLocationSelected,
        onCurrentLocationSelected: _onGpsSelected,
      ),
      appBar: _buildAppBar(),
      body: Stack(
        children: [
          AnimatedContainer(
            duration: const Duration(seconds: 2),
            decoration: BoxDecoration(gradient: gradient),
          ),
          LayoutBuilder(builder: (ctx, constraints) {
            final parallaxOffset = _scrollOffset * 0.30;
            return ClipRect(
              child: Transform.translate(
                offset: Offset(0, -parallaxOffset),
                child: WeatherAnimationBg(
                  type:   animType,
                  width:  constraints.maxWidth,
                  height: constraints.maxHeight + parallaxOffset,
                ),
              ),
            );
          }),
          IgnorePointer(
            child: Container(
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.transparent,
                    Colors.transparent,
                    Color(0x660D1A2E),
                    Color(0xAA0D1A2E),
                    Color(0xCC0D1A2E),
                  ],
                  stops: [0.0, 0.45, 0.65, 0.82, 1.0],
                ),
              ),
            ),
          ),
          SafeArea(
            top: true, bottom: false,
            child: RefreshIndicator(
              onRefresh: _fetchAll, color: Colors.white,
              child: _buildBody(animType),
            ),
          ),
        ],
      ),
    );
  }

  PreferredSizeWidget _buildAppBar() {
    return PreferredSize(
      preferredSize: Size.fromHeight(kToolbarHeight + _alertBannerHeight),
      child: Container(
        color: Colors.transparent,
        child: SafeArea(
          bottom: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(
                height: kToolbarHeight,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    const SizedBox(width: 4),
                    // ── Bouton SAMCAM → ouvre le drawer ─────────────
                    TextButton.icon(
                      onPressed: () => _drawerKey.currentState?.openDrawer(),
                      icon: const Icon(
                        Icons.menu,
                        color: Colors.white70,
                        size: 18,
                      ),
                      label: const Text(
                        'SAMCAM',
                        style: TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                          letterSpacing: 1.5,
                          fontSize: 18,
                          shadows: [Shadow(color: Colors.black45, blurRadius: 6)],
                        ),
                      ),
                      style: TextButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        minimumSize: Size.zero,
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        overlayColor: Colors.white12,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8)),
                      ),
                    ),
                    const Spacer(),
                    IconButton(
                      icon: const Icon(Icons.grid_view_rounded, color: Colors.white70),
                      tooltip: "Vue d'ensemble",
                      onPressed: () async {
                        final zone = await Navigator.push<String>(
                          context,
                          MaterialPageRoute(builder: (_) => const OverviewScreen()));
                        if (zone != null) _onZoneSelected(zone);
                      }),
                    IconButton(
                      icon: const Icon(Icons.history, color: Colors.white70),
                      onPressed: () => Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => HistoryScreen(
                          initialZone: _selectedZone ??
                              _report?.zone.split(' (').first,
                        )))),
                    IconButton(
                      icon: const Icon(Icons.settings_outlined, color: Colors.white70),
                      onPressed: () async {
                        await Navigator.push(
                          context,
                          MaterialPageRoute(builder: (_) => const SettingsScreen()));
                        _fetchAll();
                      }),
                    IconButton(
                      icon: const Icon(Icons.refresh, color: Colors.white70),
                      onPressed: _fetchAll),
                  ],
                ),
              ),
              // ── Bannière d'alerte : ligne dédiée pleine largeur sous les
              // icônes (auparavant tassée dans la même ligne → texte tronqué).
              if (_hasAlert)
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
                  child: _buildInlineAlertBanner(),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildInlineAlertBanner() {
    if (_report == null && _error != null) {
      return Container(
        width: double.infinity,
        height: 28,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: Colors.black.withOpacity(0.22),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: Colors.white24, width: 0.8),
        ),
        child: Row(
          children: [
            const Icon(Icons.cloud_off_outlined, color: Colors.white54, size: 12),
            const SizedBox(width: 5),
            Flexible(
              child: Text(
                _error ?? 'Serveur SAMCAM inaccessible',
                style: const TextStyle(color: Colors.white70, fontSize: 11),
                overflow: TextOverflow.ellipsis,
                maxLines: 1,
              ),
            ),
            const SizedBox(width: 6),
            GestureDetector(
              onTap: _fetchAll,
              child: const Text(
                'Réessayer',
                style: TextStyle(
                  color: Colors.white54,
                  fontSize: 11,
                  decoration: TextDecoration.underline,
                ),
              ),
            ),
          ],
        ),
      );
    }

    final r      = _report!;
    final color  = _alertColor(r.niveauAlerte);
    final isOk   = r.niveauAlerte == 'VERT';
    final isInco = r.niveauAlerte == 'INCONNU';
    final bgColor = Color.lerp(
      Colors.black.withOpacity(0.28),
      color.withOpacity(0.30),
      0.35,
    )!;

    return Container(
      width: double.infinity,
      height: 28,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withOpacity(0.45), width: 0.9),
      ),
      child: Row(
        children: [
          Icon(
            isOk
                ? Icons.check_circle_outline
                : isInco
                    ? Icons.help_outline
                    : Icons.warning_amber_rounded,
            color: color,
            size: 13,
          ),
          const SizedBox(width: 5),
          Flexible(
            child: RichText(
              overflow: TextOverflow.ellipsis,
              maxLines: 1,
              text: TextSpan(
                children: [
                  TextSpan(
                    text: _alertLabel(r.niveauAlerte),
                    style: TextStyle(
                      color: color,
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  TextSpan(
                    text: '  •  ${r.zone}  •  ${r.date}',
                    style: const TextStyle(
                      color: Colors.white60,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
              color: color.withOpacity(0.20),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: color.withOpacity(0.70), width: 0.9),
            ),
            child: Text(
              r.niveauAlerte,
              style: TextStyle(
                color: color,
                fontWeight: FontWeight.bold,
                letterSpacing: 0.8,
                fontSize: 10,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBody(WeatherAnimType animType) {
    if (_loading) {
      return ListView(
        controller: _scrollCtrl,
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
    final weather = _weather ?? WeatherData(hourly: [], daily: []);
    return ListView(
      controller: _scrollCtrl,
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      children: [
        if (_report?.fromCache == true) _buildOfflineBanner(_report!),
        _buildWeatherHeaderOverlay(weather),
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

  /// Bandeau affiché quand les données proviennent du cache hors-ligne
  /// (réseau indisponible) : indique l'ancienneté de la dernière mise à jour.
  Widget _buildOfflineBanner(RiskReport r) {
    final when = r.cachedAt;
    final quand = when == null
        ? ''
        : ' du ${DateFormat('dd/MM à HH:mm').format(when)}';
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF37474F).withOpacity(0.85),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.white24),
      ),
      child: Row(
        children: [
          const Icon(Icons.cloud_off, color: Colors.white70, size: 16),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Mode hors-ligne — données$quand',
              style: const TextStyle(color: Colors.white70, fontSize: 12),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWeatherHeaderOverlay(WeatherData weather) {
    final now = DateTime.now();
    String dateStr;
    try { dateStr = DateFormat('EEEE d MMMM', 'fr_FR').format(now); }
    catch (_) { dateStr = DateFormat('yyyy-MM-dd').format(now); }

    final city = _cityName.isNotEmpty ? _cityName : (_report?.zone ?? 'Kribi');
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
    if (weather.hourly.isNotEmpty && cur == null) {
      final h = weather.hourly.first;
      currentTemp = h.temperature.toStringAsFixed(0);
      currentIcon = weatherCodeIcon(h.weatherCode);
      currentDesc = weatherCodeLabel(h.weatherCode);
      humidity    = h.humidity;
      wind        = h.windSpeed;
    } else if (weather.daily.isNotEmpty && cur == null) {
      final d = weather.daily.first;
      currentTemp = d.tempMax.toStringAsFixed(0);
      currentIcon = weatherCodeIcon(d.weatherCode);
      currentDesc = weatherCodeLabel(d.weatherCode);
    }

    String minMax = '';
    if (weather.daily.isNotEmpty) {
      final d = weather.daily.first;
      minMax = '\u2191 ${d.tempMax.toStringAsFixed(0)}\u00b0  \u2193 ${d.tempMin.toStringAsFixed(0)}\u00b0';
    }

    return SizedBox(
      height: 300,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(city, style: const TextStyle(
            color: Colors.white, fontSize: 26,
            fontWeight: FontWeight.w300, letterSpacing: 1.2,
            shadows: [Shadow(color: Colors.black38, blurRadius: 8)])),
          const SizedBox(height: 2),
          Text(dateStr, style: const TextStyle(
            color: Colors.white70, fontSize: 13,
            shadows: [Shadow(color: Colors.black38, blurRadius: 4)])),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(currentIcon, style: const TextStyle(fontSize: 52)),
              const SizedBox(width: 6),
              Text('$currentTemp\u00b0', style: const TextStyle(
                color: Colors.white, fontSize: 80,
                fontWeight: FontWeight.w200, height: 1,
                shadows: [Shadow(color: Colors.black45, blurRadius: 12)])),
            ],
          ),
          const SizedBox(height: 4),
          Text(currentDesc, style: const TextStyle(
            color: Colors.white, fontSize: 17,
            fontWeight: FontWeight.w400,
            shadows: [Shadow(color: Colors.black45, blurRadius: 6)])),
          if (minMax.isNotEmpty) ...[const SizedBox(height: 3),
            Text(minMax, style: const TextStyle(
              color: Colors.white60, fontSize: 13,
              shadows: [Shadow(color: Colors.black38, blurRadius: 4)]))],
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 11),
            decoration: BoxDecoration(
              color: Colors.black.withOpacity(0.20),
              borderRadius: BorderRadius.circular(30),
              border: Border.all(color: Colors.white.withOpacity(0.15)),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.10),
                  blurRadius: 16, spreadRadius: 0),
              ],
            ),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              _headerStat(Icons.water_drop_outlined, '$humidity %', 'Humidité'),
              Container(width: 1, height: 28,
                margin: const EdgeInsets.symmetric(horizontal: 22),
                color: Colors.white.withOpacity(0.20)),
              _headerStat(Icons.air, '${wind.toStringAsFixed(0)} km/h', 'Vent'),
            ]),
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }

  Widget _buildSkeletonHeader() => const SizedBox(
    height: 300,
    child: Center(
      child: CircularProgressIndicator(color: Colors.white30, strokeWidth: 2)));

  Widget _buildSkeletonCard({required double height}) => Container(
    height: height,
    decoration: BoxDecoration(
      color: Colors.white10, borderRadius: BorderRadius.circular(20)),
    child: const Center(
      child: CircularProgressIndicator(color: Colors.white30, strokeWidth: 2)));

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

    final globalMin = weather.daily.map((d) => d.tempMin).reduce((a, b) => a < b ? a : b) - 1;
    final globalMax = weather.daily.map((d) => d.tempMax).reduce((a, b) => a > b ? a : b) + 1;

    return List.generate(
      weather.daily.length,
      (i) => _dailyRow(weather.daily[i], i == 0, globalMin, globalMax),
    );
  }

  Widget _dailyRow(DailyForecast d, bool isToday, double globalMin, double globalMax) {
    String dayLabel;
    try {
      final raw = DateFormat('EEEE', 'fr_FR').format(d.date);
      dayLabel = isToday ? "Aujourd'hui" : _capitalize(raw);
    } catch (_) {
      const days = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
      dayLabel = isToday ? "Auj." : days[d.date.weekday % 7];
    }

    final range    = (globalMax - globalMin).clamp(1.0, double.infinity);
    final barStart = ((d.tempMin - globalMin) / range).clamp(0.0, 1.0);
    final barEnd   = ((d.tempMax - globalMin) / range).clamp(0.0, 1.0);
    final barWidth = (barEnd - barStart).clamp(0.04, 1.0 - barStart);

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

  Widget _buildWeatherTiles(WeatherData weather) {
    final cur   = weather.current;
    final today = weather.daily.isNotEmpty ? weather.daily.first : null;

    final uv         = cur?.uvIndex ?? (today?.uvIndexMax.toInt() ?? 0);
    final feelsLike  = cur?.feelsLike ?? (weather.hourly.isNotEmpty ? weather.hourly.first.feelsLike : 0.0);
    final pressure   = cur?.pressure ?? 1013.0;
    final visibility = cur?.visibility ?? 10.0;
    final gusts      = cur?.windGusts ?? 0.0;
    final windSpeed  = cur?.windSpeed ?? (weather.hourly.isNotEmpty ? weather.hourly.first.windSpeed : 0.0);
    final humidity   = cur?.humidity ?? (weather.hourly.isNotEmpty ? weather.hourly.first.humidity : 0);
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

    return Column(children: [
      IntrinsicHeight(
        child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
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
                Text('Protection jusqu\'\u00e0 $sunsetStr.',
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
      ),
      const SizedBox(height: 10),
      IntrinsicHeight(
        child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
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
      ),
      const SizedBox(height: 10),
      IntrinsicHeight(
        child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
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
      ),
      const SizedBox(height: 10),
      IntrinsicHeight(
        child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
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
          _appleCard(
            icon: Icons.water_drop_outlined, label: 'HUMIDITÉ',
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                Text('$humidity', style: const TextStyle(
                  color: Colors.white, fontSize: 36,
                  fontWeight: FontWeight.w200, height: 1.1)),
                const Padding(
                  padding: EdgeInsets.only(bottom: 6, left: 3),
                  child: Text('%', style: TextStyle(color: Colors.white60, fontSize: 14))),
              ]),
              const SizedBox(height: 8),
              Text(
                humidity >= 80 ? 'Humidité très élevée.' :
                humidity >= 60 ? 'Humidité modérée.' : 'Air relativement sec.',
                style: const TextStyle(color: Colors.white60, fontSize: 12)),
            ]),
          ),
        ]),
      ),
    ]);
  }

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

  List<Widget> _buildRiskSection(RiskReport r) {
    final isML = r.methodeRisque.toLowerCase().contains('ia') ||
                 r.methodeRisque.toLowerCase().contains('ai') ||
                 r.methodeRisque.toLowerCase().contains('ml') ||
                 r.methodeRisque == 'modele_ml';

    return [
      IntrinsicHeight(
        child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
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
        ]),
      ),
      const SizedBox(height: 10),
      _buildPrevCardsGrid(r),
      const SizedBox(height: 10),
      _glassCard(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 6),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                _sectionLabel('RISQUES CLIMATIQUES'),
                const Spacer(),
                // Partage du bulletin en texte (WhatsApp, SMS, e-mail…)
                InkWell(
                  borderRadius: BorderRadius.circular(20),
                  onTap: () => ReportShare.share(r),
                  child: const Padding(
                    padding: EdgeInsets.all(6),
                    child: Icon(Icons.share_outlined,
                      color: Colors.white54, size: 16),
                  ),
                ),
                const SizedBox(width: 4),
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
              _riskTrendChart(r),
            ],
          ),
        ),
      ),
      const SizedBox(height: 10),
      // Signalement communautaire : les observations terrain servent de
      // vérité terrain pour recalibrer les modèles côté serveur.
      OutlinedButton.icon(
        onPressed: () async {
          final zone = r.zone.split(' (').first;
          final sent = await showSignalementSheet(context, zone);
          if (sent == true && mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('Merci ! Votre signalement a été enregistré.'),
                backgroundColor: Color(0xFF01696F),
              ),
            );
          }
        },
        style: OutlinedButton.styleFrom(
          foregroundColor: Colors.white70,
          side: const BorderSide(color: Colors.white24),
          padding: const EdgeInsets.symmetric(vertical: 13),
        ),
        icon: const Icon(Icons.campaign_outlined, size: 18),
        label: const Text('Signaler un événement observé'),
      ),
    ];
  }

  static const _colorInondation = Color(0xFF5BAFE0);
  static const _colorSecheresse = Color(0xFFFFB74D);
  static const _colorChaleur    = Color(0xFFEF5350);

  /// Graphique en courbes de l'évolution des 3 risques sur les horizons
  /// disponibles (aujourd'hui, J+3/J+7/J+10/J+14 selon ce que l'API expose).
  Widget _riskTrendChart(RiskReport r) {
    final horizons = r.horizons;
    if (horizons.length < 2) return const SizedBox.shrink();

    List<FlSpot> spotsFor(double Function(RiskScores) pick) => [
      for (int i = 0; i < horizons.length; i++)
        FlSpot(i.toDouble(), pick(horizons[i].periode.scores) * 100),
    ];

    LineChartBarData line(List<FlSpot> spots, Color color) => LineChartBarData(
      spots: spots,
      isCurved: true,
      curveSmoothness: 0.2,
      color: color,
      barWidth: 2.5,
      dotData: FlDotData(
        show: true,
        getDotPainter: (spot, percent, bar, index) =>
          FlDotCirclePainter(radius: 3.5, color: color, strokeWidth: 0),
      ),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          height: 170,
          child: LineChart(
            LineChartData(
              minY: 0, maxY: 100,
              minX: 0, maxX: (horizons.length - 1).toDouble(),
              gridData: FlGridData(
                show: true, drawVerticalLine: false,
                horizontalInterval: 25,
                getDrawingHorizontalLine: (_) =>
                  const FlLine(color: Colors.white10, strokeWidth: 1),
              ),
              borderData: FlBorderData(show: false),
              titlesData: FlTitlesData(
                topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                leftTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true, reservedSize: 34, interval: 25,
                    getTitlesWidget: (v, meta) => Text('${v.toInt()}%',
                      style: const TextStyle(color: Colors.white38, fontSize: 10)))),
                bottomTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true, reservedSize: 24, interval: 1,
                    getTitlesWidget: (v, meta) {
                      // interval:1 garantit un appel par unité, mais on vérifie quand
                      // même l'entier exact pour éviter tout doublon d'arrondi fl_chart.
                      if (v != v.roundToDouble()) return const SizedBox.shrink();
                      final i = v.round();
                      if (i < 0 || i >= horizons.length) return const SizedBox.shrink();
                      final lbl = horizons[i].label == 'Aujourd\'hui' ? 'Auj.' : horizons[i].label;
                      return Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(lbl, style: const TextStyle(color: Colors.white38, fontSize: 10)));
                    })),
              ),
              lineTouchData: LineTouchData(
                touchTooltipData: LineTouchTooltipData(
                  getTooltipColor: (_) => const Color(0xFF1C2530),
                  getTooltipItems: (spots) => spots.map((s) => LineTooltipItem(
                    '${s.y.toStringAsFixed(0)}%',
                    const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 11)),
                  ).toList(),
                ),
              ),
              lineBarsData: [
                line(spotsFor((s) => s.inondation), _colorInondation),
                line(spotsFor((s) => s.secheresse), _colorSecheresse),
                line(spotsFor((s) => s.chaleur),    _colorChaleur),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _chartLegendItem(_colorInondation, 'Inondation'),
            const SizedBox(width: 18),
            _chartLegendItem(_colorSecheresse, 'Sécheresse'),
            const SizedBox(width: 18),
            _chartLegendItem(_colorChaleur, 'Chaleur'),
          ],
        ),
      ],
    );
  }

  Widget _chartLegendItem(Color color, String label) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Container(width: 8, height: 8,
        decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
      const SizedBox(width: 5),
      Text(label, style: const TextStyle(color: Colors.white60, fontSize: 11)),
    ],
  );

  String _floodDetail(RiskReport r) {
    final p = r.indicateurs.pluie7j;
    if (r.actuel.scores.inondation < 0.05) return "Pas de risque d'inondation en ce moment.";
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

  Widget _headerStat(IconData icon, String value, String label) =>
    Row(children: [
      Icon(icon, color: Colors.white70, size: 16),
      const SizedBox(width: 6),
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(value, style: const TextStyle(
          color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500)),
        Text(label, style: const TextStyle(color: Colors.white54, fontSize: 11)),
      ]),
    ]);

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

  /// Grille 2×2 des cartes de prévision (3j+7j sur une ligne, 10j+14j sur la
  /// suivante) — une seule ligne de 4 cartes serrait trop chaque carte sur un
  /// écran de téléphone (texte tronqué "10 jo…", niveau qui retourne à la ligne).
  Widget _buildPrevCardsGrid(RiskReport r) {
    final futurs = r.horizons.where((h) => h.label != 'Aujourd\'hui').toList();
    final rangees = <Widget>[];
    for (int i = 0; i < futurs.length; i += 2) {
      final paire = futurs.sublist(i, (i + 2 <= futurs.length) ? i + 2 : i + 1);
      if (rangees.isNotEmpty) rangees.add(const SizedBox(height: 10));
      rangees.add(IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (int j = 0; j < paire.length; j++) ...[
              if (j > 0) const SizedBox(width: 10),
              Expanded(
                child: _prevCard(
                  '${paire[j].label.replaceAll('J+', '')} jours',
                  paire[j].periode.niveauGlobal),
              ),
            ],
          ],
        ),
      ));
    }
    return Column(children: rangees);
  }

  Widget _prevCard(String horizon, String niveau) {
    final color = _alertColor(niveau);
    // Empilé (libellé au-dessus du badge) plutôt qu'en ligne : évite toute
    // troncature quel que soit le texte ("3 jours" à "14 jours"). Largeur
    // fournie par le parent (Expanded) — les cartes se répartissent la
    // largeur totale de l'écran au lieu d'être tassées dans un scroll.
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 14),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.12),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white24, width: 0.8)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(horizon,
            style: const TextStyle(
              color: Colors.white70, fontSize: 13, fontWeight: FontWeight.w500),
            overflow: TextOverflow.ellipsis,
            maxLines: 1),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: color.withOpacity(0.2),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: color.withOpacity(0.5))),
            child: Text(_alertShort(niveau),
              overflow: TextOverflow.ellipsis,
              maxLines: 1,
              style: TextStyle(
                color: color, fontWeight: FontWeight.bold,
                fontSize: 12, letterSpacing: 0.3))),
        ],
      ),
    );
  }

  Widget _glassCard({required Widget child}) => Container(
    width: double.infinity,
    decoration: BoxDecoration(
      color: Colors.white.withOpacity(0.10),
      borderRadius: BorderRadius.circular(20),
      border: Border.all(color: Colors.white.withOpacity(0.15), width: 0.8)),
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

// ════════════════════════════════════════════════════════════════
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
