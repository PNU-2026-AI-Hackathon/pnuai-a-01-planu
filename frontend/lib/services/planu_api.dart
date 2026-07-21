import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../models/major_models.dart';

class PlanuApi {
  PlanuApi({required this.baseUrl, http.Client? client})
    : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  Future<String> uploadMajor({
    required String department,
    required String fileName,
    required Uint8List bytes,
  }) async {
    final request =
        http.MultipartRequest('POST', Uri.parse('$baseUrl/catalog/major'))
          ..fields['department'] = department
          ..files.add(
            http.MultipartFile.fromBytes(
              'major_catalog',
              bytes,
              filename: fileName,
            ),
          );
    final response = await http.Response.fromStream(
      await _client.send(request),
    );
    return (await _decode(response))['session_id'] as String;
  }

  Future<Map<String, dynamic>> prepareGeneral({
    required String sessionId,
    int? electiveArea,
    String? fileName,
    Uint8List? bytes,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/general/prepare'),
    )..fields['session_id'] = sessionId;
    if (electiveArea != null) request.fields['elective_area'] = '$electiveArea';
    if (bytes != null && fileName != null) {
      request.files.add(
        http.MultipartFile.fromBytes(
          'elective_catalog',
          bytes,
          filename: fileName,
        ),
      );
    }
    return _decode(await http.Response.fromStream(await _client.send(request)));
  }

  Future<Map<String, dynamic>> generate({
    required String sessionId,
    required String prompt,
    required double targetCredits,
    required int electiveCount,
  }) => _post('/recommend/generate', {
    'session_id': sessionId,
    'preference_prompt': prompt,
    'target_total_credits': targetCredits,
    'additional_elective_count': electiveCount,
  });

  Future<Map<String, dynamic>> rank({
    required String sessionId,
    required String template,
  }) => _post('/recommend/rank', {
    'session_id': sessionId,
    'template': template,
    'top_n': 3,
  });

  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, dynamic> body,
  ) async {
    try {
      final response = await _client.post(
        Uri.parse('$baseUrl$path'),
        headers: const {'content-type': 'application/json'},
        body: jsonEncode(body),
      );
      return _decode(response);
    } on ApiError {
      rethrow;
    } on Object {
      throw const ApiError('NETWORK_ERROR', '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.');
    }
  }

  Future<Map<String, dynamic>> _decode(http.Response response) async {
    Map<String, dynamic> value;
    try {
      value = (jsonDecode(utf8.decode(response.bodyBytes)) as Map)
          .cast<String, dynamic>();
    } on Object {
      throw const ApiError('INVALID_RESPONSE', '서버 응답을 읽을 수 없습니다.');
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiError.fromJson(value);
    }
    return value;
  }
}
