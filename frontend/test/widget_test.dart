import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/main.dart';

void main() {
  testWidgets('파일 업로드 화면을 표시한다', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());

    expect(find.text('수강편람 업로드'), findsOneWidget);
    expect(find.text('1학년 전공 수강편람'), findsOneWidget);
    expect(find.text('교양선택 수강편람'), findsOneWidget);
    expect(find.text('수강편람 분석하기'), findsOneWidget);
  });
}
