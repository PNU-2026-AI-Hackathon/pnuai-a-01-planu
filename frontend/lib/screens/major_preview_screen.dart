import 'package:flutter/material.dart';
import '../models/major_models.dart';
import '../state/major_flow_controller.dart';
import '../widgets/flow_step_badge.dart';
import 'major_manual_select_screen.dart';

class MajorPreviewScreen extends StatefulWidget {
  const MajorPreviewScreen({
    super.key,
    required this.controller,
    this.onSessionExpired,
    this.onConfirmed,
  });
  final MajorFlowController controller;
  final VoidCallback? onSessionExpired;
  final ValueChanged<MajorConfirmResponse>? onConfirmed;
  @override
  State<MajorPreviewScreen> createState() => _MajorPreviewScreenState();
}

class _MajorPreviewScreenState extends State<MajorPreviewScreen> {
  final _feedback = TextEditingController();
  bool _showFeedback = false;
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_changed);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_changed);
    _feedback.dispose();
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  Future<void> _feedbackSubmit() async {
    if (_feedback.text.trim().isEmpty) return;
    await widget.controller.requestFeedback(_feedback.text);
  }

  Future<void> _confirm() async {
    final ok = await widget.controller.confirm();
    if (!mounted || !ok) return;
    final value = widget.controller.confirmation!;
    widget.onConfirmed?.call(value);
    if (widget.onConfirmed == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('전공 시간표가 확정되었습니다. 다음 교양 선택 단계로 이동해 주세요.')),
      );
    }
  }

  Future<void> _openManualSelection() async {
    await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => MajorManualSelectScreen(
          controller: widget.controller,
          onSessionExpired: widget.onSessionExpired,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final preview = widget.controller.preview!;
    final feedbackBusy =
        widget.controller.state == MajorRequestState.feedbackPreviewing;
    final confirmBusy = widget.controller.state == MajorRequestState.confirming;
    return PopScope(
      canPop: !confirmBusy,
      child: Scaffold(
        backgroundColor: Colors.white,
        appBar: AppBar(
          backgroundColor: Colors.white,
          surfaceTintColor: Colors.white,
          title: const Text('전공 시간표 미리보기'),
        ),
        body: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 960),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(24, 24, 24, 40),
                children: [
                  const FlowStepBadge(label: '전공 검증', current: 5),
                  const SizedBox(height: 24),
                  Text(
                    '이 시간표가 맞습니까?',
                    style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text('요청한 과목과 분반이 올바르게 반영되었는지 확인해 주세요.'),
                  const SizedBox(height: 24),
                  _Summary(preview),
                  const SizedBox(height: 24),
                  Text(
                    '주간 시간표',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 12),
                  _Timetable(entries: preview.timetableEntries),
                  const SizedBox(height: 24),
                  Text(
                    '과목 상세',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 12),
                  if (preview.courses.isEmpty)
                    const _Empty()
                  else
                    ...preview.courses.map(
                      (e) => Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: _CourseCard(e),
                      ),
                    ),
                  _Issues(preview),
                  if (widget.controller.error != null) ...[
                    const SizedBox(height: 16),
                    _ApiErrorCard(
                      error: widget.controller.error!,
                      retryPreview: () => widget.controller.requestPreview(
                        widget.controller.originalPrompt,
                      ),
                      onSessionExpired: widget.onSessionExpired,
                    ),
                  ],
                  const SizedBox(height: 24),
                  OutlinedButton(
                    onPressed: feedbackBusy || confirmBusy
                        ? null
                        : () => setState(() => _showFeedback = !_showFeedback),
                    child: const Text('수정 요청하기'),
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton(
                    key: const Key('majorManualSelectButton'),
                    onPressed: feedbackBusy || confirmBusy
                        ? null
                        : _openManualSelection,
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size.fromHeight(48),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: const Text('직접 선택하기'),
                  ),
                  if (_showFeedback) ...[
                    const SizedBox(height: 12),
                    TextField(
                      key: const Key('majorFeedbackField'),
                      controller: _feedback,
                      onChanged: (_) => setState(() {}),
                      minLines: 3,
                      maxLines: 6,
                      decoration: InputDecoration(
                        hintText: '예: 자료구조를 002분반으로 바꿔 주세요.',
                        filled: true,
                        fillColor: const Color(0xFFF8F9FA),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    OutlinedButton(
                      key: const Key('feedbackSubmitButton'),
                      onPressed: feedbackBusy || _feedback.text.trim().isEmpty
                          ? null
                          : _feedbackSubmit,
                      child: feedbackBusy
                          ? const SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('새 미리보기 생성'),
                    ),
                  ],
                  const SizedBox(height: 12),
                  FilledButton(
                    key: const Key('majorConfirmButton'),
                    onPressed:
                        preview.isConfirmable && !feedbackBusy && !confirmBusy
                        ? _confirm
                        : null,
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF111111),
                      minimumSize: const Size.fromHeight(48),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: confirmBusy
                        ? const SizedBox.square(
                            dimension: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Text('이 시간표로 확정'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Summary extends StatelessWidget {
  const _Summary(this.p);
  final MajorPreviewResponse p;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(24),
    decoration: BoxDecoration(
      color: const Color(0xFFF5F5F5),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Wrap(
      spacing: 32,
      runSpacing: 16,
      children: [
        _Metric('선택된 전공 과목', '${p.courses.length}개'),
        _Metric(
          '전체 전공 학점',
          '${p.totalCredits.toStringAsFixed(p.totalCredits % 1 == 0 ? 0 : 1)}학점',
        ),
        _Metric(
          '시간 충돌',
          p.hasTimeConflict ? '있음' : '없음',
          warning: p.hasTimeConflict,
        ),
      ],
    ),
  );
}

class _Metric extends StatelessWidget {
  const _Metric(this.label, this.value, {this.warning = false});
  final String label, value;
  final bool warning;
  @override
  Widget build(BuildContext context) => SizedBox(
    width: 180,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Color(0xFF6B7280))),
        const SizedBox(height: 4),
        Text(
          value,
          style: TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.w600,
            color: warning ? const Color(0xFFD97706) : const Color(0xFF111111),
          ),
        ),
      ],
    ),
  );
}

class _Timetable extends StatelessWidget {
  const _Timetable({required this.entries});
  final List<MajorCourse> entries;
  static const days = {
    'MON': '월',
    'TUE': '화',
    'WED': '수',
    'THU': '목',
    'FRI': '금',
    'SAT': '토',
  };
  @override
  Widget build(BuildContext context) => Container(
    decoration: BoxDecoration(
      border: Border.all(color: const Color(0xFFE5E7EB)),
      borderRadius: BorderRadius.circular(12),
    ),
    child: SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: days.entries.map((day) {
          final items = entries
              .where((e) => e.classTimes.first.day == day.key)
              .toList();
          return SizedBox(
            width: 150,
            child: Column(
              children: [
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  color: const Color(0xFFF8F9FA),
                  child: Text(
                    day.value,
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                ),
                ...items.map((e) {
                  final t = e.classTimes.first;
                  return Container(
                    width: double.infinity,
                    margin: const EdgeInsets.all(6),
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: const Color(0xFFEFF6FF),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      '${t.start}–${t.end}\n${e.name} ${e.division}',
                      overflow: TextOverflow.visible,
                    ),
                  );
                }),
              ],
            ),
          );
        }).toList(),
      ),
    ),
  );
}

class _CourseCard extends StatelessWidget {
  const _CourseCard(this.course);
  final MajorCourse course;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      color: const Color(0xFFF5F5F5),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          course.name,
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
        Text(
          '분반 ${course.division} · ${course.professor.isEmpty ? '담당 교수 미정' : course.professor} · ${course.credit}학점',
        ),
        ...course.classTimes.map(
          (t) => Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text(
              '${_Timetable.days[t.day] ?? t.day} ${t.start}–${t.end} · ${t.classroom.isEmpty ? '강의실 미정' : t.classroom}',
            ),
          ),
        ),
      ],
    ),
  );
}

class _Empty extends StatelessWidget {
  const _Empty();
  @override
  Widget build(BuildContext context) => const Padding(
    padding: EdgeInsets.symmetric(vertical: 24),
    child: Text('일치하는 전공 과목이 없습니다. 입력을 더 구체적으로 작성해 주세요.'),
  );
}

class _Issues extends StatelessWidget {
  const _Issues(this.p);
  final MajorPreviewResponse p;
  @override
  Widget build(BuildContext context) {
    final cards = <Widget>[];
    if (p.ambiguousCourses.isNotEmpty) {
      cards.add(
        _Warning(
          '과목 또는 분반을 정확히 입력해 주세요.',
          p.ambiguousCourses
              .map(
                (e) =>
                    '${e.reference.courseName}${e.reference.section == null ? '' : ' ${e.reference.section}분반'}',
              )
              .toList(),
        ),
      );
    }
    if (p.unmatchedCourses.isNotEmpty) {
      cards.add(
        _Warning(
          '수강편람에서 다음 과목을 찾지 못했습니다.',
          p.unmatchedCourses.map((e) => e.reference.courseName).toList(),
        ),
      );
    }
    if (p.ambiguousTexts.isNotEmpty) {
      cards.add(
        _Warning('다음 표현을 이해하기 어렵습니다. 더 구체적으로 입력해 주세요.', p.ambiguousTexts),
      );
    }
    if (p.hasTimeConflict) {
      cards.add(
        _Warning(
          '수업 시간이 충돌합니다.',
          p.conflicts
              .map(
                (e) =>
                    '${e.firstCourseId} ↔ ${e.secondCourseId} · ${_Timetable.days[e.day] ?? e.day} ${e.start}–${e.end}',
              )
              .toList(),
        ),
      );
    }
    return Column(
      children: cards
          .map(
            (e) => Padding(padding: const EdgeInsets.only(top: 12), child: e),
          )
          .toList(),
    );
  }
}

class _Warning extends StatelessWidget {
  const _Warning(this.title, this.items);
  final String title;
  final List<String> items;
  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: const Color(0xFFFFFBEB),
      border: Border.all(color: const Color(0xFFF59E0B)),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            fontWeight: FontWeight.w600,
            color: Color(0xFF92400E),
          ),
        ),
        ...items.map((e) => Text('• $e')),
      ],
    ),
  );
}

class _ApiErrorCard extends StatelessWidget {
  const _ApiErrorCard({
    required this.error,
    required this.retryPreview,
    this.onSessionExpired,
  });
  final ApiError error;
  final VoidCallback retryPreview;
  final VoidCallback? onSessionExpired;
  @override
  Widget build(BuildContext context) {
    final messages = {
      'SESSION_NOT_FOUND': '세션이 만료되었습니다. 처음부터 다시 시작해 주세요.',
      'STALE_MAJOR_PREVIEW': '최신 미리보기 결과가 아닙니다. 다시 미리보기를 생성해 주세요.',
      'MAJOR_PREVIEW_NOT_CONFIRMABLE': '현재 결과는 확정할 수 없습니다. 입력 내용을 수정해 주세요.',
      'MAJOR_TIME_CONFLICT': '수업 시간이 충돌하여 확정할 수 없습니다.',
      'INVALID_SESSION_STAGE': '현재 단계에서는 이 작업을 실행할 수 없습니다.',
    };
    final expired = error.code == 'SESSION_NOT_FOUND';
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFFEF2F2),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            messages[error.code] ?? '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.',
            style: const TextStyle(color: Color(0xFFB91C1C)),
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: expired ? onSessionExpired : retryPreview,
            child: Text(expired ? '처음 화면으로 이동' : '다시 시도'),
          ),
        ],
      ),
    );
  }
}
