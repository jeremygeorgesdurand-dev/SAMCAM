// SAMCAM — Endroit personnalisé ajouté par l'utilisateur (nom + coordonnées GPS)

class CustomLocation {
  final String name;
  final double lat;
  final double lon;

  const CustomLocation({required this.name, required this.lat, required this.lon});

  Map<String, dynamic> toJson() => {'name': name, 'lat': lat, 'lon': lon};

  factory CustomLocation.fromJson(Map<String, dynamic> json) => CustomLocation(
        name: json['name'] as String,
        lat: (json['lat'] as num).toDouble(),
        lon: (json['lon'] as num).toDouble(),
      );
}

/// Résultat brut d'une recherche de géocodage (avant confirmation par l'utilisateur).
class GeocodeResult {
  final String shortName;
  final String fullAddress;
  final double lat;
  final double lon;

  const GeocodeResult({
    required this.shortName,
    required this.fullAddress,
    required this.lat,
    required this.lon,
  });

  CustomLocation toCustomLocation() => CustomLocation(name: shortName, lat: lat, lon: lon);
}
