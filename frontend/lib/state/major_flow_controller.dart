import 'package:flutter/foundation.dart';
import '../models/major_models.dart';
import '../repositories/major_repository.dart';

enum MajorRequestState {
  idle,
  previewing,
  previewReady,
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
  ApiError? error;
  bool get busy =>
      state == MajorRequestState.previewing ||
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
