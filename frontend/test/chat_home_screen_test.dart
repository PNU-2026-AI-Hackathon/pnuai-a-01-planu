import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/screens/chat_home_screen.dart';
import 'package:frontend/screens/file_upload_screen2.dart';
import 'package:frontend/services/planu_api.dart';

class FakePlanuApi extends PlanuApi {
  FakePlanuApi() : super(baseUrl: 'http://localhost');

  int uploadCalls = 0;

  @override
  Future<Map<String, dynamic>> uploadMajorDetails({
    required String department,
    required String fileName,
    required Uint8List bytes,
  }) async {
    uploadCalls += 1;
    return {
      'session_id': 'session-123',
      'session_stage': 'ready',
      'parsed_course_count': 12,
      'warnings': ['예시 경고'],
    };
  }
}

void main() {
  testWidgets('학과와 파일이 없으면 계속 버튼이 비활성화된다', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: ChatHomeScreen(api: FakePlanuApi())),
    );
    await tester.pumpAndSettle();

    final continueButton = tester.widget<ElevatedButton>(
      find.byKey(const Key('continue-button')),
    );
    expect(continueButton.onPressed, isNull);
    expect(find.text('과목 확인으로 이동'), findsOneWidget);
  });

  testWidgets('업로드 성공 후 계속 버튼이 활성화된다', (tester) async {
    final api = FakePlanuApi();
    await tester.pumpWidget(
      MaterialApp(
        home: ChatHomeScreen(
          api: api,
          onPickMajorCatalog: () async => CatalogFile(
            name: 'history_major.xlsx',
            sizeInBytes: 124000,
            bytes: Uint8List.fromList(<int>[1, 2, 3]),
          ),
        ),
      ),
    );

    await tester.enterText(find.byKey(const Key('department-field')), '컴퓨터공학부');
    await tester.pump();
    await tester.tap(find.text('컴퓨터공학부').last);
    await tester.pump();

    await tester.ensureVisible(find.byKey(const Key('catalog-picker-button')));
    await tester.tap(find.byKey(const Key('catalog-picker-button')));
    await tester.pump();

    await tester.ensureVisible(find.byKey(const Key('upload-catalog-button')));
    await tester.tap(find.byKey(const Key('upload-catalog-button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    final continueButton = tester.widget<ElevatedButton>(
      find.byKey(const Key('continue-button')),
    );
    expect(continueButton.onPressed, isNotNull);
    expect(find.textContaining('수강편람 분석이 완료되었습니다.'), findsOneWidget);
    expect(find.textContaining('전공 과목 12개를 확인했습니다.'), findsOneWidget);
  });

  testWidgets('업로드 성공 시 과목 수와 성공 메시지를 표시한다', (tester) async {
    final api = FakePlanuApi();
    await tester.pumpWidget(
      MaterialApp(
        home: ChatHomeScreen(
          api: api,
          onPickMajorCatalog: () async => CatalogFile(
            name: 'history_major.xlsx',
            sizeInBytes: 124000,
            bytes: Uint8List.fromList(<int>[1, 2, 3]),
          ),
        ),
      ),
    );

    await tester.enterText(find.byKey(const Key('department-field')), '컴퓨터공학부');
    await tester.pump();
    await tester.tap(find.text('컴퓨터공학부').last);
    await tester.pump();

    await tester.ensureVisible(find.byKey(const Key('catalog-picker-button')));
    await tester.tap(find.byKey(const Key('catalog-picker-button')));
    await tester.pump();

    await tester.ensureVisible(find.byKey(const Key('upload-catalog-button')));
    await tester.tap(find.byKey(const Key('upload-catalog-button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(api.uploadCalls, 1);
    expect(find.textContaining('수강편람 분석이 완료되었습니다.'), findsOneWidget);
    expect(find.textContaining('전공 과목 12개를 확인했습니다.'), findsOneWidget);
  });
}
