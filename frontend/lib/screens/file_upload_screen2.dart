import 'dart:typed_data';

import 'package:flutter/material.dart';

class CatalogFile {
  const CatalogFile({
    required this.name,
    required this.sizeInBytes,
    this.path,
    this.bytes,
  });

  final String name;
  final int sizeInBytes;
  final String? path;
  final Uint8List? bytes;
}

typedef CatalogFilePicker = Future<CatalogFile?> Function();
typedef CatalogContinueCallback = Future<String?> Function(CatalogFile file);

class FileUploadScreen2 extends StatefulWidget {
  const FileUploadScreen2({
    super.key,
    required this.onPickMajorCatalog,
    this.onContinue,
    this.maxFileSizeInBytes = 5 * 1024 * 1024,
  });

  final CatalogFilePicker onPickMajorCatalog;
  final CatalogContinueCallback? onContinue;
  final int maxFileSizeInBytes;

  @override
  State<FileUploadScreen2> createState() => _FileUploadScreen2State();
}

class _FileUploadScreen2State extends State<FileUploadScreen2> {
  static const Color _ink = Color(0xFF111111);
  static const Color _body = Color(0xFF374151);
  static const Color _muted = Color(0xFF6B7280);
  static const Color _hairline = Color(0xFFE5E7EB);
  static const Color _surfaceSoft = Color(0xFFF8F9FA);
  static const Color _surfaceCard = Color(0xFFF5F5F5);
  static const Color _error = Color(0xFFEF4444);

  CatalogFile? _majorCatalog;
  String? _errorText;
  bool _isPicking = false;
  bool _isSubmitting = false;

  bool get _canContinue =>
      _majorCatalog != null && !_isPicking && !_isSubmitting;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        foregroundColor: _ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        title: const Text('PlaNU'),
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 40, 24, 32),
              children: <Widget>[
                const Align(
                  alignment: Alignment.centerLeft,
                  child: _StepPill(),
                ),
                const SizedBox(height: 24),
                Text(
                  '전공 수강편람 업로드',
                  style: theme.textTheme.displaySmall?.copyWith(
                    color: _ink,
                    fontWeight: FontWeight.w600,
                    letterSpacing: -1,
                    height: 1.15,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  '학생지원시스템에서 내려받은 전공 수강편람 파일을 선택해 주세요.',
                  style: theme.textTheme.bodyLarge?.copyWith(
                    color: _body,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 32),
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: _surfaceCard,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          '1학년 전공 수강편람',
                          style: theme.textTheme.titleMedium?.copyWith(
                            color: _ink,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          '전공기초와 전공필수 과목이 포함된 파일이 필요합니다.',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: _muted,
                            height: 1.5,
                          ),
                        ),
                        const SizedBox(height: 20),
                        if (_majorCatalog == null)
                          OutlinedButton.icon(
                            key: const Key('major-file-picker'),
                            onPressed: _isPicking ? null : _pickFile,
                            icon: _isPicking
                                ? const SizedBox.square(
                                    dimension: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      color: _ink,
                                    ),
                                  )
                                : const Icon(Icons.upload_file_outlined),
                            label: Text(_isPicking ? '파일 선택 중' : '파일 선택'),
                            style: OutlinedButton.styleFrom(
                              foregroundColor: _ink,
                              backgroundColor: Colors.white,
                              side: const BorderSide(color: _hairline),
                              minimumSize: const Size(0, 44),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(8),
                              ),
                            ),
                          )
                        else
                          _SelectedFile(
                            file: _majorCatalog!,
                            onRemove: _isPicking || _isSubmitting
                                ? null
                                : _removeFile,
                          ),
                        if (_errorText != null) ...<Widget>[
                          const SizedBox(height: 12),
                          Text(
                            _errorText!,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: _error,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
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
                        const Icon(Icons.info_outline, size: 20, color: _muted),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            '지원 형식은 .xlsx, .xls이며 파일 크기는 최대 '
                            '${_formatFileSize(widget.maxFileSizeInBytes)}입니다.',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: _muted,
                              height: 1.5,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 24),
                FilledButton(
                  key: const Key('continue-button'),
                  onPressed: _canContinue ? _continue : null,
                  style: FilledButton.styleFrom(
                    backgroundColor: _ink,
                    foregroundColor: Colors.white,
                    disabledBackgroundColor: _hairline,
                    disabledForegroundColor: _muted,
                    minimumSize: const Size.fromHeight(48),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  child: _isSubmitting
                      ? const SizedBox.square(
                          dimension: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Text('전공 수강편람 확인하기'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _pickFile() async {
    setState(() {
      _isPicking = true;
      _errorText = null;
    });

    CatalogFile? selectedFile;
    try {
      selectedFile = await widget.onPickMajorCatalog();
    } on Object {
      if (mounted) {
        setState(() {
          _errorText = '파일을 선택하지 못했습니다. 다시 시도해 주세요.';
        });
      }
    } finally {
      if (mounted) setState(() => _isPicking = false);
    }

    // 파일 선택기에서 취소한 경우에는 기존 상태를 유지하고 조용히 종료한다.
    if (!mounted || selectedFile == null) return;

    final validationError = _validate(selectedFile);
    setState(() {
      _errorText = validationError;
      if (validationError == null) _majorCatalog = selectedFile;
    });
  }

  String? _validate(CatalogFile file) {
    final name = file.name.toLowerCase();
    if (!name.endsWith('.xlsx') && !name.endsWith('.xls')) {
      return '.xlsx 또는 .xls 형식의 수강편람 파일을 선택해 주세요.';
    }
    if (file.sizeInBytes > widget.maxFileSizeInBytes) {
      return '파일 크기는 ${_formatFileSize(widget.maxFileSizeInBytes)} 이하여야 합니다.';
    }
    return null;
  }

  void _removeFile() {
    setState(() {
      _majorCatalog = null;
      _errorText = null;
    });
  }

  Future<void> _continue() async {
    final file = _majorCatalog;
    if (file == null) return;
    final callback = widget.onContinue;
    if (callback != null) {
      setState(() {
        _isSubmitting = true;
        _errorText = null;
      });
      final error = await callback(file);
      if (!mounted) return;
      setState(() {
        _isSubmitting = false;
        _errorText = error;
      });
      return;
    }
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('전공 수강편람 파일이 준비되었습니다.')));
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

class _StepPill extends StatelessWidget {
  const _StepPill();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: _FileUploadScreen2State._surfaceSoft,
        borderRadius: BorderRadius.circular(999),
      ),
      child: const Padding(
        padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        child: Text(
          '전공 파일',
          style: TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
        ),
      ),
    );
  }
}

class _SelectedFile extends StatelessWidget {
  const _SelectedFile({required this.file, required this.onRemove});

  final CatalogFile file;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: _FileUploadScreen2State._hairline),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 10, 6, 10),
        child: Row(
          children: <Widget>[
            const Icon(Icons.description_outlined),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    file.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: _FileUploadScreen2State._ink,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    _FileUploadScreen2State._formatFileSize(file.sizeInBytes),
                    style: const TextStyle(
                      color: _FileUploadScreen2State._muted,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
            IconButton(
              onPressed: onRemove,
              tooltip: '선택한 파일 삭제',
              icon: const Icon(Icons.close),
            ),
          ],
        ),
      ),
    );
  }
}
