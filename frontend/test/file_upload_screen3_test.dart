import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/app_flow_state.dart';
import 'package:frontend/screens/file_upload_screen2.dart';
import 'package:frontend/screens/file_upload_screen3.dart';
import 'package:frontend/screens/general_preference_screen.dart';
import 'package:frontend/services/planu_api.dart';

void main() {
  testWidgets('교양 파일 없이도 교양 조건 단계로 진행할 수 있다', (tester) async {
    bool continued = false;
    CatalogFile? continuedFile;
    await tester.pumpWidget(
      MaterialApp(
        home: FileUploadScreen3(
          onPickElectiveCatalog: () async => null,
          onContinue: (file) {
            continued = true;
            continuedFile = file;
          },
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('elective-continue-button')));
    await tester.pump();

    expect(continued, isTrue);
    expect(continuedFile, isNull);
  });

  testWidgets('교양 파일 선택 후 교양 조건 단계로 값을 전달한다', (tester) async {
    CatalogFile? continuedFile;
    await tester.pumpWidget(
      MaterialApp(
        home: FileUploadScreen3(
          onPickElectiveCatalog: () async => CatalogFile(
            name: '교양수강편람.xlsx',
            sizeInBytes: 3,
            bytes: Uint8List.fromList([1, 2, 3]),
          ),
          onContinue: (file) => continuedFile = file,
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('elective-file-picker')));
    await tester.pump();
    expect(find.textContaining('교양수강편람.xlsx'), findsOneWidget);

    await tester.tap(find.byKey(const Key('elective-continue-button')));
    expect(continuedFile?.name, '교양수강편람.xlsx');
  });

  testWidgets('교양 조건 화면에서 뒤로 가면 교양 파일 화면으로 복귀한다', (tester) async {
    final flow = AppFlowState();
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => FileUploadScreen3(
            initialFile: CatalogFile(
              name: '교양수강편람.xlsx',
              sizeInBytes: 1,
              bytes: Uint8List.fromList([1]),
            ),
            onPickElectiveCatalog: () async => null,
            onContinue: (_) => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => GeneralPreferenceScreen(
                  flow: flow,
                  api: PlanuApi(baseUrl: 'http://localhost'),
                  onSessionExpired: () {},
                ),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('elective-continue-button')));
    await tester.pumpAndSettle();
    expect(find.byType(GeneralPreferenceScreen), findsOneWidget);

    await tester.tap(find.byTooltip('Back'));
    await tester.pumpAndSettle();
    expect(find.byType(FileUploadScreen3), findsOneWidget);
    expect(find.textContaining('교양수강편람.xlsx'), findsOneWidget);
  });
}
