import 'package:flutter/material.dart';

class DepartmentSelectScreen extends StatefulWidget {
  const DepartmentSelectScreen({
    super.key,
    this.departments = _defaultDepartments,
    this.onDepartmentSelected,
  });

  final List<String> departments;
  final ValueChanged<String>? onDepartmentSelected;

  static const List<String> _defaultDepartments = <String>[
    '\uAC04\uD638\uB300\uD559',
    '\uAC04\uD638\uD559\uACFC',
    '\uACBD\uC601\uB300\uD559',
    '\uACBD\uC601\uD559\uACFC',
    '\uACBD\uC81C\uD1B5\uC0C1\uB300\uD559',
    '\uACE0\uACE0\uD559\uACFC',
    '\uACF5\uACF5\uC815\uCC45\uD559\uBD80',
    '\uACF5\uACFC\uB300\uD559',
    '\uAD00\uC545\u002E\uD0C0\uC545\uC804\uACF5',
    '\uAD50\uC721\uD559\uACFC',
    '\uAD6D\uC5B4\uAD50\uC721\uACFC',
    '\uAD6D\uC5B4\uAD6D\uBB38\uD559\uACFC',
    '\uB098\uB178\uACFC\uD559\uAE30\uC220\uB300\uD559',
    '\uB178\uC5B4\uB178\uBB38\uD559\uACFC',
    '\uB300\uAE30\uD658\uACBD\uACFC\uD559\uACFC',
    '\uB370\uC774\uD130\uC0AC\uC774\uC5B8\uC2A4\uC804\uACF5',
    '\uB3C4\uC608\uC804\uACF5',
    '\uB514\uC790\uC778\uD14C\uD06C\uB180\uB85C\uC9C0\uC804\uACF5',
    '\uB514\uC790\uC778\uD559\uACFC',
    '\uBB34\uC5ED\uD559\uBD80',
    '\uBB34\uC6A9\uD559\uACFC',
    '\uBB38\uD5CC\uC815\uBCF4\uD559\uACFC',
    '\uBB3C\uB9AC\uAD50\uC721\uACFC',
    '\uBB3C\uB9AC\uD559\uACFC',
    '\uBBF8\uC0DD\uBB3C\uD559\uACFC',
    '\uBBF8\uC220\uD559\uACFC',
    '\uBD84\uC790\uC0DD\uBB3C\uD559\uACFC',
    '\uBD88\uC5B4\uBD88\uBB38\uD559\uACFC',
    '\uC0AC\uBC94\uB300\uD559',
    '\uC0AC\uD559\uACFC',
    '\uC0AC\uD68C\uACFC\uD559\uB300\uD559',
    '\uC0AC\uD68C\uAE30\uBC18\uC2DC\uC2A4\uD15C\uACF5\uD559\uACFC',
    '\uC0AC\uD68C\uBCF5\uC9C0\uD559\uACFC',
    '\uC0B0\uC5C5\uACF5\uD559\uACFC',
    '\uC0DD\uBA85\uACFC\uD559\uACFC',
    '\uC0DD\uBA85\uC790\uC6D0\uACFC\uD559\uB300\uD559',
    '\uC0DD\uBB3C\uAD50\uC721\uACFC',
    '\uC0DD\uD65C\uACFC\uD559\uB300\uD559',
    '\uC218\uD559\uACFC',
    '\uC2A4\uD3EC\uCE20\uACFC\uD559\uACFC',
    '\uC2A4\uD3EC\uCE20\uACFC\uD559\uBD80',
    '\uC2DD\uD488\uACF5\uD559\uACFC',
    '\uC2DD\uD488\uC601\uC591\uD559\uACFC',
    '\uC2E4\uB0B4\uD658\uACBD\uB514\uC790\uC778\uD559\uACFC',
    '\uC2EC\uB9AC\uD559\uACFC',
    '\uC57D\uD559\uB300\uD559',
    '\uC5B8\uC5B4\uC815\uBCF4\uD559\uACFC',
    '\uC601\uC5B4\uC601\uBB38\uD559\uACFC',
    '\uC608\uC220\uB300\uD559',
    '\uC608\uC220\uBB38\uD654\uC601\uC0C1\uD559\uACFC',
    '\uC720\uAE30\uC18C\uC7AC\uC2DC\uC2A4\uD15C\uACF5\uD559\uACFC',
    '\uC720\uC544\uAD50\uC721\uACFC',
    '\uC724\uB9AC\uAD50\uC721\uACFC',
    '\uC758\uACFC\uB300\uD559',
    '\uC758\uB958\uD559\uACFC',
    '\uC758\uC0DD\uBA85\uACF5\uD559\uC804\uACF5',
    '\uC758\uC0DD\uBA85\uC735\uD569\uACF5\uD559\uBD80',
    '\uC758\uC608\uACFC',
    '\uC758\uD559\uACFC',
    '\uC774\uB860\u002E\uC791\uACE1\uC804\uACF5',
    '\uC778\uACF5\uC9C0\uB2A5\uC804\uACF5',
    '\uC778\uBB38\uB300\uD559',
    '\uC77C\uBC18\uC0AC\uD68C\uAD50\uC721\uACFC',
    '\uC77C\uC5B4\uC77C\uBB38\uD559\uACFC',
    '\uC790\uC5F0\uACFC\uD559\uB300\uD559',
    '\uC790\uC720\uC804\uACF5\uD559\uBD80',
    '\uC7AC\uB8CC\uACF5\uD559\uBD80',
    '\uC804\uAE30\uCEF4\uD4E8\uD130\uACF5\uD559\uBD80',
    '\uC804\uC790\uACF5\uD559\uC804\uACF5',
    '\uC815\uBCF4\uC758\uC0DD\uBA85\uACF5\uD559\uB300\uD559',
    '\uC815\uBCF4\uC758\uC0DD\uBA85\uACF5\uD559\uC790\uC728\uC804\uACF5',
    '\uC815\uBCF4\uCEF4\uD4E8\uD130\uACF5\uD559\uBD80',
    '\uC815\uBCF4\uCEF4\uD4E8\uD130\uACF5\uD559\uC804\uACF5',
    '\uC815\uCE58\uC678\uAD50\uD559\uACFC',
    '\uC870\uACBD\uD559\uACFC',
    '\uC870\uC120\u00B7\uD574\uC591\uACF5\uD559\uACFC',
    '\uC870\uD615\uD559\uACFC',
    '\uC911\uC5B4\uC911\uBB38\uD559\uACFC',
    '\uC9C0\uAD6C\uACFC\uD559\uAD50\uC721\uACFC',
    '\uC9C0\uC9C8\uD658\uACBD\uACFC\uD559\uACFC',
    '\uCCA0\uD559\uACFC',
    '\uCCA8\uB2E8\u0049\u0054\uC790\uC728\uC804\uACF5',
    '\uCCA8\uB2E8\uBAA8\uBE4C\uB9AC\uD2F0\uC790\uC728\uC804\uACF5',
    '\uCCA8\uB2E8\uC735\uD569\uD559\uBD80',
    '\uCCB4\uC721\uAD50\uC721\uACFC',
    '\uCE58\uACFC\uB300\uD559',
    '\uCE58\uC758\uD559\uACFC',
    '\uCEF4\uD4E8\uD130\uACF5\uD559\uC804\uACF5',
    '\uD1B5\uACC4\uD559\uACFC',
    '\uD559\uBD80\uB300\uD559',
    '\uD55C\uAD6D\uC74C\uC545\uD559\uACFC',
    '\uD55C\uAD6D\uD654\uC804\uACF5',
    '\uD55C\uBB38\uD559\uACFC',
    '\uD55C\uC758\uACFC\uD559\uACFC',
    '\uD55C\uC758\uD559\uACFC',
    '\uD604\uC545\u002E\uC131\uC545\uC804\uACF5',
    '\uD654\uD559\uACFC',
    '\uD654\uD559\uAD50\uC721\uACFC',
    '\uD658\uACBD\uACF5\uD559\uACFC',
  ];

  @override
  State<DepartmentSelectScreen> createState() => _DepartmentSelectScreenState();
}

class _DepartmentSelectScreenState extends State<DepartmentSelectScreen> {
  static const Color _ink = Color(0xFF111111);
  static const Color _body = Color(0xFF374151);
  static const Color _muted = Color(0xFF6B7280);
  static const Color _hairline = Color(0xFFE5E7EB);
  static const Color _surfaceSoft = Color(0xFFF8F9FA);
  static const Color _surfaceCard = Color(0xFFF5F5F5);

  String? _selectedDepartment;

  bool get _canContinue => _selectedDepartment != null;

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
        centerTitle: false,
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 40, 24, 32),
              children: <Widget>[
                _StepPill(theme: theme),
                const SizedBox(height: 24),
                Text(
                  '학과 선택',
                  style: theme.textTheme.displaySmall?.copyWith(
                    color: _ink,
                    fontWeight: FontWeight.w600,
                    letterSpacing: -0.5,
                    height: 1.2,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  '정확한 수강 계획을 위해 본인의 학과를 선택해주세요.',
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
                          '학과명',
                          style: theme.textTheme.titleMedium?.copyWith(
                            color: _ink,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 12),
                        Autocomplete<String>(
                          optionsBuilder: _buildDepartmentOptions,
                          onSelected: (String department) {
                            setState(() {
                              _selectedDepartment = department;
                            });
                          },
                          fieldViewBuilder: _buildField,
                          optionsViewBuilder: _buildOptions,
                        ),
                        const SizedBox(height: 16),
                        AnimatedSwitcher(
                          duration: const Duration(milliseconds: 180),
                          child: _selectedDepartment == null
                              ? Text(
                                  '검색 결과에서 학과를 선택하면 다음 단계로 넘어갈 수 있습니다.',
                                  key: const ValueKey<String>('empty'),
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: _muted,
                                  ),
                                )
                              : _SelectedDepartmentBadge(
                                  key: const ValueKey<String>('selected'),
                                  department: _selectedDepartment!,
                                ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 24),
                FilledButton(
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
                    textStyle: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  child: const Text('다음'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Iterable<String> _buildDepartmentOptions(TextEditingValue value) {
    final keyword = value.text.trim().toLowerCase();
    if (keyword.isEmpty) {
      return widget.departments;
    }

    return widget.departments.where((department) {
      return department.toLowerCase().contains(keyword);
    });
  }

  Widget _buildField(
    BuildContext context,
    TextEditingController textEditingController,
    FocusNode focusNode,
    VoidCallback onFieldSubmitted,
  ) {
    return TextField(
      controller: textEditingController,
      focusNode: focusNode,
      textInputAction: TextInputAction.search,
      decoration: InputDecoration(
        hintText: '예시: 컴퓨터',
        filled: true,
        fillColor: Colors.white,
        prefixIcon: const Icon(Icons.search),
        suffixIcon: _selectedDepartment == null
            ? null
            : IconButton(
                tooltip: '선택 초기화',
                icon: const Icon(Icons.close),
                onPressed: () {
                  textEditingController.clear();
                  setState(() {
                    _selectedDepartment = null;
                  });
                },
              ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: _hairline),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: _hairline),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: _ink),
        ),
      ),
      onChanged: (value) {
        if (value != _selectedDepartment) {
          setState(() {
            _selectedDepartment = null;
          });
        }
      },
    );
  }

  Widget _buildOptions(
    BuildContext context,
    AutocompleteOnSelected<String> onSelected,
    Iterable<String> options,
  ) {
    return Align(
      alignment: Alignment.topLeft,
      child: Material(
        color: Colors.white,
        elevation: 6,
        borderRadius: BorderRadius.circular(12),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 260, maxWidth: 672),
          child: ListView.separated(
            padding: const EdgeInsets.symmetric(vertical: 8),
            shrinkWrap: true,
            itemCount: options.length,
            separatorBuilder: (_, _) => const Divider(height: 1),
            itemBuilder: (context, index) {
              final department = options.elementAt(index);

              return ListTile(
                dense: true,
                title: Text(department),
                onTap: () => onSelected(department),
              );
            },
          ),
        ),
      ),
    );
  }

  void _continue() {
    final selectedDepartment = _selectedDepartment;
    if (selectedDepartment == null) {
      return;
    }

    widget.onDepartmentSelected?.call(selectedDepartment);
  }
}

class _StepPill extends StatelessWidget {
  const _StepPill({required this.theme});

  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: _DepartmentSelectScreenState._surfaceSoft,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Text(
            '2 / 6',
            style: theme.textTheme.labelMedium?.copyWith(
              color: _DepartmentSelectScreenState._ink,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }
}

class _SelectedDepartmentBadge extends StatelessWidget {
  const _SelectedDepartmentBadge({super.key, required this.department});

  final String department;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: _DepartmentSelectScreenState._hairline),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Icon(Icons.check_circle, color: Color(0xFF10B981), size: 18),
            const SizedBox(width: 8),
            Flexible(
              child: Text(
                department,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: _DepartmentSelectScreenState._ink,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
