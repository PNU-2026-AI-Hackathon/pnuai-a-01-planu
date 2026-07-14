import 'package:flutter/material.dart';

class GeneralRecommendationRequest {
  const GeneralRecommendationRequest({
    required this.userPrompt,
    required this.requiredGeneralCount,
    required this.electiveGeneralCount,
  });

  final String userPrompt;
  final int requiredGeneralCount;
  final int electiveGeneralCount;
}

typedef GeneralRecommendationCallback = Future<void> Function(
  GeneralRecommendationRequest request,
);

class GeneralPromptScreen extends StatefulWidget {
  const GeneralPromptScreen({
    super.key,
    this.onRecommend,
    this.initialPrompt = '',
    this.initialRequiredGeneralCount = 1,
    this.initialElectiveGeneralCount = 1,
  });

  final GeneralRecommendationCallback? onRecommend;
  final String initialPrompt;
  final int initialRequiredGeneralCount;
  final int initialElectiveGeneralCount;

  @override
  State<GeneralPromptScreen> createState() => _GeneralPromptScreenState();
}

class _GeneralPromptScreenState extends State<GeneralPromptScreen> {
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
    height: 1.15,
    letterSpacing: -1,
  );
  static const TextStyle _titleStyle = TextStyle(
    fontSize: 18,
    fontWeight: FontWeight.w600,
    height: 1.4,
  );
  static const TextStyle _bodyStyle = TextStyle(fontSize: 16, height: 1.5);
  static const TextStyle _bodySmallStyle = TextStyle(fontSize: 14, height: 1.5);
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

  late final TextEditingController _promptController;
  late int _requiredGeneralCount;
  late int _electiveGeneralCount;
  bool _isLoading = false;
  String? _errorMessage;

  bool get _canRecommend =>
      _promptController.text.trim().isNotEmpty && !_isLoading;

  @override
  void initState() {
    super.initState();
    _promptController = TextEditingController(text: widget.initialPrompt)
      ..addListener(_handlePromptChanged);
    _requiredGeneralCount = widget.initialRequiredGeneralCount.clamp(0, 9);
    _electiveGeneralCount = widget.initialElectiveGeneralCount.clamp(0, 9);
  }

  @override
  void dispose() {
    _promptController
      ..removeListener(_handlePromptChanged)
      ..dispose();
    super.dispose();
  }

  void _handlePromptChanged() {
    setState(() => _errorMessage = null);
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
        title: const Text('PlaNU'),
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
                  '교양 추천 조건 입력',
                  style: _displayStyle.copyWith(color: _ink),
                ),
                const SizedBox(height: 12),
                Text(
                  '확정한 전공 시간표에 맞춰 원하는 교양 수업의 조건을 알려주세요.',
                  style: _bodyStyle.copyWith(color: _body),
                ),
                const SizedBox(height: 32),
                _buildPromptCard(),
                const SizedBox(height: 16),
                _CountCard(
                  label: '교양필수 개수',
                  description: '시간표에 포함할 교양필수 과목 수',
                  value: _requiredGeneralCount,
                  onChanged: (int value) {
                    setState(() => _requiredGeneralCount = value);
                  },
                ),
                const SizedBox(height: 12),
                _CountCard(
                  label: '교양선택 개수',
                  description: '시간표에 포함할 교양선택 과목 수',
                  value: _electiveGeneralCount,
                  onChanged: (int value) {
                    setState(() => _electiveGeneralCount = value);
                  },
                ),
                if (_errorMessage != null) ...<Widget>[
                  const SizedBox(height: 16),
                  Text(
                    _errorMessage!,
                    style: _bodySmallStyle.copyWith(color: _error),
                  ),
                ],
                const SizedBox(height: 24),
                FilledButton(
                  onPressed: _canRecommend ? _recommend : null,
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
                  child: _isLoading
                      ? const SizedBox.square(
                          dimension: 20,
                          child: CircularProgressIndicator(
                            color: Colors.white,
                            strokeWidth: 2,
                          ),
                        )
                      : const Text('최종 시간표 추천받기'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildPromptCard() {
    return DecoratedBox(
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
              '교양 수업에 대한 조건을 입력해주세요.',
              style: _titleStyle.copyWith(color: _ink),
            ),
            const SizedBox(height: 8),
            Text(
              '예: 오전 수업은 피하고 싶어요. 금요일은 공강이면 좋겠어요.',
              style: _bodySmallStyle.copyWith(color: _muted),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _promptController,
              minLines: 5,
              maxLines: 8,
              maxLength: 500,
              textInputAction: TextInputAction.newline,
              style: _bodyStyle.copyWith(color: _ink),
              decoration: InputDecoration(
                hintText: '원하는 수업 시간, 공강 요일, 이동 조건 등을 자유롭게 입력하세요.',
                hintStyle: _bodyStyle.copyWith(color: _muted),
                filled: true,
                fillColor: Colors.white,
                contentPadding: const EdgeInsets.all(16),
                enabledBorder: OutlineInputBorder(
                  borderSide: const BorderSide(color: _hairline),
                  borderRadius: BorderRadius.circular(8),
                ),
                focusedBorder: OutlineInputBorder(
                  borderSide: const BorderSide(color: _ink, width: 1.5),
                  borderRadius: BorderRadius.circular(8),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _recommend() async {
    final callback = widget.onRecommend;
    if (callback == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('추천 기능은 백엔드 연결 후 사용할 수 있어요.')),
      );
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      await callback(
        GeneralRecommendationRequest(
          userPrompt: _promptController.text.trim(),
          requiredGeneralCount: _requiredGeneralCount,
          electiveGeneralCount: _electiveGeneralCount,
        ),
      );
    } on Object {
      if (mounted) {
        setState(() {
          _errorMessage = '시간표를 추천하지 못했어요. 잠시 후 다시 시도해주세요.';
        });
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
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
          color: _GeneralPromptScreenState._surfaceSoft,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Text(
            '5 / 6',
            style: _GeneralPromptScreenState._captionStyle.copyWith(
              color: _GeneralPromptScreenState._ink,
            ),
          ),
        ),
      ),
    );
  }
}

class _CountCard extends StatelessWidget {
  const _CountCard({
    required this.label,
    required this.description,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final String description;
  final int value;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: _GeneralPromptScreenState._surfaceSoft,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        child: Row(
          children: <Widget>[
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    label,
                    style: _GeneralPromptScreenState._titleStyle.copyWith(
                      color: _GeneralPromptScreenState._ink,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    description,
                    style: _GeneralPromptScreenState._bodySmallStyle.copyWith(
                      color: _GeneralPromptScreenState._muted,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 16),
            _CountButton(
              icon: Icons.remove,
              tooltip: '$label 줄이기',
              onPressed: value > 0 ? () => onChanged(value - 1) : null,
            ),
            SizedBox(
              width: 44,
              child: Text(
                '$value',
                textAlign: TextAlign.center,
                style: _GeneralPromptScreenState._titleStyle.copyWith(
                  color: _GeneralPromptScreenState._ink,
                ),
              ),
            ),
            _CountButton(
              icon: Icons.add,
              tooltip: '$label 늘리기',
              onPressed: value < 9 ? () => onChanged(value + 1) : null,
            ),
          ],
        ),
      ),
    );
  }
}

class _CountButton extends StatelessWidget {
  const _CountButton({
    required this.icon,
    required this.tooltip,
    required this.onPressed,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return IconButton.outlined(
      onPressed: onPressed,
      tooltip: tooltip,
      icon: Icon(icon, size: 18),
      style: IconButton.styleFrom(
        foregroundColor: _GeneralPromptScreenState._ink,
        disabledForegroundColor: _GeneralPromptScreenState._muted,
        side: const BorderSide(color: _GeneralPromptScreenState._hairline),
        minimumSize: const Size.square(40),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
    );
  }
}
