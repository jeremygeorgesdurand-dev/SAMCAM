// Test de fumée : vérifie que l'application démarre sans exception.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:samcam_app/main.dart';

void main() {
  testWidgets('SamcamApp démarre et affiche un MaterialApp', (WidgetTester tester) async {
    await tester.pumpWidget(const SamcamApp());
    await tester.pump();

    expect(find.byType(MaterialApp), findsOneWidget);
  });
}
