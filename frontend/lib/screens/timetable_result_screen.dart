import 'package:flutter/material.dart';

enum CourseCategory {
  major('전공'),
  requiredGeneral('교양필수'),
  electiveGeneral('교양선택');

  const CourseCategory(this.label);

  final String label;
}

class TimetableCourse {
  const TimetableCourse({
    required this.name,
    required this.division,
    required this.professor,
    required this.category,
    required this.credit,
    required this.times,
  });

  final String name;
  final String division;
  final String professor;
  final CourseCategory category;
  final int credit;
  final List<TimetableClassTime> times;
}

class TimetableClassTime {
  const TimetableClassTime({
    required this.weekday,
    required this.startMinutes,
    required this.endMinutes,
    required this.classroom,
  });

  final int weekday;
  final int startMinutes;
  final int endMinutes;
  final String classroom;
}

class ScoreDetail {
  const ScoreDetail({required this.value, required this.reason});

  final int value;
  final String reason;
}

class TimetableRecommendation {
  const TimetableRecommendation({
    required this.rank,
    required this.preferenceScore,
    required this.courses,
    required this.hardConstraintResults,
    required this.scoreBreakdown,
    required this.reasons,
    required this.warnings,
  });

  final int rank;
  final int preferenceScore;
  final List<TimetableCourse> courses;
  final List<String> hardConstraintResults;
  final List<ScoreDetail> scoreBreakdown;
  final List<String> reasons;
  final List<String> warnings;

  int get totalCredit => courses.fold(0, (sum, course) => sum + course.credit);

  int get attendanceDays => courses
      .expand((course) => course.times)
      .map((time) => time.weekday)
      .toSet()
      .length;

  int get firstClassMinutes => courses
      .expand((course) => course.times)
      .map((time) => time.startMinutes)
      .reduce((a, b) => a < b ? a : b);

  int get lastClassMinutes => courses
      .expand((course) => course.times)
      .map((time) => time.endMinutes)
      .reduce((a, b) => a > b ? a : b);
}

class TimetableResultScreen extends StatefulWidget {
  const TimetableResultScreen({
    super.key,
    this.recommendations = sampleRecommendations,
    this.onEditPreferences,
    this.onReselectMajor,
    this.onReuploadFiles,
  });

  final List<TimetableRecommendation> recommendations;
  final VoidCallback? onEditPreferences;
  final VoidCallback? onReselectMajor;
  final VoidCallback? onReuploadFiles;

  static const sampleRecommendations = <TimetableRecommendation>[
    TimetableRecommendation(
      rank: 1,
      preferenceScore: 92,
      courses: [
        TimetableCourse(
          name: '컴퓨터프로그래밍',
          division: '001',
          professor: '김민준',
          category: CourseCategory.major,
          credit: 3,
          times: [
            TimetableClassTime(weekday: 0, startMinutes: 540, endMinutes: 615, classroom: '과학기술관 201'),
            TimetableClassTime(weekday: 2, startMinutes: 540, endMinutes: 615, classroom: '과학기술관 201'),
          ],
        ),
        TimetableCourse(
          name: '고전읽기와토론',
          division: '023',
          professor: '박서연',
          category: CourseCategory.requiredGeneral,
          credit: 2,
          times: [
            TimetableClassTime(weekday: 1, startMinutes: 630, endMinutes: 750, classroom: '인문관 312'),
          ],
        ),
        TimetableCourse(
          name: '문학과상상력',
          division: '002',
          professor: '최지우',
          category: CourseCategory.electiveGeneral,
          credit: 3,
          times: [
            TimetableClassTime(weekday: 3, startMinutes: 810, endMinutes: 960, classroom: '성학관 101'),
          ],
        ),
      ],
      hardConstraintResults: ['금요일 공강', '최대 연속 수업 2개 이하', '이동 불가능한 연강 없음'],
      scoreBreakdown: [
        ScoreDetail(value: 8, reason: '금요일 공강 선호 만족'),
        ScoreDetail(value: 4, reason: '수업 사이 총 빈 시간 40분'),
        ScoreDetail(value: -4, reason: '오전 수업 1개 포함'),
        ScoreDetail(value: -3, reason: '연강 구간 1개 포함'),
      ],
      reasons: ['전공 수업과 시간 충돌이 없습니다.', '금요일 공강 조건을 만족합니다.', '연강 이동 위험이 없습니다.'],
      warnings: ['실제 수강 가능 여부와 정원은 학생지원시스템에서 확인해 주세요.'],
    ),
    TimetableRecommendation(
      rank: 2,
      preferenceScore: 87,
      courses: [
        TimetableCourse(
          name: '컴퓨터프로그래밍', division: '001', professor: '김민준', category: CourseCategory.major, credit: 3,
          times: [TimetableClassTime(weekday: 0, startMinutes: 540, endMinutes: 615, classroom: '과학기술관 201')],
        ),
        TimetableCourse(
          name: '대학영어', division: '014', professor: '이하은', category: CourseCategory.requiredGeneral, credit: 2,
          times: [TimetableClassTime(weekday: 2, startMinutes: 780, endMinutes: 900, classroom: '언어교육원 204')],
        ),
        TimetableCourse(
          name: '과학과문화', division: '006', professor: '정도윤', category: CourseCategory.electiveGeneral, credit: 3,
          times: [TimetableClassTime(weekday: 3, startMinutes: 600, endMinutes: 750, classroom: '공동연구소동 110')],
        ),
      ],
      hardConstraintResults: ['금요일 공강', '최대 연속 수업 2개 이하', '시간 충돌 없음'],
      scoreBreakdown: [ScoreDetail(value: 6, reason: '주 3일 등교'), ScoreDetail(value: -5, reason: '오전 수업 포함')],
      reasons: ['등교일을 3일로 줄였습니다.', '수업 간 이동 시간을 충분히 확보했습니다.'],
      warnings: ['일부 강의실은 학기 시작 전 변경될 수 있습니다.'],
    ),
    TimetableRecommendation(
      rank: 3,
      preferenceScore: 81,
      courses: [
        TimetableCourse(
          name: '컴퓨터프로그래밍', division: '001', professor: '김민준', category: CourseCategory.major, credit: 3,
          times: [TimetableClassTime(weekday: 0, startMinutes: 540, endMinutes: 615, classroom: '과학기술관 201')],
        ),
        TimetableCourse(
          name: '열린사고와표현', division: '009', professor: '한유진', category: CourseCategory.requiredGeneral, credit: 2,
          times: [TimetableClassTime(weekday: 1, startMinutes: 900, endMinutes: 1020, classroom: '인문관 208')],
        ),
        TimetableCourse(
          name: '행복의심리학', division: '004', professor: '윤서준', category: CourseCategory.electiveGeneral, credit: 3,
          times: [TimetableClassTime(weekday: 4, startMinutes: 780, endMinutes: 930, classroom: '사회관 305')],
        ),
      ],
      hardConstraintResults: ['최대 연속 수업 2개 이하', '이동 불가능한 연강 없음', '시간 충돌 없음'],
      scoreBreakdown: [ScoreDetail(value: 5, reason: '늦은 첫 수업 선호 반영'), ScoreDetail(value: -7, reason: '금요일 수업 포함')],
      reasons: ['오후 수업 중심으로 구성했습니다.', '모든 수업의 이동 시간을 확보했습니다.'],
      warnings: ['금요일 공강 선호는 반영되지 않았습니다.'],
    ),
  ];

  @override
  State<TimetableResultScreen> createState() => _TimetableResultScreenState();
}

class _TimetableResultScreenState extends State<TimetableResultScreen> {
  late int _selectedIndex;

  @override
  void initState() {
    super.initState();
    _selectedIndex = _highestRankIndex(widget.recommendations);
  }

  @override
  void didUpdateWidget(covariant TimetableResultScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.recommendations != widget.recommendations) {
      _selectedIndex = _highestRankIndex(widget.recommendations);
    }
  }

  int _highestRankIndex(List<TimetableRecommendation> items) {
    if (items.isEmpty) return 0;
    var bestIndex = 0;
    for (var index = 1; index < items.length; index++) {
      if (items[index].rank < items[bestIndex].rank) bestIndex = index;
    }
    return bestIndex;
  }

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: Theme.of(context).copyWith(
        textTheme: Theme.of(context).textTheme.apply(
          fontFamily: 'Inter',
          fontFamilyFallback: const ['Pretendard', 'Noto Sans KR', 'sans-serif'],
          bodyColor: _Palette.body,
          displayColor: _Palette.ink,
        ),
      ),
      child: Scaffold(
        backgroundColor: _Palette.canvas,
        body: SafeArea(
          child: widget.recommendations.isEmpty
              ? _EmptyResult(onEditPreferences: widget.onEditPreferences)
              : CustomScrollView(
                  slivers: [
                    SliverToBoxAdapter(child: _TopBar(candidateCount: widget.recommendations.length)),
                    SliverPadding(
                      padding: const EdgeInsets.fromLTRB(24, 40, 24, 48),
                      sliver: SliverToBoxAdapter(
                        child: Center(
                          child: ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 1200),
                            child: _ResultContent(
                              recommendation: widget.recommendations[_selectedIndex],
                              recommendations: widget.recommendations,
                              selectedIndex: _selectedIndex,
                              onSelected: (index) => setState(() => _selectedIndex = index),
                              onEditPreferences: widget.onEditPreferences,
                              onReselectMajor: widget.onReselectMajor,
                              onReuploadFiles: widget.onReuploadFiles,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}

class _Palette {
  static const ink = Color(0xFF111111);
  static const body = Color(0xFF374151);
  static const muted = Color(0xFF6B7280);
  static const hairline = Color(0xFFE5E7EB);
  static const surfaceSoft = Color(0xFFF8F9FA);
  static const surfaceCard = Color(0xFFF5F5F5);
  static const canvas = Colors.white;
  static const success = Color(0xFF10B981);
  static const warningSurface = Color(0xFFFFFBEB);
  static const warningInk = Color(0xFF92400E);
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.candidateCount});
  final int candidateCount;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 64,
      padding: const EdgeInsets.symmetric(horizontal: 24),
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: _Palette.hairline))),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1200),
          child: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: const BoxDecoration(color: _Palette.ink, shape: BoxShape.circle),
                child: const Icon(Icons.calendar_month_rounded, color: Colors.white, size: 20),
              ),
              const SizedBox(width: 12),
              Text('PlaNU', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w600)),
              const Spacer(),
              _Pill(label: '7 / 7  결과 · 후보 $candidateCount개'),
            ],
          ),
        ),
      ),
    );
  }
}

class _ResultContent extends StatelessWidget {
  const _ResultContent({
    required this.recommendation,
    required this.recommendations,
    required this.selectedIndex,
    required this.onSelected,
    this.onEditPreferences,
    this.onReselectMajor,
    this.onReuploadFiles,
  });

  final TimetableRecommendation recommendation;
  final List<TimetableRecommendation> recommendations;
  final int selectedIndex;
  final ValueChanged<int> onSelected;
  final VoidCallback? onEditPreferences;
  final VoidCallback? onReselectMajor;
  final VoidCallback? onReuploadFiles;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _Pill(label: '추천 시간표'),
        const SizedBox(height: 20),
        Text(
          '나에게 맞는 시간표를 찾았어요',
          style: Theme.of(context).textTheme.headlineLarge?.copyWith(fontWeight: FontWeight.w600, letterSpacing: -1, height: 1.15),
        ),
        const SizedBox(height: 12),
        Text('필수 조건을 모두 확인하고 선호 기준을 비교해 추천한 결과입니다.', style: Theme.of(context).textTheme.bodyLarge?.copyWith(height: 1.5)),
        const SizedBox(height: 32),
        _CandidateTabs(recommendations: recommendations, selectedIndex: selectedIndex, onSelected: onSelected),
        const SizedBox(height: 24),
        AnimatedSwitcher(
          duration: const Duration(milliseconds: 180),
          child: Column(
            key: ValueKey(recommendation.rank),
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _CandidateHeader(recommendation: recommendation),
              const SizedBox(height: 24),
              _SummaryMetrics(recommendation: recommendation),
              const SizedBox(height: 24),
              _TwoColumn(
                left: _CheckSection(items: recommendation.hardConstraintResults),
                right: _ScoreSection(items: recommendation.scoreBreakdown),
              ),
              const SizedBox(height: 24),
              _SectionCard(title: '시간표', subtitle: '과목 유형은 색상과 라벨로 함께 구분했어요.', child: _TimetableGrid(courses: recommendation.courses)),
              const SizedBox(height: 24),
              _CourseList(courses: recommendation.courses),
              const SizedBox(height: 24),
              _TwoColumn(
                left: _BulletSection(title: '추천 이유', icon: Icons.auto_awesome_outlined, items: recommendation.reasons),
                right: _WarningSection(items: recommendation.warnings),
              ),
            ],
          ),
        ),
        const SizedBox(height: 32),
        _BottomActions(onEditPreferences: onEditPreferences, onReselectMajor: onReselectMajor, onReuploadFiles: onReuploadFiles),
      ],
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(color: _Palette.surfaceCard, borderRadius: BorderRadius.circular(999)),
        child: Text(label, style: Theme.of(context).textTheme.labelMedium?.copyWith(color: _Palette.ink, fontWeight: FontWeight.w600)),
      ),
    );
  }
}

class _CandidateTabs extends StatelessWidget {
  const _CandidateTabs({required this.recommendations, required this.selectedIndex, required this.onSelected});
  final List<TimetableRecommendation> recommendations;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(6),
      decoration: BoxDecoration(color: _Palette.surfaceSoft, borderRadius: BorderRadius.circular(12)),
      child: Row(
        children: List.generate(recommendations.length, (index) {
          final selected = index == selectedIndex;
          return Expanded(
            child: Semantics(
              selected: selected,
              button: true,
              child: InkWell(
                borderRadius: BorderRadius.circular(8),
                onTap: () => onSelected(index),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 160),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  decoration: BoxDecoration(
                    color: selected ? Colors.white : Colors.transparent,
                    borderRadius: BorderRadius.circular(8),
                    border: selected ? Border.all(color: _Palette.hairline) : null,
                  ),
                  child: Text('후보 ${recommendations[index].rank}', textAlign: TextAlign.center, style: TextStyle(color: selected ? _Palette.ink : _Palette.muted, fontWeight: FontWeight.w600, fontSize: 14)),
                ),
              ),
            ),
          );
        }),
      ),
    );
  }
}

class _CandidateHeader extends StatelessWidget {
  const _CandidateHeader({required this.recommendation});
  final TimetableRecommendation recommendation;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(color: _Palette.ink, borderRadius: BorderRadius.circular(16)),
      child: Wrap(
        spacing: 24,
        runSpacing: 12,
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('후보 ${recommendation.rank}', style: Theme.of(context).textTheme.titleLarge?.copyWith(color: Colors.white, fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            const Text('가장 높은 순위의 추천안부터 확인해 보세요.', style: TextStyle(color: Color(0xFFA1A1AA), fontSize: 14, height: 1.5)),
          ]),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            const Text('선호 적합도 점수', style: TextStyle(color: Color(0xFFA1A1AA), fontSize: 13, fontWeight: FontWeight.w500)),
            const SizedBox(height: 4),
            Text('${recommendation.preferenceScore}점', style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w600, letterSpacing: -0.5)),
          ]),
        ],
      ),
    );
  }
}

class _SummaryMetrics extends StatelessWidget {
  const _SummaryMetrics({required this.recommendation});
  final TimetableRecommendation recommendation;

  @override
  Widget build(BuildContext context) {
    final metrics = [
      ('총 학점', '${recommendation.totalCredit}학점', Icons.school_outlined),
      ('등교일', '주 ${recommendation.attendanceDays}일', Icons.directions_walk_outlined),
      ('첫 수업', _formatMinutes(recommendation.firstClassMinutes), Icons.wb_sunny_outlined),
      ('마지막 수업', _formatMinutes(recommendation.lastClassMinutes), Icons.nights_stay_outlined),
    ];
    return LayoutBuilder(builder: (context, constraints) {
      final width = constraints.maxWidth < 640 ? (constraints.maxWidth - 12) / 2 : (constraints.maxWidth - 36) / 4;
      return Wrap(
        spacing: 12,
        runSpacing: 12,
        children: metrics.map((metric) => SizedBox(width: width, child: _MetricCard(label: metric.$1, value: metric.$2, icon: metric.$3))).toList(),
      );
    });
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({required this.label, required this.value, required this.icon});
  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: _Palette.surfaceCard, borderRadius: BorderRadius.circular(12)),
      child: Row(children: [
        Icon(icon, size: 20, color: _Palette.ink),
        const SizedBox(width: 12),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label, style: const TextStyle(color: _Palette.muted, fontSize: 13, fontWeight: FontWeight.w500)),
          const SizedBox(height: 3),
          Text(value, style: const TextStyle(color: _Palette.ink, fontSize: 16, fontWeight: FontWeight.w600)),
        ])),
      ]),
    );
  }
}

class _TwoColumn extends StatelessWidget {
  const _TwoColumn({required this.left, required this.right});
  final Widget left;
  final Widget right;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      if (constraints.maxWidth < 760) return Column(children: [left, const SizedBox(height: 16), right]);
      return IntrinsicHeight(child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [Expanded(child: left), const SizedBox(width: 16), Expanded(child: right)]));
    });
  }
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({required this.title, required this.child, this.subtitle});
  final String title;
  final String? subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(12), border: Border.all(color: _Palette.hairline)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: Theme.of(context).textTheme.titleMedium?.copyWith(color: _Palette.ink, fontWeight: FontWeight.w600)),
        if (subtitle != null) ...[const SizedBox(height: 6), Text(subtitle!, style: const TextStyle(color: _Palette.muted, fontSize: 14, height: 1.5))],
        const SizedBox(height: 20),
        child,
      ]),
    );
  }
}

class _CheckSection extends StatelessWidget {
  const _CheckSection({required this.items});
  final List<String> items;

  @override
  Widget build(BuildContext context) {
    return _SectionCard(
      title: '필수 조건',
      child: Column(children: items.map((item) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Icon(Icons.check_circle_rounded, color: _Palette.success, size: 20),
          const SizedBox(width: 10),
          Expanded(child: Text(item, style: const TextStyle(fontSize: 14, height: 1.4))),
        ]),
      )).toList()),
    );
  }
}

class _ScoreSection extends StatelessWidget {
  const _ScoreSection({required this.items});
  final List<ScoreDetail> items;

  @override
  Widget build(BuildContext context) {
    final visibleItems = items.where((item) => item.value != 0);
    return _SectionCard(
      title: '점수 계산 내역',
      child: Column(children: visibleItems.map((item) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: 36, child: Text(item.value > 0 ? '+${item.value}' : '${item.value}', style: TextStyle(color: item.value > 0 ? _Palette.success : const Color(0xFFEF4444), fontWeight: FontWeight.w600))),
          Expanded(child: Text(item.reason, style: const TextStyle(fontSize: 14, height: 1.4))),
        ]),
      )).toList()),
    );
  }
}

class _TimetableGrid extends StatelessWidget {
  const _TimetableGrid({required this.courses});
  final List<TimetableCourse> courses;
  static const _days = ['월', '화', '수', '목', '금'];
  static const _start = 540;
  static const _end = 1080;
  static const _hourHeight = 72.0;

  @override
  Widget build(BuildContext context) {
    const timeWidth = 48.0;
    const dayWidth = 164.0;
    final gridHeight = ((_end - _start) / 60) * _hourHeight;
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SizedBox(
        width: timeWidth + dayWidth * 5,
        child: Column(children: [
          Row(children: [
            const SizedBox(width: timeWidth, height: 40),
            ..._days.map((day) => Container(width: dayWidth, height: 40, alignment: Alignment.center, decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: _Palette.hairline))), child: Text(day, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)))),
          ]),
          SizedBox(
            height: gridHeight,
            child: Stack(children: [
              for (var hour = 9; hour <= 18; hour++) ...[
                Positioned(top: (hour - 9) * _hourHeight, left: 0, child: SizedBox(width: timeWidth, child: Text('${hour.toString().padLeft(2, '0')}:00', style: const TextStyle(fontSize: 11, color: _Palette.muted)))),
                Positioned(top: (hour - 9) * _hourHeight, left: timeWidth, right: 0, child: const Divider(height: 1, color: _Palette.hairline)),
              ],
              for (var day = 0; day <= 5; day++) Positioned(left: timeWidth + day * dayWidth, top: 0, bottom: 0, child: const VerticalDivider(width: 1, color: _Palette.hairline)),
              for (final course in courses)
                for (final time in course.times)
                  Positioned(
                    left: timeWidth + time.weekday * dayWidth + 4,
                    top: (time.startMinutes - _start) / 60 * _hourHeight + 3,
                    width: dayWidth - 8,
                    height: (time.endMinutes - time.startMinutes) / 60 * _hourHeight - 6,
                    child: _ScheduleBlock(course: course, time: time),
                  ),
            ]),
          ),
        ]),
      ),
    );
  }
}

class _ScheduleBlock extends StatelessWidget {
  const _ScheduleBlock({required this.course, required this.time});
  final TimetableCourse course;
  final TimetableClassTime time;

  @override
  Widget build(BuildContext context) {
    final color = switch (course.category) {
      CourseCategory.major => const Color(0xFFE0E7FF),
      CourseCategory.requiredGeneral => const Color(0xFFD1FAE5),
      CourseCategory.electiveGeneral => const Color(0xFFFFEDD5),
    };
    return Container(
      padding: const EdgeInsets.all(7),
      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(6)),
      child: ClipRect(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('[${course.category.label}]', style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: _Palette.body)),
        const SizedBox(height: 2),
        Text(course.name, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, height: 1.2)),
        const SizedBox(height: 2),
        Text(time.classroom, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 10, color: _Palette.muted)),
      ])),
    );
  }
}

class _CourseList extends StatelessWidget {
  const _CourseList({required this.courses});
  final List<TimetableCourse> courses;

  @override
  Widget build(BuildContext context) {
    final sorted = [...courses]..sort((a, b) {
      final dayCompare = a.times.first.weekday.compareTo(b.times.first.weekday);
      return dayCompare != 0 ? dayCompare : a.times.first.startMinutes.compareTo(b.times.first.startMinutes);
    });
    return _SectionCard(
      title: '과목 목록',
      child: Column(children: List.generate(sorted.length, (index) {
        final course = sorted[index];
        return Container(
          padding: const EdgeInsets.symmetric(vertical: 14),
          decoration: BoxDecoration(border: index == sorted.length - 1 ? null : const Border(bottom: BorderSide(color: _Palette.hairline))),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4), decoration: BoxDecoration(color: _Palette.surfaceCard, borderRadius: BorderRadius.circular(999)), child: Text(course.category.label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600))),
            const SizedBox(width: 12),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${course.name} ${course.division}', style: const TextStyle(color: _Palette.ink, fontSize: 15, fontWeight: FontWeight.w600)),
              const SizedBox(height: 5),
              Text('${course.professor} · ${_formatCourseTimes(course.times)} · ${course.credit}학점', style: const TextStyle(color: _Palette.muted, fontSize: 13, height: 1.4)),
            ])),
          ]),
        );
      })),
    );
  }
}

class _BulletSection extends StatelessWidget {
  const _BulletSection({required this.title, required this.icon, required this.items});
  final String title;
  final IconData icon;
  final List<String> items;

  @override
  Widget build(BuildContext context) {
    return _SectionCard(title: title, child: Column(children: items.map((item) => Padding(padding: const EdgeInsets.only(bottom: 12), child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [Icon(icon, size: 18, color: _Palette.ink), const SizedBox(width: 10), Expanded(child: Text(item, style: const TextStyle(fontSize: 14, height: 1.45)))]))).toList()));
  }
}

class _WarningSection extends StatelessWidget {
  const _WarningSection({required this.items});
  final List<String> items;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(color: _Palette.warningSurface, borderRadius: BorderRadius.circular(12), border: Border.all(color: const Color(0xFFFDE68A))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('주의사항', style: Theme.of(context).textTheme.titleMedium?.copyWith(color: _Palette.warningInk, fontWeight: FontWeight.w600)),
        const SizedBox(height: 20),
        ...items.map((item) => Padding(padding: const EdgeInsets.only(bottom: 12), child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [const Icon(Icons.info_outline_rounded, size: 18, color: _Palette.warningInk), const SizedBox(width: 10), Expanded(child: Text(item, style: const TextStyle(color: _Palette.warningInk, fontSize: 14, height: 1.45)))]))),
      ]),
    );
  }
}

class _BottomActions extends StatelessWidget {
  const _BottomActions({this.onEditPreferences, this.onReselectMajor, this.onReuploadFiles});
  final VoidCallback? onEditPreferences;
  final VoidCallback? onReselectMajor;
  final VoidCallback? onReuploadFiles;

  @override
  Widget build(BuildContext context) {
    final buttonStyle = ButtonStyle(
      backgroundColor: const WidgetStatePropertyAll(Colors.white),
      foregroundColor: const WidgetStatePropertyAll(_Palette.ink),
      side: const WidgetStatePropertyAll(BorderSide(color: _Palette.hairline)),
    );
    final actions = [
      OutlinedButton.icon(style: buttonStyle, onPressed: onReuploadFiles ?? () {}, icon: const Icon(Icons.upload_file_outlined, size: 18), label: const Text('파일 다시 업로드')),
      OutlinedButton.icon(style: buttonStyle, onPressed: onReselectMajor ?? () {}, icon: const Icon(Icons.school_outlined, size: 18), label: const Text('전공 다시 선택')),
      FilledButton.icon(style: buttonStyle, onPressed: onEditPreferences ?? () {}, icon: const Icon(Icons.tune_rounded, size: 18), label: const Text('교양 조건 수정')),
    ];
    return LayoutBuilder(builder: (context, constraints) {
      if (constraints.maxWidth < 680) return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: actions.expand((button) => [SizedBox(height: 48, child: button), const SizedBox(height: 12)]).toList());
      return Row(mainAxisAlignment: MainAxisAlignment.end, children: actions.map((button) => Padding(padding: const EdgeInsets.only(left: 12), child: SizedBox(height: 44, child: button))).toList());
    });
  }
}

class _EmptyResult extends StatelessWidget {
  const _EmptyResult({this.onEditPreferences});
  final VoidCallback? onEditPreferences;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.event_busy_outlined, size: 48, color: _Palette.muted),
            const SizedBox(height: 20),
            Text('추천 결과가 없어요', style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w600)),
            const SizedBox(height: 12),
            const Text('조건을 조금 완화한 뒤 다시 추천을 요청해 주세요.', textAlign: TextAlign.center, style: TextStyle(color: _Palette.muted, height: 1.5)),
            const SizedBox(height: 24),
            FilledButton(onPressed: onEditPreferences, child: const Text('교양 조건 수정')),
          ]),
        ),
      ),
    );
  }
}

String _formatMinutes(int minutes) {
  final hour = minutes ~/ 60;
  final minute = minutes % 60;
  return '${hour.toString().padLeft(2, '0')}:${minute.toString().padLeft(2, '0')}';
}

String _formatCourseTimes(List<TimetableClassTime> times) {
  const days = ['월', '화', '수', '목', '금'];
  return times.map((time) => '${days[time.weekday]} ${_formatMinutes(time.startMinutes)}').join(' · ');
}
