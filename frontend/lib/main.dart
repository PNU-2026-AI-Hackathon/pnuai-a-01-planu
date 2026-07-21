import 'package:file_picker/file_picker.dart' as picker;
import 'package:flutter/material.dart';

import 'models/app_flow_state.dart';
import 'models/major_models.dart';
import 'repositories/major_repository.dart';
import 'screens/department_select_screen.dart';
import 'screens/file_upload_screen2.dart';
import 'screens/file_upload_screen3.dart';
import 'screens/general_preference_screen.dart';
import 'screens/guide_screen.dart';
import 'screens/major_prompt_screen.dart';
import 'services/major_api.dart';
import 'services/planu_api.dart';
import 'state/major_flow_controller.dart';

void main() => runApp(const PlaNUApp());

class PlaNUApp extends StatefulWidget {
  const PlaNUApp({super.key});
  @override
  State<PlaNUApp> createState() => _PlaNUAppState();
}

class _PlaNUAppState extends State<PlaNUApp> {
  static const _baseUrl = String.fromEnvironment(
    'PLANU_API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );
  final _navigatorKey = GlobalKey<NavigatorState>();
  final _flow = AppFlowState();
  late final PlanuApi _api = PlanuApi(baseUrl: _baseUrl);

  void _reset() {
    _flow.reset();
    _navigatorKey.currentState!.popUntil((route) => route.isFirst);
  }

  void _start(BuildContext context) {
    Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        settings: const RouteSettings(name: '/department'),
        builder: (departmentContext) => DepartmentSelectScreen(
          onDepartmentSelected: (department) {
            _flow.department = department;
            _openMajorUpload(departmentContext);
          },
        ),
      ),
    );
  }

  void _openMajorUpload(BuildContext context) {
    Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        settings: const RouteSettings(name: '/major-upload'),
        builder: (uploadContext) => FileUploadScreen2(
          onPickMajorCatalog: _pickCatalog,
          onContinue: (file) => _uploadMajor(file, uploadContext),
        ),
      ),
    );
  }

  Future<CatalogFile?> _pickCatalog() async {
    final picked = await picker.FilePicker.pickFiles(
      type: picker.FileType.custom,
      allowedExtensions: const ['xlsx'],
      withData: true,
    );
    final value = picked?.files.single;
    if (value == null) return null;
    return CatalogFile(
      name: value.name,
      sizeInBytes: value.size,
      path: value.path,
      bytes: value.bytes,
    );
  }

  Future<String?> _uploadMajor(CatalogFile file, BuildContext context) async {
    final bytes = file.bytes;
    if (bytes == null) return '선택한 파일을 읽을 수 없습니다.';
    try {
      _flow.majorCatalogName = file.name;
      _flow.majorCatalogBytes = bytes;
      _flow.sessionId = await _api.uploadMajor(
        department: _flow.department,
        fileName: file.name,
        bytes: bytes,
      );
    } on ApiError catch (error) {
      return error.message;
    }
    if (!mounted || !context.mounted) return null;
    final controller = MajorFlowController(
      sessionId: _flow.sessionId!,
      repository: MajorRepository(HttpMajorApi(baseUrl: _baseUrl)),
    );
    Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        settings: const RouteSettings(name: '/major-prompt'),
        builder: (promptContext) => MajorPromptScreen(
          controller: controller,
          onSessionExpired: _reset,
          onConfirmed: (confirmation) {
            _flow.majorPrompt = controller.originalPrompt;
            _flow.majorPreview = controller.preview;
            _flow.majorConfirmation = confirmation;
            _openElectiveUpload(promptContext);
          },
        ),
      ),
    );
    return null;
  }

  void _openElectiveUpload(BuildContext context) {
    Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        settings: const RouteSettings(name: '/elective-upload'),
        builder: (uploadContext) => FileUploadScreen3(
          initialFile: _flow.electiveCatalogBytes == null
              ? null
              : CatalogFile(
                  name: _flow.electiveCatalogName!,
                  sizeInBytes: _flow.electiveCatalogBytes!.length,
                  bytes: _flow.electiveCatalogBytes,
                ),
          onPickElectiveCatalog: _pickCatalog,
          onContinue: (file) {
            _flow.electiveCatalogName = file.name;
            _flow.electiveCatalogBytes = file.bytes;
            Navigator.of(uploadContext).push<void>(
              MaterialPageRoute<void>(
                settings: const RouteSettings(name: '/general-preference'),
                builder: (_) => GeneralPreferenceScreen(
                  flow: _flow,
                  api: _api,
                  onSessionExpired: _reset,
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    navigatorKey: _navigatorKey,
    debugShowCheckedModeBanner: false,
    title: 'PlaNU',
    home: Builder(
      builder: (context) => GuideScreen(onNext: () => _start(context)),
    ),
  );
}
