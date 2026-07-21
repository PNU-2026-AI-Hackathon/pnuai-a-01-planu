import 'package:flutter/material.dart';
import '../models/app_flow_state.dart';
import '../models/major_models.dart';
import '../services/planu_api.dart';
import 'timetable_result_screen.dart';
import '../widgets/flow_step_badge.dart';

class TimetableLoadingScreen extends StatefulWidget {
  const TimetableLoadingScreen({
    super.key,
    required this.flow,
    required this.api,
    required this.onSessionExpired,
  });
  final AppFlowState flow;
  final PlanuApi api;
  final VoidCallback onSessionExpired;
  @override
  State<TimetableLoadingScreen> createState() => _TimetableLoadingScreenState();
}

class _TimetableLoadingScreenState extends State<TimetableLoadingScreen> {
  String _step = '교양 과목 준비 중';
  bool _started = false;
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_started) {
      _started = true;
      _run();
    }
  }

  Future<void> _run() async {
    try {
      final id = widget.flow.sessionId!;
      await widget.api.prepareGeneral(
        sessionId: id,
        electiveArea: widget.flow.electiveArea,
        fileName: widget.flow.electiveCatalogName,
        bytes: widget.flow.electiveCatalogBytes,
      );
      if (!mounted) return;
      setState(() => _step = '시간표 후보 생성 중');
      widget.flow.generatedCandidates = await widget.api.generate(
        sessionId: id,
        prompt: widget.flow.preferencePrompt,
        targetCredits: widget.flow.targetTotalCredits,
        electiveCount: widget.flow.additionalElectiveCount,
      );
      if (!mounted) return;
      setState(() => _step = '추천 순위 계산 중');
      widget.flow.rankedCandidates = await widget.api.rank(
        sessionId: id,
        template: widget.flow.selectedTemplate,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => TimetableResultScreen(
            flow: widget.flow,
            api: widget.api,
            onSessionExpired: widget.onSessionExpired,
          ),
        ),
      );
    } on ApiError catch (e) {
      if (!mounted) return;
      if (e.code == 'SESSION_NOT_FOUND') {
        widget.onSessionExpired();
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.message)));
      Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: false,
    child: Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const FlowStepBadge(label: '시간표 생성', current: 8),
            const SizedBox(height: 24),
            const CircularProgressIndicator(),
            const SizedBox(height: 24),
            Text(_step),
          ],
        ),
      ),
    ),
  );
}
