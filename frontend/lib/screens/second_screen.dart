import 'package:flutter/material.dart';

import '../models/condition_summary_models.dart';
import '../models/major_models.dart';
import '../repositories/major_repository.dart';
import '../services/major_api.dart';
import '../services/planu_api.dart';
import '../widgets/flow_step_badge.dart';

class SecondScreen extends StatefulWidget {
  const SecondScreen({
    super.key,
    required this.api,
    required this.selectedDepartment,
    required this.sessionId,
    required this.parsedCourseCount,
    required this.catalogWarnings,
    this.majorRepository,
    this.onSessionExpired,
  });

  final PlanuApi api;
  final String selectedDepartment;
  final String sessionId;
  final int parsedCourseCount;
  final List<String> catalogWarnings;
  final MajorRepository? majorRepository;
  final VoidCallback? onSessionExpired;

  @override
  State<SecondScreen> createState() => _SecondScreenState();
}

class _SecondScreenState extends State<SecondScreen> {
  final _messageController = TextEditingController();
  final Map<String, String> _selectedCourseIdsByName = {};

  ConditionSummary? _latestConditionSummary;
  String? _latestConditionText;
  List<MajorCourse> _majorCourses = const [];
  MajorPreviewResponse? _selectionPreview;
  MajorConfirmResponse? _confirmation;

  String? _courseLoadError;
  String? _selectionError;
  String? _actionHint;
  bool _isLoadingCourses = true;
  bool _isSendingCondition = false;
  bool _isPreviewing = false;
  bool _isConfirming = false;

  late final MajorRepository _majorRepository = widget.majorRepository ??
      MajorRepository(HttpMajorApi(baseUrl: widget.api.baseUrl));

  @override
  void initState() {
    super.initState();
    _loadMajorCourses();
  }

  @override
  void dispose() {
    _messageController.dispose();
    super.dispose();
  }

  Future<void> _loadMajorCourses() async {
    setState(() {
      _isLoadingCourses = true;
      _courseLoadError = null;
    });

    try {
      final response =
          await _majorRepository.listCourses(sessionId: widget.sessionId);
      if (!mounted) return;
      setState(() => _majorCourses = response.courses);
    } on ApiError catch (error) {
      if (!mounted) return;
      setState(() => _courseLoadError = error.message);
    } finally {
      if (mounted) {
        setState(() => _isLoadingCourses = false);
      }
    }
  }

  Future<void> _sendCondition() async {
    final message = _messageController.text.trim();
    if (message.isEmpty || _isSendingCondition) return;

    setState(() {
      _latestConditionText = message;
      _messageController.clear();
      _isSendingCondition = true;
      _actionHint = null;
    });

    try {
      final response = await widget.api.sendChatMessage(
        sessionId: widget.sessionId,
        message: message,
      );
      if (!mounted) return;
      setState(() {
        if (response.conditionSummary != null) {
          _latestConditionSummary = response.conditionSummary;
        }
        _actionHint = response.message;
      });
    } on ApiError catch (error) {
      if (!mounted) return;
      setState(() => _actionHint = error.message);
    } finally {
      if (mounted) {
        setState(() => _isSendingCondition = false);
      }
    }
  }

  Future<void> _previewSelection() async {
    final selectedIds = _selectedCourseIdsByName.values.toList();
    if (selectedIds.isEmpty || _isPreviewing || _isSendingCondition) return;

    setState(() {
      _isPreviewing = true;
      _selectionError = null;
      _selectionPreview = null;
      _confirmation = null;
      _actionHint = null;
    });

    try {
      final preview = await _majorRepository.manualPreview(
        sessionId: widget.sessionId,
        courseIds: selectedIds,
      );
      if (!mounted) return;
      setState(() {
        _selectionPreview = preview;
        if (preview.hasTimeConflict) {
          _selectionError = '선택한 전공 분반에 시간 충돌이 있습니다. 다른 분반을 선택해 주세요.';
        } else if (!preview.canConfirm) {
          _selectionError = '현재 선택은 아직 확정할 수 없습니다. 과목과 분반을 다시 확인해 주세요.';
        }
      });
    } on ApiError catch (error) {
      if (!mounted) return;
      setState(() => _selectionError = error.message);
    } finally {
      if (mounted) {
        setState(() => _isPreviewing = false);
      }
    }
  }

  Future<void> _confirmSelection() async {
    final preview = _selectionPreview;
    if (preview == null || !preview.isConfirmable || _isConfirming) return;

    setState(() {
      _isConfirming = true;
      _selectionError = null;
      _actionHint = null;
    });

    try {
      final confirmation = await _majorRepository.confirm(
        sessionId: widget.sessionId,
        previewId: preview.previewId,
      );
      if (!mounted) return;
      setState(() {
        _confirmation = confirmation;
        _actionHint = '전공 분반을 확정했습니다.';
      });
    } on ApiError catch (error) {
      if (!mounted) return;
      setState(() => _selectionError = error.message);
    } finally {
      if (mounted) {
        setState(() => _isConfirming = false);
      }
    }
  }

  void _openLoadingScreen() {
    if (!_canGenerate) return;
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => const _SecondLoadingScreen()),
    );
  }

  bool get _canGenerate =>
      _latestConditionSummary?.generationReadiness.ready == true &&
      _confirmation != null;

  String get _generateStatusMessage {
    if (_canGenerate) {
      return '시간표를 만들 준비가 완료되었습니다.';
    }
    return '시간표 생성 전, 전공 과목과 시간표 조건 확정이 필요합니다.';
  }

  Map<String, List<MajorCourse>> get _groupedCourses {
    final groups = <String, List<MajorCourse>>{};
    for (final course in _majorCourses) {
      groups.putIfAbsent(course.name, () => []).add(course);
    }
    return groups;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.white,
        foregroundColor: const Color(0xFF111111),
        elevation: 0,
        title: const Text('PlaNU'),
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 960),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 24, 24, 24),
              children: [
                const FlowStepBadge(label: '조건 설정', current: 4),
                const SizedBox(height: 24),
                Text(
                  '전공 분반을 선택하고, 시간표 조건을 입력해주세요',
                  style: theme.textTheme.headlineMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  '앞에서 업로드한 전공 수강편람을 바탕으로 분반을 먼저 고르고, 교양 선택에 반영할 시간표 조건을 입력해 주세요.',
                  style: theme.textTheme.bodyLarge?.copyWith(
                    color: const Color(0xFF374151),
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 18),
                _InfoPill(
                  department: widget.selectedDepartment,
                  parsedCourseCount: widget.parsedCourseCount,
                  warnings: widget.catalogWarnings,
                ),
                const SizedBox(height: 24),
                _SectionCard(
                  title: '1. 전공 과목/분반 선택',
                  child: _buildMajorSelectionSection(theme),
                ),
                const SizedBox(height: 24),
                _SectionCard(
                  title: '2. 시간표 조건 입력',
                  child: _buildConditionSection(),
                ),
                const SizedBox(height: 24),
                _SectionCard(
                  title: '3. 현재 시간표 조건',
                  child: _latestConditionSummary == null
                      ? const Text('조건을 입력하면 이곳에 최신 조건 요약이 표시됩니다.')
                      : ConditionSummaryCard(summary: _latestConditionSummary!),
                ),
                const SizedBox(height: 24),
                _SectionCard(
                  title: '4. 생성 준비',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        _generateStatusMessage,
                        style: theme.textTheme.bodyLarge?.copyWith(
                          color: const Color(0xFF374151),
                          height: 1.5,
                        ),
                      ),
                      const SizedBox(height: 16),
                      FilledButton(
                        key: const Key('generateButton'),
                        onPressed: _canGenerate ? _openLoadingScreen : null,
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFF111111),
                          minimumSize: const Size.fromHeight(52),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                        ),
                        child: const Text('이대로 시간표 만들기'),
                      ),
                    ],
                  ),
                ),
                if (_actionHint != null) ...[
                  const SizedBox(height: 20),
                  Text(
                    _actionHint!,
                    style: const TextStyle(color: Color(0xFF111111)),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildConditionSection() {
    final hasCondition = _latestConditionText != null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (hasCondition) ...[
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: const Color(0xFFF8F9FA),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFE5E7EB)),
            ),
            child: Text('현재 입력한 조건: $_latestConditionText'),
          ),
          const SizedBox(height: 16),
        ],
        TextField(
          key: const Key('secondScreenConditionField'),
          controller: _messageController,
          minLines: 2,
          maxLines: 5,
          enabled: !_isSendingCondition,
          decoration: InputDecoration(
            hintText: '예) 금요일 공강, 오전 10시 이전 수업은 없었으면 좋겠어요.',
            filled: true,
            fillColor: const Color(0xFFF8F9FA),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
            ),
          ),
        ),
        const SizedBox(height: 12),
        FilledButton(
          key: const Key('addConditionButton'),
          onPressed: _isSendingCondition ? null : _sendCondition,
          style: FilledButton.styleFrom(
            backgroundColor: const Color(0xFF111111),
            minimumSize: const Size.fromHeight(48),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
          ),
          child: _isSendingCondition
              ? const SizedBox.square(
                  dimension: 20,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white,
                  ),
                )
              : Text(hasCondition ? '조건 더 추가하기' : '조건 추가하기'),
        ),
      ],
    );
  }

  Widget _buildMajorSelectionSection(ThemeData theme) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_isLoadingCourses)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 24),
            child: Center(child: CircularProgressIndicator()),
          )
        else if (_courseLoadError != null)
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                _courseLoadError!,
                style: const TextStyle(color: Color(0xFFEF4444)),
              ),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: _loadMajorCourses,
                child: const Text('다시 불러오기'),
              ),
            ],
          )
        else if (_majorCourses.isEmpty)
          const Text('선택할 수 있는 전공 과목이 없습니다.')
        else
          ..._buildCourseGroups(),
        const SizedBox(height: 16),
        const Divider(),
        const SizedBox(height: 16),
        Text(
          '선택한 전공',
          style: theme.textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        if (_selectedCourseIdsByName.isNotEmpty)
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: _selectedCourseIdsByName.entries
                .map((entry) => Text('${entry.key} ${entry.value}'))
                .toList(),
          ),
        const SizedBox(height: 20),
        if (_selectionError != null)
          Text(
            _selectionError!,
            style: const TextStyle(color: Color(0xFFEF4444)),
          ),
        if (_selectionPreview != null) ...[
          const SizedBox(height: 12),
          _SelectionPreviewCard(preview: _selectionPreview!),
        ],
        if (_confirmation != null) ...[
          const SizedBox(height: 12),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFFEFF6FF),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFBFDBFE)),
            ),
            child: Text(
              '전공 분반을 확정했습니다.',
              style: theme.textTheme.bodyLarge?.copyWith(
                color: const Color(0xFF1D4ED8),
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
        const SizedBox(height: 16),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: _selectedCourseIdsByName.isEmpty || _isPreviewing
                    ? null
                    : _previewSelection,
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(48),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
                child: _isPreviewing
                    ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('선택한 전공 미리보기'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FilledButton(
                onPressed:
                    _selectionPreview?.isConfirmable == true && !_isConfirming
                        ? _confirmSelection
                        : null,
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF111111),
                  minimumSize: const Size.fromHeight(48),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
                child: _isConfirming
                    ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Text('전공 분반 확정'),
              ),
            ),
          ],
        ),
      ],
    );
  }

  List<Widget> _buildCourseGroups() {
    final groups = _groupedCourses.entries.toList();
    if (groups.isEmpty) {
      return [const Text('선택 가능한 과목이 없습니다.')];
    }

    return groups
        .map(
          (entry) => Padding(
            padding: const EdgeInsets.only(bottom: 16),
            child: _CourseGroupCard(
              courseName: entry.key,
              courses: entry.value,
              selectedCourseId: _selectedCourseIdsByName[entry.key],
              onChanged: (courseId) {
                setState(() {
                  if (courseId == null) {
                    _selectedCourseIdsByName.remove(entry.key);
                  } else {
                    _selectedCourseIdsByName[entry.key] = courseId;
                  }
                  _selectionPreview = null;
                  _confirmation = null;
                  _selectionError = null;
                });
              },
            ),
          ),
        )
        .toList();
  }
}

class ConditionSummaryCard extends StatelessWidget {
  const ConditionSummaryCard({super.key, required this.summary});

  final ConditionSummary summary;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFFF5F5F5),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            '현재 시간표 조건',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 16),
          _ConditionSummarySection(
            title: '필수 조건',
            items: summary.hardConstraints,
          ),
          const SizedBox(height: 16),
          _ConditionSummarySection(
            title: '선호 조건',
            items: summary.softPreferences,
          ),
        ],
      ),
    );
  }
}

class _ConditionSummarySection extends StatelessWidget {
  const _ConditionSummarySection({
    required this.title,
    required this.items,
  });

  final String title;
  final List<ConditionSummaryItem> items;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return Text('$title: 없음');
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          title,
          style: Theme.of(context).textTheme.titleSmall?.copyWith(
                fontWeight: FontWeight.w700,
              ),
        ),
        const SizedBox(height: 10),
        ...items.map(_ConditionSummaryRow.new),
      ],
    );
  }
}

class _ConditionSummaryRow extends StatelessWidget {
  const _ConditionSummaryRow(this.item);

  final ConditionSummaryItem item;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 3,
            child: Text(
              item.label,
              style: const TextStyle(
                color: Color(0xFF6B7280),
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            flex: 7,
            child: Text(
              item.formattedValue(),
              style: const TextStyle(color: Color(0xFF111111)),
            ),
          ),
        ],
      ),
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
  final List<MajorCourse> courses;
  final String? selectedCourseId;
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: const Color(0xFFE5E7EB)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              courseName,
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            RadioGroup<String?>(
              groupValue: selectedCourseId,
              onChanged: onChanged,
              child: Column(
                children: courses.map((course) {
                  final title =
                      '${course.division}분반 · ${course.professor.isEmpty ? '담당 교수 미정' : course.professor}';
                  final timeText = course.classTimes
                      .map((time) =>
                          '${_dayLabel(time.day)} ${time.start}-${time.end}')
                      .join(' · ');

                  return Column(
                    children: [
                      RadioListTile<String>(
                        value: course.id,
                        title: Text(
                          title,
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                        subtitle: Text(
                          '${course.name.isNotEmpty ? course.name : course.id}${timeText.isNotEmpty ? ' · $timeText' : ''}',
                          style: const TextStyle(color: Color(0xFF6B7280)),
                        ),
                        activeColor: const Color(0xFF111111),
                        // ignore: deprecated_member_use
                        onChanged: onChanged,
                        contentPadding: EdgeInsets.zero,
                      ),
                      if (course != courses.last)
                        const Divider(color: Color(0xFFE5E7EB), height: 1),
                    ],
                  );
                }).toList(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _dayLabel(String day) {
    return switch (day) {
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
}

class _SelectionPreviewCard extends StatelessWidget {
  const _SelectionPreviewCard({required this.preview});

  final MajorPreviewResponse preview;

  @override
  Widget build(BuildContext context) {
    final warning = preview.hasTimeConflict || !preview.canConfirm;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: warning ? const Color(0xFFFEF2F2) : const Color(0xFFF5F5F5),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: warning ? const Color(0xFFEF4444) : const Color(0xFFE5E7EB),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '선택 미리보기',
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 10),
          Text('전공 과목 ${preview.courses.length}개를 선택했습니다.'),
          const SizedBox(height: 8),
          Text('시간 충돌: ${preview.hasTimeConflict ? '있음' : '없음'}'),
          if (preview.conflicts.isNotEmpty) ...[
            const SizedBox(height: 10),
            ...preview.conflicts.map(
              (conflict) => Text(
                '${conflict.firstCourseId} / ${conflict.secondCourseId} · ${_dayLabel(conflict.day)} ${conflict.start}-${conflict.end}',
                style: const TextStyle(color: Color(0xFF991B1B)),
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _dayLabel(String day) {
    return switch (day) {
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
}

class _InfoPill extends StatelessWidget {
  const _InfoPill({
    required this.department,
    required this.parsedCourseCount,
    required this.warnings,
  });

  final String department;
  final int parsedCourseCount;
  final List<String> warnings;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFF8F9FA),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            '전공 정보',
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 8),
          Text('학과: $department'),
          Text('분석한 전공 과목: $parsedCourseCount개'),
          if (warnings.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              '경고: ${warnings.join(', ')}',
              style: const TextStyle(color: Color(0xFFEF4444)),
            ),
          ],
        ],
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: const Color(0xFFE5E7EB)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            title,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 18),
          child,
        ],
      ),
    );
  }
}

class _SecondLoadingScreen extends StatelessWidget {
  const _SecondLoadingScreen();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.white,
        foregroundColor: const Color(0xFF111111),
        elevation: 0,
        title: const Text('시간표 생성 준비'),
      ),
      body: const SafeArea(
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(height: 40),
              CircularProgressIndicator(),
              SizedBox(height: 24),
              Text(
                '시간표를 만드는 중입니다...',
                style: TextStyle(fontSize: 16, color: Color(0xFF374151)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
