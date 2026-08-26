import 'package:flutter/material.dart';

import '../models/app_flow_state.dart';
import '../models/major_models.dart';
import '../services/planu_api.dart';
import '../services/session_error_handler.dart';
import '../widgets/flow_step_badge.dart';
import '../widgets/timetable_grid.dart';
import 'last_screen.dart';

class TimetableResultScreen extends StatefulWidget {
  const TimetableResultScreen({
    super.key,
    required this.flow,
    required this.api,
    required this.onSessionExpired,
  });

  final AppFlowState flow;
  final PlanuApi api;
  final VoidCallback onSessionExpired;

  @override
  State<TimetableResultScreen> createState() => _TimetableResultScreenState();
}

class _TimetableResultScreenState extends State<TimetableResultScreen> {
  static const _ink = Color(0xFF111111);
  static const _body = Color(0xFF374151);
  static const _muted = Color(0xFF6B7280);
  static const _line = Color(0xFFE5E7EB);
  static const _soft = Color(0xFFF5F5F5);

  int _selectedIndex = 0;
  bool _isSelecting = false;
  String? _selectionError;

  List<Map<String, dynamic>> get _candidates =>
      (widget.flow.rankedCandidates?['ranked_candidates'] as List? ?? const [])
          .whereType<Map>()
          .map((value) => value.cast<String, dynamic>())
          .take(3)
          .toList();

  Map<String, dynamic>? get _selectedCandidate {
    final candidates = _candidates;
    if (candidates.isEmpty) return null;
    return candidates[_selectedIndex.clamp(0, candidates.length - 1)];
  }

  Future<void> _selectCandidate() async {
    final candidate = _selectedCandidate;
    final sessionId = widget.flow.sessionId;
    if (candidate == null || sessionId == null || _isSelecting) return;

    setState(() {
      _isSelecting = true;
      _selectionError = null;
    });

    try {
      final candidateId = _candidateId(candidate);
      if (candidateId == null) {
        setState(() => _selectionError = '후보 ID가 없어 최종 선택을 진행할 수 없습니다.');
        return;
      }
      final response = await widget.api.selectTimetableCandidate(
        sessionId: sessionId,
        candidateId: candidateId,
      );
      final selected = (response['selected_timetable'] as Map?)
          ?.cast<String, dynamic>();
      if (selected == null) {
        throw const ApiError(
          'TIMETABLE_SELECTION_EMPTY',
          '선택된 시간표 정보를 받지 못했습니다.',
        );
      }
      final selectedCandidateId = selected['candidate_id']?.toString();
      if (selectedCandidateId != null && selectedCandidateId != candidateId) {
        throw const ApiError(
          'TIMETABLE_SELECTION_MISMATCH',
          '선택한 시간표와 서버에 저장된 시간표가 일치하지 않습니다.',
        );
      }
      if (!mounted) return;
      final finalCandidate = _candidateForFinalScreen(
        candidate: candidate,
        selected: selected,
      );
      widget.flow.selectedTimetable = finalCandidate;
      widget.flow.rankedCandidates = {
        ...?widget.flow.rankedCandidates,
        'selected_candidate': finalCandidate,
      };
      Navigator.of(context).push(
        MaterialPageRoute<void>(
          settings: const RouteSettings(name: '/timetable-final'),
          builder: (_) => LastScreen(
            flow: widget.flow,
            candidate: finalCandidate,
            onViewCandidates: () => Navigator.of(context).pop(),
            onStartOver: widget.onSessionExpired,
          ),
        ),
      );
    } on ApiError catch (error) {
      if (!mounted) return;
      if (handleSessionExpiredError(
        context,
        error,
        flow: widget.flow,
        onSessionExpired: widget.onSessionExpired,
      )) {
        return;
      }
      setState(() => _selectionError = error.message);
    } finally {
      if (mounted) setState(() => _isSelecting = false);
    }
  }

  void _editConditions() {
    var foundSecondScreen = false;
    Navigator.of(context).popUntil((route) {
      if (route.settings.name == '/second') {
        foundSecondScreen = true;
        return true;
      }
      return route.isFirst;
    });
    if (!foundSecondScreen && Navigator.of(context).canPop()) {
      Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    final selected = _selectedCandidate;

    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        title: const Text('PlaNU'),
        backgroundColor: Colors.white,
        foregroundColor: _ink,
        surfaceTintColor: Colors.white,
        elevation: 0,
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1040),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 28, 24, 36),
              children: [
                const FlowStepBadge(label: '시간표 후보 선택', current: 9),
                const SizedBox(height: 24),
                Text(
                  '추천 시간표 후보를 비교해보세요',
                  style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                    color: _ink,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -1,
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  '서버가 검증하고 정렬한 상위 후보만 보여드립니다. 마음에 드는 시간표를 하나 선택해주세요.',
                  style: TextStyle(color: _body, fontSize: 16, height: 1.5),
                ),
                const SizedBox(height: 24),
                if (selected == null)
                  _EmptyResult(onEditConditions: _editConditions)
                else ...[
                  _CandidateTabs(
                    candidates: _candidates,
                    selected: _selectedIndex,
                    onSelected: (index) => setState(() {
                      _selectedIndex = index;
                      _selectionError = null;
                    }),
                  ),
                  if (_candidates.length < 3) ...[
                    const SizedBox(height: 12),
                    _InfoBanner(
                      message: '현재 조건을 모두 만족하는 시간표는 ${_candidates.length}개입니다.',
                    ),
                  ],
                  const SizedBox(height: 22),
                  _CandidateView(
                    key: ValueKey(
                      _candidateId(selected) ?? _candidateSignature(selected),
                    ),
                    candidate: selected,
                  ),
                  const SizedBox(height: 24),
                  if (_selectionError != null) ...[
                    _ErrorBanner(message: _selectionError!),
                    const SizedBox(height: 12),
                  ],
                  FilledButton(
                    key: const Key('selectTimetableButton'),
                    onPressed: _isSelecting ? null : _selectCandidate,
                    style: FilledButton.styleFrom(
                      backgroundColor: _ink,
                      foregroundColor: Colors.white,
                      minimumSize: const Size.fromHeight(52),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: _isSelecting
                        ? const SizedBox.square(
                            dimension: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Text('이 시간표 선택하기'),
                  ),
                  const SizedBox(height: 10),
                  OutlinedButton(
                    onPressed: _isSelecting ? null : _editConditions,
                    style: OutlinedButton.styleFrom(
                      foregroundColor: _ink,
                      minimumSize: const Size.fromHeight(48),
                      side: const BorderSide(color: _line),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: const Text('조건 수정하기'),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _CandidateTabs extends StatelessWidget {
  const _CandidateTabs({
    required this.candidates,
    required this.selected,
    required this.onSelected,
  });

  final List<Map<String, dynamic>> candidates;
  final int selected;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(6),
    decoration: BoxDecoration(
      color: _TimetableResultScreenState._soft,
      borderRadius: BorderRadius.circular(999),
    ),
    child: Row(
      children: List.generate(candidates.length, (index) {
        final rank = candidates[index]['rank'] ?? index + 1;
        final label = index == 0 ? '$rank순위 · 추천' : '$rank순위';
        return Expanded(
          child: InkWell(
            onTap: () => onSelected(index),
            borderRadius: BorderRadius.circular(8),
            child: Container(
              height: 44,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: selected == index ? Colors.white : Colors.transparent,
                borderRadius: BorderRadius.circular(8),
                border: selected == index
                    ? Border.all(color: _TimetableResultScreenState._line)
                    : null,
              ),
              child: Text(
                label,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: selected == index
                      ? _TimetableResultScreenState._ink
                      : _TimetableResultScreenState._muted,
                ),
              ),
            ),
          ),
        );
      }),
    ),
  );
}

class _CandidateView extends StatelessWidget {
  const _CandidateView({super.key, required this.candidate});

  final Map<String, dynamic> candidate;

  Map<String, dynamic> get timetable =>
      (candidate['timetable'] as Map?)?.cast<String, dynamic>() ?? const {};
  Map<String, dynamic> get load =>
      (candidate['load_satisfaction'] as Map?)?.cast<String, dynamic>() ??
      const {};
  List<Map<String, dynamic>> get schedule =>
      (timetable['schedule_items'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList();
  List<Map<String, dynamic>> get courses =>
      (timetable['courses'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList();
  List<String> get reasons =>
      (timetable['reasons'] as List? ?? const []).whereType<String>().toList();
  List<String> get warnings => [
    ...(timetable['warnings'] as List? ?? const []).whereType<String>(),
    ...(candidate['warnings'] as List? ?? const []).whereType<String>(),
  ];
  List<Map<String, dynamic>> get scoreComponents =>
      (candidate['score_components'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .where(_isUserConditionComponent)
          .toList();

  @override
  Widget build(BuildContext context) {
    final first = _firstClassTime(schedule);
    final last = _lastClassTime(schedule);
    final freeDays = _freeDayLabels(schedule);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _SummaryBand(
          rank: '${candidate['rank'] ?? '-'}',
          score: _score(candidate['raw_score']),
        ),
        const SizedBox(height: 16),
        _MetricGrid(
          totalCredits:
              '${load['final_total_credits'] ?? timetable['total_credit'] ?? '-'}학점',
          freeDays: freeDays.isEmpty ? '공강 없음' : '${freeDays.join(', ')} 공강',
          firstClassTime: first,
          lastClassTime: last,
        ),
        const SizedBox(height: 20),
        _Section(
          title: '주간 시간표',
          child: TimetableGrid(items: schedule),
        ),
        const SizedBox(height: 20),
        _Section(
          title: '수업 정보',
          child: Column(
            children: courses
                .map((course) => _CourseRow(course: course, schedule: schedule))
                .toList(),
          ),
        ),
        if (reasons.isNotEmpty) ...[
          const SizedBox(height: 20),
          _Section(
            title: '추천 이유',
            child: _Bullets(items: reasons, icon: Icons.check_circle_outline),
          ),
        ],
        const SizedBox(height: 20),
        _ConditionStatusBanner(warnings: warnings),
        if (scoreComponents.isNotEmpty) ...[
          const SizedBox(height: 20),
          _Section(
            title: '조건 충족 결과',
            child: Column(
              children: scoreComponents
                  .map((item) => _ScoreComponentRow(item: item))
                  .toList(),
            ),
          ),
        ],
      ],
    );
  }
}

class _SummaryBand extends StatelessWidget {
  const _SummaryBand({required this.rank, required this.score});

  final String rank;
  final String score;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(22),
    decoration: BoxDecoration(
      color: _TimetableResultScreenState._ink,
      borderRadius: BorderRadius.circular(12),
    ),
    child: Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '$rank순위 후보',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 6),
              const Text(
                '현재 선택한 후보의 상세 정보입니다.',
                style: TextStyle(color: Color(0xFFA1A1AA)),
              ),
            ],
          ),
        ),
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            const Text('비교 점수', style: TextStyle(color: Color(0xFFA1A1AA))),
            Text(
              score,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 30,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      ],
    ),
  );
}

class _MetricGrid extends StatelessWidget {
  const _MetricGrid({
    required this.totalCredits,
    required this.freeDays,
    required this.firstClassTime,
    required this.lastClassTime,
  });

  final String totalCredits;
  final String freeDays;
  final String firstClassTime;
  final String lastClassTime;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final width = constraints.maxWidth < 620
          ? (constraints.maxWidth - 12) / 2
          : (constraints.maxWidth - 36) / 4;
      return Wrap(
        spacing: 12,
        runSpacing: 12,
        children: [
          _Metric(
            width: width,
            icon: Icons.school_outlined,
            label: '총 학점',
            value: totalCredits,
          ),
          _Metric(
            width: width,
            icon: Icons.event_available_outlined,
            label: '공강',
            value: freeDays,
          ),
          _Metric(
            width: width,
            icon: Icons.wb_sunny_outlined,
            label: '첫 수업',
            value: firstClassTime,
          ),
          _Metric(
            width: width,
            icon: Icons.nights_stay_outlined,
            label: '마지막 수업',
            value: lastClassTime,
          ),
        ],
      );
    },
  );
}

class _Metric extends StatelessWidget {
  const _Metric({
    required this.width,
    required this.icon,
    required this.label,
    required this.value,
  });

  final double width;
  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: width,
    child: Container(
      constraints: const BoxConstraints(minHeight: 76),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: _TimetableResultScreenState._soft,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(icon, size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  label,
                  style: const TextStyle(
                    color: _TimetableResultScreenState._muted,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  value,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ],
            ),
          ),
        ],
      ),
    ),
  );
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      border: Border.all(color: _TimetableResultScreenState._line),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: Theme.of(
            context,
          ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 16),
        child,
      ],
    ),
  );
}

class _CourseRow extends StatelessWidget {
  const _CourseRow({required this.course, required this.schedule});

  final Map<String, dynamic> course;
  final List<Map<String, dynamic>> schedule;

  @override
  Widget build(BuildContext context) {
    final name = '${course['course_name'] ?? course['name'] ?? ''}';
    final division = '${course['division'] ?? course['section'] ?? ''}';
    final meetings = schedule.where(
      (item) =>
          '${item['course_name']}' == name && '${item['division']}' == division,
    );
    final timeText = meetings
        .map(
          (item) =>
              '${_dayLabel('${item['day']}')} ${item['start']}-${item['end']}',
        )
        .join(' · ');

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14),
      decoration: const BoxDecoration(
        border: Border(
          bottom: BorderSide(color: _TimetableResultScreenState._line),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _CategoryChip(category: '${course['category'] ?? ''}'),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '$name $division'.trim(),
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  [
                    '${course['professor'] ?? ''}',
                    if (timeText.isNotEmpty) timeText,
                    '${course['credit'] ?? course['credits'] ?? 0}학점',
                  ].where((value) => value.trim().isNotEmpty).join(' · '),
                  style: const TextStyle(
                    color: _TimetableResultScreenState._muted,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ScoreComponentRow extends StatelessWidget {
  const _ScoreComponentRow({required this.item});

  final Map<String, dynamic> item;

  @override
  Widget build(BuildContext context) {
    final value = (item['value'] as num?)?.toDouble() ?? 0;
    final text = '${item['reason'] ?? item['label'] ?? ''}';
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 58,
            child: Text(
              value >= 0 ? '+${_score(value)}' : _score(value),
              style: TextStyle(
                color: value >= 0
                    ? const Color(0xFF10B981)
                    : const Color(0xFFEF4444),
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          Expanded(child: Text(text)),
        ],
      ),
    );
  }
}

class _CategoryChip extends StatelessWidget {
  const _CategoryChip({required this.category});

  final String category;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
    decoration: BoxDecoration(
      color: _categoryColor(category),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Text(
      _categoryLabel(category),
      style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
    ),
  );
}

class _Bullets extends StatelessWidget {
  const _Bullets({required this.items, required this.icon});

  final List<String> items;
  final IconData icon;

  @override
  Widget build(BuildContext context) => Column(
    children: items
        .map(
          (item) => Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(icon, size: 18),
                const SizedBox(width: 10),
                Expanded(child: Text(item)),
              ],
            ),
          ),
        )
        .toList(),
  );
}

class _ConditionStatusBanner extends StatelessWidget {
  const _ConditionStatusBanner({required this.warnings});

  final List<String> warnings;

  @override
  Widget build(BuildContext context) {
    final hasWarnings = warnings.isNotEmpty;
    final background = hasWarnings
        ? const Color(0xFFFFFBEB)
        : const Color(0xFFECFDF5);
    final border = hasWarnings
        ? const Color(0xFFF59E0B)
        : const Color(0xFF10B981);
    final foreground = hasWarnings
        ? const Color(0xFF92400E)
        : const Color(0xFF047857);
    final icon = hasWarnings ? Icons.info_outline : Icons.check_circle_outline;
    final messages = hasWarnings
        ? warnings.map(_formatConditionWarning).toList()
        : const ['모든 조건을 만족합니다'];

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: background,
        border: Border.all(color: border),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: messages
            .map(
              (message) => Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(icon, color: foreground, size: 18),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        message,
                        style: TextStyle(
                          color: foreground,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            )
            .toList(),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: const Color(0xFFFEF2F2),
      border: Border.all(color: const Color(0xFFEF4444)),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Text(message, style: const TextStyle(color: Color(0xFF991B1B))),
  );
}

class _InfoBanner extends StatelessWidget {
  const _InfoBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: const Color(0xFFF0F9FF),
      border: Border.all(color: const Color(0xFF38BDF8)),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Text(message, style: const TextStyle(color: Color(0xFF075985))),
  );
}

class _EmptyResult extends StatelessWidget {
  const _EmptyResult({required this.onEditConditions});

  final VoidCallback onEditConditions;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(24),
    decoration: BoxDecoration(
      color: _TimetableResultScreenState._soft,
      borderRadius: BorderRadius.circular(8),
    ),
    child: Column(
      children: [
        const Icon(
          Icons.event_busy_outlined,
          size: 42,
          color: _TimetableResultScreenState._muted,
        ),
        const SizedBox(height: 14),
        const Text('조건에 맞는 추천 후보가 없습니다.'),
        const SizedBox(height: 16),
        OutlinedButton(
          onPressed: onEditConditions,
          child: const Text('조건 수정하기'),
        ),
      ],
    ),
  );
}

// ignore: unused_element
class _FinalTimetableScreen extends StatelessWidget {
  const _FinalTimetableScreen({required this.candidate});

  final Map<String, dynamic> candidate;

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: Colors.white,
    appBar: AppBar(
      title: const Text('PlaNU'),
      backgroundColor: Colors.white,
      foregroundColor: _TimetableResultScreenState._ink,
      surfaceTintColor: Colors.white,
      elevation: 0,
    ),
    body: SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Icon(Icons.event_available_outlined, size: 48),
                const SizedBox(height: 20),
                Text(
                  '${candidate['rank'] ?? ''}순위 시간표를 선택했습니다',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 10),
                const Text(
                  '선택한 후보가 저장되었습니다.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: _TimetableResultScreenState._muted),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

String? _candidateId(Map<String, dynamic> candidate) {
  final direct = candidate['candidate_id'] ?? candidate['id'];
  if (direct is String && direct.trim().isNotEmpty) return direct.trim();
  final timetable = (candidate['timetable'] as Map?)?.cast<String, dynamic>();
  final nested = timetable?['candidate_id'] ?? timetable?['id'];
  if (nested is String && nested.trim().isNotEmpty) return nested.trim();
  return null;
}

Map<String, dynamic> _candidateForFinalScreen({
  required Map<String, dynamic> candidate,
  required Map<String, dynamic> selected,
}) {
  return {
    ...candidate,
    'candidate_id': selected['candidate_id'] ?? candidate['candidate_id'],
    'selection': selected,
    'selected_at': selected['selected_at'],
    'selected_status': selected['status'],
    'selected_section_ids': selected['section_ids'],
    'selected_course_ids': [
      for (final course in selected['courses'] as List? ?? const [])
        if (course is Map && course['course_id'] != null)
          course['course_id'].toString(),
    ],
    'selected_total_credits': selected['total_credits'],
  };
}

String _candidateSignature(Map<String, dynamic> candidate) {
  final timetable = (candidate['timetable'] as Map?)?.cast<String, dynamic>();
  final courses =
      (timetable?['courses'] as List? ?? const []).whereType<Map>().map((
        course,
      ) {
        final value = course.cast<String, dynamic>();
        return '${value['course_id'] ?? value['course_name']}:${value['division'] ?? value['section'] ?? ''}';
      }).toList()..sort();
  return courses.join('|');
}

String _formatConditionWarning(String value) {
  final normalized = value.trim();
  if (normalized.isEmpty) return '조건을 만족하지 못했습니다.';
  if (normalized.contains('금요일') || normalized.contains('FRI')) {
    return '금요일 수업이 포함되어 있어 금요일 공강 조건을 만족하지 못했습니다.';
  }
  if (normalized.contains('10') ||
      normalized.contains('09:') ||
      normalized.contains('9:')) {
    return '10시 이전 수업이 포함되어 있어 10시 이전 수업 제외 조건을 만족하지 못했습니다.';
  }
  if (normalized.endsWith('조건을 만족하지 못했습니다.')) {
    return normalized;
  }
  return '$normalized 조건을 만족하지 못했습니다.';
}

int _minutes(String value) {
  final match = RegExp(r'(\d{1,2})(?::(\d{1,2}))?').firstMatch(value.trim());
  if (match == null) return 0;
  final hour = (int.tryParse(match.group(1) ?? '') ?? 0).clamp(0, 24);
  final minute = hour == 24
      ? 0
      : (int.tryParse(match.group(2) ?? '') ?? 0).clamp(0, 59);
  return hour * 60 + minute;
}

String _formatMinutes(int minutes) =>
    '${(minutes ~/ 60).toString().padLeft(2, '0')}:${(minutes % 60).toString().padLeft(2, '0')}';

String _firstClassTime(List<Map<String, dynamic>> schedule) {
  if (schedule.isEmpty) return '-';
  return _formatMinutes(
    schedule
        .map((item) => _minutes('${item['start']}'))
        .reduce((a, b) => a < b ? a : b),
  );
}

String _lastClassTime(List<Map<String, dynamic>> schedule) {
  if (schedule.isEmpty) return '-';
  return _formatMinutes(
    schedule
        .map((item) => _minutes('${item['end']}'))
        .reduce((a, b) => a > b ? a : b),
  );
}

List<String> _freeDayLabels(List<Map<String, dynamic>> schedule) {
  final occupied = schedule.map((item) => '${item['day']}').toSet();
  return [
    'MON',
    'TUE',
    'WED',
    'THU',
    'FRI',
  ].where((day) => !occupied.contains(day)).map(_dayLabel).toList();
}

String _dayLabel(String value) => switch (value) {
  'MON' => '월',
  'TUE' => '화',
  'WED' => '수',
  'THU' => '목',
  'FRI' => '금',
  'SAT' => '토',
  'SUN' => '일',
  _ => value,
};

String _score(Object? value) {
  final number = (value as num?)?.toDouble() ?? 0;
  return number == number.roundToDouble()
      ? '${number.round()}'
      : number.toStringAsFixed(1);
}

String _categoryLabel(String value) => switch (value) {
  'MAJOR_BASIC' || 'major_basic' || '전공기초' => '전공기초',
  'MAJOR_REQUIRED' || 'major_required' || 'major' || '전공필수' || '전공' => '전공필수',
  'MAJOR_ELECTIVE' || 'major_elective' || '전공선택' => '전공선택',
  'GENERAL_REQUIRED' || 'general_required' || '교양필수' => '교양필수',
  'GENERAL_ELECTIVE' || 'general_elective' || '교양선택' => '교양선택',
  _ => value.isEmpty ? '수업' : value,
};

Color _categoryColor(String value) => switch (value) {
  'MAJOR_BASIC' || 'major_basic' => const Color(0xFFDDE5FF),
  'MAJOR_REQUIRED' || 'major_required' || 'major' => const Color(0xFFDDE5FF),
  'MAJOR_ELECTIVE' || 'major_elective' => const Color(0xFFE0E7FF),
  'GENERAL_REQUIRED' || 'general_required' => const Color(0xFFCCF5E3),
  'GENERAL_ELECTIVE' || 'general_elective' => const Color(0xFFFFE5C7),
  _ => const Color(0xFFF5F5F5),
};

bool _isUserConditionComponent(Map<String, dynamic> item) {
  final key = '${item['key'] ?? ''}';
  return !{
    'valid_candidate',
    'attendance_days',
    'consecutive_classes',
    'daily_first_start',
  }.contains(key);
}
