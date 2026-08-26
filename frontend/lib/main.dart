import 'package:flutter/material.dart';

import 'models/app_flow_state.dart';
import 'screens/chat_home_screen.dart';
import 'screens/guide_screen.dart';
import 'screens/second_screen.dart';
import 'services/planu_api.dart';

void main() => runApp(const PlaNUApp());

class PlaNUApp extends StatefulWidget {
  const PlaNUApp({super.key});

  @override
  State<PlaNUApp> createState() => _PlaNUAppState();
}

class _PlaNUAppState extends State<PlaNUApp> {
  static const _baseUrl = String.fromEnvironment(
    'PLANU_API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  final _navigatorKey = GlobalKey<NavigatorState>();
  final _flow = AppFlowState();
  late final PlanuApi _api = PlanuApi(baseUrl: _baseUrl);

  void _reset() {
    _flow.reset();
    _navigatorKey.currentState?.popUntil((route) => route.isFirst);
  }

  void _openChatHomeScreen(BuildContext context) {
    Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        settings: const RouteSettings(name: '/chat-home'),
        builder: (chatContext) => ChatHomeScreen(
          api: _api,
          onContinue: (data) => _openSecondScreen(chatContext, data),
        ),
      ),
    );
  }

  void _openSecondScreen(BuildContext context, Map<String, dynamic> data) {
    _flow.department = data['selectedDepartment']?.toString() ?? '';
    _flow.sessionId = data['sessionId']?.toString();
    _flow.majorCatalogName = data['parsedCourseCount'] != null
        ? 'uploaded'
        : null;

    final sessionId = _flow.sessionId;
    if (sessionId == null || sessionId.isEmpty) return;

    Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        settings: const RouteSettings(name: '/second'),
        builder: (_) => SecondScreen(
          api: _api,
          selectedDepartment: _flow.department,
          sessionId: sessionId,
          parsedCourseCount: data['parsedCourseCount'] as int? ?? 0,
          catalogWarnings: List<String>.from(
            data['catalogWarnings'] as List<dynamic>? ?? const [],
          ),
          flow: _flow,
          onSessionExpired: _reset,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: _navigatorKey,
      debugShowCheckedModeBanner: false,
      title: 'PlaNU',
      home: Builder(
        builder: (context) =>
            GuideScreen(onNext: () => _openChatHomeScreen(context)),
      ),
    );
  }
}
