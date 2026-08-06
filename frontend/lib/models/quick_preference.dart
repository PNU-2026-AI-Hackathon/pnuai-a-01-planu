enum QuickPreference {
  requiredFridayOff,
  excludeMorningClasses,
  minimizeAttendanceDays,
  minimizeConsecutiveClasses,
  preferLateStart,
  compactSchedule,
}

extension QuickPreferenceLabel on QuickPreference {
  String get label {
    switch (this) {
      case QuickPreference.requiredFridayOff:
        return '금요일 공강';
      case QuickPreference.excludeMorningClasses:
        return '오전 수업 제외';
      case QuickPreference.minimizeAttendanceDays:
        return '등교일 줄이기';
      case QuickPreference.minimizeConsecutiveClasses:
        return '연강 줄이기';
      case QuickPreference.preferLateStart:
        return '늦게 시작하기';
      case QuickPreference.compactSchedule:
        return '수업 몰아서 듣기';
    }
  }

  String get key {
    switch (this) {
      case QuickPreference.requiredFridayOff:
        return 'requiredFridayOff';
      case QuickPreference.excludeMorningClasses:
        return 'excludeMorningClasses';
      case QuickPreference.minimizeAttendanceDays:
        return 'minimizeAttendanceDays';
      case QuickPreference.minimizeConsecutiveClasses:
        return 'minimizeConsecutiveClasses';
      case QuickPreference.preferLateStart:
        return 'preferLateStart';
      case QuickPreference.compactSchedule:
        return 'compactSchedule';
    }
  }
}
