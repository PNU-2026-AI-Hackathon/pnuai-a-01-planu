import 'package:flutter/material.dart';
import '../models/major_models.dart';
import '../state/major_flow_controller.dart';

class MajorManualSelectScreen extends StatefulWidget {
  const MajorManualSelectScreen({
    super.key,
    required this.controller,
    this.onSessionExpired,
  });
  final MajorFlowController controller;
  final VoidCallback? onSessionExpired;

  @override
  State<MajorManualSelectScreen> createState() =>
      _MajorManualSelectScreenState();
}

class _MajorManualSelectScreenState extends State<MajorManualSelectScreen> {
  final _query = TextEditingController();
  final _selected = <String>{};

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_changed);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.controller.loadAvailableCourses();
    });
  }

  @override
  void dispose() {
    widget.controller.removeListener(_changed);
    _query.dispose();
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  Future<void> _createPreview() async {
    final ok = await widget.controller.requestManualPreview(_selected.toList());
    if (!mounted || !ok) return;
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.controller.state;
    final loading = state == MajorRequestState.loadingCourses;
    final submitting = state == MajorRequestState.manualPreviewing;
    final courses = _filteredCourses(widget.controller.availableCourses);
    final error = widget.controller.error;

    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.white,
        title: const Text('전공 과목 직접 선택'),
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 860),
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 24, 24, 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      TextField(
                        key: const Key('majorManualSearchField'),
                        controller: _query,
                        onChanged: (_) => setState(() {}),
                        decoration: InputDecoration(
                          prefixIcon: const Icon(Icons.search),
                          hintText: '과목명, 분반, 교수명 검색',
                          filled: true,
                          fillColor: const Color(0xFFF8F9FA),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        '${_selected.length}개 선택',
                        style: const TextStyle(
                          color: Color(0xFF374151),
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (error != null) ...[
                        const SizedBox(height: 12),
                        _ManualError(
                          error: error,
                          retry: () => widget.controller.loadAvailableCourses(
                            force: true,
                          ),
                          onSessionExpired: widget.onSessionExpired,
                        ),
                      ],
                    ],
                  ),
                ),
                Expanded(
                  child: loading
                      ? const Center(child: CircularProgressIndicator())
                      : courses.isEmpty
                      ? const Center(child: Text('표시할 전공 과목이 없습니다.'))
                      : ListView.separated(
                          key: const Key('majorManualCourseList'),
                          padding: const EdgeInsets.fromLTRB(24, 0, 24, 16),
                          itemCount: courses.length,
                          separatorBuilder: (context, index) =>
                              const SizedBox(height: 8),
                          itemBuilder: (context, index) {
                            final course = courses[index];
                            final checked = _selected.contains(course.id);
                            return _CourseOption(
                              course: course,
                              checked: checked,
                              onChanged: submitting
                                  ? null
                                  : (value) {
                                      setState(() {
                                        if (value ?? false) {
                                          _selected.add(course.id);
                                        } else {
                                          _selected.remove(course.id);
                                        }
                                      });
                                    },
                            );
                          },
                        ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
                  child: FilledButton(
                    key: const Key('majorManualPreviewButton'),
                    onPressed: _selected.isEmpty || loading || submitting
                        ? null
                        : _createPreview,
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF111111),
                      minimumSize: const Size.fromHeight(48),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: submitting
                        ? const SizedBox.square(
                            dimension: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Text('선택한 과목으로 미리보기'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  List<MajorCourse> _filteredCourses(List<MajorCourse> courses) {
    final query = _query.text.trim().toLowerCase();
    if (query.isEmpty) return courses;
    return courses.where((course) {
      final haystack = [
        course.name,
        course.division,
        course.professor,
        course.id,
      ].join(' ').toLowerCase();
      return haystack.contains(query);
    }).toList();
  }
}

class _CourseOption extends StatelessWidget {
  const _CourseOption({
    required this.course,
    required this.checked,
    required this.onChanged,
  });
  final MajorCourse course;
  final bool checked;
  final ValueChanged<bool?>? onChanged;

  @override
  Widget build(BuildContext context) {
    final timeText = course.classTimes
        .map((time) => '${_dayLabel(time.day)} ${time.start}-${time.end}')
        .join(' · ');
    return Material(
      color: const Color(0xFFF8F9FA),
      borderRadius: BorderRadius.circular(8),
      child: CheckboxListTile(
        key: Key('majorManualCourse-${course.id}'),
        value: checked,
        onChanged: onChanged,
        controlAffinity: ListTileControlAffinity.leading,
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        title: Text(
          '${course.name} ${course.division}',
          style: const TextStyle(fontWeight: FontWeight.w600),
        ),
        subtitle: Text(
          '${course.professor.isEmpty ? '담당 교수 미정' : course.professor} · ${course.credit}학점${timeText.isEmpty ? '' : ' · $timeText'}',
        ),
      ),
    );
  }

  String _dayLabel(String day) => switch (day) {
    'MON' => '월',
    'TUE' => '화',
    'WED' => '수',
    'THU' => '목',
    'FRI' => '금',
    'SAT' => '토',
    'SUN' => '일',
    _ => day,
  };
}

class _ManualError extends StatelessWidget {
  const _ManualError({
    required this.error,
    required this.retry,
    this.onSessionExpired,
  });
  final ApiError error;
  final VoidCallback retry;
  final VoidCallback? onSessionExpired;

  @override
  Widget build(BuildContext context) {
    final expired = error.code == 'SESSION_NOT_FOUND';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFFEF2F2),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              expired ? '세션이 만료되었습니다.' : '과목 목록을 불러오지 못했습니다.',
              style: const TextStyle(color: Color(0xFFB91C1C)),
            ),
          ),
          TextButton(
            onPressed: expired ? onSessionExpired : retry,
            child: Text(expired ? '처음으로' : '다시 시도'),
          ),
        ],
      ),
    );
  }
}
