import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/main.dart';

void main() {
  testWidgets('Guide screen renders', (WidgetTester tester) async {
    await tester.pumpWidget(const PlaNUApp());

    expect(find.text('PlaNU'), findsOneWidget);
    expect(find.text('수강편람 다운로드 안내'), findsOneWidget);
    expect(find.text('수강편람 준비'), findsNothing);
    expect(find.text('수강편람 다운로드 방법 보기'), findsOneWidget);
    expect(find.text('파일 준비하러 가기'), findsOneWidget);
    expect(find.text('다음'), findsOneWidget);

    await tester.tap(find.text('수강편람 다운로드 방법 보기'));
    await tester.pumpAndSettle();

    expect(find.text('수강편람 다운로드 방법'), findsOneWidget);
    expect(find.text('수강편람 준비'), findsOneWidget);
    expect(find.text('필수 파일'), findsNothing);
    expect(find.text('선택 파일'), findsNothing);
    expect(find.text('업로드 확인'), findsNothing);
    expect(find.text('아래 엑셀 버튼을 누르고 다운받은 엑셀 파일을 업로드 합니다.'), findsOneWidget);
    expect(find.text('전공 선택 안내'), findsNothing);
    expect(find.text('개인정보 및 세션 안내'), findsNothing);

    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('수강편람 다운로드 방법 보기'), findsOneWidget);

    await tester.scrollUntilVisible(find.text('필수 파일'), 300);
    expect(find.text('필수 파일'), findsOneWidget);
    expect(find.text('선택 파일'), findsOneWidget);
    expect(find.text('1학년 전공기초 혹은 전공필수 수강편람 파일을 준비합니다.'), findsOneWidget);

    await tester.scrollUntilVisible(find.text('업로드 확인'), 300);
    expect(find.text('업로드 확인'), findsOneWidget);

    await tester.scrollUntilVisible(find.text('전공 선택 안내'), 300);
    expect(find.text('전공 선택 안내'), findsOneWidget);
    expect(find.text('전공 과목 직접 선택'), findsOneWidget);
    expect(find.text('시간표 작성 기준'), findsOneWidget);
    expect(find.text('전공 시간표 미리 준비'), findsOneWidget);
    expect(
      find.text('에브리타임의 수업 평가와 시간표를 참고해 원하는 전공 과목과 분반을 미리 정해 주세요.'),
      findsOneWidget,
    );
    expect(find.text('개인정보 및 세션 안내'), findsOneWidget);
    expect(find.text('개인정보 보호'), findsOneWidget);
    expect(find.text('30분 세션'), findsOneWidget);
    expect(find.text('파일 자동 삭제'), findsOneWidget);
  });
}
