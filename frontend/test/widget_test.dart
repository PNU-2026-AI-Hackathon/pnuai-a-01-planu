import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/main.dart';

void main() {
  testWidgets('Guide screen renders', (WidgetTester tester) async {
    await tester.pumpWidget(const PlaNUApp());

    expect(find.text('PlaNU'), findsOneWidget);
    expect(find.text('수강편람 다운로드 안내'), findsOneWidget);
    expect(find.text('수강편람 다운로드 방법 보기'), findsOneWidget);
    expect(find.text('다음'), findsOneWidget);
    expect(find.text('수강편람 준비'), findsNothing);
    expect(find.text('전공 선택 안내'), findsOneWidget);
    expect(find.text('개인정보 및 세션 안내'), findsOneWidget);

    await tester.tap(find.text('수강편람 다운로드 방법 보기'));
    await tester.pumpAndSettle();

    expect(find.text('수강편람 다운로드 방법'), findsOneWidget);
    expect(find.text('수강편람 준비'), findsOneWidget);
    expect(find.text('필수 파일'), findsOneWidget);
    expect(find.text('전공 선택 안내'), findsNothing);
    expect(find.text('개인정보 및 세션 안내'), findsNothing);

    await tester.pageBack();
    await tester.pumpAndSettle();

    expect(find.text('수강편람 다운로드 방법 보기'), findsOneWidget);
  });
}
