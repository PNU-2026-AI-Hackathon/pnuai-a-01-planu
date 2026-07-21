import 'package:flutter/material.dart';

import 'screens/guide_screen.dart';

void main() {
  runApp(const PlaNUApp());
}

class PlaNUApp extends StatelessWidget {
  const PlaNUApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'PlaNU',
      home: GuideScreen(),
    );
  }
}