import 'package:flutter/material.dart';

import 'screens/guide_screen.dart';

void main() {
  runApp(const PlaNUApp());
}

class PlaNUApp extends StatelessWidget {
  const PlaNUApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'PlaNU',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF111111),
          primary: const Color(0xFF111111),
          surface: Colors.white,
        ),
        scaffoldBackgroundColor: Colors.white,
        useMaterial3: true,
        fontFamily: 'Inter',
        textTheme: const TextTheme(
          headlineLarge: TextStyle(
            color: Color(0xFF111111),
            fontSize: 36,
            fontWeight: FontWeight.w600,
            height: 1.15,
            letterSpacing: -1,
          ),
          titleLarge: TextStyle(
            color: Color(0xFF111111),
            fontSize: 22,
            fontWeight: FontWeight.w600,
            height: 1.3,
            letterSpacing: -0.3,
          ),
          titleMedium: TextStyle(
            color: Color(0xFF111111),
            fontSize: 18,
            fontWeight: FontWeight.w600,
            height: 1.4,
          ),
          bodyLarge: TextStyle(
            color: Color(0xFF374151),
            fontSize: 16,
            height: 1.5,
          ),
          bodyMedium: TextStyle(
            color: Color(0xFF374151),
            fontSize: 14,
            height: 1.5,
          ),
          labelLarge: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            height: 1,
          ),
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFF111111),
            foregroundColor: Colors.white,
            elevation: 0,
            minimumSize: const Size(0, 40),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
          ),
        ),
        outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
            foregroundColor: const Color(0xFF111111),
            minimumSize: const Size(0, 40),
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
            side: const BorderSide(color: Color(0xFFE5E7EB)),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
          ),
        ),
      ),
      home: const GuideScreen(),
    );
  }
}
