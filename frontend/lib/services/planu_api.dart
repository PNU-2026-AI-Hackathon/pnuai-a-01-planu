import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../models/condition_summary_models.dart';
import '../models/major_models.dart';

class PlanuApi {
  PlanuApi({required this.baseUrl, http.Client? client})
    : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;
  static const _requestTimeout = Duration(seconds: 60);

  Future<String> uploadMajor({
    required String department,
    required String fileName,
    required Uint8List bytes,
  }) async => (await uploadMajorDetails(
    department: department,
    fileName: fileName,
    bytes: bytes,
  ))['session_id'] as String;

  Future<Map<String, dynamic>> uploadMajorDetails({
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
    return _decode(response);
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
    double? targetCredits,
    int? electiveCount,
    int? maxCandidates,
  }) {
    final body = <String, dynamic>{
      'session_id': sessionId,
      'preference_prompt': prompt,
    };
    if (targetCredits != null) {
      body['target_total_credits'] = targetCredits;
    }
    if (electiveCount != null) {
      body['additional_elective_count'] = electiveCount;
    }
    if (maxCandidates != null) {
      body['max_candidates'] = maxCandidates;
    }
    return _post('/recommend/generate', body);
  }

  Future<Map<String, dynamic>> rank({
    required String sessionId,
    required String template,
  }) => _post('/recommend/rank', {
    'session_id': sessionId,
    'template': template,
    'top_n': 3,
  });

  Future<Map<String, dynamic>> selectTimetableCandidate({
    required String sessionId,
    required String candidateId,
  }) => _post(
    '/sessions/${Uri.encodeComponent(sessionId)}/timetables/${Uri.encodeComponent(candidateId)}/select',
    const {},
  );

  Future<PlanuChatResponse> sendChatMessage({
    required String sessionId,
    required String message,
    String? requestId,
  }) async {
    final body = <String, dynamic>{'message': message};
    if (requestId != null) {
      body['request_id'] = requestId;
    }
    final response = await _post('/sessions/${Uri.encodeComponent(sessionId)}/chat', {
      ...body,
    });
    return PlanuChatResponse.fromJson(response);
  }

  Future<ConditionSummary> confirmTimetableConditions({
    required String sessionId,
  }) async {
    final response = await _post(
      '/sessions/${Uri.encodeComponent(sessionId)}/conditions/confirm',
      const {},
    );
    return ConditionSummary.fromJson(response);
  }

  Future<ConditionSummary> deleteTimetableCondition({
    required String sessionId,
    required String scope,
    required String key,
    Object? value,
  }) async {
    final body = <String, dynamic>{
      'scope': scope,
      'key': key,
    };
    if (value != null) body['value'] = value;
    final response = await _patch(
      '/sessions/${Uri.encodeComponent(sessionId)}/conditions',
      body,
    );
    return ConditionSummary.fromJson(response);
  }

  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, dynamic> body,
  ) async {
    try {
      final response = await _client.post(
        Uri.parse('$baseUrl$path'),
        headers: const {'content-type': 'application/json'},
        body: jsonEncode(body),
      ).timeout(_requestTimeout);
      return _decode(response);
    } on TimeoutException {
      throw const ApiError(
        'REQUEST_TIMEOUT',
        '시간표 생성 요청 시간이 초과되었습니다. 조건을 확인한 뒤 다시 시도해 주세요.',
      );
    } on ApiError {
      rethrow;
    } on Object {
      throw const ApiError('NETWORK_ERROR', '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.');
    }
  }

  Future<Map<String, dynamic>> _patch(
    String path,
    Map<String, dynamic> body,
  ) async {
    try {
      final response = await _client.patch(
        Uri.parse('$baseUrl$path'),
        headers: const {'content-type': 'application/json'},
        body: jsonEncode(body),
      ).timeout(_requestTimeout);
      return _decode(response);
    } on TimeoutException {
      throw const ApiError(
        'REQUEST_TIMEOUT',
        '?쒓컙??議곌굔 ??젣 ?붿껌 ?쒓컙??珥덇낵?섏뿀?듬땲?? ?ㅼ떆 ?쒕룄??二쇱꽭??',
      );
    } on ApiError {
      rethrow;
    } on Object {
      throw const ApiError('NETWORK_ERROR', '?쒕쾭???곌껐?????놁뒿?덈떎. ?좎떆 ???ㅼ떆 ?쒕룄??二쇱꽭??');
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
