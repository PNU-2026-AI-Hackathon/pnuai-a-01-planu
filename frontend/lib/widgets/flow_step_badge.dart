import 'package:flutter/material.dart';

class FlowStepBadge extends StatelessWidget {
  const FlowStepBadge({
    super.key,
    required this.label,
    required int current,
    int total = 9,
  });

  final String label;

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.centerLeft,
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFFF8F9FA),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
          color: const Color(0xFF111111),
          fontWeight: FontWeight.w600,
        ),
      ),
    ),
  );
}
