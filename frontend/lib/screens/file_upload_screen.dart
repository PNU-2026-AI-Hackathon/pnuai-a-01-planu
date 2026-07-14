import 'package:flutter/material.dart';

/// A file selected from a platform file picker.
class CatalogFile {
  const CatalogFile({required this.name, required this.sizeInBytes});

  final String name;
  final int sizeInBytes;
}

typedef CatalogFilePicker = Future<CatalogFile?> Function();
typedef CatalogAnalyzeCallback = Future<void> Function(
  CatalogFile majorCatalogFile,
  CatalogFile? electiveCatalogFile,
);

class FileUploadScreen extends StatefulWidget {
  const FileUploadScreen({
    super.key,
    this.onPickMajorCatalog,
    this.onPickElectiveCatalog,
    this.onAnalyze,
    this.initialMajorCatalog,
    this.initialElectiveCatalog,
    this.maxFileSizeInBytes = 10 * 1024 * 1024,
  });

  final CatalogFilePicker? onPickMajorCatalog;
  final CatalogFilePicker? onPickElectiveCatalog;
  final CatalogAnalyzeCallback? onAnalyze;
  final CatalogFile? initialMajorCatalog;
  final CatalogFile? initialElectiveCatalog;
  final int maxFileSizeInBytes;

  @override
  State<FileUploadScreen> createState() => _FileUploadScreenState();
}

class _FileUploadScreenState extends State<FileUploadScreen> {
  static const Color _ink = Color(0xFF111111);
  static const Color _body = Color(0xFF374151);
  static const Color _muted = Color(0xFF6B7280);
  static const Color _hairline = Color(0xFFE5E7EB);
  static const Color _surfaceSoft = Color(0xFFF8F9FA);
  static const Color _surfaceCard = Color(0xFFF5F5F5);
  static const Color _error = Color(0xFFEF4444);
  static const TextStyle _displayStyle = TextStyle(
    fontSize: 36,
    fontWeight: FontWeight.w600,
    letterSpacing: -1,
    height: 1.15,
  );
  static const TextStyle _titleStyle = TextStyle(
    fontSize: 18,
    fontWeight: FontWeight.w600,
    height: 1.4,
  );
  static const TextStyle _bodyStyle = TextStyle(fontSize: 16, height: 1.5);
  static const TextStyle _bodySmallStyle = TextStyle(
    fontSize: 14,
    height: 1.5,
  );
  static const TextStyle _captionStyle = TextStyle(
    fontSize: 13,
    fontWeight: FontWeight.w500,
    height: 1.4,
  );
  static const TextStyle _buttonStyle = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w600,
    height: 1,
  );

  CatalogFile? _majorCatalog;
  CatalogFile? _electiveCatalog;
  String? _majorError;
  String? _electiveError;
  bool _isPicking = false;
  bool _isAnalyzing = false;

  bool get _canAnalyze =>
      _majorCatalog != null && !_isPicking && !_isAnalyzing;

  @override
  void initState() {
    super.initState();
    _majorCatalog = widget.initialMajorCatalog;
    _electiveCatalog = widget.initialElectiveCatalog;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        foregroundColor: _ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        title: const Text(
          'PlaNU',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        ),
        centerTitle: false,
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 40, 24, 32),
              children: <Widget>[
                const _StepPill(),
                const SizedBox(height: 24),
                Text(
                  '수강편람 업로드',
                  textAlign: TextAlign.left,
                  style: _displayStyle.copyWith(color: _ink),
                ),
                const SizedBox(height: 12),
                Text(
                  '학생지원시스템에서 내려받은 수강편람 파일을 올려주세요.',
                  textAlign: TextAlign.left,
                  style: _bodyStyle.copyWith(color: _body),
                ),
                const SizedBox(height: 32),
                _FilePickerCard(
                  title: '1학년 전공 수강편람',
                  description: '전공기초·전공필수 과목이 포함된 파일이 필요합니다.',
                  isRequired: true,
                  file: _majorCatalog,
                  errorText: _majorError,
                  isBusy: _isPicking,
                  onPick: () => _pickFile(isMajor: true),
                  onRemove: () => _removeFile(isMajor: true),
                ),
                const SizedBox(height: 16),
                _FilePickerCard(
                  title: '교양선택 수강편람',
                  description: '업로드하지 않으면 PlaNU 기본 데이터를 사용합니다.',
                  isRequired: false,
                  file: _electiveCatalog,
                  errorText: _electiveError,
                  isBusy: _isPicking,
                  onPick: () => _pickFile(isMajor: false),
                  onRemove: () => _removeFile(isMajor: false),
                ),
                const SizedBox(height: 16),
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: _surfaceSoft,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        const Icon(
                          Icons.info_outline,
                          size: 20,
                          color: _muted,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            '지원 형식은 .xlsx이며, 파일당 최대 '
                            '${_formatFileSize(widget.maxFileSizeInBytes)}까지 업로드할 수 있습니다.',
                            textAlign: TextAlign.left,
                            style: _bodySmallStyle.copyWith(color: _muted),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 24),
                FilledButton(
                  onPressed: _canAnalyze ? _analyze : null,
                  style: FilledButton.styleFrom(
                    backgroundColor: _ink,
                    foregroundColor: Colors.white,
                    disabledBackgroundColor: _hairline,
                    disabledForegroundColor: _muted,
                    minimumSize: const Size.fromHeight(48),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                    textStyle: _buttonStyle,
                  ),
                  child: _isAnalyzing
                      ? const SizedBox.square(
                          dimension: 20,
                          child: CircularProgressIndicator(
                            color: Colors.white,
                            strokeWidth: 2,
                          ),
                        )
                      : const Text('수강편람 분석하기'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _pickFile({required bool isMajor}) async {
    final picker = isMajor
        ? widget.onPickMajorCatalog
        : widget.onPickElectiveCatalog;
    if (picker == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('파일 선택기를 먼저 연결해주세요.')),
      );
      return;
    }

    setState(() {
      _isPicking = true;
      if (isMajor) {
        _majorError = null;
      } else {
        _electiveError = null;
      }
    });

    CatalogFile? selectedFile;
    try {
      selectedFile = await picker();
    } on Object {
      if (!mounted) return;
      setState(() {
        if (isMajor) {
          _majorError = '파일을 선택하지 못했습니다. 다시 시도해주세요.';
        } else {
          _electiveError = '파일을 선택하지 못했습니다. 다시 시도해주세요.';
        }
      });
    } finally {
      if (mounted) {
        setState(() => _isPicking = false);
      }
    }

    if (!mounted || selectedFile == null) return;
    final validationError = _validate(selectedFile);
    setState(() {
      if (isMajor) {
        _majorError = validationError;
        if (validationError == null) _majorCatalog = selectedFile;
      } else {
        _electiveError = validationError;
        if (validationError == null) _electiveCatalog = selectedFile;
      }
    });
  }

  String? _validate(CatalogFile file) {
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      return '학생지원시스템에서 내려받은 .xlsx 파일만 사용할 수 있습니다.';
    }
    if (file.sizeInBytes > widget.maxFileSizeInBytes) {
      return '파일 크기는 ${_formatFileSize(widget.maxFileSizeInBytes)} 이하여야 합니다.';
    }
    return null;
  }

  void _removeFile({required bool isMajor}) {
    setState(() {
      if (isMajor) {
        _majorCatalog = null;
        _majorError = null;
      } else {
        _electiveCatalog = null;
        _electiveError = null;
      }
    });
  }

  Future<void> _analyze() async {
    final majorCatalog = _majorCatalog;
    final onAnalyze = widget.onAnalyze;
    if (majorCatalog == null || onAnalyze == null) return;

    setState(() => _isAnalyzing = true);
    try {
      await onAnalyze(majorCatalog, _electiveCatalog);
    } on Object {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            '수강편람을 분석하지 못했습니다. 파일을 확인하고 다시 시도해주세요.',
          ),
        ),
      );
    } finally {
      if (mounted) {
        setState(() => _isAnalyzing = false);
      }
    }
  }

  static String _formatFileSize(int bytes) {
    if (bytes >= 1024 * 1024) {
      final megabytes = bytes / (1024 * 1024);
      return '${megabytes.toStringAsFixed(megabytes.truncateToDouble() == megabytes ? 0 : 1)}MB';
    }
    if (bytes >= 1024) return '${(bytes / 1024).toStringAsFixed(0)}KB';
    return '$bytes B';
  }
}

class _StepPill extends StatelessWidget {
  const _StepPill();

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: _FileUploadScreenState._surfaceSoft,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Text(
            '3 / 6',
            style: _FileUploadScreenState._captionStyle.copyWith(
              color: _FileUploadScreenState._ink,
            ),
          ),
        ),
      ),
    );
  }
}

class _FilePickerCard extends StatelessWidget {
  const _FilePickerCard({
    required this.title,
    required this.description,
    required this.isRequired,
    required this.file,
    required this.errorText,
    required this.isBusy,
    required this.onPick,
    required this.onRemove,
  });

  final String title;
  final String description;
  final bool isRequired;
  final CatalogFile? file;
  final String? errorText;
  final bool isBusy;
  final VoidCallback onPick;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final selectedFile = file;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: _FileUploadScreenState._surfaceCard,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    title,
                    textAlign: TextAlign.left,
                    style: _FileUploadScreenState._titleStyle.copyWith(
                      color: _FileUploadScreenState._ink,
                    ),
                  ),
                ),
                _RequirementBadge(isRequired: isRequired),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              description,
              textAlign: TextAlign.left,
              style: _FileUploadScreenState._bodySmallStyle.copyWith(
                color: _FileUploadScreenState._muted,
              ),
            ),
            const SizedBox(height: 16),
            if (selectedFile == null)
              OutlinedButton.icon(
                onPressed: isBusy ? null : onPick,
                icon: const Icon(Icons.upload_file_outlined, size: 20),
                label: const Text('파일 선택'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: _FileUploadScreenState._ink,
                  side: const BorderSide(
                    color: _FileUploadScreenState._hairline,
                  ),
                  minimumSize: const Size(0, 44),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                  textStyle: _FileUploadScreenState._buttonStyle,
                ),
              )
            else
              DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.white,
                  border: Border.all(
                    color: _FileUploadScreenState._hairline,
                  ),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(14, 10, 6, 10),
                  child: Row(
                    children: <Widget>[
                      const Icon(
                        Icons.description_outlined,
                        color: _FileUploadScreenState._ink,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(
                              selectedFile.name,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              textAlign: TextAlign.left,
                              style: _FileUploadScreenState._bodySmallStyle
                                  .copyWith(
                                color: _FileUploadScreenState._ink,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            Text(
                              _FileUploadScreenState._formatFileSize(
                                selectedFile.sizeInBytes,
                              ),
                              textAlign: TextAlign.left,
                              style: _FileUploadScreenState._captionStyle
                                  .copyWith(
                                color: _FileUploadScreenState._muted,
                              ),
                            ),
                          ],
                        ),
                      ),
                      IconButton(
                        onPressed: isBusy ? null : onRemove,
                        tooltip: '$title 파일 제거',
                        icon: const Icon(Icons.close),
                      ),
                    ],
                  ),
                ),
              ),
            if (errorText != null) ...<Widget>[
              const SizedBox(height: 10),
              Text(
                errorText!,
                textAlign: TextAlign.left,
                style: _FileUploadScreenState._bodySmallStyle.copyWith(
                  color: _FileUploadScreenState._error,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _RequirementBadge extends StatelessWidget {
  const _RequirementBadge({required this.isRequired});

  final bool isRequired;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: isRequired
            ? _FileUploadScreenState._ink
            : _FileUploadScreenState._surfaceSoft,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        child: Text(
          isRequired ? '필수' : '선택',
          style: _FileUploadScreenState._captionStyle.copyWith(
            color: isRequired
                ? Colors.white
                : _FileUploadScreenState._muted,
          ),
        ),
      ),
    );
  }
}
