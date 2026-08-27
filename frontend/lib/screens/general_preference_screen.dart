import 'package:flutter/material.dart';

import '../models/app_flow_state.dart';
import '../services/planu_api.dart';
import '../widgets/flow_step_badge.dart';
import 'timetable_loading_screen.dart';

class GeneralPreferenceScreen extends StatefulWidget {
  const GeneralPreferenceScreen({
    super.key,
    required this.flow,
    required this.api,
    required this.onSessionExpired,
  });
  final AppFlowState flow;
  final PlanuApi api;
  final VoidCallback onSessionExpired;
  @override
  State<GeneralPreferenceScreen> createState() =>
      _GeneralPreferenceScreenState();
}

class _GeneralPreferenceScreenState extends State<GeneralPreferenceScreen> {
  late final _prompt = TextEditingController(
    text: widget.flow.preferencePrompt,
  );
  String? _promptError;
  String? _areaError;
  static const templates = {
    'balanced': '균형형',
    'free_day_priority': '공강 우선',
    'no_morning_priority': '오전 수업 최소화',
    'compact_schedule': '수업 시간 압축',
  };
  static const electiveAreas = {
    1: '사상과역사',
    2: '사회와문화',
    3: '문학과예술',
    4: '과학과기술',
    5: '건강과레포츠',
    6: '세계와소통',
    7: '융합과창의',
    8: '효원브릿지',
    9: '인성과사회봉사',
  };

  void _submit() {
    widget.flow.preferencePrompt = _prompt.text.trim();
    if (widget.flow.electiveArea == null) {
      setState(() => _areaError = '교양 영역을 선택해 주세요.');
      return;
    }
    if (widget.flow.preferencePrompt.isEmpty) {
      setState(() => _promptError = '교양 조건을 입력해 주세요.');
      return;
    }
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => TimetableLoadingScreen(
          flow: widget.flow,
          api: widget.api,
          onSessionExpired: widget.onSessionExpired,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('교양 조건 및 추천 방식')),
    body: SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              const FlowStepBadge(label: '교양 조건', current: 7),
              const SizedBox(height: 24),
              Text(
                '교양 조건을 알려주세요',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 24),
              TextField(
                controller: _prompt,
                onChanged: (_) {
                  if (_promptError != null) {
                    setState(() => _promptError = null);
                  }
                },
                minLines: 4,
                maxLines: 8,
                decoration: InputDecoration(
                  labelText: '교양 조건',
                  hintText: '금요일은 공강이고 오전 수업은 피하고 싶어요.',
                  errorText: _promptError,
                  border: const OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 20),
              DropdownButtonFormField<int>(
                key: const Key('elective-area-field'),
                initialValue: widget.flow.electiveArea,
                decoration: InputDecoration(
                  labelText: '교양 영역',
                  helperText: '업로드한 수강편람에서 추천받을 교양선택 영역을 선택해 주세요.',
                  errorText: _areaError,
                  border: const OutlineInputBorder(),
                ),
                items: electiveAreas.entries
                    .map(
                      (entry) => DropdownMenuItem(
                        value: entry.key,
                        child: Text(entry.value),
                      ),
                    )
                    .toList(),
                onChanged: (value) {
                  setState(() {
                    widget.flow.electiveArea = value;
                    _areaError = null;
                  });
                },
              ),
              const SizedBox(height: 20),
              DropdownButtonFormField<String>(
                initialValue: widget.flow.selectedTemplate,
                decoration: const InputDecoration(
                  labelText: '추천 템플릿',
                  border: OutlineInputBorder(),
                ),
                items: templates.entries
                    .map(
                      (e) =>
                          DropdownMenuItem(value: e.key, child: Text(e.value)),
                    )
                    .toList(),
                onChanged: (value) => widget.flow.selectedTemplate = value!,
              ),
              const SizedBox(height: 20),
              TextFormField(
                initialValue: '${widget.flow.targetTotalCredits}',
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: '목표 총 학점',
                  border: OutlineInputBorder(),
                ),
                onChanged: (v) => widget.flow.targetTotalCredits =
                    double.tryParse(v) ?? widget.flow.targetTotalCredits,
              ),
              const SizedBox(height: 16),
              TextFormField(
                initialValue: '${widget.flow.additionalElectiveCount}',
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: '추가 교양 과목 수',
                  border: OutlineInputBorder(),
                ),
                onChanged: (v) => widget.flow.additionalElectiveCount =
                    int.tryParse(v) ?? widget.flow.additionalElectiveCount,
              ),
              const SizedBox(height: 24),
              FilledButton(onPressed: _submit, child: const Text('시간표 생성')),
            ],
          ),
        ),
      ),
    ),
  );

  @override
  void dispose() {
    _prompt.dispose();
    super.dispose();
  }
}
