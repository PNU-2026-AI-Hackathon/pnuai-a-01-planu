import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/main.dart';

void main() {
  testWidgets('PlaNU 앱은 학과 선택 화면으로 시작한다', (tester) async {
    await tester.pumpWidget(const PlaNUApp());

    expect(find.text('학과 선택'), findsOneWidget);
    expect(find.text('다음'), findsOneWidget);
  });
}
