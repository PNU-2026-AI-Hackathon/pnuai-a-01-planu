import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/condition_summary_models.dart';
import 'package:frontend/screens/second_screen.dart';

void main() {
  testWidgets('applied condition summary shows compact schedule preference',
      (tester) async {
    final summary = ConditionSummary(
      hardConstraints: const [],
      softPreferences: const [
        ConditionSummaryItem(
          key: 'compact_schedule',
          label: '몰아듣기',
          status: ConditionItemStatus.set,
          displayValue: '몰아듣기 선호',
          rawValue: true,
        ),
      ],
      generationReadiness: GenerationReadiness(
        ready: false,
        generationConfirmed: false,
        currentVersion: 1,
      ),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AppliedConditionSummaryCard(
            summary: summary,
            deletingConditionId: null,
            onDelete: (_, scope, {value}) async {},
          ),
        ),
      ),
    );

    expect(find.text('몰아듣기'), findsOneWidget);
    expect(find.text('몰아듣기 선호'), findsOneWidget);
    expect(find.byIcon(Icons.close), findsOneWidget);
  });
}
