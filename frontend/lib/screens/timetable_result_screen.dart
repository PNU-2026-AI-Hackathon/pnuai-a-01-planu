import 'package:flutter/material.dart';

import '../models/app_flow_state.dart';
import '../models/major_models.dart';
import '../services/planu_api.dart';
import '../widgets/flow_step_badge.dart';

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
  static const _muted = Color(0xFF6B7280);
  static const _line = Color(0xFFE5E7EB);
  static const _soft = Color(0xFFF5F5F5);
  int _selected = 0;
  bool _ranking = false;

  List<Map<String, dynamic>> get _candidates =>
      (widget.flow.rankedCandidates?['ranked_candidates'] as List? ?? const [])
          .whereType<Map>()
          .map((value) => value.cast<String, dynamic>())
          .toList();

  Future<void> _rerank(String template) async {
    if (_ranking) return;
    setState(() => _ranking = true);
    widget.flow.selectedTemplate = template;
    try {
      widget.flow.rankedCandidates = await widget.api.rank(
        sessionId: widget.flow.sessionId!,
        template: template,
      );
      _selected = 0;
    } on ApiError catch (error) {
      if (error.code == 'SESSION_NOT_FOUND') {
        widget.onSessionExpired();
      } else if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
    if (mounted) setState(() => _ranking = false);
  }

  void _popTo(String routeName) {
    Navigator.of(
      context,
    ).popUntil((route) => route.settings.name == routeName || route.isFirst);
  }

  @override
  Widget build(BuildContext context) {
    final candidates = _candidates;
    final selected = candidates.isEmpty
        ? null
        : candidates[_selected.clamp(0, candidates.length - 1)];
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        title: const Text('PlaNU'),
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.white,
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(24, 28, 24, 48),
          children: [
            const FlowStepBadge(label: '추천 결과', current: 9),
            const SizedBox(height: 24),
            Text(
              '나에게 맞는 시간표를 찾았어요',
              style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                color: _ink,
                fontWeight: FontWeight.w700,
                letterSpacing: -1,
              ),
            ),
            const SizedBox(height: 12),
            const Text(
              '필수 조건을 확인하고 선호 기준을 비교해 추천한 결과입니다.',
              style: TextStyle(color: _muted, fontSize: 16, height: 1.5),
            ),
            const SizedBox(height: 28),
            _TemplateSelector(
              value: widget.flow.selectedTemplate,
              enabled: !_ranking,
              onChanged: _rerank,
            ),
            if (_ranking) const LinearProgressIndicator(),
            const SizedBox(height: 24),
            if (selected == null)
              const _EmptyResult()
            else ...[
              _CandidateTabs(
                candidates: candidates,
                selected: _selected,
                onSelected: (index) => setState(() => _selected = index),
              ),
              const SizedBox(height: 24),
              _CandidateView(candidate: selected),
            ],
            const SizedBox(height: 24),
            _ActionButton(
              icon: Icons.upload_file_outlined,
              label: '파일 다시 업로드',
              onPressed: () => _popTo('/elective-upload'),
            ),
            const SizedBox(height: 12),
            _ActionButton(
              icon: Icons.school_outlined,
              label: '전공 다시 선택',
              onPressed: () => _popTo('/major-prompt'),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: () => _popTo('/general-preference'),
              icon: const Icon(Icons.tune),
              label: const Text('교양 조건 수정'),
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF087D85),
                minimumSize: const Size.fromHeight(52),
              ),
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: widget.onSessionExpired,
              child: const Text('처음부터 다시 시작'),
            ),
          ],
        ),
      ),
    );
  }
}

class _TemplateSelector extends StatelessWidget {
  const _TemplateSelector({
    required this.value,
    required this.enabled,
    required this.onChanged,
  });
  final String value;
  final bool enabled;
  final ValueChanged<String> onChanged;
  @override
  Widget build(BuildContext context) => DropdownButtonFormField<String>(
    initialValue: value,
    decoration: const InputDecoration(
      labelText: '추천 템플릿',
      border: OutlineInputBorder(),
    ),
    items: const [
      DropdownMenuItem(value: 'balanced', child: Text('균형형')),
      DropdownMenuItem(value: 'free_day_priority', child: Text('공강 우선')),
      DropdownMenuItem(value: 'no_morning_priority', child: Text('오전 수업 최소화')),
      DropdownMenuItem(value: 'compact_schedule', child: Text('수업 시간 압축')),
    ],
    onChanged: enabled
        ? (value) {
            if (value != null) onChanged(value);
          }
        : null,
  );
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
      borderRadius: BorderRadius.circular(12),
    ),
    child: Row(
      children: List.generate(
        candidates.length,
        (index) => Expanded(
          child: InkWell(
            onTap: () => onSelected(index),
            borderRadius: BorderRadius.circular(8),
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 13),
              decoration: BoxDecoration(
                color: selected == index ? Colors.white : Colors.transparent,
                borderRadius: BorderRadius.circular(8),
                border: selected == index
                    ? Border.all(color: _TimetableResultScreenState._line)
                    : null,
              ),
              child: Text(
                '후보 ${candidates[index]['rank'] ?? index + 1}',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: selected == index
                      ? _TimetableResultScreenState._ink
                      : _TimetableResultScreenState._muted,
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}

class _CandidateView extends StatelessWidget {
  const _CandidateView({required this.candidate});
  final Map<String, dynamic> candidate;
  Map<String, dynamic> get timetable =>
      (candidate['timetable'] as Map?)?.cast<String, dynamic>() ?? const {};
  Map<String, dynamic> get load =>
      (candidate['load_satisfaction'] as Map?)?.cast<String, dynamic>() ??
      const {};
  List<Map<String, dynamic>> get schedule =>
      (timetable['schedule_items'] as List? ?? const [])
          .whereType<Map>()
          .map((e) => e.cast<String, dynamic>())
          .toList();
  List<Map<String, dynamic>> get courses =>
      (timetable['courses'] as List? ?? const [])
          .whereType<Map>()
          .map((e) => e.cast<String, dynamic>())
          .toList();

  @override
  Widget build(BuildContext context) {
    final first = schedule.isEmpty
        ? '-'
        : schedule
              .map((e) => '${e['start']}')
              .reduce((a, b) => a.compareTo(b) < 0 ? a : b);
    final last = schedule.isEmpty
        ? '-'
        : schedule
              .map((e) => '${e['end']}')
              .reduce((a, b) => a.compareTo(b) > 0 ? a : b);
    final days = schedule.map((e) => e['day']).toSet().length;
    final components = (candidate['score_components'] as List? ?? const [])
        .whereType<Map>()
        .map((e) => e.cast<String, dynamic>())
        .toList();
    final reasons = _derivedReasons(schedule);
    final warnings = (timetable['warnings'] as List? ?? const [])
        .whereType<String>()
        .toList();
    if (warnings.isEmpty) {
      warnings.add('실제 수강 가능 여부와 정원은 학생지원시스템에서 확인해 주세요.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: _TimetableResultScreenState._ink,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '후보 ${candidate['rank']}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 24,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      '가장 높은 순위의 추천안부터 확인해 보세요.',
                      style: TextStyle(color: Color(0xFFA1A1AA)),
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  const Text(
                    '선호 적합도 점수',
                    style: TextStyle(color: Color(0xFFA1A1AA)),
                  ),
                  Text(
                    '${_score(candidate['raw_score'])}점',
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
        ),
        const SizedBox(height: 20),
        LayoutBuilder(
          builder: (context, constraints) {
            final width = constraints.maxWidth < 600
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
                  value:
                      '${load['final_total_credits'] ?? timetable['total_credit'] ?? 0}학점',
                ),
                _Metric(
                  width: width,
                  icon: Icons.directions_walk,
                  label: '등교일',
                  value: '주 $days일',
                ),
                _Metric(
                  width: width,
                  icon: Icons.wb_sunny_outlined,
                  label: '첫 수업',
                  value: first,
                ),
                _Metric(
                  width: width,
                  icon: Icons.nights_stay_outlined,
                  label: '마지막 수업',
                  value: last,
                ),
              ],
            );
          },
        ),
        const SizedBox(height: 20),
        if (components.isNotEmpty)
          _Section(
            title: '점수 계산 내역',
            child: Column(
              children: components.map((item) {
                final value = (item['value'] as num?)?.toDouble() ?? 0;
                return ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Text(
                    value >= 0 ? '+${_score(value)}' : _score(value),
                    style: TextStyle(
                      color: value >= 0 ? const Color(0xFF10B981) : Colors.red,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  title: Text('${item['reason'] ?? item['label'] ?? ''}'),
                );
              }).toList(),
            ),
          ),
        const SizedBox(height: 20),
        _Section(
          title: '시간표',
          subtitle: '과목 유형은 색상과 라벨로 구분했어요.',
          child: _TimetableGrid(items: schedule),
        ),
        const SizedBox(height: 20),
        _Section(
          title: '과목 목록',
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
            child: _Bullets(items: reasons, icon: Icons.auto_awesome_outlined),
          ),
        ],
        const SizedBox(height: 20),
        _WarningSection(items: warnings),
      ],
    );
  }
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
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _TimetableResultScreenState._soft,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(icon),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: const TextStyle(
                    color: _TimetableResultScreenState._muted,
                  ),
                ),
                Text(
                  value,
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
  const _Section({required this.title, required this.child, this.subtitle});
  final String title;
  final String? subtitle;
  final Widget child;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      border: Border.all(color: _TimetableResultScreenState._line),
      borderRadius: BorderRadius.circular(12),
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
        if (subtitle != null) ...[
          const SizedBox(height: 6),
          Text(
            subtitle!,
            style: const TextStyle(color: _TimetableResultScreenState._muted),
          ),
        ],
        const SizedBox(height: 16),
        child,
      ],
    ),
  );
}

class _TimetableGrid extends StatelessWidget {
  const _TimetableGrid({required this.items});
  final List<Map<String, dynamic>> items;
  static const days = ['MON', 'TUE', 'WED', 'THU', 'FRI'];
  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    child: SizedBox(
      width: 760,
      child: Column(
        children: [
          Row(
            children: [
              const SizedBox(width: 52),
              for (final day in ['월', '화', '수', '목', '금'])
                SizedBox(
                  width: 140,
                  child: Center(
                    child: Text(
                      day,
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                ),
            ],
          ),
          const Divider(),
          SizedBox(
            height: 640,
            child: Stack(
              children: [
                for (var hour = 9; hour <= 18; hour++) ...[
                  Positioned(
                    top: (hour - 9) * 64,
                    left: 0,
                    child: Text(
                      '${hour.toString().padLeft(2, '0')}:00',
                      style: const TextStyle(
                        color: _TimetableResultScreenState._muted,
                        fontSize: 12,
                      ),
                    ),
                  ),
                  Positioned(
                    top: (hour - 9) * 64,
                    left: 52,
                    right: 0,
                    child: const Divider(height: 1),
                  ),
                ],
                for (final item in items)
                  if (days.contains('${item['day']}'))
                    Positioned(
                      left: 52 + days.indexOf('${item['day']}') * 140 + 4,
                      top: (_minutes('${item['start']}') - 540) / 60 * 64,
                      width: 132,
                      height:
                          ((_minutes('${item['end']}') -
                                      _minutes('${item['start']}')) /
                                  60 *
                                  64)
                              .clamp(32, 300),
                      child: Container(
                        padding: const EdgeInsets.all(7),
                        decoration: BoxDecoration(
                          color: _categoryColor('${item['category']}'),
                          borderRadius: BorderRadius.circular(7),
                        ),
                        child: Text(
                          '[${_categoryLabel('${item['category']}')}]\n${item['course_name']}\n${item['classroom']}',
                          overflow: TextOverflow.fade,
                          style: const TextStyle(fontSize: 11),
                        ),
                      ),
                    ),
              ],
            ),
          ),
        ],
      ),
    ),
  );
}

class _CategoryChip extends StatelessWidget {
  const _CategoryChip({required this.category});
  final String category;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
    decoration: BoxDecoration(
      color: _categoryColor(category),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Text(_categoryLabel(category)),
  );
}

class _CourseRow extends StatelessWidget {
  const _CourseRow({required this.course, required this.schedule});
  final Map<String, dynamic> course;
  final List<Map<String, dynamic>> schedule;

  @override
  Widget build(BuildContext context) {
    final name = '${course['course_name'] ?? ''}';
    final division = '${course['division'] ?? ''}';
    final meetings = schedule.where(
      (item) =>
          '${item['course_name']}' == name && '${item['division']}' == division,
    );
    final timeText = meetings
        .map((item) => '${_dayLabel('${item['day']}')} ${item['start']}')
        .join(' · ');
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 16),
      decoration: const BoxDecoration(
        border: Border(
          bottom: BorderSide(color: _TimetableResultScreenState._line),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _CategoryChip(category: '${course['category'] ?? ''}'),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '$name $division',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  '${course['professor'] ?? ''}${timeText.isEmpty ? '' : ' · $timeText'} · ${course['credit'] ?? 0}학점',
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

class _WarningSection extends StatelessWidget {
  const _WarningSection({required this.items});
  final List<String> items;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(22),
    decoration: BoxDecoration(
      color: const Color(0xFFFFFBEB),
      border: Border.all(color: const Color(0xFFF6C84C)),
      borderRadius: BorderRadius.circular(14),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '주의사항',
          style: TextStyle(
            color: Color(0xFF9A3F00),
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 14),
        _Bullets(items: items, icon: Icons.info_outline),
      ],
    ),
  );
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.icon,
    required this.label,
    required this.onPressed,
  });
  final IconData icon;
  final String label;
  final VoidCallback onPressed;
  @override
  Widget build(BuildContext context) => OutlinedButton.icon(
    onPressed: onPressed,
    icon: Icon(icon),
    label: Text(label),
    style: OutlinedButton.styleFrom(
      foregroundColor: const Color(0xFF087D85),
      minimumSize: const Size.fromHeight(52),
      side: const BorderSide(color: Color(0xFF6B7280)),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
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

class _EmptyResult extends StatelessWidget {
  const _EmptyResult();
  @override
  Widget build(BuildContext context) => const Padding(
    padding: EdgeInsets.symmetric(vertical: 48),
    child: Column(
      children: [
        Icon(
          Icons.event_busy_outlined,
          size: 48,
          color: _TimetableResultScreenState._muted,
        ),
        SizedBox(height: 16),
        Text('조건에 맞는 추천 후보가 없습니다.'),
      ],
    ),
  );
}

int _minutes(String value) {
  final parts = value.split(':');
  if (parts.length < 2) return 540;
  return (int.tryParse(parts[0]) ?? 9) * 60 + (int.tryParse(parts[1]) ?? 0);
}

List<String> _derivedReasons(List<Map<String, dynamic>> schedule) {
  if (schedule.isEmpty) return const ['표시할 수업 시간 정보가 없습니다.'];
  final byDay = <String, List<Map<String, dynamic>>>{};
  for (final item in schedule) {
    byDay.putIfAbsent('${item['day']}', () => []).add(item);
  }
  var consecutiveCount = 0;
  var hasConflict = false;
  for (final items in byDay.values) {
    items.sort(
      (a, b) => _minutes('${a['start']}').compareTo(_minutes('${b['start']}')),
    );
    for (var index = 0; index < items.length - 1; index++) {
      final end = _minutes('${items[index]['end']}');
      final nextStart = _minutes('${items[index + 1]['start']}');
      if (end == nextStart) consecutiveCount++;
      if (end > nextStart) hasConflict = true;
    }
  }
  final first = schedule
      .map((item) => _minutes('${item['start']}'))
      .reduce((a, b) => a < b ? a : b);
  final reasons = <String>[
    hasConflict ? '서로 시간이 겹치는 수업이 포함되어 있습니다.' : '과목 간 시간 충돌이 없습니다.',
    byDay.containsKey('FRI') ? '금요일 수업이 포함되어 있습니다.' : '금요일 공강 조건을 만족합니다.',
    consecutiveCount == 0 ? '연강이 없습니다.' : '연강이 $consecutiveCount회 포함되어 있습니다.',
    '등교일이 주 ${byDay.length}일입니다.',
    '첫 수업이 ${_formatMinutes(first)}에 시작합니다.',
  ];
  return reasons;
}

String _formatMinutes(int minutes) =>
    '${(minutes ~/ 60).toString().padLeft(2, '0')}:${(minutes % 60).toString().padLeft(2, '0')}';
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
  'major' => '전공',
  'general_required' => '교양필수',
  'general_elective' => '교양선택',
  _ => value,
};
Color _categoryColor(String value) => switch (value) {
  'major' => const Color(0xFFDDE5FF),
  'general_required' => const Color(0xFFCCF5E3),
  _ => const Color(0xFFFFE5C7),
};
