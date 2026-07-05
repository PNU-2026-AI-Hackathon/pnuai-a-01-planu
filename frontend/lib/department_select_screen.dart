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
    'Computer Science and Engineering',
    'Computer Engineering',
    'Artificial Intelligence',
    'Electrical and Computer Engineering',
    'Electronic Engineering',
    'Mechanical Engineering',
    'Industrial Engineering',
    'Business Administration',
    'Economics',
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
