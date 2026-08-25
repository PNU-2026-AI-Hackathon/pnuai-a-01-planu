enum ConditionItemStatus { set, empty, unset, unknown }

ConditionItemStatus _conditionItemStatusFromString(String? value) {
  switch (value) {
    case 'SET':
      return ConditionItemStatus.set;
    case 'EMPTY':
      return ConditionItemStatus.empty;
    case 'UNSET':
      return ConditionItemStatus.unset;
    default:
      return ConditionItemStatus.unknown;
  }
}

class ConditionCourseRef {
  const ConditionCourseRef({
    required this.courseId,
    this.courseName,
    this.courseCode,
  });

  final String courseId;
  final String? courseName;
  final String? courseCode;

  factory ConditionCourseRef.fromJson(Map<String, dynamic> json) =>
      ConditionCourseRef(
        courseId: json['course_id'] as String? ?? '',
        courseName: json['course_name'] as String?,
        courseCode: json['course_code'] as String?,
      );
}

class ConditionSummaryItem {
  const ConditionSummaryItem({
    required this.key,
    required this.label,
    required this.status,
    this.displayValue,
    this.courseRefs = const [],
    this.rawValue,
  });

  final String key;
  final String label;
  final ConditionItemStatus status;
  final String? displayValue;
  final List<ConditionCourseRef> courseRefs;
  final Object? rawValue;

  factory ConditionSummaryItem.fromJson(Map<String, dynamic> json) =>
      ConditionSummaryItem(
        key: json['key'] as String? ?? '',
        label: json['label'] as String? ?? '',
        status: _conditionItemStatusFromString(json['status'] as String?),
        displayValue: json['display_value'] as String?,
        courseRefs: (json['course_refs'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(ConditionCourseRef.fromJson)
            .toList(),
        rawValue: json['raw_value'],
      );

  String formattedValue() {
    switch (status) {
      case ConditionItemStatus.set:
        if (displayValue != null && displayValue!.trim().isNotEmpty) {
          return displayValue!;
        }
        if (courseRefs.isNotEmpty) {
          final candidates = courseRefs
              .map(
                (ref) => ref.courseName?.trim().isNotEmpty == true
                    ? ref.courseName
                    : ref.courseId,
              )
              .whereType<String>()
              .toSet()
              .join(', ');
          if (candidates.isNotEmpty) {
            return candidates;
          }
        }
        if (rawValue != null) {
          return rawValue.toString();
        }
        return '설정됨';
      case ConditionItemStatus.empty:
        return '없음';
      case ConditionItemStatus.unset:
        return '설정 안 함';
      case ConditionItemStatus.unknown:
        return displayValue?.isNotEmpty == true
            ? displayValue!
            : rawValue?.toString() ?? '설정 안 함';
    }
  }
}

class MissingGenerationRequirement {
  const MissingGenerationRequirement({
    required this.code,
    required this.message,
  });

  final String code;
  final String message;

  factory MissingGenerationRequirement.fromJson(Map<String, dynamic> json) =>
      MissingGenerationRequirement(
        code: json['code'] as String? ?? '',
        message: json['message'] as String? ?? '',
      );
}

class GenerationReadiness {
  const GenerationReadiness({
    required this.ready,
    required this.generationConfirmed,
    this.confirmedAt,
    this.confirmedVersion,
    required this.currentVersion,
    this.missingRequirements = const [],
  });

  final bool ready;
  final bool generationConfirmed;
  final String? confirmedAt;
  final int? confirmedVersion;
  final int currentVersion;
  final List<MissingGenerationRequirement> missingRequirements;

  factory GenerationReadiness.fromJson(Map<String, dynamic> json) =>
      GenerationReadiness(
        ready: json['ready'] as bool? ?? false,
        generationConfirmed: json['generation_confirmed'] as bool? ?? false,
        confirmedAt: json['confirmed_at']?.toString(),
        confirmedVersion: json['confirmed_version'] as int?,
        currentVersion: json['current_version'] as int? ?? 0,
        missingRequirements: (json['missing_requirements'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(MissingGenerationRequirement.fromJson)
            .toList(),
      );
}

class ConditionSummary {
  const ConditionSummary({
    required this.hardConstraints,
    required this.softPreferences,
    this.selectedMajorCourses = const [],
    required this.generationReadiness,
  });

  final List<ConditionSummaryItem> hardConstraints;
  final List<ConditionSummaryItem> softPreferences;
  final List<ConditionCourseRef> selectedMajorCourses;
  final GenerationReadiness generationReadiness;

  factory ConditionSummary.fromJson(Map<String, dynamic> json) =>
      ConditionSummary(
        hardConstraints: (json['hard_constraints'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(ConditionSummaryItem.fromJson)
            .toList(),
        softPreferences: (json['soft_preferences'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(ConditionSummaryItem.fromJson)
            .toList(),
        selectedMajorCourses:
            (json['selected_major_courses'] as List? ?? const [])
                .whereType<Map<String, dynamic>>()
                .map(ConditionCourseRef.fromJson)
                .toList(),
        generationReadiness: GenerationReadiness.fromJson(
          (json['generation_readiness'] as Map<String, dynamic>?) ?? const {},
        ),
      );
}

class PlanuChatResponse {
  const PlanuChatResponse({
    required this.sessionId,
    required this.message,
    this.success = true,
    this.error,
    this.conditionSummary,
  });

  final String sessionId;
  final String message;
  final bool success;
  final Map<String, dynamic>? error;
  final ConditionSummary? conditionSummary;

  factory PlanuChatResponse.fromJson(Map<String, dynamic> json) =>
      PlanuChatResponse(
        sessionId: json['session_id'] as String? ?? '',
        message: json['message'] as String? ?? '',
        success: json['success'] as bool? ?? true,
        error: json['error'] == null
            ? null
            : (json['error'] as Map).cast<String, dynamic>(),
        conditionSummary: json['condition_summary'] == null
            ? null
            : ConditionSummary.fromJson(
                (json['condition_summary'] as Map).cast<String, dynamic>(),
              ),
      );
}
