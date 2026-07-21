import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import 'screens/file_upload_screen2.dart';

void main() {
  runApp(const PlaNUApp());
}

class PlaNUApp extends StatelessWidget {
  const PlaNUApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'PlaNU',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF111111)),
        useMaterial3: true,
      ),
      home: FileUploadScreen2(onPickMajorCatalog: _pickMajorCatalog),
    );
  }
}

Future<CatalogFile?> _pickMajorCatalog() async {
  final result = await FilePicker.pickFiles(
    type: FileType.custom,
    allowedExtensions: const <String>['xlsx', 'xls'],
    allowMultiple: false,
    withData: true,
  );

  if (result == null || result.files.isEmpty) return null;

  final file = result.files.single;
  return CatalogFile(
    name: file.name,
    sizeInBytes: file.size,
    path: file.path,
    bytes: file.bytes,
  );
}
