import 'package:file_picker/file_picker.dart' as picker;
import 'package:flutter/material.dart';

import '../models/app_flow_state.dart';
import '../models/condition_summary_models.dart';
import '../models/major_models.dart';
import '../repositories/major_repository.dart';
import '../services/major_api.dart';
import '../services/planu_api.dart';
import '../services/session_error_handler.dart';
import '../widgets/flow_step_badge.dart';
import 'file_upload_screen2.dart' show CatalogFile;
import 'timetable_loading_screen.dart';

class SecondScreen extends StatefulWidget {
  const SecondScreen({
    super.key,
    required this.api,
    required this.selectedDepartment,
    required this.sessionId,
    required this.parsedCourseCount,
    required this.catalogWarnings,
    required this.flow,
    this.majorRepository,
    this.onSessionExpired,
  });

  final PlanuApi api;
  final String selectedDepartment;
  final String sessionId;
  final int parsedCourseCount;
  final List<String> catalogWarnings;
  final AppFlowState flow;
  final MajorRepository? majorRepository;
  final VoidCallback? onSessionExpired;

  @override
  State<SecondScreen> createState() => _SecondScreenState();
}

class _SecondScreenState extends State<SecondScreen> {
  final _messageController = TextEditingController();
  final _conditionFocusNode = FocusNode();
  final Map<String, String> _selectedCourseIdsByName = {};

  ConditionSummary? _latestConditionSummary;
  String? _latestConditionText;
  final List<String> _conditionHistory = [];
  bool _showAllConditionHistory = false;
  List<MajorCourse> _majorCourses = const [];
  MajorPreviewResponse? _selectionPreview;
  MajorConfirmResponse? _confirmation;

  String? _courseLoadError;
  String? _selectionError;
  String? _actionHint;
  String? _conditionError;
  bool _isLoadingCourses = true;
  bool _isSendingCondition = false;
  bool _isPreviewing = false;
  bool _isConfirming = false;
  bool _isContinuing = false;
  String? _deletingConditionId;
  bool _showElectiveSettings = false;
  bool _isPickingElectiveCatalog = false;
  String? _electiveCatalogError;

  static const _electiveAreas = {
    1: '사상과역사',
    2: '사회와문화',
    3: '문학과예술',
    4: '과학과기술',
    5: '건강과레포츠',
    6: '외국어',
    7: '융복합',
    8: '효원브릿지',
    9: '인성과봉사',
  };

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
    _conditionFocusNode.dispose();
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
      if (handleSessionExpiredError(
        context,
        error,
        flow: widget.flow,
        onSessionExpired: widget.onSessionExpired ?? () {},
      )) {
        return;
      }
      setState(() => _courseLoadError = error.message);
    } finally {
      if (mounted) {
        setState(() => _isLoadingCourses = false);
      }
    }
  }

  Future<void> _sendCondition() async {
    final message = _messageController.text.trim();
    if (_isSendingCondition) return;
    if (message.isEmpty) {
      setState(() => _conditionError = '시간표 조건을 입력해 주세요.');
      _conditionFocusNode.requestFocus();
      return;
    }

    setState(() {
      _messageController.clear();
      _isSendingCondition = true;
      _actionHint = null;
      _conditionError = null;
    });

    try {
      final response = await widget.api.sendChatMessage(
        sessionId: widget.sessionId,
        message: message,
      );
      if (!mounted) return;
      setState(() {
        _latestConditionText = message;
        _conditionHistory.insert(0, message);
        if (response.conditionSummary != null) {
          _latestConditionSummary = response.conditionSummary;
        }
        _actionHint = response.message;
      });
    } on ApiError catch (error) {
      if (!mounted) return;
      if (handleSessionExpiredError(
        context,
        error,
        flow: widget.flow,
        onSessionExpired: widget.onSessionExpired ?? () {},
      )) {
        return;
      }
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
      if (handleSessionExpiredError(
        context,
        error,
        flow: widget.flow,
        onSessionExpired: widget.onSessionExpired ?? () {},
      )) {
        return;
      }
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
      if (handleSessionExpiredError(
        context,
        error,
        flow: widget.flow,
        onSessionExpired: widget.onSessionExpired ?? () {},
      )) {
        return;
      }
      setState(() => _selectionError = error.message);
    } finally {
      if (mounted) {
        setState(() => _isConfirming = false);
      }
    }
  }

  void _openLoadingScreen() {
    widget.flow
      ..department = widget.selectedDepartment
      ..sessionId = widget.sessionId
      ..majorConfirmation = _confirmation
      ..preferencePrompt = '';
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        settings: const RouteSettings(name: '/timetable-loading'),
        builder: (_) => TimetableLoadingScreen(
          flow: widget.flow,
          api: widget.api,
          onSessionExpired: widget.onSessionExpired ?? () {},
        ),
      ),
    );
  }

  Future<void> _continueToTimetable() async {
    if (!_canContinue || _isContinuing) return;
    setState(() {
      _isContinuing = true;
      _selectionError = null;
      _actionHint = null;
    });
    try {
      if (_confirmation == null) {
        await _previewSelection();
        if (!mounted || _selectionPreview?.isConfirmable != true) return;
        await _confirmSelection();
        if (!mounted || _confirmation == null) return;
      }
      final summary = await widget.api.confirmTimetableConditions(
        sessionId: widget.sessionId,
      );
      if (!mounted) return;
      setState(() => _latestConditionSummary = summary);
      _openLoadingScreen();
    } on ApiError catch (error) {
      if (!mounted) return;
      if (handleSessionExpiredError(
        context,
        error,
        flow: widget.flow,
        onSessionExpired: widget.onSessionExpired ?? () {},
      )) {
        return;
      }
      setState(() {
        _conditionError = error.message;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message)),
      );
    } finally {
      if (mounted) setState(() => _isContinuing = false);
    }
  }

  Future<void> _deleteCondition(
    ConditionSummaryItem item,
    String scope, {
    Object? value,
  }) async {
    final deleteId = '$scope:${item.key}:${value ?? '*'}';
    if (_deletingConditionId != null) return;
    setState(() {
      _deletingConditionId = deleteId;
      _conditionError = null;
      _actionHint = null;
    });
    try {
      final summary = await widget.api.deleteTimetableCondition(
        sessionId: widget.sessionId,
        scope: scope,
        key: item.key,
        value: value,
      );
      if (!mounted) return;
      setState(() {
        _latestConditionSummary = summary;
        _actionHint = '조건을 삭제했습니다.';
      });
    } on ApiError catch (error) {
      if (!mounted) return;
      if (handleSessionExpiredError(
        context,
        error,
        flow: widget.flow,
        onSessionExpired: widget.onSessionExpired ?? () {},
      )) {
        return;
      }
      setState(() => _conditionError = error.message);
    } finally {
      if (mounted) {
        setState(() => _deletingConditionId = null);
      }
    }
  }

  bool get _canGenerate =>
      _latestConditionSummary?.generationReadiness.ready == true &&
      _confirmation != null;

  bool get _hasUploadedElectiveCatalog =>
      widget.flow.electiveCatalogBytes != null || widget.flow.electiveCatalogName != null;

  bool get _canContinue =>
      _selectedCourseIdsByName.isNotEmpty &&
      _latestConditionSummary != null &&
      (!_hasUploadedElectiveCatalog || widget.flow.electiveArea != null) &&
      !_isSendingCondition &&
      !_isPreviewing &&
      !_isConfirming &&
      !_isContinuing;

  String get _generateStatusMessage {
    if (_canGenerate) {
      return '시간표를 만들 준비가 완료되었습니다.';
    }
    if (_selectedCourseIdsByName.isEmpty) {
      return '시간표 생성 전, 전공 과목을 선택해 주세요.';
    }
    if (_latestConditionSummary == null) {
      return '시간표 조건을 입력하고 적용 결과를 확인해 주세요.';
    }
    if (_hasUploadedElectiveCatalog && widget.flow.electiveArea == null) {
      return '교양 수강편람 파일을 직접 업로드할 때는 교양 영역을 선택해 주세요.';
    }
    return '시간표 생성하기 버튼을 누르면 전공 분반과 현재 시간표 조건을 확정합니다.';
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
                      : Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            AppliedConditionSummaryCard(
                              summary: _latestConditionSummary!,
                              deletingConditionId: _deletingConditionId,
                              onDelete: _deleteCondition,
                            ),
                            const SizedBox(height: 14),
                            OutlinedButton(
                              key: const Key('addMoreConditionButton'),
                              onPressed: _focusConditionInput,
                              child: const Text('조건 더 추가하기'),
                            ),
                          ],
                        ),
                ),
                const SizedBox(height: 24),
                _SectionCard(
                  title: '4. 교양영역 조건설정',
                  child: _buildElectiveSettingsSection(theme),
                ),
                const SizedBox(height: 24),
                _SectionCard(
                  title: '5. 생성 준비',
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
                        onPressed: _canContinue ? _continueToTimetable : null,
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFF111111),
                          minimumSize: const Size.fromHeight(52),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                        ),
                        child: _isContinuing
                            ? const SizedBox.square(
                                dimension: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : const Text('시간표 생성하기'),
                      ),
                    ],
                  ),
                ),
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
        const Text(
          '원하는 교양 시간표 조건을 편하게 입력해 주세요.',
          style: TextStyle(color: Color(0xFF374151), height: 1.5),
        ),
        const SizedBox(height: 8),
        const Text(
          '예) 금요일은 공강으로 하고 오전 수업은 피하고 싶어요.',
          style: TextStyle(color: Color(0xFF6B7280)),
        ),
        const SizedBox(height: 16),
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
        if (_conditionHistory.isNotEmpty) ...[
          _ConditionHistoryPanel(
            entries: _showAllConditionHistory
                ? _conditionHistory
                : _conditionHistory.take(3).toList(),
            hasMore: _conditionHistory.length > 3,
            showingAll: _showAllConditionHistory,
            onToggle: () => setState(
              () => _showAllConditionHistory = !_showAllConditionHistory,
            ),
          ),
          const SizedBox(height: 16),
        ],
        TextField(
          key: const Key('secondScreenConditionField'),
          controller: _messageController,
          focusNode: _conditionFocusNode,
          onChanged: (_) {
            if (_conditionError != null) {
              setState(() => _conditionError = null);
            }
          },
          minLines: 2,
          maxLines: 5,
          enabled: !_isSendingCondition,
          decoration: InputDecoration(
            hintText: '예) 금요일 공강, 오전 10시 이전 수업은 없었으면 좋겠어요.',
            filled: true,
            fillColor: const Color(0xFFF8F9FA),
            errorText: _conditionError,
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
              : const Text('조건 추가'),
        ),
        if (_isSendingCondition) ...[
          const SizedBox(height: 12),
          const Text(
            'PlaNU가 조건을 확인하고 있어요...',
            textAlign: TextAlign.center,
            style: TextStyle(color: Color(0xFF6B7280)),
          ),
        ],
        if (_actionHint != null && !_isSendingCondition) ...[
          const SizedBox(height: 12),
          Text(
            _actionHint!,
            style: const TextStyle(color: Color(0xFF374151)),
          ),
        ],
      ],
    );
  }

  Widget _buildElectiveSettingsSection(ThemeData theme) {
    final fileName = widget.flow.electiveCatalogName;
    final selectedArea = widget.flow.electiveArea;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        InkWell(
          key: const Key('electiveSettingsToggle'),
          borderRadius: BorderRadius.circular(8),
          onTap: () =>
              setState(() => _showElectiveSettings = !_showElectiveSettings),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    fileName == null
                        ? '업로드하지 않으면 서버 기본 교양 데이터를 사용합니다.'
                        : '업로드 파일: $fileName',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: const Color(0xFF374151),
                    ),
                  ),
                ),
                Icon(
                  _showElectiveSettings
                      ? Icons.keyboard_arrow_up
                      : Icons.keyboard_arrow_down,
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        Text(
          selectedArea == null
              ? '영역을 선택하지 않으면 전체 교양 영역을 후보 풀로 사용합니다.'
              : '선택 영역: ${_electiveAreas[selectedArea] ?? '$selectedArea영역'}',
          style: const TextStyle(color: Color(0xFF6B7280)),
        ),
        if (_showElectiveSettings) ...[
          const SizedBox(height: 16),
          DropdownButtonFormField<int>(
            key: const Key('secondScreenElectiveAreaField'),
            initialValue: widget.flow.electiveArea,
            decoration: const InputDecoration(
              labelText: '교양 영역',
              helperText: '선택한 영역만 교양 후보에 포함됩니다.',
              border: OutlineInputBorder(),
            ),
            items: [
              const DropdownMenuItem<int>(
                child: Text('전체 영역 사용'),
              ),
              ..._electiveAreas.entries.map(
                (entry) => DropdownMenuItem<int>(
                  value: entry.key,
                  child: Text(entry.value),
                ),
              ),
            ],
            onChanged: (value) => setState(() {
              widget.flow.electiveArea = value;
            }),
          ),
          const SizedBox(height: 12),
          if (fileName == null)
            OutlinedButton.icon(
              key: const Key('secondScreenElectiveUploadButton'),
              onPressed:
                  _isPickingElectiveCatalog ? null : _pickElectiveCatalog,
              icon: _isPickingElectiveCatalog
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.upload_file_outlined),
              label: Text(_isPickingElectiveCatalog ? '파일 선택 중' : '교양 수강편람 업로드'),
            )
          else
            _SelectedElectiveCatalog(
              fileName: fileName,
              sizeInBytes: widget.flow.electiveCatalogBytes?.length,
              onRemove: () => setState(() {
                widget.flow.electiveCatalogName = null;
                widget.flow.electiveCatalogBytes = null;
                _electiveCatalogError = null;
              }),
            ),
          if (_electiveCatalogError != null) ...[
            const SizedBox(height: 8),
            Text(
              _electiveCatalogError!,
              style: const TextStyle(color: Color(0xFFEF4444)),
            ),
          ],
        ],
      ],
    );
  }

  Future<void> _pickElectiveCatalog() async {
    setState(() {
      _isPickingElectiveCatalog = true;
      _electiveCatalogError = null;
    });
    try {
      final result = await picker.FilePicker.pickFiles(
        type: picker.FileType.custom,
        allowedExtensions: const ['xlsx'],
        withData: true,
      );
      if (!mounted || result == null || result.files.isEmpty) return;
      final file = result.files.single;
      final selected = CatalogFile(
        name: file.name,
        sizeInBytes: file.size,
        path: file.path,
        bytes: file.bytes,
      );
      final error = _validateElectiveCatalog(selected);
      setState(() {
        _electiveCatalogError = error;
        if (error == null) {
          widget.flow.electiveCatalogName = selected.name;
          widget.flow.electiveCatalogBytes = selected.bytes;
        }
      });
    } on Object {
      if (mounted) {
        setState(() => _electiveCatalogError = '파일을 선택하지 못했습니다. 다시 시도해 주세요.');
      }
    } finally {
      if (mounted) setState(() => _isPickingElectiveCatalog = false);
    }
  }

  String? _validateElectiveCatalog(CatalogFile file) {
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      return '.xlsx 형식의 교양 수강편람 파일을 선택해 주세요.';
    }
    if (file.sizeInBytes > 5 * 1024 * 1024) {
      return '파일 크기는 5MB 이하여야 합니다.';
    }
    if (file.bytes == null) return '선택한 파일을 읽을 수 없습니다.';
    return null;
  }

  void _focusConditionInput() {
    _conditionFocusNode.requestFocus();
    final inputContext = _conditionFocusNode.context;
    if (inputContext != null) {
      Scrollable.ensureVisible(
        inputContext,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
        alignment: 0.25,
      );
    }
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

class _ConditionHistoryPanel extends StatelessWidget {
  const _ConditionHistoryPanel({
    required this.entries,
    required this.hasMore,
    required this.showingAll,
    required this.onToggle,
  });

  final List<String> entries;
  final bool hasMore;
  final bool showingAll;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(color: const Color(0xFFE5E7EB)),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '최근 입력',
              style: TextStyle(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            for (final entry in entries)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text(
                  entry,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Color(0xFF374151)),
                ),
              ),
            if (hasMore)
              TextButton(
                onPressed: onToggle,
                child: Text(showingAll ? '최근 입력만 보기' : '이전 입력 보기'),
              ),
          ],
        ),
      );
}

class ConditionSummaryCard extends StatelessWidget {
  const ConditionSummaryCard({
    super.key,
    required this.summary,
    required this.deletingConditionId,
    required this.onDelete,
  });

  final ConditionSummary summary;
  final String? deletingConditionId;
  final Future<void> Function(
    ConditionSummaryItem item,
    String scope, {
    Object? value,
  }) onDelete;

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

class AppliedConditionSummaryCard extends StatelessWidget {
  const AppliedConditionSummaryCard({
    super.key,
    required this.summary,
    required this.deletingConditionId,
    required this.onDelete,
  });

  final ConditionSummary summary;
  final String? deletingConditionId;
  final Future<void> Function(
    ConditionSummaryItem item,
    String scope, {
    Object? value,
  }) onDelete;

  @override
  Widget build(BuildContext context) {
    final hardItems = summary.hardConstraints
        .where((item) => item.status == ConditionItemStatus.set)
        .toList();
    final softItems = summary.softPreferences
        .where((item) => item.status == ConditionItemStatus.set)
        .toList();
    final hasConditions = hardItems.isNotEmpty || softItems.isNotEmpty;

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
          if (!hasConditions)
            const Text('아직 적용된 시간표 조건이 없습니다.')
          else ...[
            _AppliedConditionSection(
              title: '필수 조건',
              scope: 'hard',
              items: hardItems,
              deletingConditionId: deletingConditionId,
              onDelete: onDelete,
            ),
            if (hardItems.isNotEmpty && softItems.isNotEmpty)
              const SizedBox(height: 16),
            _AppliedConditionSection(
              title: '선호 조건',
              scope: 'soft',
              items: softItems,
              deletingConditionId: deletingConditionId,
              onDelete: onDelete,
            ),
          ],
        ],
      ),
    );
  }
}

class _AppliedConditionSection extends StatelessWidget {
  const _AppliedConditionSection({
    required this.title,
    required this.scope,
    required this.items,
    required this.deletingConditionId,
    required this.onDelete,
  });

  final String title;
  final String scope;
  final List<ConditionSummaryItem> items;
  final String? deletingConditionId;
  final Future<void> Function(
    ConditionSummaryItem item,
    String scope, {
    Object? value,
  }) onDelete;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
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
        ...items.map(
          (item) => _AppliedConditionRow(
            item: item,
            scope: scope,
            deletingConditionId: deletingConditionId,
            onDelete: onDelete,
          ),
        ),
      ],
    );
  }
}

class _AppliedConditionRow extends StatelessWidget {
  const _AppliedConditionRow({
    required this.item,
    required this.scope,
    required this.deletingConditionId,
    required this.onDelete,
  });

  final ConditionSummaryItem item;
  final String scope;
  final String? deletingConditionId;
  final Future<void> Function(
    ConditionSummaryItem item,
    String scope, {
    Object? value,
  }) onDelete;

  @override
  Widget build(BuildContext context) {
    final values = _conditionDeleteValues(item);
    if (values.length > 1) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              item.label,
              style: const TextStyle(
                color: Color(0xFF6B7280),
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: values
                  .map(
                    (value) => InputChip(
                      label: Text(value.label),
                      onDeleted: deletingConditionId == null
                          ? () => onDelete(item, scope, value: value.value)
                          : null,
                      deleteIcon: deletingConditionId ==
                              '$scope:${item.key}:${value.value}'
                          ? const SizedBox.square(
                              dimension: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.close, size: 16),
                    ),
                  )
                  .toList(),
            ),
          ],
        ),
      );
    }

    final deleteId = '$scope:${item.key}:*';
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
          IconButton(
            tooltip: '조건 삭제',
            onPressed: deletingConditionId == null
                ? () => onDelete(item, scope)
                : null,
            icon: deletingConditionId == deleteId
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.close, size: 18),
          ),
        ],
      ),
    );
  }
}

class _ConditionDeleteValue {
  const _ConditionDeleteValue({required this.label, required this.value});

  final String label;
  final Object value;
}

List<_ConditionDeleteValue> _conditionDeleteValues(ConditionSummaryItem item) {
  final raw = item.rawValue;
  if (raw is! List || raw.length <= 1) return const [];
  final labels = item.displayValue
          ?.split(',')
          .map((value) => value.trim())
          .where((value) => value.isNotEmpty)
          .toList() ??
      const <String>[];
  return [
    for (var index = 0; index < raw.length; index += 1)
      _ConditionDeleteValue(
        label: index < labels.length ? labels[index] : '${raw[index]}',
        value: raw[index] as Object,
      ),
  ];
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
            Column(
                children: courses.map((course) {
                  final title =
                      '${course.division}분반 · ${course.professor.isEmpty ? '담당 교수 미정' : course.professor}';
                  final timeText = course.classTimes
                      .map((time) =>
                          '${_dayLabel(time.day)} ${time.start}-${time.end}')
                      .join(' · ');

                  return Column(
                    children: [
                      InkWell(
                        key: Key('majorCourse-${course.id}'),
                        onTap: () => onChanged(
                          course.id == selectedCourseId ? null : course.id,
                        ),
                        borderRadius: BorderRadius.circular(8),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              _SelectionCircle(
                                selected: course.id == selectedCourseId,
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      title,
                                      style: const TextStyle(
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(
                                      '${course.name.isNotEmpty ? course.name : course.id}${timeText.isNotEmpty ? ' · $timeText' : ''}',
                                      style: const TextStyle(
                                        color: Color(0xFF6B7280),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      if (course != courses.last)
                        const Divider(color: Color(0xFFE5E7EB), height: 1),
                    ],
                  );
                }).toList(),
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

class _SelectionCircle extends StatelessWidget {
  const _SelectionCircle({required this.selected});

  final bool selected;

  @override
  Widget build(BuildContext context) => AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        width: 22,
        height: 22,
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(
            color: selected ? const Color(0xFF111111) : const Color(0xFF9CA3AF),
            width: 2,
          ),
        ),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: selected ? const Color(0xFF111111) : Colors.transparent,
          ),
        ),
      );
}

class _SelectedElectiveCatalog extends StatelessWidget {
  const _SelectedElectiveCatalog({
    required this.fileName,
    required this.onRemove,
    this.sizeInBytes,
  });

  final String fileName;
  final int? sizeInBytes;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(color: const Color(0xFFE5E7EB)),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          children: [
            const Icon(Icons.description_outlined),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                sizeInBytes == null
                    ? fileName
                    : '$fileName\n${_formatBytes(sizeInBytes!)}',
              ),
            ),
            IconButton(
              key: const Key('secondScreenElectiveRemoveButton'),
              onPressed: onRemove,
              tooltip: '선택한 파일 제거',
              icon: const Icon(Icons.close),
            ),
          ],
        ),
      );

  static String _formatBytes(int bytes) => bytes >= 1024 * 1024
      ? '${(bytes / (1024 * 1024)).toStringAsFixed(1)}MB'
      : '${(bytes / 1024).toStringAsFixed(0)}KB';
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

// ignore: unused_element
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
