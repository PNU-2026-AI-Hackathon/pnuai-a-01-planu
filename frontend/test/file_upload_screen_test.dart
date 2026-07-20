import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/screens/file_upload_screen.dart';

void main() {
  testWidgets('shows the selected major catalog file', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: FileUploadScreen(
          onPickMajorCatalog: () async => const CatalogFile(
            name: 'major-catalog.xlsx',
            sizeInBytes: 1024,
          ),
        ),
      ),
    );

    await tester.tap(find.byIcon(Icons.upload_file_outlined).first);
    await tester.pump();

    expect(find.text('major-catalog.xlsx'), findsOneWidget);
    expect(find.text('1KB'), findsOneWidget);
  });

  testWidgets('does not show an error when file selection is cancelled', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: FileUploadScreen(onPickMajorCatalog: () async => null),
      ),
    );

    await tester.tap(find.byIcon(Icons.upload_file_outlined).first);
    await tester.pump();

    expect(find.byType(SnackBar), findsNothing);
    expect(find.byIcon(Icons.upload_file_outlined), findsNWidgets(2));
  });
}
