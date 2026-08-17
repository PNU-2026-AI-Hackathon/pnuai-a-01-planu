import 'package:flutter/material.dart';

import 'file_upload_screen2.dart' show CatalogFile, CatalogFilePicker;

class FileUploadScreen3 extends StatefulWidget {
  const FileUploadScreen3({
    super.key,
    required this.onPickElectiveCatalog,
    required this.onContinue,
    this.initialFile,
    this.maxFileSizeInBytes = 10 * 1024 * 1024,
  });

  final CatalogFilePicker onPickElectiveCatalog;
  final ValueChanged<CatalogFile?> onContinue;
  final CatalogFile? initialFile;
  final int maxFileSizeInBytes;

  @override
  State<FileUploadScreen3> createState() => _FileUploadScreen3State();
}

class _FileUploadScreen3State extends State<FileUploadScreen3> {
  static const _ink = Color(0xFF111111);
  static const _muted = Color(0xFF6B7280);
  static const _hairline = Color(0xFFE5E7EB);
  static const _surfaceSoft = Color(0xFFF8F9FA);
  static const _surfaceCard = Color(0xFFF5F5F5);
  static const _error = Color(0xFFEF4444);

  CatalogFile? _file;
  String? _errorText;
  bool _isPicking = false;

  @override
  void initState() {
    super.initState();
    _file = widget.initialFile;
  }

  Future<void> _pickFile() async {
    setState(() {
      _isPicking = true;
      _errorText = null;
    });
    CatalogFile? selected;
    try {
      selected = await widget.onPickElectiveCatalog();
    } on Object {
      if (mounted) _errorText = '파일을 선택하지 못했습니다. 다시 시도해 주세요.';
    } finally {
      if (mounted) setState(() => _isPicking = false);
    }
    if (!mounted || selected == null) return;
    final error = _validate(selected);
    setState(() {
      _errorText = error;
      if (error == null) _file = selected;
    });
  }

  String? _validate(CatalogFile file) {
    final name = file.name.toLowerCase();
    if (!name.endsWith('.xlsx')) {
      return '.xlsx 형식의 수강편람 파일을 선택해 주세요.';
    }
    if (file.sizeInBytes > widget.maxFileSizeInBytes) {
      return '파일 크기는 ${_formatSize(widget.maxFileSizeInBytes)} 이하여야 합니다.';
    }
    if (file.bytes == null) return '선택한 파일을 읽을 수 없습니다.';
    return null;
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: Colors.white,
    appBar: AppBar(title: const Text('PlaNU'), backgroundColor: Colors.white),
    body: SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(24, 40, 24, 32),
            children: [
              const Align(alignment: Alignment.centerLeft, child: _StepPill()),
              const SizedBox(height: 24),
              Text(
                '교양 수강편람 업로드',
                style: Theme.of(
                  context,
                ).textTheme.displaySmall?.copyWith(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 12),
              const Text('교양 수강편람 파일이 있으면 업로드하고, 없으면 서버 기본 데이터로 진행합니다.'),
              const SizedBox(height: 32),
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: _surfaceCard,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      '교양과목 수강편람',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      '업로드하면 해당 파일의 교양 과목을 우선 사용합니다.',
                      style: TextStyle(color: _muted),
                    ),
                    const SizedBox(height: 20),
                    if (_file == null)
                      OutlinedButton.icon(
                        key: const Key('elective-file-picker'),
                        onPressed: _isPicking ? null : _pickFile,
                        icon: _isPicking
                            ? const SizedBox.square(
                                dimension: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Icons.upload_file_outlined),
                        label: Text(_isPicking ? '파일 선택 중' : '파일 선택'),
                      )
                    else
                      _SelectedFile(
                        file: _file!,
                        onRemove: () => setState(() => _file = null),
                      ),
                    if (_errorText != null) ...[
                      const SizedBox(height: 12),
                      Text(_errorText!, style: const TextStyle(color: _error)),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: _surfaceSoft,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  '지원 형식은 .xlsx이며 파일 크기는 최대 ${_formatSize(widget.maxFileSizeInBytes)}입니다. 파일을 선택하지 않으면 서버 기본 교양 데이터를 사용합니다.',
                ),
              ),
              const SizedBox(height: 24),
              FilledButton(
                key: const Key('elective-continue-button'),
                onPressed: _isPicking ? null : () => widget.onContinue(_file),
                style: FilledButton.styleFrom(
                  backgroundColor: _ink,
                  minimumSize: const Size.fromHeight(48),
                ),
                child: const Text('교양 조건 입력하기'),
              ),
            ],
          ),
        ),
      ),
    ),
  );

  static String _formatSize(int bytes) => bytes >= 1024 * 1024
      ? '${(bytes / (1024 * 1024)).toStringAsFixed(0)}MB'
      : '${(bytes / 1024).toStringAsFixed(0)}KB';
}

class _StepPill extends StatelessWidget {
  const _StepPill();
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
    decoration: BoxDecoration(
      color: _FileUploadScreen3State._surfaceSoft,
      borderRadius: BorderRadius.circular(999),
    ),
    child: const Text(
      '교양 파일 준비',
      style: TextStyle(fontWeight: FontWeight.w500),
    ),
  );
}

class _SelectedFile extends StatelessWidget {
  const _SelectedFile({required this.file, required this.onRemove});
  final CatalogFile file;
  final VoidCallback onRemove;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: Colors.white,
      border: Border.all(color: _FileUploadScreen3State._hairline),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Row(
      children: [
        const Icon(Icons.description_outlined),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            '${file.name}\n${_FileUploadScreen3State._formatSize(file.sizeInBytes)}',
          ),
        ),
        IconButton(
          onPressed: onRemove,
          tooltip: '선택한 파일 삭제',
          icon: const Icon(Icons.close),
        ),
      ],
    ),
  );
}
