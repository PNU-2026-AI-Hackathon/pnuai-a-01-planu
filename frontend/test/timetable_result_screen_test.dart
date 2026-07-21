import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/app_flow_state.dart';
import 'package:frontend/screens/timetable_result_screen.dart';
import 'package:frontend/services/planu_api.dart';

void main() {
  testWidgets('랭킹 API 응답을 카드와 시간표로 표시한다', (tester) async {
    final flow = AppFlowState()
      ..rankedCandidates = {
        'ranked_candidates': [
          {
            'rank': 1,
            'raw_score': 12,
            'score_components': [
              {'value': 8, 'reason': '금요일 공강 선호 만족'},
              {'value': 4, 'reason': '수업 간 공백 최소화'},
            ],
            'load_satisfaction': {'final_total_credits': 3},
            'timetable': {
              'total_credit': 3,
              'reasons': ['전공 수업과 충돌하지 않습니다.'],
              'warnings': ['수강 정원을 확인해 주세요.'],
              'schedule_items': [
                {
                  'day': 'MON',
                  'start': '09:00',
                  'end': '10:15',
                  'course_name': '컴퓨터프로그래밍',
                  'category': 'major',
                  'division': '001',
                  'professor': '김교수',
                  'classroom': '201',
                },
                {
                  'day': 'MON',
                  'start': '10:15',
                  'end': '11:30',
                  'course_name': '고전읽기와토론',
                  'category': 'general_required',
                  'division': '023',
                  'professor': '박교수',
                  'classroom': '202',
                },
              ],
              'courses': [
                {
                  'course_name': '컴퓨터프로그래밍',
                  'category': 'major',
                  'division': '001',
                  'professor': '김교수',
                  'credit': 3,
                },
              ],
            },
          },
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

    expect(find.text('나에게 맞는 시간표를 찾았어요'), findsOneWidget);
    expect(find.text('12점'), findsOneWidget);
    expect(find.text('컴퓨터프로그래밍 001'), findsOneWidget);
    expect(find.text('금요일 공강 선호 만족'), findsOneWidget);
    expect(find.text('연강이 1회 포함되어 있습니다.'), findsOneWidget);
    expect(find.text('연강이 없습니다.'), findsNothing);
  });
}
