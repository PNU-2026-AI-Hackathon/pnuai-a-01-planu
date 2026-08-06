import 'dart:convert';

import 'package:file_picker/file_picker.dart' as picker;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/major_models.dart';
import '../models/quick_preference.dart';
import '../services/planu_api.dart';
import 'file_upload_screen2.dart';

class ChatHomeScreen extends StatefulWidget {
  const ChatHomeScreen({
    super.key,
    this.api,
    this.onPickMajorCatalog,
    this.onContinue,
  });

  final PlanuApi? api;
  final Future<CatalogFile?> Function()? onPickMajorCatalog;
  final ValueChanged<Map<String, dynamic>>? onContinue;

  @override
  State<ChatHomeScreen> createState() => _ChatHomeScreenState();
}

class _ChatHomeScreenState extends State<ChatHomeScreen> {
  static const Color _ink = Color(0xFF111111);
  static const Color _body = Color(0xFF374151);
  static const Color _muted = Color(0xFF6B7280);
  static const Color _hairline = Color(0xFFE5E7EB);
  static const Color _surfaceSoft = Color(0xFFF8F9FA);
  static const Color _surfaceCard = Color(0xFFF5F5F5);
  static const Color _error = Color(0xFFEF4444);
  static const Color _success = Color(0xFF10B981);

  final TextEditingController _departmentController = TextEditingController();
  final TextEditingController _freeTextController = TextEditingController();
  final FocusNode _freeTextFocusNode = FocusNode();

  List<String> _departments = const <String>[];
  String? _selectedDepartment;
  CatalogFile? _selectedFile;
  String? _fileError;
  String? _uploadError;
  bool _isUploading = false;
  bool _uploadSucceeded = false;
  String? _sessionId;
  int _parsedCourseCount = 0;
  List<String> _catalogWarnings = const [];
  Set<QuickPreference> _selectedQuickPreferences = <QuickPreference>{};
  String? _assistantHint;
  bool _isLoadingDepartments = false;
  String? _departmentError;

  PlanuApi get _api => widget.api ?? PlanuApi(baseUrl: 'http://10.0.2.2:8000');

  bool get _hasValidDepartment =>
      (_selectedDepartment ?? _departmentController.text).trim().isNotEmpty &&
      _departments.contains(_selectedDepartment ?? _departmentController.text.trim());

  bool get _hasValidUploadedCatalog => _uploadSucceeded && _sessionId != null;

  bool get _hasAnyPreference =>
      _freeTextController.text.trim().isNotEmpty ||
      _selectedQuickPreferences.isNotEmpty;

  bool get _canContinue =>
      _hasValidDepartment && _hasValidUploadedCatalog && _hasAnyPreference;

  @override
  void initState() {
    super.initState();
    _loadDepartments();
  }

  @override
  void dispose() {
    _departmentController.dispose();
    _freeTextController.dispose();
    _freeTextFocusNode.dispose();
    super.dispose();
  }

  Future<void> _loadDepartments() async {
    setState(() {
      _isLoadingDepartments = true;
      _departmentError = null;
    });

    try {
      final data = await rootBundle.loadString('src/data/departments.json');
      final decoded = (await Future.value(jsonDecode(data))) as List<dynamic>;
      final departments = decoded
          .map((item) {
            if (item is String) {
              return item.trim();
            }
            if (item is Map<String, dynamic>) {
              return (item['department'] ?? item['name'] ?? item['학과명'])?.toString().trim();
            }
            return null;
          })
          .whereType<String>()
          .where((value) => value.isNotEmpty)
          .toSet()
          .toList(growable: false);
      if (!mounted) return;
      setState(() {
        _departments = departments;
        _isLoadingDepartments = false;
      });
    } on Object catch (_) {
      if (!mounted) return;
      setState(() {
        _isLoadingDepartments = false;
        _departmentError = '학과 목록을 불러오지 못했습니다.';
      });
    }
  }

  Future<void> _pickFile() async {
    final pickerFn = widget.onPickMajorCatalog;
    if (pickerFn == null) {
      final picked = await picker.FilePicker.pickFiles(
        type: picker.FileType.custom,
        allowedExtensions: const ['xlsx'],
        withData: true,
      );
      if (picked == null || picked.files.isEmpty) return;
      final file = picked.files.single;
      _handleSelectedFile(
        CatalogFile(
          name: file.name,
          sizeInBytes: file.size,
          path: file.path,
          bytes: file.bytes,
        ),
      );
      return;
    }

    final picked = await pickerFn();
    if (picked != null) {
      _handleSelectedFile(picked);
    }
  }

  void _handleSelectedFile(CatalogFile file) {
    final validationError = _validateFile(file);
    setState(() {
      _fileError = validationError;
      if (validationError == null) {
        _selectedFile = file;
        _uploadSucceeded = false;
        _sessionId = null;
        _parsedCourseCount = 0;
        _catalogWarnings = const [];
        _uploadError = null;
      }
    });
  }

  String? _validateFile(CatalogFile file) {
    final lower = file.name.toLowerCase();
    if (!lower.endsWith('.xlsx')) {
      return '.xlsx 파일만 업로드할 수 있습니다.';
    }
    return null;
  }

  Future<void> _uploadCatalog() async {
    final file = _selectedFile;
    final department = (_selectedDepartment ?? _departmentController.text).trim();
    if (file == null || department.isEmpty || _isUploading) return;

    setState(() {
      _isUploading = true;
      _uploadError = null;
      _assistantHint = '수강편람을 분석하고 있어요.';
    });

    try {
      final response = await _api.uploadMajorDetails(
        department: department,
        fileName: file.name,
        bytes: file.bytes ?? Uint8List(0),
      );
      if (!mounted) return;
      setState(() {
        _uploadSucceeded = true;
        _sessionId = response['session_id']?.toString();
        _parsedCourseCount = int.tryParse('${response['parsed_course_count']}') ?? 0;
        _catalogWarnings = (response['warnings'] as List?)?.whereType<String>().toList() ?? const [];
        _assistantHint = '수강편람 분석이 완료되었습니다.';
        _uploadError = null;
      });
    } on ApiError catch (error) {
      if (!mounted) return;
      setState(() {
        _uploadSucceeded = false;
        _uploadError = error.message;
        _assistantHint = '업로드에 실패했습니다. 다시 시도해 주세요.';
      });
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _uploadSucceeded = false;
        _uploadError = '업로드 중 문제가 발생했습니다.';
        _assistantHint = '업로드에 실패했습니다. 다시 시도해 주세요.';
      });
      debugPrint('catalog upload failed: $error');
    } finally {
      if (mounted) {
        setState(() => _isUploading = false);
      }
    }
  }

  void _togglePreference(QuickPreference preference) {
    setState(() {
      if (_selectedQuickPreferences.contains(preference)) {
        _selectedQuickPreferences.remove(preference);
      } else {
        _selectedQuickPreferences.add(preference);
      }
    });
  }

  void _reset() {
    setState(() {
      _departmentController.clear();
      _freeTextController.clear();
      _selectedDepartment = null;
      _selectedFile = null;
      _fileError = null;
      _uploadError = null;
      _isUploading = false;
      _uploadSucceeded = false;
      _sessionId = null;
      _parsedCourseCount = 0;
      _catalogWarnings = const [];
      _selectedQuickPreferences = <QuickPreference>{};
      _assistantHint = null;
    });
  }

  void _continue() {
    if (!_canContinue) return;
    widget.onContinue?.call({
      'selectedDepartment': (_selectedDepartment ?? _departmentController.text).trim(),
      'sessionId': _sessionId,
      'parsedCourseCount': _parsedCourseCount,
      'catalogWarnings': _catalogWarnings,
      'selectedQuickPreferences': _selectedQuickPreferences.toList(),
      'freeText': _freeTextController.text.trim(),
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final mediaQuery = MediaQuery.of(context);

    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        foregroundColor: _ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        title: const Text('PlaNU'),
        actions: [
          TextButton(
            onPressed: _reset,
            child: const Text('처음부터'),
          ),
        ],
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 900),
            child: ListView(
              padding: EdgeInsets.fromLTRB(
                24,
                24,
                24,
                24 + mediaQuery.viewInsets.bottom,
              ),
              children: [
                _ChatHeader(theme: theme),
                const SizedBox(height: 24),
                _ChatBubble(
                  title: '안녕하세요. PlaNU입니다.',
                  body: '전공 수강편람 파일을 업로드하고\n원하는 시간표 조건을 말씀해주세요.\n\n예:\n- 금요일은 반드시 공강\n- 오전 10시 이전 수업 제외\n- 18학점 구성\n- 인공지능 관련 교양 선호',
                ),
                const SizedBox(height: 24),
                _SectionCard(
                  title: '학과 선택',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      TextField(
                        key: const Key('department-field'),
                        controller: _departmentController,
                        onChanged: (value) {
                          setState(() {
                            _selectedDepartment = null;
                            if (_departments.contains(value.trim())) {
                              _selectedDepartment = value.trim();
                            }
                          });
                        },
                        decoration: InputDecoration(
                          hintText: '학과명을 입력하세요',
                          filled: true,
                          fillColor: Colors.white,
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                        ),
                      ),
                      if (_departments.isNotEmpty) ...[
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: _departments
                              .where((value) => value.toLowerCase().contains(_departmentController.text.toLowerCase()))
                              .take(6)
                              .map(
                                (value) => GestureDetector(
                                  onTap: () {
                                    setState(() {
                                      _departmentController.text = value;
                                      _selectedDepartment = value;
                                    });
                                  },
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                    decoration: BoxDecoration(
                                      color: _selectedDepartment == value ? _ink : _surfaceSoft,
                                      borderRadius: BorderRadius.circular(999),
                                      border: Border.all(color: _hairline),
                                    ),
                                    child: Text(
                                      value,
                                      style: TextStyle(
                                        color: _selectedDepartment == value ? Colors.white : _ink,
                                        fontSize: 13,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  ),
                                ),
                              )
                              .toList(),
                        ),
                      ],
                      if (_isLoadingDepartments) ...[
                        const SizedBox(height: 12),
                        const LinearProgressIndicator(),
                      ],
                      if (_departmentError != null) ...[
                        const SizedBox(height: 8),
                        Text(
                          _departmentError!,
                          style: const TextStyle(color: _error),
                        ),
                      ],
                      if (_selectedDepartment != null) ...[
                        const SizedBox(height: 12),
                        Text(
                          '선택한 학과: $_selectedDepartment',
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 18),
                _SectionCard(
                  title: '전공 수강편람',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (_selectedFile == null)
                        OutlinedButton.icon(
                          key: const Key('catalog-picker-button'),
                          onPressed: _isUploading ? null : _pickFile,
                          icon: const Icon(Icons.upload_file_outlined),
                          label: const Text('파일 선택'),
                          style: OutlinedButton.styleFrom(
                            minimumSize: const Size(0, 46),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                          ),
                        )
                      else
                        _SelectedCatalogCard(
                          file: _selectedFile!,
                          onRemove: _isUploading ? null : () => setState(() => _selectedFile = null),
                        ),
                      const SizedBox(height: 12),
                      Text(
                        '지원 형식: .xlsx',
                        style: TextStyle(color: _muted, fontSize: 13),
                      ),
                      if (_fileError != null) ...[
                        const SizedBox(height: 8),
                        Text(_fileError!, style: const TextStyle(color: _error)),
                      ],
                      const SizedBox(height: 16),
                      FilledButton.icon(
                        key: const Key('upload-catalog-button'),
                        onPressed: _selectedFile != null && !_isUploading ? _uploadCatalog : null,
                        icon: _isUploading
                            ? const SizedBox.square(
                                dimension: 16,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                              )
                            : const Icon(Icons.auto_awesome_outlined),
                        label: Text(_isUploading ? '수강편람을 분석하고 있어요.' : '수강편람 분석하기'),
                        style: FilledButton.styleFrom(
                          minimumSize: const Size.fromHeight(48),
                          backgroundColor: _ink,
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                        ),
                      ),
                      if (_uploadError != null) ...[
                        const SizedBox(height: 12),
                        Text(_uploadError!, style: const TextStyle(color: _error)),
                      ],
                      if (_uploadSucceeded) ...[
                        const SizedBox(height: 12),
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: const Color(0xFFECFDF5),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Row(
                            children: [
                              const Icon(Icons.check_circle_outline, color: _success),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  '수강편람 분석이 완료되었습니다.\n전공 과목 $_parsedCourseCount개를 확인했습니다.',
                                  style: const TextStyle(color: _success, fontWeight: FontWeight.w600),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 18),
                _SectionCard(
                  title: '원하는 시간표 조건',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      TextField(
                        key: const Key('free-text-field'),
                        controller: _freeTextController,
                        focusNode: _freeTextFocusNode,
                        minLines: 3,
                        maxLines: 5,
                        maxLength: 2000,
                        decoration: InputDecoration(
                          hintText: '예: 금요일은 공강으로 하고 오전 10시 이전 수업은 제외해주세요.',
                          filled: true,
                          fillColor: Colors.white,
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                      Text('빠른 조건', style: theme.textTheme.titleSmall?.copyWith(color: _ink)),
                      const SizedBox(height: 10),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: QuickPreference.values.map((preference) {
                          final selected = _selectedQuickPreferences.contains(preference);
                          return FilterChip(
                            key: Key('quick-pref-${preference.key}'),
                            label: Text(preference.label),
                            selected: selected,
                            onSelected: (_) => _togglePreference(preference),
                            showCheckmark: true,
                            selectedColor: const Color(0xFFE5E7EB),
                            side: const BorderSide(color: _hairline),
                            labelStyle: TextStyle(color: selected ? _ink : _body),
                            avatar: selected ? const Icon(Icons.check, size: 16) : null,
                          );
                        }).toList(),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),
                ElevatedButton(
                  key: const Key('continue-button'),
                  onPressed: _canContinue ? _continue : null,
                  style: ElevatedButton.styleFrom(
                    minimumSize: const Size.fromHeight(50),
                    backgroundColor: _ink,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  child: const Text('과목 확인으로 이동'),
                ),
                if (_assistantHint != null) ...[
                  const SizedBox(height: 12),
                  Text(_assistantHint!, style: const TextStyle(color: _muted)),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ChatHeader extends StatelessWidget {
  const _ChatHeader({required this.theme});

  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 40,
          height: 40,
          decoration: const BoxDecoration(
            color: _ChatHomeScreenState._ink,
            shape: BoxShape.circle,
          ),
          child: const Icon(Icons.auto_awesome, color: Colors.white, size: 20),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('PlaNU', style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
              Text(
                '부산대학교 AI 시간표 도우미',
                style: TextStyle(color: _ChatHomeScreenState._muted, fontSize: 13),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ChatBubble extends StatelessWidget {
  const _ChatBubble({required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _ChatHomeScreenState._surfaceCard,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.chat_bubble_outline, size: 18, color: _ChatHomeScreenState._ink),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 6),
                Text(body, style: const TextStyle(height: 1.5, color: _ChatHomeScreenState._body)),
              ],
            ),
          ),
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
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: _ChatHomeScreenState._hairline),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          child,
        ],
      ),
    );
  }
}

class _SelectedCatalogCard extends StatelessWidget {
  const _SelectedCatalogCard({required this.file, required this.onRemove});

  final CatalogFile file;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        border: Border.all(color: _ChatHomeScreenState._hairline),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          const Icon(Icons.description_outlined),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(file.name, maxLines: 1, overflow: TextOverflow.ellipsis),
                Text(_formatFileSize(file.sizeInBytes), style: const TextStyle(color: _ChatHomeScreenState._muted)),
              ],
            ),
          ),
          if (onRemove != null)
            TextButton(onPressed: onRemove, child: const Text('삭제')),
        ],
      ),
    );
  }

  static String _formatFileSize(int bytes) {
    if (bytes >= 1024 * 1024) {
      final megabytes = bytes / (1024 * 1024);
      final digits = megabytes == megabytes.truncateToDouble() ? 0 : 1;
      return '${megabytes.toStringAsFixed(digits)}MB';
    }
    if (bytes >= 1024) return '${(bytes / 1024).toStringAsFixed(0)}KB';
    return '$bytes B';
  }
}
