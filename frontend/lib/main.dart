import 'package:flutter/material.dart';

import 'screens/general_prompt_screen.dart';

void main() => runApp(const MyApp());

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'PlaNU',
      theme: ThemeData(
        fontFamily: 'Inter',
        fontFamilyFallback: const <String>[
          'Noto Sans KR',
          'Malgun Gothic',
          'Apple SD Gothic Neo',
          'sans-serif',
        ],
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF111111),
        ),
        useMaterial3: true,
      ),
      home: const GeneralPromptScreen(),
    );
  }
}
