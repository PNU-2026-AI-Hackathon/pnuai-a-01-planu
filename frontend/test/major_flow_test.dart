import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/major_models.dart';
import 'package:frontend/repositories/major_repository.dart';
import 'package:frontend/screens/major_preview_screen.dart';
import 'package:frontend/screens/major_prompt_screen.dart';
import 'package:frontend/services/major_api.dart';
import 'package:frontend/state/major_flow_controller.dart';

class FakeMajorApi implements MajorApi {
  final listRequests = <String>[];
  final previewRequests = <MajorPreviewRequest>[];
  final manualPreviewRequests = <MajorManualPreviewRequest>[];
  final confirmRequests = <MajorConfirmRequest>[];
  Completer<MajorCourseListResponse>? listCompleter;
  Completer<MajorPreviewResponse>? previewCompleter;
  Completer<MajorPreviewResponse>? manualPreviewCompleter;
  Completer<MajorConfirmResponse>? confirmCompleter;

  @override
  Future<MajorCourseListResponse> listCourses(String sessionId) {
    listRequests.add(sessionId);
    return listCompleter?.future ??
        Future.value(
          const MajorCourseListResponse(
            sessionId: 'session-1',
            courses: [course],
          ),
        );
  }

  @override
  Future<MajorPreviewResponse> preview(MajorPreviewRequest request) {
    previewRequests.add(request);
    return previewCompleter?.future ?? Future.value(samplePreview);
  }

  @override
  Future<MajorPreviewResponse> manualPreview(
    MajorManualPreviewRequest request,
  ) {
    manualPreviewRequests.add(request);
    return manualPreviewCompleter?.future ?? Future.value(samplePreview);
  }

  @override
  Future<MajorConfirmResponse> confirm(MajorConfirmRequest request) {
    confirmRequests.add(request);
    return confirmCompleter?.future ?? Future.value(sampleConfirm);
  }
}

const time = MajorClassTime(
  day: 'MON',
  start: '09:00',
  end: '10:15',
  classroom: '제6공학관 6201',
  buildingCode: '6201',
);
const tuesdayTime = MajorClassTime(
  day: 'TUE',
  start: '13',
  end: '14',
  classroom: '제6공학관 6301',
  buildingCode: '6301',
);
const course = MajorCourse(
  id: 'MA100-001',
  name: '자료구조',
  category: 'MAJOR_REQUIRED',
  credit: 3,
  division: '001',
  professor: '김교수',
  classTimes: [time],
);
const tuesdayCourse = MajorCourse(
  id: 'MA200-001',
  name: '운영체제',
  category: 'MAJOR_REQUIRED',
  credit: 3,
  division: '001',
  professor: '이교수',
  classTimes: [tuesdayTime],
);
const samplePreview = MajorPreviewResponse(
  sessionId: 'session-1',
  previewId: 'preview-1',
  courses: [course],
  ambiguousCourses: [],
  unmatchedCourses: [],
  ambiguousTexts: [],
  timetableEntries: [course],
  hasTimeConflict: false,
  conflicts: [],
  canConfirm: true,
);
const sampleConfirm = MajorConfirmResponse(
  courses: [course],
  courseCount: 1,
  credits: 3,
  sessionStage: 'major_confirmed',
);
MajorFlowController controller(FakeMajorApi api) => MajorFlowController(
  sessionId: 'session-1',
  repository: MajorRepository(api),
);

void main() {
  testWidgets('empty input does not call API and loading disables button', (
    tester,
  ) async {
    final api = FakeMajorApi();
    final c = controller(api);
    await tester.pumpWidget(
      MaterialApp(home: MajorPromptScreen(controller: c)),
    );
    await tester.tap(find.byKey(const Key('majorPreviewButton')));
    await tester.pump();
    expect(api.previewRequests, isEmpty);
    expect(find.text('전공 과목명과 분반을 입력해 주세요.'), findsOneWidget);
    api.previewCompleter = Completer();
    await tester.enterText(
      find.byKey(const Key('majorPromptField')),
      '자료구조 001분반',
    );
    await tester.tap(find.byKey(const Key('majorPreviewButton')));
    await tester.pump();
    expect(api.previewRequests.length, 1);
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('majorPreviewButton')))
          .onPressed,
      isNull,
    );
  });

  testWidgets('preview displays data and issues and blocks confirm', (
    tester,
  ) async {
    final c = controller(FakeMajorApi());
    c.preview = const MajorPreviewResponse(
      sessionId: 's',
      previewId: 'new-id',
      courses: [course],
      ambiguousCourses: [
        MajorIssue(
          reference: CourseReference(courseName: '운영체제'),
          reason: 'section',
        ),
      ],
      unmatchedCourses: [
        MajorIssue(
          reference: CourseReference(courseName: '컴파일러'),
          reason: 'missing',
        ),
      ],
      ambiguousTexts: ['아무거나'],
      timetableEntries: [course],
      hasTimeConflict: true,
      conflicts: [
        MajorConflict(
          firstCourseId: 'MA100-001',
          secondCourseId: 'MA200-001',
          day: 'MON',
          start: '09:30',
          end: '10:00',
        ),
      ],
      canConfirm: false,
    );
    await tester.pumpWidget(
      MaterialApp(home: MajorPreviewScreen(controller: c)),
    );
    expect(find.textContaining('자료구조'), findsWidgets);
    expect(find.text('1개'), findsOneWidget);
    expect(find.text('3학점'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.textContaining('운영체제'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.textContaining('운영체제'), findsOneWidget);
    expect(find.textContaining('컴파일러'), findsOneWidget);
    expect(find.textContaining('아무거나'), findsOneWidget);
    expect(find.textContaining('MA100-001 ↔ MA200-001'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.byKey(const Key('majorConfirmButton')),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('majorConfirmButton')))
          .onPressed,
      isNull,
    );
  });

  testWidgets('preview timetable places classes by absolute time', (
    tester,
  ) async {
    final c = controller(FakeMajorApi())
      ..preview = const MajorPreviewResponse(
        sessionId: 's',
        previewId: 'time-position-id',
        courses: [course, tuesdayCourse],
        ambiguousCourses: [],
        unmatchedCourses: [],
        ambiguousTexts: [],
        timetableEntries: [course, tuesdayCourse],
        hasTimeConflict: false,
        conflicts: [],
        canConfirm: true,
      );
    await tester.pumpWidget(
      MaterialApp(home: MajorPreviewScreen(controller: c)),
    );

    final mondayClass = find.text('자료구조 001\n제6공학관 6201');
    final tuesdayClass = find.text('운영체제 001\n제6공학관 6301');
    expect(mondayClass, findsOneWidget);
    expect(tuesdayClass, findsOneWidget);
    expect(
      tester.getTopLeft(tuesdayClass).dy,
      greaterThan(tester.getTopLeft(mondayClass).dy),
    );
  });

  testWidgets('feedback combines original prompt and refreshes preview', (
    tester,
  ) async {
    final api = FakeMajorApi();
    final c = controller(api)
      ..originalPrompt = '자료구조 001분반'
      ..preview = samplePreview;
    await tester.pumpWidget(
      MaterialApp(home: MajorPreviewScreen(controller: c)),
    );
    await tester.scrollUntilVisible(
      find.text('수정 요청하기'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('수정 요청하기'));
    await tester.pump();
    await tester.enterText(
      find.byKey(const Key('majorFeedbackField')),
      '002분반으로 변경',
    );
    await tester.scrollUntilVisible(
      find.byKey(const Key('feedbackSubmitButton')),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(const Key('feedbackSubmitButton')));
    await tester.pumpAndSettle();
    expect(api.previewRequests.single.prompt, contains('기존 요청: 자료구조 001분반'));
    expect(api.previewRequests.single.prompt, contains('추가 수정 요청: 002분반으로 변경'));
    expect(c.preview!.previewId, 'preview-1');
  });

  testWidgets('manual selection builds preview from checked uploaded courses', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(800, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = FakeMajorApi();
    final c = controller(api);
    await tester.pumpWidget(
      MaterialApp(home: MajorPromptScreen(controller: c)),
    );

    await tester.scrollUntilVisible(
      find.byKey(const Key('majorManualSelectButton')),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(const Key('majorManualSelectButton')));
    await tester.pumpAndSettle();

    expect(api.listRequests, ['session-1']);
    expect(
      find.byKey(const Key('majorManualCourse-MA100-001')),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const Key('majorManualCourse-MA100-001')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('majorManualPreviewButton')));
    await tester.pumpAndSettle();

    expect(api.manualPreviewRequests.single.courseIds, ['MA100-001']);
    expect(find.byType(MajorPreviewScreen), findsOneWidget);
  });

  testWidgets('confirm blocks duplicate calls and stores result', (
    tester,
  ) async {
    final api = FakeMajorApi()..confirmCompleter = Completer();
    final c = controller(api)..preview = samplePreview;
    await tester.pumpWidget(
      MaterialApp(home: MajorPreviewScreen(controller: c)),
    );
    await tester.scrollUntilVisible(
      find.byKey(const Key('majorConfirmButton')),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(const Key('majorConfirmButton')));
    await tester.pump();
    expect(api.confirmRequests.length, 1);
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('majorConfirmButton')))
          .onPressed,
      isNull,
    );
    api.confirmCompleter!.complete(sampleConfirm);
    await tester.pumpAndSettle();
    expect(c.confirmation!.courseCount, 1);
    expect(c.confirmation!.sessionStage, 'major_confirmed');
  });

  testWidgets('small mobile viewport has no overflow', (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final c = controller(FakeMajorApi())..preview = samplePreview;
    await tester.pumpWidget(
      MaterialApp(home: MajorPreviewScreen(controller: c)),
    );
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}
