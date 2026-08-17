import 'package:flutter/material.dart';
import '../models/major_models.dart';
import '../state/major_flow_controller.dart';
import 'major_manual_select_screen.dart';
import 'major_preview_screen.dart';

class MajorPromptScreen extends StatefulWidget {
  const MajorPromptScreen({
    super.key,
    required this.controller,
    this.onSessionExpired,
    this.onConfirmed,
  });
  final MajorFlowController controller;
  final VoidCallback? onSessionExpired;
  final ValueChanged<MajorConfirmResponse>? onConfirmed;
  @override
  State<MajorPromptScreen> createState() => _MajorPromptScreenState();
}

class _MajorPromptScreenState extends State<MajorPromptScreen> {
  final _prompt = TextEditingController();
  String? _validation;
  @override
  void initState() {
    super.initState();
    _prompt.text = widget.controller.originalPrompt;
    widget.controller.addListener(_changed);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_changed);
    _prompt.dispose();
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  Future<void> _submit() async {
    if (_prompt.text.trim().isEmpty) {
      setState(() => _validation = '전공 과목명과 분반을 입력해 주세요.');
      return;
    }
    setState(() => _validation = null);
    final ok = await widget.controller.requestPreview(_prompt.text);
    if (!mounted || !ok) return;
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => MajorPreviewScreen(
          controller: widget.controller,
          onSessionExpired: widget.onSessionExpired,
          onConfirmed: widget.onConfirmed,
        ),
      ),
    );
  }

  Future<void> _openManualSelection() async {
    final ok = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => MajorManualSelectScreen(
          controller: widget.controller,
          onSessionExpired: widget.onSessionExpired,
        ),
      ),
    );
    if (!mounted || ok != true) return;
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => MajorPreviewScreen(
          controller: widget.controller,
          onSessionExpired: widget.onSessionExpired,
          onConfirmed: widget.onConfirmed,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final busy = widget.controller.state == MajorRequestState.previewing;
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.white,
        title: const Text('PlaNU'),
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: ListView(
              padding: EdgeInsets.fromLTRB(
                24,
                32,
                24,
                32 + MediaQuery.viewInsetsOf(context).bottom,
              ),
              children: [
                const _StepBadge(),
                const SizedBox(height: 24),
                Text(
                  '원하는 전공 과목을 알려주세요',
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    letterSpacing: -0.5,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  '수강할 전공 과목명과 분반을 문장으로 입력하면 PlaNU가 시간표를 구성합니다.',
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                    color: const Color(0xFF374151),
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 32),
                Container(
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF5F5F5),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: TextField(
                    key: const Key('majorPromptField'),
                    controller: _prompt,
                    enabled: !busy,
                    minLines: 5,
                    maxLines: 9,
                    maxLength: 1000,
                    textInputAction: TextInputAction.newline,
                    decoration: InputDecoration(
                      labelText: '전공 과목 요청',
                      hintText: '자료구조 001분반, 운영체제 002분반을 들을게요.',
                      errorText: _validation,
                      alignLabelWithHint: true,
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                  ),
                ),
                if (widget.controller.error != null) ...[
                  const SizedBox(height: 16),
                  _PromptError(
                    error: widget.controller.error!,
                    retry: _submit,
                    manualSelect: _openManualSelection,
                    onSessionExpired: widget.onSessionExpired,
                  ),
                ],
                const SizedBox(height: 24),
                FilledButton(
                  key: const Key('majorPreviewButton'),
                  onPressed: busy ? null : _submit,
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF111111),
                    minimumSize: const Size.fromHeight(48),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  child: busy
                      ? const SizedBox.square(
                          dimension: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Text('전공 시간표 미리보기'),
                ),
                const SizedBox(height: 12),
                OutlinedButton(
                  key: const Key('majorManualSelectButton'),
                  onPressed: busy ? null : _openManualSelection,
                  style: OutlinedButton.styleFrom(
                    minimumSize: const Size.fromHeight(48),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  child: const Text('직접 선택하기'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _StepBadge extends StatelessWidget {
  const _StepBadge();
  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.centerLeft,
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFFF8F9FA),
        borderRadius: BorderRadius.circular(999),
      ),
      child: const Text(
        '전공 요청',
        style: TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
  );
}

class _PromptError extends StatelessWidget {
  const _PromptError({
    required this.error,
    required this.retry,
    required this.manualSelect,
    this.onSessionExpired,
  });
  final dynamic error;
  final VoidCallback retry;
  final VoidCallback manualSelect;
  final VoidCallback? onSessionExpired;
  @override
  Widget build(BuildContext context) {
    final expired = error.code == 'SESSION_NOT_FOUND';
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFFEF2F2),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            expired
                ? '세션이 만료되었습니다. 처음부터 다시 시작해 주세요.'
                : '미리보기를 불러오지 못했습니다. 입력 내용은 유지됩니다.',
            style: const TextStyle(color: Color(0xFFB91C1C)),
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: expired ? onSessionExpired : retry,
            child: Text(expired ? '처음 화면으로 이동' : '다시 시도'),
          ),
          if (!expired)
            TextButton(onPressed: manualSelect, child: const Text('직접 선택하기')),
        ],
      ),
    );
  }
}
