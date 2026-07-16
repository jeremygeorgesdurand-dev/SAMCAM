import 'dart:async';
import 'package:flutter/material.dart';
import '../l10n/app_localizations.dart';
import '../widgets/weather_animation.dart';

// ══════════════════════════════════════════════════════════════════════════════
// DemoScreen — Mode démo météo : carousel auto de toutes les conditions
// ══════════════════════════════════════════════════════════════════════════════

class _DemoScenario {
  final String id;
  final String emoji;
  final WeatherAnimType animType;
  final double temperature;
  final double humidity;
  final double wind;
  final double tempMin;
  final double tempMax;
  final Color accentColor;

  const _DemoScenario({
    required this.id,
    required this.emoji,
    required this.animType,
    required this.temperature,
    required this.humidity,
    required this.wind,
    required this.tempMin,
    required this.tempMax,
    required this.accentColor,
  });
}

/// Libellé localisé (titre du scénario), ex. "Ciel dégagé — Jour".
String _scenarioLabel(AppLocalizations t, String id) {
  switch (id) {
    case 'clearDay':      return t.demoScenarioClearDayLabel;
    case 'clearNight':    return t.demoScenarioClearNightLabel;
    case 'partlyCloudy':  return t.demoScenarioPartlyCloudyLabel;
    case 'cloudy':        return t.demoScenarioCloudyLabel;
    case 'lightRain':     return t.demoScenarioLightRainLabel;
    case 'heavyRain':     return t.demoScenarioHeavyRainLabel;
    case 'storm':         return t.demoScenarioStormLabel;
    case 'foggy':         return t.demoScenarioFoggyLabel;
    case 'snow':          return t.demoScenarioSnowLabel;
    default:              return '';
  }
}

/// Description localisée (sous-titre du scénario).
String _scenarioDescription(AppLocalizations t, String id) {
  switch (id) {
    case 'clearDay':      return t.demoScenarioClearDayDescription;
    case 'clearNight':    return t.demoScenarioClearNightDescription;
    case 'partlyCloudy':  return t.demoScenarioPartlyCloudyDescription;
    case 'cloudy':        return t.demoScenarioCloudyDescription;
    case 'lightRain':     return t.demoScenarioLightRainDescription;
    case 'heavyRain':     return t.demoScenarioHeavyRainDescription;
    case 'storm':         return t.demoScenarioStormDescription;
    case 'foggy':         return t.demoScenarioFoggyDescription;
    case 'snow':          return t.demoScenarioSnowDescription;
    default:              return '';
  }
}

/// Nom de condition météo localisé, affiché sous la température.
String _scenarioCondition(AppLocalizations t, String id) {
  switch (id) {
    case 'clearDay':      return t.demoScenarioClearDayCondition;
    case 'clearNight':    return t.demoScenarioClearNightCondition;
    case 'partlyCloudy':  return t.demoScenarioPartlyCloudyCondition;
    case 'cloudy':        return t.demoScenarioCloudyCondition;
    case 'lightRain':     return t.demoScenarioLightRainCondition;
    case 'heavyRain':     return t.demoScenarioHeavyRainCondition;
    case 'storm':         return t.demoScenarioStormCondition;
    case 'foggy':         return t.demoScenarioFoggyCondition;
    case 'snow':          return t.demoScenarioSnowCondition;
    default:              return '';
  }
}

const _scenarios = [
  _DemoScenario(
    id: 'clearDay',
    emoji: '☀️',
    animType: WeatherAnimType.clearDay,
    temperature: 34.0,
    humidity: 42,
    wind: 8,
    tempMin: 26,
    tempMax: 36,
    accentColor: Color(0xFFFFCC30),
  ),
  _DemoScenario(
    id: 'clearNight',
    emoji: '🌙',
    animType: WeatherAnimType.clearNight,
    temperature: 22.0,
    humidity: 58,
    wind: 5,
    tempMin: 20,
    tempMax: 24,
    accentColor: Color(0xFF6688CC),
  ),
  _DemoScenario(
    id: 'partlyCloudy',
    emoji: '⛅',
    animType: WeatherAnimType.partlyCloudyDay,
    temperature: 28.0,
    humidity: 63,
    wind: 14,
    tempMin: 23,
    tempMax: 30,
    accentColor: Color(0xFF4EB3E8),
  ),
  _DemoScenario(
    id: 'cloudy',
    emoji: '☁️',
    animType: WeatherAnimType.cloudy,
    temperature: 24.0,
    humidity: 74,
    wind: 18,
    tempMin: 20,
    tempMax: 26,
    accentColor: Color(0xFF8899AA),
  ),
  _DemoScenario(
    id: 'lightRain',
    emoji: '🌦️',
    animType: WeatherAnimType.lightRain,
    temperature: 21.0,
    humidity: 86,
    wind: 22,
    tempMin: 18,
    tempMax: 23,
    accentColor: Color(0xFF5599CC),
  ),
  _DemoScenario(
    id: 'heavyRain',
    emoji: '🌧️',
    animType: WeatherAnimType.heavyRain,
    temperature: 18.0,
    humidity: 94,
    wind: 35,
    tempMin: 16,
    tempMax: 20,
    accentColor: Color(0xFF4477AA),
  ),
  _DemoScenario(
    id: 'storm',
    emoji: '⛈️',
    animType: WeatherAnimType.storm,
    temperature: 17.0,
    humidity: 97,
    wind: 68,
    tempMin: 15,
    tempMax: 19,
    accentColor: Color(0xFF6655BB),
  ),
  _DemoScenario(
    id: 'foggy',
    emoji: '🌫️',
    animType: WeatherAnimType.foggy,
    temperature: 16.0,
    humidity: 99,
    wind: 4,
    tempMin: 14,
    tempMax: 18,
    accentColor: Color(0xFF99AABB),
  ),
  _DemoScenario(
    id: 'snow',
    emoji: '❄️',
    animType: WeatherAnimType.snow,
    temperature: -2.0,
    humidity: 88,
    wind: 16,
    tempMin: -5,
    tempMax: 1,
    accentColor: Color(0xFFAADDFF),
  ),
];

class DemoScreen extends StatefulWidget {
  const DemoScreen({super.key});

  @override
  State<DemoScreen> createState() => _DemoScreenState();
}

class _DemoScreenState extends State<DemoScreen>
    with TickerProviderStateMixin {
  int    _current   = 0;
  bool   _autoPlay  = true;
  Timer? _timer;
  int    _countdown = 5;
  Timer? _countTimer;

  late AnimationController _fadeCtrl;
  late Animation<double>   _fadeAnim;
  late AnimationController _slideCtrl;
  late Animation<Offset>   _slideAnim;

  final PageController _pageCtrl = PageController();

  @override
  void initState() {
    super.initState();
    _fadeCtrl  = AnimationController(vsync: this, duration: const Duration(milliseconds: 600));
    _fadeAnim  = CurvedAnimation(parent: _fadeCtrl, curve: Curves.easeInOut);
    _slideCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 500));
    _slideAnim = Tween<Offset>(begin: const Offset(0, 0.06), end: Offset.zero)
        .animate(CurvedAnimation(parent: _slideCtrl, curve: Curves.easeOutCubic));
    _fadeCtrl.forward();
    _slideCtrl.forward();
    if (_autoPlay) _startAuto();
  }

  void _startAuto() {
    _timer?.cancel();
    _countTimer?.cancel();
    _countdown = 5;
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _next());
    _countTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _countdown--);
    });
  }

  void _stopAuto() {
    _timer?.cancel();
    _countTimer?.cancel();
    setState(() { _autoPlay = false; _countdown = 0; });
  }

  void _goTo(int idx) {
    if (idx == _current) return;
    setState(() => _current = idx % _scenarios.length);
    _pageCtrl.animateToPage(_current,
        duration: const Duration(milliseconds: 450),
        curve: Curves.easeInOutCubic);
    _fadeCtrl.forward(from: 0);
    _slideCtrl.forward(from: 0);
    if (_autoPlay) {
      setState(() => _countdown = 5);
    }
  }

  void _next() => _goTo(_current + 1);
  void _prev() => _goTo((_current - 1 + _scenarios.length) % _scenarios.length);

  @override
  void dispose() {
    _timer?.cancel();
    _countTimer?.cancel();
    _fadeCtrl.dispose();
    _slideCtrl.dispose();
    _pageCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context)!;
    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      body: Stack(
        children: [
          // ── Fond animé plein écran
          PageView.builder(
            controller: _pageCtrl,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: _scenarios.length,
            itemBuilder: (ctx, i) {
              final s = _scenarios[i];
              return LayoutBuilder(builder: (ctx, constraints) {
                return Container(
                  decoration: BoxDecoration(
                    gradient: weatherGradient(s.animType),
                  ),
                  child: WeatherAnimationBg(
                    type:   s.animType,
                    width:  constraints.maxWidth,
                    height: constraints.maxHeight,
                  ),
                );
              });
            },
          ),

          // ── Dégradé sombre bas de page
          Positioned(
            bottom: 0, left: 0, right: 0,
            child: Container(
              height: 280,
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Colors.transparent, Color(0xCC000000)],
                ),
              ),
            ),
          ),

          // ── Contenu principal
          SafeArea(
            child: Column(
              children: [
                // ── AppBar custom
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: Row(
                    children: [
                      IconButton(
                        icon: const Icon(Icons.arrow_back_ios_new_rounded,
                            color: Colors.white, size: 20),
                        onPressed: () => Navigator.pop(context),
                      ),
                      Expanded(
                        child: Text(t.settingsDemoMode,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.3,
                          )),
                      ),
                      // Bouton auto/pause
                      GestureDetector(
                        onTap: () {
                          if (_autoPlay) {
                            _stopAuto();
                          } else {
                            setState(() => _autoPlay = true);
                            _startAuto();
                          }
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 12, vertical: 6),
                          decoration: BoxDecoration(
                            color: Colors.white.withOpacity(0.12),
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(
                                color: Colors.white.withOpacity(0.25)),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                _autoPlay
                                    ? Icons.pause_rounded
                                    : Icons.play_arrow_rounded,
                                color: Colors.white,
                                size: 16,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                _autoPlay
                                    ? t.demoAutoCountdown('$_countdown')
                                    : t.demoManualLabel,
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 12,
                                    fontWeight: FontWeight.w500),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),

                // ── Infos météo (au centre, animées)
                Expanded(
                  child: FadeTransition(
                    opacity: _fadeAnim,
                    child: SlideTransition(
                      position: _slideAnim,
                      child: _WeatherInfoPanel(scenario: _scenarios[_current]),
                    ),
                  ),
                ),

                // ── Contrôles nav + dots
                _buildControls(),

                // ── Carousel de vignettes
                _buildThumbnails(),

                const SizedBox(height: 12),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildControls() {
    final s = _scenarios[_current];
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          _NavBtn(
            icon: Icons.chevron_left_rounded,
            onTap: () { _stopAuto(); _prev(); },
          ),
          // Dots indicateurs
          Row(
            children: List.generate(_scenarios.length, (i) {
              final active = i == _current;
              return AnimatedContainer(
                duration: const Duration(milliseconds: 250),
                margin: const EdgeInsets.symmetric(horizontal: 3),
                width:  active ? 20 : 6,
                height: 6,
                decoration: BoxDecoration(
                  color: active
                      ? s.accentColor
                      : Colors.white.withOpacity(0.30),
                  borderRadius: BorderRadius.circular(3),
                ),
              );
            }),
          ),
          _NavBtn(
            icon: Icons.chevron_right_rounded,
            onTap: () { _stopAuto(); _next(); },
          ),
        ],
      ),
    );
  }

  Widget _buildThumbnails() {
    return SizedBox(
      height: 72,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: _scenarios.length,
        itemBuilder: (ctx, i) {
          final s = _scenarios[i];
          final active = i == _current;
          return GestureDetector(
            onTap: () { _stopAuto(); _goTo(i); },
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              margin: const EdgeInsets.only(right: 10),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: active
                    ? s.accentColor.withOpacity(0.25)
                    : Colors.white.withOpacity(0.08),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: active
                      ? s.accentColor.withOpacity(0.7)
                      : Colors.white.withOpacity(0.12),
                  width: active ? 1.5 : 1,
                ),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(s.emoji, style: const TextStyle(fontSize: 20)),
                  const SizedBox(height: 2),
                  Text(
                    '${s.temperature.toStringAsFixed(0)}°',
                    style: TextStyle(
                      color: active ? s.accentColor : Colors.white70,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

// ══ Panneau météo principal ══════════════════════════════════════════════════
class _WeatherInfoPanel extends StatelessWidget {
  final _DemoScenario scenario;
  const _WeatherInfoPanel({required this.scenario});

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context)!;
    final s = scenario;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Ville + badge démo
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 10, vertical: 3),
                decoration: BoxDecoration(
                  color: s.accentColor.withOpacity(0.22),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(
                      color: s.accentColor.withOpacity(0.5)),
                ),
                child: Text(
                  t.demoBadgeLabel,
                  style: TextStyle(
                    color: s.accentColor,
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.5,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),

          // Condition
          Text(
            _scenarioLabel(t, s.id),
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.2,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            _scenarioDescription(t, s.id),
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Colors.white.withOpacity(0.65),
              fontSize: 14,
            ),
          ),

          const SizedBox(height: 28),

          // Température grande
          Text(
            '${s.temperature.toStringAsFixed(s.temperature == s.temperature.roundToDouble() ? 0 : 1)}°',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 88,
              fontWeight: FontWeight.w200,
              height: 1.0,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            _scenarioCondition(t, s.id),
            style: TextStyle(
              color: Colors.white.withOpacity(0.80),
              fontSize: 18,
              fontWeight: FontWeight.w400,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '↑ ${s.tempMax.toStringAsFixed(0)}°  ↓ ${s.tempMin.toStringAsFixed(0)}°',
            style: TextStyle(
              color: Colors.white.withOpacity(0.60),
              fontSize: 14,
            ),
          ),

          const SizedBox(height: 28),

          // Stats row
          Container(
            padding: const EdgeInsets.symmetric(
                horizontal: 20, vertical: 14),
            decoration: BoxDecoration(
              color: Colors.black.withOpacity(0.25),
              borderRadius: BorderRadius.circular(18),
              border: Border.all(
                  color: Colors.white.withOpacity(0.12)),
            ),
            child: IntrinsicHeight(
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _StatTile(
                    icon: Icons.water_drop_outlined,
                    value: '${s.humidity.toStringAsFixed(0)} %',
                    label: t.homeHumidityStat,
                    color: s.accentColor,
                  ),
                  VerticalDivider(
                      color: Colors.white.withOpacity(0.15), width: 1),
                  _StatTile(
                    icon: Icons.air_rounded,
                    value: '${s.wind.toStringAsFixed(0)} km/h',
                    label: t.homeWindStat,
                    color: s.accentColor,
                  ),
                  VerticalDivider(
                      color: Colors.white.withOpacity(0.15), width: 1),
                  _StatTile(
                    icon: Icons.thermostat_rounded,
                    value: '${((s.tempMax + s.tempMin) / 2).toStringAsFixed(0)}°',
                    label: t.demoAvgDayLabel,
                    color: s.accentColor,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatTile extends StatelessWidget {
  final IconData icon;
  final String   value;
  final String   label;
  final Color    color;
  const _StatTile({
    required this.icon,
    required this.value,
    required this.label,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, color: color, size: 20),
        const SizedBox(height: 6),
        Text(value,
            style: const TextStyle(
                color: Colors.white,
                fontSize: 15,
                fontWeight: FontWeight.w600)),
        const SizedBox(height: 2),
        Text(label,
            style: TextStyle(
                color: Colors.white.withOpacity(0.55),
                fontSize: 11)),
      ],
    );
  }
}

class _NavBtn extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  const _NavBtn({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.10),
          shape: BoxShape.circle,
          border: Border.all(color: Colors.white.withOpacity(0.20)),
        ),
        child: Icon(icon, color: Colors.white, size: 24),
      ),
    );
  }
}
