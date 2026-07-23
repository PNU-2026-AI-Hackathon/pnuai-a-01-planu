import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/screens/file_upload_screen2.dart';

void main() {
  testWidgets('전공 수강편람을 선택하면 파일 정보와 활성화된 버튼을 표시한다', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: FileUploadScreen2(
          onPickMajorCatalog: () async =>
              const CatalogFile(name: '전공수강편람.xlsx', sizeInBytes: 2048),
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('major-file-picker')));
    await tester.pump();

    expect(find.text('전공수강편람.xlsx'), findsOneWidget);
    expect(find.text('2KB'), findsOneWidget);
    final button = tester.widget<FilledButton>(
      find.byKey(const Key('continue-button')),
    );
    expect(button.onPressed, isNotNull);
  });

  testWidgets('파일 선택을 취소하면 오류 없이 선택 전 상태를 유지한다', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: FileUploadScreen2(onPickMajorCatalog: () async => null),
      ),
    );

    await tester.tap(find.byKey(const Key('major-file-picker')));
    await tester.pump();

    expect(find.text('파일을 선택하지 못했습니다. 다시 시도해 주세요.'), findsNothing);
    expect(find.byKey(const Key('major-file-picker')), findsOneWidget);
    final button = tester.widget<FilledButton>(
      find.byKey(const Key('continue-button')),
    );
    expect(button.onPressed, isNull);
  });

  testWidgets('업로드가 끝날 때까지 현재 화면을 유지하고 중복 제출을 막는다', (tester) async {
    final upload = Completer<String?>();
    await tester.pumpWidget(
      MaterialApp(
        home: FileUploadScreen2(
          onPickMajorCatalog: () async =>
              const CatalogFile(name: '전공수강편람.xlsx', sizeInBytes: 2048),
          onContinue: (_) => upload.future,
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('major-file-picker')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('continue-button')));
    await tester.pump();

    expect(find.byType(FileUploadScreen2), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('continue-button')))
          .onPressed,
      isNull,
    );

    upload.complete('업로드 오류');
    await tester.pump();
    expect(find.text('업로드 오류'), findsOneWidget);
    expect(find.byType(FileUploadScreen2), findsOneWidget);
  });
}
