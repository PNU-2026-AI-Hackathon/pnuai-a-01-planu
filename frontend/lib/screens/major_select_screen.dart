import 'dart:async';

import 'package:flutter/material.dart';

class MajorSelectScreen extends StatefulWidget {
  const MajorSelectScreen({
    super.key,
    this.sessionId,
    this.majorCandidates = _sampleCandidates,
    this.onConfirmMajorCourses,
    this.onBack,
  });

  final String? sessionId;
  final List<MajorCourseCandidate> majorCandidates;
  final FutureOr<void> Function(List<MajorCourseCandidate> selectedCourses)?
  onConfirmMajorCourses;
  final VoidCallback? onBack;

  static const List<MajorCourseCandidate> _sampleCandidates =
      <MajorCourseCandidate>[
        MajorCourseCandidate(
          courseId: 'CSE101-001',
          courseName: '컴퓨터프로그래밍',
          category: 'MAJOR_BASIC',
          credit: 3,
          division: '001',
          professor: '김민수',
          classTimes: <MajorClassTime>[
            MajorClassTime(
              day: 'MON',
              start: '09:00',
              end: '10:15',
              classroom: '제6공학관 101호',
              buildingCode: 'ENG',
            ),
            MajorClassTime(
              day: 'WED',
              start: '09:00',
              end: '10:15',
              classroom: '제6공학관 101호',
              buildingCode: 'ENG',
            ),
          ],
        ),
        MajorCourseCandidate(
          courseId: 'CSE101-002',
          courseName: '컴퓨터프로그래밍',
          category: 'MAJOR_BASIC',
          credit: 3,
          division: '002',
          professor: '박서연',
          classTimes: <MajorClassTime>[
            MajorClassTime(
              day: 'MON',
              start: '10:30',
              end: '11:45',
              classroom: '제6공학관 201호',
              buildingCode: 'ENG',
            ),
            MajorClassTime(
              day: 'WED',
              start: '10:30',
              end: '11:45',
              classroom: '제6공학관 201호',
              buildingCode: 'ENG',
            ),
          ],
        ),
        MajorCourseCandidate(
          courseId: 'MATH110-001',
          courseName: '이산수학',
          category: 'MAJOR_REQUIRED',
          credit: 3,
          division: '001',
          professor: '최지훈',
          classTimes: <MajorClassTime>[
            MajorClassTime(
              day: 'TUE',
              start: '13:30',
              end: '14:45',
              classroom: '자연대연구실험동 305호',
              buildingCode: 'SCI',
            ),
            MajorClassTime(
              day: 'THU',
              start: '13:30',
              end: '14:45',
              classroom: '자연대연구실험동 305호',
              buildingCode: 'SCI',
            ),
          ],
        ),
        MajorCourseCandidate(
          courseId: 'MATH110-002',
          courseName: '이산수학',
          category: 'MAJOR_REQUIRED',
          credit: 3,
          division: '002',
          professor: '이하은',
          classTimes: <MajorClassTime>[
            MajorClassTime(
              day: 'TUE',
              start: '15:00',
              end: '16:15',
              classroom: '자연대연구실험동 211호',
              buildingCode: 'SCI',
            ),
            MajorClassTime(
              day: 'THU',
              start: '15:00',
              end: '16:15',
              classroom: '자연대연구실험동 211호',
              buildingCode: 'SCI',
            ),
          ],
        ),
        MajorCourseCandidate(
          courseId: 'CSE210-001',
          courseName: '알고리즘',
          category: 'MAJOR_REQUIRED',
          credit: 3,
          division: '001',
          professor: '정우진',
          classTimes: <MajorClassTime>[
            MajorClassTime(
              day: 'FRI',
              start: '10:30',
              end: '13:00',
              classroom: '제6공학관 401호',
              buildingCode: 'ENG',
            ),
          ],
        ),
      ];

  @override
  State<MajorSelectScreen> createState() => _MajorSelectScreenState();
}

class _MajorSelectScreenState extends State<MajorSelectScreen> {
  static const Color _ink = Color(0xFF111111);
  static const Color _body = Color(0xFF374151);
  static const Color _muted = Color(0xFF6B7280);
  static const Color _hairline = Color(0xFFE5E7EB);
  static const Color _surfaceSoft = Color(0xFFF8F9FA);
  static const Color _surfaceCard = Color(0xFFF5F5F5);
  static const Color _warning = Color(0xFFF59E0B);
  static const Color _error = Color(0xFFEF4444);

  final Map<String, String> _selectedCourseIdsByName = <String, String>{};
  bool _isConfirming = false;

  List<MajorCourseCandidate> get _selectedCourses {
    final selectedIds = _selectedCourseIdsByName.values.toSet();
    return widget.majorCandidates
        .where((course) => selectedIds.contains(course.courseId))
        .toList();
  }

  List<_CourseConflict> get _conflicts {
    final selected = _selectedCourses;
    final conflicts = <_CourseConflict>[];

    for (var index = 0; index < selected.length; index += 1) {
      for (
        var otherIndex = index + 1;
        otherIndex < selected.length;
        otherIndex += 1
      ) {
        if (selected[index].conflictsWith(selected[otherIndex])) {
          conflicts.add(_CourseConflict(selected[index], selected[otherIndex]));
        }
      }
    }

    return conflicts;
  }

  bool get _canConfirm =>
      _selectedCourses.isNotEmpty && _conflicts.isEmpty && !_isConfirming;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final courseGroups = _groupCandidates(widget.majorCandidates);
    final conflicts = _conflicts;

    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        foregroundColor: _ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        leading: widget.onBack == null
            ? null
            : IconButton(
                tooltip: '이전',
                icon: const Icon(Icons.arrow_back_rounded),
                onPressed: widget.onBack,
              ),
        title: const Text('PlaNU'),
        centerTitle: false,
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1080),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 40, 24, 32),
              children: <Widget>[
                const _StepPill(),
                const SizedBox(height: 24),
                Text(
                  '전공 과목 선택',
                  style: theme.textTheme.displaySmall?.copyWith(
                    color: _ink,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0,
                    height: 1.2,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  '수강할 전공 과목의 분반을 직접 선택해 주세요. 선택한 전공 시간표 위에 교양 과목을 추천해 드릴게요.',
                  style: theme.textTheme.bodyLarge?.copyWith(
                    color: _body,
                    height: 1.5,
                  ),
                ),
                if (widget.sessionId != null) ...<Widget>[
                  const SizedBox(height: 16),
                  _SessionBadge(sessionId: widget.sessionId!),
                ],
                const SizedBox(height: 32),
                if (widget.majorCandidates.isEmpty)
                  const _EmptyMajorNotice()
                else
                  LayoutBuilder(
                    builder: (context, constraints) {
                      final isCompact = constraints.maxWidth < 860;
                      final selector = _CourseGroupList(
                        groups: courseGroups,
                        selectedCourseIdsByName: _selectedCourseIdsByName,
                        onChanged: _selectCourse,
                      );
                      final summary = _SelectedCourseSummary(
                        selectedCourses: _selectedCourses,
                        conflicts: conflicts,
                        isConfirming: _isConfirming,
                        canConfirm: _canConfirm,
                        onClearCourse: _clearCourse,
                        onConfirm: _confirmSelection,
                      );

                      if (isCompact) {
                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: <Widget>[
                            selector,
                            const SizedBox(height: 24),
                            summary,
                          ],
                        );
                      }

                      return Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Expanded(flex: 7, child: selector),
                          const SizedBox(width: 24),
                          Expanded(flex: 4, child: summary),
                        ],
                      );
                    },
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Map<String, List<MajorCourseCandidate>> _groupCandidates(
    List<MajorCourseCandidate> candidates,
  ) {
    final groups = <String, List<MajorCourseCandidate>>{};

    for (final candidate in candidates) {
      groups.putIfAbsent(candidate.courseName, () => <MajorCourseCandidate>[]);
      groups[candidate.courseName]!.add(candidate);
    }

    return groups;
  }

  void _selectCourse(String courseName, String? courseId) {
    setState(() {
      if (courseId == null) {
        _selectedCourseIdsByName.remove(courseName);
      } else {
        _selectedCourseIdsByName[courseName] = courseId;
      }
    });
  }

  void _clearCourse(MajorCourseCandidate course) {
    setState(() {
      _selectedCourseIdsByName.remove(course.courseName);
    });
  }

  Future<void> _confirmSelection() async {
    if (!_canConfirm) {
      return;
    }

    setState(() {
      _isConfirming = true;
    });

    try {
      await widget.onConfirmMajorCourses?.call(_selectedCourses);
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('전공 시간표를 확정했어요.')));
      }
    } finally {
      if (mounted) {
        setState(() {
          _isConfirming = false;
        });
      }
    }
  }
}

class MajorCourseCandidate {
  const MajorCourseCandidate({
    required this.courseId,
    required this.courseName,
    required this.category,
    required this.credit,
    required this.division,
    required this.professor,
    required this.classTimes,
    this.area,
  });

  final String courseId;
  final String courseName;
  final String category;
  final int? area;
  final double credit;
  final String division;
  final String professor;
  final List<MajorClassTime> classTimes;

  bool conflictsWith(MajorCourseCandidate other) {
    return classTimes.any((time) => other.classTimes.any(time.overlaps));
  }
}

class MajorClassTime {
  const MajorClassTime({
    required this.day,
    required this.start,
    required this.end,
    required this.classroom,
    required this.buildingCode,
  });

  final String day;
  final String start;
  final String end;
  final String classroom;
  final String buildingCode;

  bool overlaps(MajorClassTime other) {
    return day == other.day &&
        _minutesFromTime(start) < _minutesFromTime(other.end) &&
        _minutesFromTime(other.start) < _minutesFromTime(end);
  }

  String get displayText {
    return '${_dayLabel(day)} $start~$end / $classroom';
  }

  static int _minutesFromTime(String value) {
    final parts = value.split(':');
    if (parts.length != 2) {
      return 0;
    }

    final hour = int.tryParse(parts[0]) ?? 0;
    final minute = int.tryParse(parts[1]) ?? 0;
    return hour * 60 + minute;
  }

  static String _dayLabel(String value) {
    return switch (value) {
      'MON' => '월',
      'TUE' => '화',
      'WED' => '수',
      'THU' => '목',
      'FRI' => '금',
      _ => value,
    };
  }
}

class _CourseConflict {
  const _CourseConflict(this.first, this.second);

  final MajorCourseCandidate first;
  final MajorCourseCandidate second;
}

class _StepPill extends StatelessWidget {
  const _StepPill();

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: _MajorSelectScreenState._surfaceSoft,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Text(
            '전공 직접 선택 · 5 / 9',
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: _MajorSelectScreenState._ink,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }
}

class _SessionBadge extends StatelessWidget {
  const _SessionBadge({required this.sessionId});

  final String sessionId;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: _MajorSelectScreenState._surfaceCard,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Text(
            '세션 $sessionId',
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: _MajorSelectScreenState._muted,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }
}

class _CourseGroupList extends StatelessWidget {
  const _CourseGroupList({
    required this.groups,
    required this.selectedCourseIdsByName,
    required this.onChanged,
  });

  final Map<String, List<MajorCourseCandidate>> groups;
  final Map<String, String> selectedCourseIdsByName;
  final void Function(String courseName, String? courseId) onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        for (final entry in groups.entries) ...<Widget>[
          _CourseGroupCard(
            courseName: entry.key,
            courses: entry.value,
            selectedCourseId: selectedCourseIdsByName[entry.key],
            onChanged: (courseId) => onChanged(entry.key, courseId),
          ),
          if (entry.key != groups.keys.last) const SizedBox(height: 16),
        ],
      ],
    );
  }
}

class _CourseGroupCard extends StatelessWidget {
  const _CourseGroupCard({
    required this.courseName,
    required this.courses,
    required this.selectedCourseId,
    required this.onChanged,
  });

  final String courseName;
  final List<MajorCourseCandidate> courses;
  final String? selectedCourseId;
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final selectedCourse = courses
        .where((course) => course.courseId == selectedCourseId)
        .firstOrNull;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: _MajorSelectScreenState._hairline),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        courseName,
                        style: theme.textTheme.titleMedium?.copyWith(
                          color: _MajorSelectScreenState._ink,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        '분반 ${courses.length}개',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: _MajorSelectScreenState._muted,
                        ),
                      ),
                    ],
                  ),
                ),
                if (selectedCourse != null)
                  TextButton.icon(
                    onPressed: () => onChanged(null),
                    icon: const Icon(Icons.close_rounded, size: 18),
                    label: const Text('선택 해제'),
                  ),
              ],
            ),
            const SizedBox(height: 16),
            RadioGroup<String>(
              groupValue: selectedCourseId,
              onChanged: onChanged,
              child: Column(
                children: <Widget>[
                  for (final course in courses) ...<Widget>[
                    _CourseOptionTile(course: course),
                    if (course != courses.last)
                      const Divider(
                        height: 1,
                        color: _MajorSelectScreenState._hairline,
                      ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CourseOptionTile extends StatelessWidget {
  const _CourseOptionTile({required this.course});

  final MajorCourseCandidate course;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return RadioListTile<String>(
      value: course.courseId,
      contentPadding: EdgeInsets.zero,
      activeColor: _MajorSelectScreenState._ink,
      title: Wrap(
        spacing: 8,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: <Widget>[
          _SmallBadge(label: course.division),
          Text(
            course.professor,
            style: theme.textTheme.titleSmall?.copyWith(
              color: _MajorSelectScreenState._ink,
              fontWeight: FontWeight.w600,
            ),
          ),
          Text(
            '${course.credit.toStringAsFixed(course.credit.truncateToDouble() == course.credit ? 0 : 1)}학점',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: _MajorSelectScreenState._muted,
            ),
          ),
        ],
      ),
      subtitle: Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            for (final classTime in course.classTimes)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  classTime.displayText,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: _MajorSelectScreenState._body,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _SelectedCourseSummary extends StatelessWidget {
  const _SelectedCourseSummary({
    required this.selectedCourses,
    required this.conflicts,
    required this.isConfirming,
    required this.canConfirm,
    required this.onClearCourse,
    required this.onConfirm,
  });

  final List<MajorCourseCandidate> selectedCourses;
  final List<_CourseConflict> conflicts;
  final bool isConfirming;
  final bool canConfirm;
  final ValueChanged<MajorCourseCandidate> onClearCourse;
  final VoidCallback onConfirm;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: _MajorSelectScreenState._surfaceCard,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text(
              '선택한 전공',
              style: theme.textTheme.titleMedium?.copyWith(
                color: _MajorSelectScreenState._ink,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              selectedCourses.isEmpty
                  ? '아직 선택한 과목이 없어요.'
                  : '${selectedCourses.length}과목 선택됨',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: _MajorSelectScreenState._muted,
              ),
            ),
            const SizedBox(height: 20),
            if (selectedCourses.isEmpty)
              const _EmptySelectionHint()
            else
              for (final course in selectedCourses) ...<Widget>[
                _SelectedCourseTile(course: course, onClear: onClearCourse),
                if (course != selectedCourses.last) const SizedBox(height: 10),
              ],
            if (conflicts.isNotEmpty) ...<Widget>[
              const SizedBox(height: 20),
              _ConflictNotice(conflicts: conflicts),
            ],
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: canConfirm ? onConfirm : null,
              style: FilledButton.styleFrom(
                backgroundColor: _MajorSelectScreenState._ink,
                foregroundColor: Colors.white,
                disabledBackgroundColor: _MajorSelectScreenState._hairline,
                disabledForegroundColor: _MajorSelectScreenState._muted,
                minimumSize: const Size.fromHeight(48),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                textStyle: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              icon: isConfirming
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(Icons.check_rounded, size: 18),
              label: Text(isConfirming ? '확정 중' : '전공 시간표 확정'),
            ),
          ],
        ),
      ),
    );
  }
}

class _SelectedCourseTile extends StatelessWidget {
  const _SelectedCourseTile({required this.course, required this.onClear});

  final MajorCourseCandidate course;
  final ValueChanged<MajorCourseCandidate> onClear;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _MajorSelectScreenState._hairline),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    '${course.courseName} ${course.division}',
                    style: theme.textTheme.titleSmall?.copyWith(
                      color: _MajorSelectScreenState._ink,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    course.professor,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: _MajorSelectScreenState._muted,
                    ),
                  ),
                ],
              ),
            ),
            IconButton(
              tooltip: '${course.courseName} 선택 해제',
              icon: const Icon(Icons.close_rounded, size: 18),
              onPressed: () => onClear(course),
              visualDensity: VisualDensity.compact,
            ),
          ],
        ),
      ),
    );
  }
}

class _EmptySelectionHint extends StatelessWidget {
  const _EmptySelectionHint();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _MajorSelectScreenState._hairline),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Text(
          '과목별로 수강할 분반을 하나씩 선택해 주세요.',
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            color: _MajorSelectScreenState._muted,
          ),
        ),
      ),
    );
  }
}

class _ConflictNotice extends StatelessWidget {
  const _ConflictNotice({required this.conflicts});

  final List<_CourseConflict> conflicts;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFFFFFBEB),
        border: Border.all(color: const Color(0xFFFDE68A)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const Icon(
                  Icons.warning_amber_rounded,
                  color: _MajorSelectScreenState._warning,
                  size: 20,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '선택한 전공 시간이 겹쳐요.',
                    style: theme.textTheme.titleSmall?.copyWith(
                      color: _MajorSelectScreenState._ink,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            for (final conflict in conflicts)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  '${conflict.first.courseName} ${conflict.first.division}, ${conflict.second.courseName} ${conflict.second.division}',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: _MajorSelectScreenState._body,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _EmptyMajorNotice extends StatelessWidget {
  const _EmptyMajorNotice();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFFFFFBEB),
        border: Border.all(color: const Color(0xFFFDE68A)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const Icon(
              Icons.error_outline_rounded,
              color: _MajorSelectScreenState._error,
              size: 22,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    '전공 과목을 찾지 못했어요.',
                    style: theme.textTheme.titleMedium?.copyWith(
                      color: _MajorSelectScreenState._ink,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '1학년 전공기초 또는 전공필수 수강편람 파일인지 다시 확인해 주세요.',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: _MajorSelectScreenState._body,
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
}

class _SmallBadge extends StatelessWidget {
  const _SmallBadge({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: _MajorSelectScreenState._surfaceSoft,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        child: Text(
          label,
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
            color: _MajorSelectScreenState._ink,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }
}
