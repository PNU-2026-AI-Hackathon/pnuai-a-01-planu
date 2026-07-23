import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/screens/department_select_screen.dart';

void main() {
  testWidgets('학과 후보가 없어도 직접 입력한 학과로 진행할 수 있다', (tester) async {
    String? selected;
    await tester.pumpWidget(
      MaterialApp(
        home: DepartmentSelectScreen(
          departments: const [],
          onDepartmentSelected: (value) => selected = value,
        ),
      ),
    );

    expect(find.textContaining('직접 입력'), findsOneWidget);

    await tester.enterText(find.byType(TextField), '새로운학과');
    await tester.pump();
    await tester.tap(find.text('다음'));
    await tester.pump();

    expect(selected, '새로운학과');
  });

  testWidgets('학과 후보에서 선택해도 진행할 수 있다', (tester) async {
    String? selected;
    await tester.pumpWidget(
      MaterialApp(
        home: DepartmentSelectScreen(
          departments: const ['컴퓨터공학과', '전자공학과'],
          onDepartmentSelected: (value) => selected = value,
        ),
      ),
    );

    await tester.enterText(find.byType(TextField), '컴퓨터');
    await tester.pumpAndSettle();
    await tester.tap(find.text('컴퓨터공학과').last);
    await tester.pump();
    await tester.tap(find.text('다음'));
    await tester.pump();

    expect(selected, '컴퓨터공학과');
  });
}
