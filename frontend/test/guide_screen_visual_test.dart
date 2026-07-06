import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
import 'package:frontend/main.dart';
import 'package:frontend/screens/guide_screen.dart';

void main() {
  testWidgets('Guide screen visual snapshot', (WidgetTester tester) async {
    final fontBytes = File(r'C:\Windows\Fonts\malgun.ttf').readAsBytesSync();
    final fontLoader = FontLoader('Inter')
      ..addFont(
        Future.value(ByteData.view(Uint8List.fromList(fontBytes).buffer)),
      );
    await fontLoader.load();

    final iconBytes = File(
      r'C:\flutter\bin\cache\artifacts\material_fonts\MaterialIcons-Regular.otf',
    ).readAsBytesSync();
    final iconLoader = FontLoader('MaterialIcons')
      ..addFont(
        Future.value(ByteData.view(Uint8List.fromList(iconBytes).buffer)),
      );
    await iconLoader.load();

    tester.view.physicalSize = const Size(1200, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const PlaNUApp());

    await expectLater(
      find.byType(GuideScreen),
      matchesGoldenFile('goldens/guide_screen.png'),
    );
  });
}
