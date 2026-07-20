class MajorClassTime {
  const MajorClassTime({
    required this.day,
    required this.start,
    required this.end,
    required this.classroom,
    required this.buildingCode,
  });
  final String day, start, end, classroom, buildingCode;
  factory MajorClassTime.fromJson(Map<String, dynamic> json) => MajorClassTime(
    day: json['day'] as String? ?? '',
    start: json['start'] as String? ?? '',
    end: json['end'] as String? ?? '',
    classroom: json['classroom'] as String? ?? '',
    buildingCode: json['building_code'] as String? ?? '',
  );
  Map<String, dynamic> toJson() => {
    'day': day,
    'start': start,
    'end': end,
    'classroom': classroom,
    'building_code': buildingCode,
  };
}

class MajorCourse {
  const MajorCourse({
    required this.id,
    required this.name,
    required this.category,
    required this.credit,
    required this.division,
    required this.professor,
    required this.classTimes,
  });
  final String id, name, category, division, professor;
  final double credit;
  final List<MajorClassTime> classTimes;
  factory MajorCourse.fromJson(Map<String, dynamic> json) => MajorCourse(
    id: json['course_id'] as String? ?? '',
    name: json['course_name'] as String? ?? '',
    category: json['category'] as String? ?? '',
    credit: (json['credit'] as num?)?.toDouble() ?? 0,
    division: json['division'] as String? ?? '',
    professor: json['professor'] as String? ?? '',
    classTimes: (json['class_times'] as List? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(MajorClassTime.fromJson)
        .toList(),
  );
  Map<String, dynamic> toJson() => {
    'course_id': id,
    'course_name': name,
    'category': category,
    'credit': credit,
    'division': division,
    'professor': professor,
    'class_times': classTimes.map((e) => e.toJson()).toList(),
  };
}

class CourseReference {
  const CourseReference({required this.courseName, this.section});
  final String courseName;
  final String? section;
  factory CourseReference.fromJson(Map<String, dynamic> json) =>
      CourseReference(
        courseName: json['course_name'] as String? ?? '',
        section: json['section'] as String?,
      );
}

class MajorIssue {
  const MajorIssue({
    required this.reference,
    required this.reason,
    this.candidates = const [],
  });
  final CourseReference reference;
  final String reason;
  final List<MajorCourse> candidates;
  factory MajorIssue.fromJson(Map<String, dynamic> json) => MajorIssue(
    reference: CourseReference.fromJson(
      (json['reference'] as Map?)?.cast<String, dynamic>() ?? const {},
    ),
    reason: json['reason'] as String? ?? '',
    candidates: (json['candidates'] as List? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(MajorCourse.fromJson)
        .toList(),
  );
}

class MajorConflict {
  const MajorConflict({
    required this.firstCourseId,
    required this.secondCourseId,
    required this.day,
    required this.start,
    required this.end,
  });
  final String firstCourseId, secondCourseId, day, start, end;
  factory MajorConflict.fromJson(Map<String, dynamic> json) => MajorConflict(
    firstCourseId: json['first_course_id'] as String? ?? '',
    secondCourseId: json['second_course_id'] as String? ?? '',
    day: json['day'] as String? ?? '',
    start: json['overlap_start'] as String? ?? '',
    end: json['overlap_end'] as String? ?? '',
  );
}

class MajorPreviewRequest {
  const MajorPreviewRequest(this.sessionId, this.prompt);
  final String sessionId, prompt;
  Map<String, dynamic> toJson() => {'session_id': sessionId, 'prompt': prompt};
}

class MajorPreviewResponse {
  const MajorPreviewResponse({
    required this.sessionId,
    required this.previewId,
    required this.courses,
    required this.ambiguousCourses,
    required this.unmatchedCourses,
    required this.ambiguousTexts,
    required this.timetableEntries,
    required this.hasTimeConflict,
    required this.conflicts,
    required this.canConfirm,
  });
  final String sessionId, previewId;
  final List<MajorCourse> courses, timetableEntries;
  final List<MajorIssue> ambiguousCourses, unmatchedCourses;
  final List<String> ambiguousTexts;
  final List<MajorConflict> conflicts;
  final bool hasTimeConflict, canConfirm;
  double get totalCredits =>
      courses.fold(0, (sum, course) => sum + course.credit);
  bool get isConfirmable =>
      canConfirm &&
      ambiguousCourses.isEmpty &&
      unmatchedCourses.isEmpty &&
      ambiguousTexts.isEmpty &&
      !hasTimeConflict;
  factory MajorPreviewResponse.fromJson(Map<String, dynamic> json) {
    List<Map<String, dynamic>> maps(String key) =>
        (json[key] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .toList();
    return MajorPreviewResponse(
      sessionId: json['session_id'] as String? ?? '',
      previewId: json['preview_id'] as String? ?? '',
      courses: maps('matched_courses')
          .map(
            (e) => MajorCourse.fromJson(
              (e['course'] as Map).cast<String, dynamic>(),
            ),
          )
          .toList(),
      ambiguousCourses: maps(
        'ambiguous_courses',
      ).map(MajorIssue.fromJson).toList(),
      unmatchedCourses: maps(
        'unmatched_courses',
      ).map(MajorIssue.fromJson).toList(),
      ambiguousTexts: (json['ambiguous_texts'] as List? ?? const [])
          .whereType<String>()
          .toList(),
      timetableEntries: maps('timetable_entries')
          .map(
            (e) => MajorCourse.fromJson({
              ...e,
              'class_times': [e],
            }),
          )
          .toList(),
      hasTimeConflict: json['has_time_conflict'] as bool? ?? false,
      conflicts: maps('conflicts').map(MajorConflict.fromJson).toList(),
      canConfirm: json['can_confirm'] as bool? ?? false,
    );
  }
}

class MajorConfirmRequest {
  const MajorConfirmRequest(this.sessionId, this.previewId);
  final String sessionId, previewId;
  Map<String, dynamic> toJson() => {
    'session_id': sessionId,
    'preview_id': previewId,
  };
}

class MajorConfirmResponse {
  const MajorConfirmResponse({
    required this.courses,
    required this.courseCount,
    required this.credits,
    required this.sessionStage,
  });
  final List<MajorCourse> courses;
  final int courseCount;
  final double credits;
  final String sessionStage;
  factory MajorConfirmResponse.fromJson(Map<String, dynamic> json) =>
      MajorConfirmResponse(
        courses: (json['confirmed_courses'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(MajorCourse.fromJson)
            .toList(),
        courseCount: json['confirmed_course_count'] as int? ?? 0,
        credits: (json['confirmed_major_credits'] as num?)?.toDouble() ?? 0,
        sessionStage: json['session_stage'] as String? ?? '',
      );
}

class ApiError implements Exception {
  const ApiError(this.code, this.message, {this.details = const {}});
  final String code, message;
  final Map<String, dynamic> details;
  factory ApiError.fromJson(Map<String, dynamic> json) {
    final value = (json['error'] as Map?)?.cast<String, dynamic>() ?? json;
    return ApiError(
      value['code'] as String? ?? 'UNKNOWN',
      value['message'] as String? ?? '요청을 처리하지 못했습니다.',
      details: (value['details'] as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }
}
