import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/main.dart';

void main() {
  testWidgets('Guide screen renders', (WidgetTester tester) async {
    await tester.pumpWidget(const PlaNUApp());

    expect(find.text('PlaNU'), findsOneWidget);
    expect(find.text('수강편람 다운로드 안내'), findsOneWidget);
    expect(find.text('다운로드 절차'), findsOneWidget);
  });
}
