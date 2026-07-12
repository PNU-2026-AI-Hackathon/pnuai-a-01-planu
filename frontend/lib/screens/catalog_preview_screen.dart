import 'package:flutter/material.dart';

class CatalogPreviewScreen extends StatelessWidget {
  const CatalogPreviewScreen({
    super.key,
    this.sessionId,
    this.majorCandidates = _sampleMajorCandidates,
    this.electiveCandidatesCount = 45,
    this.onSelectMajorCourses,
    this.onUploadAgain,
  });

  final String? sessionId;
  final List<CatalogPreviewCourse> majorCandidates;
  final int electiveCandidatesCount;
  final VoidCallback? onSelectMajorCourses;
  final VoidCallback? onUploadAgain;

  static const List<CatalogPreviewCourse> _sampleMajorCandidates =
      <CatalogPreviewCourse>[
        CatalogPreviewCourse(
          courseName: '컴퓨터 프로그래밍',
          division: '001',
          professor: '김교수',
        ),
        CatalogPreviewCourse(
          courseName: '이산수학',
          division: '002',
          professor: '박교수',
        ),
        CatalogPreviewCourse(
          courseName: '알고리즘',
          division: '001',
          professor: '최교수',
        ),
      ];

  static const Color _ink = Color(0xFF111111);
  static const Color _body = Color(0xFF374151);
  static const Color _muted = Color(0xFF6B7280);
  static const Color _hairline = Color(0xFFE5E7EB);
  static const Color _surfaceSoft = Color(0xFFF8F9FA);
  static const Color _surfaceCard = Color(0xFFF5F5F5);
  static const Color _success = Color(0xFF10B981);
  static const Color _warning = Color(0xFFF59E0B);

  bool get _hasMajorCandidates => majorCandidates.isNotEmpty;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        foregroundColor: _ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        title: const Text('PlaNU'),
        centerTitle: false,
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 960),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 40, 24, 32),
              children: <Widget>[
                const _StepPill(),
                const SizedBox(height: 24),
                Text(
                  '수강편람 분석 결과',
                  style: theme.textTheme.displaySmall?.copyWith(
                    color: _ink,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0,
                    height: 1.2,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  '전공 과목을 선택하기 전에 업로드한 수강편람이 정확히 분석되었는지 확인해 주세요.',
                  style: theme.textTheme.bodyLarge?.copyWith(
                    color: _body,
                    height: 1.5,
                  ),
                ),
                if (sessionId != null) ...<Widget>[
                  const SizedBox(height: 16),
                  _SessionBadge(sessionId: sessionId!),
                ],
                const SizedBox(height: 32),
                _SummaryGrid(
                  majorCount: majorCandidates.length,
                  electiveCount: electiveCandidatesCount,
                ),
                const SizedBox(height: 24),
                if (_hasMajorCandidates)
                  _CandidatePreview(candidates: majorCandidates)
                else
                  _EmptyMajorNotice(onUploadAgain: onUploadAgain),
                const SizedBox(height: 24),
                Row(
                  children: <Widget>[
                    if (onUploadAgain != null) ...<Widget>[
                      OutlinedButton.icon(
                        onPressed: onUploadAgain,
                        icon: const Icon(Icons.upload_file_rounded, size: 18),
                        label: const Text('다시 업로드'),
                      ),
                      const SizedBox(width: 12),
                    ],
                    Expanded(
                      child: FilledButton.icon(
                        onPressed: _hasMajorCandidates
                            ? onSelectMajorCourses ?? () {}
                            : null,
                        style: FilledButton.styleFrom(
                          backgroundColor: _ink,
                          foregroundColor: Colors.white,
                          disabledBackgroundColor: _hairline,
                          disabledForegroundColor: _muted,
                          minimumSize: const Size.fromHeight(48),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                          textStyle: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        icon: const Icon(Icons.arrow_forward_rounded, size: 18),
                        label: const Text('전공 과목 선택하기'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class CatalogPreviewCourse {
  const CatalogPreviewCourse({
    required this.courseName,
    required this.division,
    required this.professor,
  });

  final String courseName;
  final String division;
  final String professor;
}

class _StepPill extends StatelessWidget {
  const _StepPill();

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: CatalogPreviewScreen._surfaceSoft,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Text(
            '4 / 6',
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: CatalogPreviewScreen._ink,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }
}

class _SessionBadge extends StatelessWidget {
  const _SessionBadge({required this.sessionId});

  final String sessionId;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: CatalogPreviewScreen._surfaceCard,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Text(
            '세션 $sessionId',
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: CatalogPreviewScreen._muted,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }
}

class _SummaryGrid extends StatelessWidget {
  const _SummaryGrid({
    required this.majorCount,
    required this.electiveCount,
  });

  final int majorCount;
  final int electiveCount;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isCompact = constraints.maxWidth < 640;
        final cards = <Widget>[
          _SummaryCard(
            icon: Icons.school_outlined,
            label: '전공 과목 후보',
            value: '$majorCount',
            tone: majorCount > 0
                ? CatalogPreviewScreen._success
                : CatalogPreviewScreen._warning,
          ),
          _SummaryCard(
            icon: Icons.auto_stories_outlined,
            label: '교양 과목 후보',
            value: '$electiveCount',
            tone: CatalogPreviewScreen._ink,
          ),
        ];

        if (isCompact) {
          return Column(
            children: <Widget>[
              for (var index = 0; index < cards.length; index += 1) ...[
                cards[index],
                if (index != cards.length - 1) const SizedBox(height: 16),
              ],
            ],
          );
        }

        return Row(
          children: <Widget>[
            for (var index = 0; index < cards.length; index += 1) ...[
              Expanded(child: cards[index]),
              if (index != cards.length - 1) const SizedBox(width: 24),
            ],
          ],
        );
      },
    );
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({
    required this.icon,
    required this.label,
    required this.value,
    required this.tone,
  });

  final IconData icon;
  final String label;
  final String value;
  final Color tone;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: CatalogPreviewScreen._surfaceCard,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Row(
          children: <Widget>[
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(20),
              ),
              child: Icon(icon, color: tone, size: 22),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    label,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: CatalogPreviewScreen._muted,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    value,
                    style: theme.textTheme.headlineSmall?.copyWith(
                      color: CatalogPreviewScreen._ink,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CandidatePreview extends StatelessWidget {
  const _CandidatePreview({required this.candidates});

  final List<CatalogPreviewCourse> candidates;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final previewItems = candidates.take(5).toList();

    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: CatalogPreviewScreen._hairline),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                const Icon(Icons.fact_check_outlined, size: 22),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    '전공 과목 후보 미리보기',
                    style: theme.textTheme.titleMedium?.copyWith(
                      color: CatalogPreviewScreen._ink,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              '분석된 과목 중 일부입니다. 다음 화면에서 수강할 분반을 선택할 수 있습니다.',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: CatalogPreviewScreen._muted,
              ),
            ),
            const SizedBox(height: 20),
            for (var index = 0; index < previewItems.length; index += 1) ...[
              _CoursePreviewTile(course: previewItems[index]),
              if (index != previewItems.length - 1)
                const Divider(height: 1, color: CatalogPreviewScreen._hairline),
            ],
          ],
        ),
      ),
    );
  }
}

class _CoursePreviewTile extends StatelessWidget {
  const _CoursePreviewTile({required this.course});

  final CatalogPreviewCourse course;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          DecoratedBox(
            decoration: BoxDecoration(
              color: CatalogPreviewScreen._surfaceSoft,
              borderRadius: BorderRadius.circular(999),
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              child: Text(
                course.division,
                style: theme.textTheme.labelMedium?.copyWith(
                  color: CatalogPreviewScreen._ink,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  course.courseName,
                  style: theme.textTheme.titleSmall?.copyWith(
                    color: CatalogPreviewScreen._ink,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  course.professor,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: CatalogPreviewScreen._muted,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyMajorNotice extends StatelessWidget {
  const _EmptyMajorNotice({this.onUploadAgain});

  final VoidCallback? onUploadAgain;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFFFFFBEB),
        border: Border.all(color: const Color(0xFFFDE68A)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const Icon(
                  Icons.error_outline_rounded,
                  color: CatalogPreviewScreen._warning,
                  size: 22,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    '전공 과목을 찾지 못했습니다.',
                    style: theme.textTheme.titleMedium?.copyWith(
                      color: CatalogPreviewScreen._ink,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              '학생지원시스템에서 내려받은 1학년 전공 수강편람이 맞는지 확인해 주세요.',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: CatalogPreviewScreen._body,
              ),
            ),
            if (onUploadAgain != null) ...<Widget>[
              const SizedBox(height: 20),
              OutlinedButton.icon(
                onPressed: onUploadAgain,
                icon: const Icon(Icons.upload_file_rounded, size: 18),
                label: const Text('다른 파일 업로드'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
