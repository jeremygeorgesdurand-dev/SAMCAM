// SAMCAM — Carte schématique du Cameroun avec les zones de surveillance.
//
// Dessinée en CustomPainter (aucune tuile réseau) pour fonctionner
// entièrement hors-ligne. Le contour est un polygone simplifié des
// frontières du pays ; les zones sont projetées en équirectangulaire
// (linéaire lat/lon — la distorsion est négligeable entre 2°N et 13°N).

import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../config.dart';

/// Une zone à afficher sur la carte.
class MapZone {
  final String name;
  final double lat;
  final double lon;
  final String niveauAlerte; // VERT / JAUNE / ORANGE / ROUGE / INCONNU
  const MapZone({
    required this.name,
    required this.lat,
    required this.lon,
    required this.niveauAlerte,
  });
}

/// Contour simplifié du Cameroun, en (lon, lat), sens horaire depuis
/// la pointe nord (lac Tchad).
const List<Offset> _cameroonOutline = [
  Offset(14.06, 13.08), // pointe nord — lac Tchad
  Offset(14.60, 12.90),
  Offset(15.00, 12.10),
  Offset(15.10, 11.70),
  Offset(15.05, 11.00),
  Offset(14.90, 10.50),
  Offset(15.30, 9.90),
  Offset(15.50, 9.30),
  Offset(14.40, 9.00),
  Offset(14.00, 8.50),
  Offset(14.60, 8.00),
  Offset(15.20, 7.50),
  Offset(15.50, 7.00),
  Offset(15.20, 6.50),
  Offset(14.70, 6.00),
  Offset(14.60, 5.00),
  Offset(15.10, 4.50),
  Offset(16.10, 3.50),
  Offset(16.20, 2.80),
  Offset(16.15, 2.20),
  Offset(16.20, 1.70), // coin sud-est (Congo)
  Offset(15.00, 2.00),
  Offset(14.00, 2.20),
  Offset(13.00, 2.16),
  Offset(11.35, 2.30),
  Offset(10.00, 2.17),
  Offset(9.80, 2.30),  // embouchure du Ntem
  Offset(9.90, 3.00),  // côte atlantique
  Offset(9.60, 3.50),
  Offset(9.00, 4.00),
  Offset(8.90, 4.50),
  Offset(8.55, 4.70),  // presqu'île de Bakassi
  Offset(8.80, 5.20),
  Offset(9.40, 6.00),
  Offset(9.80, 6.80),
  Offset(10.60, 7.00), // frontière Nigeria
  Offset(11.00, 6.50),
  Offset(11.50, 6.40),
  Offset(11.90, 7.10),
  Offset(12.20, 7.60),
  Offset(12.40, 8.60),
  Offset(12.80, 9.00),
  Offset(13.20, 9.50),
  Offset(13.30, 10.10),
  Offset(13.60, 10.70),
  Offset(14.00, 11.30),
  Offset(14.20, 12.00),
];

class CameroonMap extends StatelessWidget {
  final List<MapZone> zones;
  final void Function(String zoneName)? onZoneTap;
  final String? selectedZone;

  const CameroonMap({
    super.key,
    required this.zones,
    this.onZoneTap,
    this.selectedZone,
  });

  static String _displayName(String name) =>
      name == 'Yaounde_peri' ? 'Yaoundé' : name;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      final size = Size(constraints.maxWidth, constraints.maxHeight);
      final painter = _CameroonMapPainter(zones, selectedZone);
      return GestureDetector(
        onTapUp: (details) {
          final hit = painter.zoneAt(details.localPosition, size);
          if (hit != null) onZoneTap?.call(hit);
        },
        child: CustomPaint(size: size, painter: painter),
      );
    });
  }
}

class _CameroonMapPainter extends CustomPainter {
  final List<MapZone> zones;
  final String? selectedZone;
  _CameroonMapPainter(this.zones, this.selectedZone);

  // Emprise géographique du contour, avec une petite marge.
  static const double _lonMin = 8.2, _lonMax = 16.6;
  static const double _latMin = 1.4, _latMax = 13.4;

  /// Projette (lat, lon) en pixels, en préservant le ratio d'aspect.
  Offset _project(double lat, double lon, Size size) {
    final geoW = _lonMax - _lonMin;
    final geoH = _latMax - _latMin;
    final scale = math.min(size.width / geoW, size.height / geoH);
    // Centrage dans le widget
    final dx = (size.width - geoW * scale) / 2;
    final dy = (size.height - geoH * scale) / 2;
    return Offset(
      dx + (lon - _lonMin) * scale,
      dy + (_latMax - lat) * scale, // lat croissante vers le haut
    );
  }

  Color _alertColor(String niveau) =>
      Color(Config.alertColors[niveau] ?? Config.alertColors['INCONNU']!);

  @override
  void paint(Canvas canvas, Size size) {
    // ── Contour du pays ────────────────────────────────────────────────
    final path = Path();
    for (int i = 0; i < _cameroonOutline.length; i++) {
      final p = _cameroonOutline[i];
      final pt = _project(p.dy, p.dx, size); // Offset(lon, lat) → (lat, lon)
      if (i == 0) {
        path.moveTo(pt.dx, pt.dy);
      } else {
        path.lineTo(pt.dx, pt.dy);
      }
    }
    path.close();

    canvas.drawPath(
      path,
      Paint()
        ..color = const Color(0xFF1C2530)
        ..style = PaintingStyle.fill,
    );
    canvas.drawPath(
      path,
      Paint()
        ..color = Colors.white24
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.4,
    );

    // ── Marqueurs de zones ─────────────────────────────────────────────
    for (final z in zones) {
      final pt = _project(z.lat, z.lon, size);
      final color = _alertColor(z.niveauAlerte);
      final isSelected = z.name == selectedZone;

      // Halo translucide (plus large si sélectionnée)
      canvas.drawCircle(
        pt,
        isSelected ? 16 : 12,
        Paint()..color = color.withOpacity(0.25),
      );
      // Point plein
      canvas.drawCircle(pt, isSelected ? 8 : 6, Paint()..color = color);
      canvas.drawCircle(
        pt,
        isSelected ? 8 : 6,
        Paint()
          ..color = Colors.white
          ..style = PaintingStyle.stroke
          ..strokeWidth = isSelected ? 2 : 1.2,
      );

      // Étiquette du nom de zone
      final tp = TextPainter(
        text: TextSpan(
          text: CameroonMap._displayName(z.name),
          style: TextStyle(
            color: isSelected ? Colors.white : Colors.white70,
            fontSize: 11,
            fontWeight: isSelected ? FontWeight.w800 : FontWeight.w600,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();

      // Placer l'étiquette à droite du point, sauf si elle déborde.
      double lx = pt.dx + 10;
      if (lx + tp.width > size.width - 4) lx = pt.dx - tp.width - 10;
      tp.paint(canvas, Offset(lx, pt.dy - tp.height / 2));
    }
  }

  /// Retourne le nom de la zone touchée (rayon de 24 px), ou null.
  String? zoneAt(Offset position, Size size) {
    String? best;
    double bestDist = 24; // rayon de tolérance tactile
    for (final z in zones) {
      final pt = _project(z.lat, z.lon, size);
      final d = (pt - position).distance;
      if (d < bestDist) {
        bestDist = d;
        best = z.name;
      }
    }
    return best;
  }

  @override
  bool shouldRepaint(_CameroonMapPainter old) =>
      old.zones != zones || old.selectedZone != selectedZone;
}
