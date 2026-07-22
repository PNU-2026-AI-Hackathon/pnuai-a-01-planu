import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/major_models.dart';

abstract interface class MajorApi {
  Future<MajorCourseListResponse> listCourses(String sessionId);
  Future<MajorPreviewResponse> preview(MajorPreviewRequest request);
  Future<MajorPreviewResponse> manualPreview(MajorManualPreviewRequest request);
  Future<MajorConfirmResponse> confirm(MajorConfirmRequest request);
}

class HttpMajorApi implements MajorApi {
  HttpMajorApi({
    required this.baseUrl,
    http.Client? client,
    this.timeout = const Duration(seconds: 20),
  }) : _client = client ?? http.Client();
  final String baseUrl;
  final http.Client _client;
  final Duration timeout;
  @override
  Future<MajorCourseListResponse> listCourses(String sessionId) async =>
      MajorCourseListResponse.fromJson(
        await _get(
          '/major/courses?session_id=${Uri.encodeQueryComponent(sessionId)}',
        ),
      );

  @override
  Future<MajorPreviewResponse> preview(MajorPreviewRequest request) async =>
      MajorPreviewResponse.fromJson(
        await _post('/major/preview', request.toJson()),
      );

  @override
  Future<MajorPreviewResponse> manualPreview(
    MajorManualPreviewRequest request,
  ) async => MajorPreviewResponse.fromJson(
    await _post('/major/manual-preview', request.toJson()),
  );

  @override
  Future<MajorConfirmResponse> confirm(MajorConfirmRequest request) async =>
      MajorConfirmResponse.fromJson(
        await _post('/major/confirm', request.toJson()),
      );

  Future<Map<String, dynamic>> _get(String path) async {
    try {
      final response = await _client
          .get(Uri.parse('$baseUrl$path'))
          .timeout(timeout);
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw ApiError.fromJson(decoded);
      }
      return decoded;
    } on ApiError {
      rethrow;
    } on Object {
      throw const ApiError('NETWORK_ERROR', '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.');
    }
  }

  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, dynamic> body,
  ) async {
    try {
      final response = await _client
          .post(
            Uri.parse('$baseUrl$path'),
            headers: const {'content-type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(timeout);
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw ApiError.fromJson(decoded);
      }
      return decoded;
    } on ApiError {
      rethrow;
    } on Object {
      throw const ApiError('NETWORK_ERROR', '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.');
    }
  }
}
