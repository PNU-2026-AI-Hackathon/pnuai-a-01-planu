import 'package:flutter/foundation.dart';
import '../models/major_models.dart';
import '../repositories/major_repository.dart';

enum MajorRequestState {
  idle,
  previewing,
  previewReady,
  loadingCourses,
  manualPreviewing,
  feedbackPreviewing,
  confirming,
  confirmed,
  error,
}

class MajorFlowController extends ChangeNotifier {
  MajorFlowController({required this.sessionId, required this.repository});
  final String sessionId;
  final MajorRepository repository;
  MajorRequestState state = MajorRequestState.idle;
  String originalPrompt = '';
  MajorPreviewResponse? preview;
  MajorConfirmResponse? confirmation;
  List<MajorCourse> availableCourses = const [];
  ApiError? error;
  bool get busy =>
      state == MajorRequestState.previewing ||
      state == MajorRequestState.loadingCourses ||
      state == MajorRequestState.manualPreviewing ||
      state == MajorRequestState.feedbackPreviewing ||
      state == MajorRequestState.confirming;

  Future<bool> requestPreview(String prompt, {bool feedback = false}) async {
    final trimmed = prompt.trim();
    if (trimmed.isEmpty || busy) return false;
    if (!feedback) originalPrompt = trimmed;
    state = feedback
        ? MajorRequestState.feedbackPreviewing
        : MajorRequestState.previewing;
    error = null;
    notifyListeners();
    try {
      preview = await repository.preview(sessionId: sessionId, prompt: trimmed);
      state = MajorRequestState.previewReady;
      notifyListeners();
      return true;
    } on ApiError catch (e) {
      error = e;
      state = preview == null
          ? MajorRequestState.error
          : MajorRequestState.previewReady;
      notifyListeners();
      return false;
    }
  }

  Future<bool> requestFeedback(String feedback) => requestPreview(
    '기존 요청: $originalPrompt\n추가 수정 요청: ${feedback.trim()}',
    feedback: true,
  );

  Future<bool> loadAvailableCourses({bool force = false}) async {
    if (busy) return false;
    if (availableCourses.isNotEmpty && !force) return true;
    final previousState = state;
    state = MajorRequestState.loadingCourses;
    error = null;
    notifyListeners();
    try {
      final response = await repository.listCourses(sessionId: sessionId);
      availableCourses = response.courses;
      state = previousState == MajorRequestState.error
          ? MajorRequestState.idle
          : previousState;
      notifyListeners();
      return true;
    } on ApiError catch (e) {
      error = e;
      state = previousState;
      notifyListeners();
      return false;
    }
  }

  Future<bool> requestManualPreview(List<String> courseIds) async {
    final selected = courseIds.where((id) => id.trim().isNotEmpty).toList();
    if (selected.isEmpty || busy) return false;
    state = MajorRequestState.manualPreviewing;
    error = null;
    notifyListeners();
    try {
      preview = await repository.manualPreview(
        sessionId: sessionId,
        courseIds: selected,
      );
      state = MajorRequestState.previewReady;
      notifyListeners();
      return true;
    } on ApiError catch (e) {
      error = e;
      state = preview == null
          ? MajorRequestState.error
          : MajorRequestState.previewReady;
      notifyListeners();
      return false;
    }
  }

  Future<bool> confirm() async {
    final value = preview;
    if (value == null || !value.isConfirmable || busy) return false;
    state = MajorRequestState.confirming;
    error = null;
    notifyListeners();
    try {
      confirmation = await repository.confirm(
        sessionId: sessionId,
        previewId: value.previewId,
      );
      state = MajorRequestState.confirmed;
      notifyListeners();
      return true;
    } on ApiError catch (e) {
      error = e;
      state = MajorRequestState.previewReady;
      notifyListeners();
      return false;
    }
  }
}
