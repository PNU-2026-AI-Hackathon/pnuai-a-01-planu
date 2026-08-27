import '../models/major_models.dart';
import '../services/major_api.dart';

class MajorRepository {
  const MajorRepository(this.api);
  final MajorApi api;
  Future<MajorCourseListResponse> listCourses({required String sessionId}) =>
      api.listCourses(sessionId);
  Future<MajorPreviewResponse> preview({
    required String sessionId,
    required String prompt,
  }) => api.preview(MajorPreviewRequest(sessionId, prompt));
  Future<MajorPreviewResponse> manualPreview({
    required String sessionId,
    required List<String> courseIds,
  }) => api.manualPreview(MajorManualPreviewRequest(sessionId, courseIds));
  Future<MajorConfirmResponse> confirm({
    required String sessionId,
    required String previewId,
  }) => api.confirm(MajorConfirmRequest(sessionId, previewId));
}
