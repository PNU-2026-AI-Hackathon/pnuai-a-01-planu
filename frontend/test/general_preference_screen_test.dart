import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/app_flow_state.dart';
import 'package:frontend/screens/general_preference_screen.dart';
import 'package:frontend/services/planu_api.dart';

void main() {
  Widget screen(AppFlowState flow) => MaterialApp(
    home: GeneralPreferenceScreen(
      flow: flow,
      api: PlanuApi(baseUrl: 'http://localhost'),
      onSessionExpired: () {},
    ),
  );

  testWidgets('교양 영역을 선택하지 않으면 생성 요청을 막는다', (tester) async {
    final flow = AppFlowState()..preferencePrompt = '오전 수업 제외';
    await tester.pumpWidget(screen(flow));

    await tester.drag(find.byType(ListView), const Offset(0, -600));
    await tester.pumpAndSettle();
    final generateButton = find.text('시간표 생성');
    await tester.tap(generateButton);
    await tester.pump();

    expect(find.text('교양 영역을 선택해 주세요.'), findsOneWidget);
    expect(find.byType(GeneralPreferenceScreen), findsOneWidget);
  });

  testWidgets('선택한 교양 영역을 흐름 상태에 저장하고 다시 표시한다', (tester) async {
    final flow = AppFlowState();
    await tester.pumpWidget(screen(flow));

    await tester.tap(find.byKey(const Key('elective-area-field')));
    await tester.pumpAndSettle();
    expect(find.text('사상과역사'), findsOneWidget);
    expect(find.text('융합과창의'), findsOneWidget);
    expect(find.text('효원브릿지'), findsOneWidget);
    expect(find.text('인성과사회봉사'), findsOneWidget);
    await tester.tap(find.text('문학과예술').last);
    await tester.pumpAndSettle();

    expect(flow.electiveArea, 3);

    await tester.pumpWidget(const SizedBox());
    await tester.pumpWidget(screen(flow));
    expect(find.text('문학과예술'), findsOneWidget);
  });
}
