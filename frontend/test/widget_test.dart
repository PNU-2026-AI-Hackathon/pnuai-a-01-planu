import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/main.dart';

void main() {
  testWidgets('교양 추천 조건 입력 화면을 표시한다', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());

    expect(find.text('교양 추천 조건 입력'), findsOneWidget);
    expect(find.text('교양필수 개수'), findsOneWidget);

    await tester.scrollUntilVisible(
      find.text('교양선택 개수'),
      200,
      scrollable: find.byType(Scrollable).first,
    );

    expect(find.text('교양선택 개수'), findsOneWidget);
    expect(find.text('최종 시간표 추천받기'), findsOneWidget);
  });
}
