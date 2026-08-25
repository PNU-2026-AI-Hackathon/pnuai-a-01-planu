import 'dart:typed_data';

import 'major_models.dart';

class AppFlowState {
  String department = '';
  String? sessionId;
  String? majorCatalogName;
  Uint8List? majorCatalogBytes;
  String majorPrompt = '';
  MajorPreviewResponse? majorPreview;
  MajorConfirmResponse? majorConfirmation;
  String preferencePrompt = '';
  String selectedTemplate = 'balanced';
  int? electiveArea;
  double targetTotalCredits = 18;
  int additionalElectiveCount = 1;
  String? electiveCatalogName;
  Uint8List? electiveCatalogBytes;
  Map<String, dynamic>? generatedCandidates;
  Map<String, dynamic>? rankedCandidates;
  Map<String, dynamic>? selectedTimetable;

  void reset() {
    department = '';
    sessionId = null;
    majorCatalogName = null;
    majorCatalogBytes = null;
    majorPrompt = '';
    majorPreview = null;
    majorConfirmation = null;
    preferencePrompt = '';
    selectedTemplate = 'balanced';
    electiveArea = null;
    targetTotalCredits = 18;
    additionalElectiveCount = 1;
    electiveCatalogName = null;
    electiveCatalogBytes = null;
    generatedCandidates = null;
    rankedCandidates = null;
    selectedTimetable = null;
  }
}
