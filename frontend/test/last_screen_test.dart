import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/app_flow_state.dart';
import 'package:frontend/screens/last_screen.dart';

void main() {
  testWidgets('final screen localizes categories and shows only user condition components',
      (tester) async {
    final flow = AppFlowState()..sessionId = 'old-session';

    await tester.pumpWidget(
      MaterialApp(
        home: LastScreen(
          flow: flow,
          candidate: _candidate(),
          onViewCandidates: () {},
          onStartOver: () {},
        ),
      ),
    );

    expect(find.text('전공필수'), findsWidgets);
    expect(find.text('교양선택'), findsWidgets);
    expect(find.text('MAJOR_REQUIRED'), findsNothing);
    expect(find.text('GENERAL_ELECTIVE'), findsNothing);
    expect(find.text('수요일 공강 선호를 만족합니다.'), findsOneWidget);
    expect(find.textContaining('요일별 첫 수업'), findsNothing);
    expect(find.textContaining('필수조건을 모두 통과'), findsNothing);
  });

  testWidgets('start over clears flow values before continuing', (tester) async {
    final flow = AppFlowState()
      ..sessionId = 'old-session'
      ..department = '컴퓨터공학과'
      ..preferencePrompt = '금요일 공강'
      ..selectedTimetable = _candidate()
      ..rankedCandidates = {'ranked_candidates': [_candidate()]};
    var startedOver = false;

    await tester.pumpWidget(
      MaterialApp(
        home: LastScreen(
          flow: flow,
          candidate: _candidate(),
          onViewCandidates: () {},
          onStartOver: () => startedOver = true,
        ),
      ),
    );

    await tester.ensureVisible(find.text('새 시간표 만들기'));
    await tester.tap(find.text('새 시간표 만들기'));
    await tester.pump();

    expect(startedOver, isTrue);
    expect(flow.sessionId, isNull);
    expect(flow.department, isEmpty);
    expect(flow.preferencePrompt, isEmpty);
    expect(flow.selectedTimetable, isNull);
    expect(flow.rankedCandidates, isNull);
  });
}

Map<String, dynamic> _candidate() => {
      'candidate_id': 'candidate-1',
      'rank': 1,
      'raw_score': 12,
      'score_components': [
        {
          'key': 'valid_candidate',
          'value': 70,
          'reason': '필수조건을 모두 통과한 시간표입니다.',
        },
        {
          'key': 'preferred_free_day',
          'value': 8,
          'reason': '수요일 공강 선호를 만족합니다.',
        },
        {
          'key': 'daily_first_start',
          'value': 4,
          'reason': '요일별 첫 수업을 평가했습니다.',
        },
      ],
      'load_satisfaction': {'final_total_credits': 6},
      'timetable': {
        'total_credit': 6,
        'schedule_items': [
          {
            'day': 'MON',
            'start': '10:00',
            'end': '11:00',
            'course_name': '자료구조',
            'category': 'MAJOR_REQUIRED',
            'division': '001',
            'classroom': '201',
          },
          {
            'day': 'TUE',
            'start': '12:00',
            'end': '13:00',
            'course_name': '과학기술과사회',
            'category': 'GENERAL_ELECTIVE',
            'division': '002',
            'classroom': '202',
          },
        ],
        'courses': [
          {
            'course_id': 'MAJ-001',
            'course_name': '자료구조',
            'category': 'MAJOR_REQUIRED',
            'division': '001',
            'professor': '김교수',
            'credit': 3,
          },
          {
            'course_id': 'GEN-001',
            'course_name': '과학기술과사회',
            'category': 'GENERAL_ELECTIVE',
            'division': '002',
            'professor': '박교수',
            'credit': 3,
          },
        ],
      },
    };
