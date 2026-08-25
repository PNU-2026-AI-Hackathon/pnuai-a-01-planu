import 'package:flutter/material.dart';

import '../models/app_flow_state.dart';

class LastScreen extends StatelessWidget {
  const LastScreen({
    super.key,
    required this.flow,
    required this.candidate,
    required this.onViewCandidates,
    required this.onStartOver,
  });

  final AppFlowState flow;
  final Map<String, dynamic>? candidate;
  final VoidCallback onViewCandidates;
  final VoidCallback onStartOver;

  static const _ink = Color(0xFF111111);
  static const _body = Color(0xFF374151);
  static const _muted = Color(0xFF6B7280);
  static const _line = Color(0xFFE5E7EB);
  static const _soft = Color(0xFFF5F5F5);
  static const _success = Color(0xFF10B981);

  @override
  Widget build(BuildContext context) {
    final selected = candidate;

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
                _Header(candidate: selected),
                const SizedBox(height: 24),
                if (selected == null)
                  _MissingCandidate(onViewCandidates: onViewCandidates)
                else ...[
                  _LastCandidateView(candidate: selected),
                  const SizedBox(height: 24),
                  _EnrollmentNotice(),
                  const SizedBox(height: 24),
                  _BottomActions(
                    onViewCandidates: onViewCandidates,
                    onStartOver: () {
                      flow.reset();
                      onStartOver();
                    },
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

class _Header extends StatelessWidget {
  const _Header({required this.candidate});

  final Map<String, dynamic>? candidate;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: LastScreen._ink,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: const BoxDecoration(
              color: LastScreen._success,
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.check, color: Colors.white),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  candidate == null
                      ? '선택한 시간표 정보가 없습니다'
                      : '최종시간표 확정',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  candidate == null
                      ? '후보 화면으로 돌아가 시간표를 다시 선택해주세요.'
                      : '선택한 후보 1개를 최종 결과로 확인합니다.',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Color(0xFFA1A1AA),
                    fontSize: 14,
                    height: 1.35,
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

class _LastCandidateView extends StatelessWidget {
  const _LastCandidateView({required this.candidate});

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
  List<Map<String, dynamic>> get scoreComponents =>
      (candidate['score_components'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .where(_isUserConditionComponent)
          .toList();
  List<String> get warnings => [
    ...(timetable['warnings'] as List? ?? const []).whereType<String>(),
    ...(candidate['warnings'] as List? ?? const []).whereType<String>(),
  ];

  @override
  Widget build(BuildContext context) {
    final first = _firstClassTime(schedule);
    final last = _lastClassTime(schedule);
    final freeDays = _freeDayLabels(schedule);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
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
          child: _TimetableGrid(items: schedule),
        ),
        const SizedBox(height: 20),
        _Section(
          title: '수강 과목',
          child: courses.isEmpty
              ? const Text('표시할 과목 정보가 없습니다.')
              : Column(
                  children: courses
                      .map(
                        (course) =>
                            _CourseCard(course: course, schedule: schedule),
                      )
                      .toList(),
                ),
        ),
        const SizedBox(height: 20),
        _Section(
          title: '적용 조건',
          child: scoreComponents.isEmpty && warnings.isEmpty
              ? const Text('서버에서 제공한 적용 조건 정보가 없습니다.')
              : Column(
                  children: [
                    ...scoreComponents.map((item) => _ConditionRow(item: item)),
                    ...warnings.map((warning) => _WarningRow(text: warning)),
                  ],
                ),
        ),
      ],
    );
  }
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
          _Metric(width: width, icon: Icons.school_outlined, label: '총 학점', value: totalCredits),
          _Metric(width: width, icon: Icons.event_available_outlined, label: '공강', value: freeDays),
          _Metric(width: width, icon: Icons.wb_sunny_outlined, label: '첫 수업', value: firstClassTime),
          _Metric(width: width, icon: Icons.nights_stay_outlined, label: '마지막 수업', value: lastClassTime),
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
        color: LastScreen._soft,
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
                Text(label, style: const TextStyle(color: LastScreen._muted)),
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
      color: Colors.white,
      border: Border.all(color: LastScreen._line),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 16),
        child,
      ],
    ),
  );
}

class _TimetableGrid extends StatelessWidget {
  const _TimetableGrid({required this.items});

  final List<Map<String, dynamic>> items;

  static const _days = ['MON', 'TUE', 'WED', 'THU', 'FRI'];
  static const _dayLabels = ['월', '화', '수', '목', '금'];
  static const _timeColumnWidth = 52.0;
  static const _dayColumnWidth = 140.0;
  static const _hourHeight = 52.0;
  static const _startHour = 9;
  static const _endHour = 22;
  static const _gridHeight = (_endHour - _startHour) * _hourHeight;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const Text('표시할 시간표 정보가 없습니다.');
    }

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SizedBox(
        width: _timeColumnWidth + _dayColumnWidth * _days.length,
        child: Column(
          children: [
            Row(
              children: [
                const SizedBox(width: _timeColumnWidth),
                for (final day in _dayLabels)
                  SizedBox(
                    width: _dayColumnWidth,
                    height: 32,
                    child: Center(
                      child: Text(
                        day,
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ),
                  ),
              ],
            ),
            const Divider(height: 1),
            SizedBox(
              height: _gridHeight,
              child: Stack(
                children: [
                  for (var hour = _startHour; hour <= _endHour; hour++) ...[
                    Positioned(
                      top: (hour - _startHour) * _hourHeight,
                      left: 0,
                      width: _timeColumnWidth,
                      child: Text(
                        '${hour.toString().padLeft(2, '0')}:00',
                        style: const TextStyle(
                          color: LastScreen._muted,
                          fontSize: 12,
                        ),
                      ),
                    ),
                    Positioned(
                      top: (hour - _startHour) * _hourHeight,
                      left: _timeColumnWidth,
                      right: 0,
                      child: const Divider(height: 1),
                    ),
                  ],
                  for (final item in items)
                    if (_days.contains('${item['day']}'))
                      Positioned(
                        left: _timeColumnWidth +
                            _days.indexOf('${item['day']}') * _dayColumnWidth +
                            4,
                        top: ((_minutes('${item['start']}') - _startHour * 60) /
                                60 *
                                _hourHeight)
                            .clamp(0, _gridHeight - 32)
                            .toDouble(),
                        width: _dayColumnWidth - 8,
                        height: ((_minutes('${item['end']}') -
                                    _minutes('${item['start']}')) /
                                60 *
                                _hourHeight)
                            .clamp(34, 260)
                            .toDouble(),
                        child: _ScheduleBlock(item: item),
                      ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ScheduleBlock extends StatelessWidget {
  const _ScheduleBlock({required this.item});

  final Map<String, dynamic> item;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(7),
    decoration: BoxDecoration(
      color: _categoryColor('${item['category']}'),
      borderRadius: BorderRadius.circular(7),
      border: Border.all(color: Colors.white, width: 1.5),
    ),
    child: Text(
      '${item['course_name'] ?? ''}\n${item['division'] ?? ''} · ${item['classroom'] ?? ''}',
      maxLines: 3,
      overflow: TextOverflow.fade,
      style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
    ),
  );
}

class _CourseCard extends StatelessWidget {
  const _CourseCard({required this.course, required this.schedule});

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
        .map((item) => '${_dayLabel('${item['day']}')} ${item['start']}-${item['end']}')
        .join(' · ');
    final classroomText = meetings
        .map((item) => '${item['classroom'] ?? ''}')
        .where((value) => value.isNotEmpty)
        .join(' · ');

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: LastScreen._line)),
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
                  name,
                  style: const TextStyle(
                    color: LastScreen._ink,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  [
                    if (division.isNotEmpty) '$division분반',
                    '${course['professor'] ?? ''}',
                  ].where((value) => value.trim().isNotEmpty).join(' · '),
                  style: const TextStyle(color: LastScreen._body),
                ),
                if (timeText.isNotEmpty) ...[
                  const SizedBox(height: 5),
                  Text(timeText, style: const TextStyle(color: LastScreen._muted)),
                ],
                const SizedBox(height: 5),
                Text(
                  [
                    classroomText,
                    '${course['credit'] ?? course['credits'] ?? 0}학점',
                  ].where((value) => value.trim().isNotEmpty).join(' · '),
                  style: const TextStyle(color: LastScreen._muted),
                ),
              ],
            ),
          ),
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

class _ConditionRow extends StatelessWidget {
  const _ConditionRow({required this.item});

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
          Icon(
            value >= 0 ? Icons.check_circle_outline : Icons.info_outline,
            size: 18,
            color: value >= 0 ? LastScreen._success : const Color(0xFFF59E0B),
          ),
          const SizedBox(width: 10),
          Expanded(child: Text(text)),
        ],
      ),
    );
  }
}

class _WarningRow extends StatelessWidget {
  const _WarningRow({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Icon(Icons.info_outline, size: 18, color: Color(0xFFF59E0B)),
        const SizedBox(width: 10),
        Expanded(child: Text(text)),
      ],
    ),
  );
}

class _EnrollmentNotice extends StatelessWidget {
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(
      color: const Color(0xFFFFFBEB),
      border: Border.all(color: const Color(0xFFF59E0B)),
      borderRadius: BorderRadius.circular(8),
    ),
    child: const Text(
      '* 실제 수강 가능 여부와 정원은 부산대학교 학생지원시스템 에서 최종확인 해주세요',
      textAlign: TextAlign.start,
      style: TextStyle(color: Color(0xFF92400E), height: 1.45),
    ),
  );
}

class _BottomActions extends StatelessWidget {
  const _BottomActions({
    required this.onViewCandidates,
    required this.onStartOver,
  });

  final VoidCallback onViewCandidates;
  final VoidCallback onStartOver;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      OutlinedButton(
        onPressed: onViewCandidates,
        style: OutlinedButton.styleFrom(
          foregroundColor: LastScreen._ink,
          minimumSize: const Size.fromHeight(48),
          side: const BorderSide(color: LastScreen._line),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
        child: const Text('시간표 후보 다시보기'),
      ),
      const SizedBox(height: 10),
      FilledButton(
        onPressed: onStartOver,
        style: FilledButton.styleFrom(
          backgroundColor: LastScreen._ink,
          foregroundColor: Colors.white,
          minimumSize: const Size.fromHeight(52),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
        child: const Text('새 시간표 만들기'),
      ),
    ],
  );
}

class _MissingCandidate extends StatelessWidget {
  const _MissingCandidate({required this.onViewCandidates});

  final VoidCallback onViewCandidates;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(24),
    decoration: BoxDecoration(
      color: LastScreen._soft,
      borderRadius: BorderRadius.circular(8),
    ),
    child: Column(
      children: [
        const Icon(Icons.event_busy_outlined, size: 42, color: LastScreen._muted),
        const SizedBox(height: 14),
        const Text('최종 시간표로 표시할 후보가 없습니다.'),
        const SizedBox(height: 16),
        OutlinedButton(
          onPressed: onViewCandidates,
          child: const Text('시간표 후보 다시보기'),
        ),
      ],
    ),
  );
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
  return ['MON', 'TUE', 'WED', 'THU', 'FRI']
      .where((day) => !occupied.contains(day))
      .map(_dayLabel)
      .toList();
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
