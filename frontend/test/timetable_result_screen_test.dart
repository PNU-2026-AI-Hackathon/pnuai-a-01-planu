import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/app_flow_state.dart';
import 'package:frontend/screens/timetable_result_screen.dart';
import 'package:frontend/services/planu_api.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('TOP 3 후보와 사용자 조건만 결과 화면에 표시한다', (tester) async {
    final flow = AppFlowState()
      ..rankedCandidates = {
        'ranked_candidates': [
          _candidate(
            rank: 1,
            courseId: 'MAJ-001',
            courseName: '자료구조',
            category: 'MAJOR_REQUIRED',
            day: 'MON',
            score: 12,
          ),
          _candidate(
            rank: 2,
            courseId: 'GEN-001',
            courseName: '고전읽기와토론',
            category: 'GENERAL_REQUIRED',
            day: 'TUE',
            score: 10,
          ),
          _candidate(
            rank: 3,
            courseId: 'ELE-001',
            courseName: '과학기술과사회',
            category: 'GENERAL_ELECTIVE',
            day: 'WED',
            score: 8,
          ),
        ],
      };

    await tester.pumpWidget(
      MaterialApp(
        home: TimetableResultScreen(
          flow: flow,
          api: PlanuApi(baseUrl: 'http://localhost'),
          onSessionExpired: () {},
        ),
      ),
    );

    expect(find.text('1순위 · 추천'), findsOneWidget);
    expect(find.text('2순위'), findsOneWidget);
    expect(find.text('3순위'), findsOneWidget);
    expect(find.text('전공필수'), findsOneWidget);
    expect(find.text('MAJOR_REQUIRED'), findsNothing);
    expect(find.text('필수조건을 모두 통과한 시간표입니다.'), findsOneWidget);
    expect(find.text('하드 조건을 모두 통과한 유효한 시간표 후보입니다.'), findsNothing);
    expect(find.text('수요일 공강 선호를 만족합니다.'), findsOneWidget);
    expect(find.textContaining('요일별 첫 수업'), findsNothing);
  });
  testWidgets('candidate tabs render the candidate matching the selected index', (tester) async {
    final flow = AppFlowState()
      ..rankedCandidates = {
        'ranked_candidates': [
          _candidate(
            rank: 1,
            courseId: 'A-001',
            courseName: 'Course Alpha',
            category: 'GENERAL_REQUIRED',
            day: 'MON',
            score: 12,
          ),
          _candidate(
            rank: 2,
            courseId: 'B-001',
            courseName: 'Course Beta',
            category: 'GENERAL_REQUIRED',
            day: 'TUE',
            score: 10,
          ),
        ],
      };

    await tester.pumpWidget(
      MaterialApp(
        home: TimetableResultScreen(
          flow: flow,
          api: PlanuApi(baseUrl: 'http://localhost'),
          onSessionExpired: () {},
        ),
      ),
    );

    expect(find.text('Course Alpha'), findsWidgets);
    expect(find.text('Course Beta'), findsNothing);
    expect(find.text('3?쒖쐞'), findsNothing);

    await tester.tap(find.text('2?쒖쐞'));
    await tester.pump();

    expect(find.text('Course Alpha'), findsNothing);
    expect(find.text('Course Beta'), findsWidgets);
  });

  testWidgets('final screen renders selected ranked candidate details after server selection',
      (tester) async {
    final flow = AppFlowState()
      ..sessionId = 'session-1'
      ..rankedCandidates = {
        'ranked_candidates': [
          _candidate(
            rank: 1,
            courseId: 'A-001',
            courseName: 'Course Alpha',
            category: 'GENERAL_REQUIRED',
            day: 'MON',
            score: 12,
          ),
        ],
      };
    final api = PlanuApi(
      baseUrl: 'http://localhost',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/sessions/session-1/timetables/candidate-1/select');
        return http.Response(
          jsonEncode({
            'session_id': 'session-1',
            'selected_timetable': {
              'candidate_id': 'candidate-1',
              'total_credits': 3,
              'section_ids': ['A-001:001'],
              'courses': [
                {'course_id': 'A-001', 'section_id': 'A-001:001'},
              ],
              'selected_at': '2026-08-24T12:00:00Z',
              'status': 'CURRENT',
            },
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: TimetableResultScreen(
          flow: flow,
          api: api,
          onSessionExpired: () {},
        ),
      ),
    );

    await tester.ensureVisible(find.byKey(const Key('selectTimetableButton')));
    await tester.tap(find.byKey(const Key('selectTimetableButton')));
    await tester.pumpAndSettle();

    expect(find.text('최종시간표 확정'), findsOneWidget);
    expect(find.text('Course Alpha'), findsWidgets);
    expect(find.text('표시할 과목 정보가 없습니다.'), findsNothing);
    expect(flow.selectedTimetable?['selection'], isA<Map<String, dynamic>>());
    expect(
      (flow.selectedTimetable?['timetable'] as Map?)?['courses'],
      isA<List<dynamic>>(),
    );
  });
}

Map<String, dynamic> _candidate({
  required int rank,
  required String courseId,
  required String courseName,
  required String category,
  required String day,
  required num score,
}) =>
    {
      'candidate_id': 'candidate-$rank',
      'rank': rank,
      'raw_score': score,
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
      'load_satisfaction': {'final_total_credits': 3},
      'timetable': {
        'rank': rank,
        'total_credit': 3,
        'reasons': ['필수조건을 모두 통과한 시간표입니다.'],
        'warnings': const [],
        'schedule_items': [
          {
            'day': day,
            'start': '10:00',
            'end': '11:00',
            'course_name': courseName,
            'category': category,
            'division': '001',
            'professor': '김교수',
            'classroom': '201',
          },
        ],
        'courses': [
          {
            'course_id': courseId,
            'course_name': courseName,
            'category': category,
            'division': '001',
            'professor': '김교수',
            'credit': 3,
          },
        ],
      },
    };
