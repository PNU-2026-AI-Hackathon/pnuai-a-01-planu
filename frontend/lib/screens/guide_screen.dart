import 'package:flutter/material.dart';

class GuideScreen extends StatelessWidget {
  const GuideScreen({super.key, this.onPrepareFiles, this.onNext});

  final VoidCallback? onPrepareFiles;
  final VoidCallback? onNext;

  static const _downloadSteps = [
    '부산대학교 학생지원시스템 접속',
    '수업 메뉴 이동',
    '수강편람 조회',
    '학년도/학기 선택',
    '전공 또는 교양 영역 선택',
    '조회 후 엑셀 다운로드',
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1200),
            child: CustomScrollView(
              slivers: [
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(24, 0, 24, 48),
                  sliver: SliverList(
                    delegate: SliverChildListDelegate.fixed([
                      const _TopNav(),
                      const SizedBox(height: 64),
                      _HeroBand(onPrepareFiles: onPrepareFiles, onNext: onNext),
                      const SizedBox(height: 48),
                      const _GuideCards(),
                      const SizedBox(height: 32),
                      Text(
                        '전공 과목은 사용자가 직접 선택합니다. PlaNU는 확정된 전공 시간표 위에 교양 과목을 추천하며, LLM은 교양 조건 입력 해석에만 사용합니다.',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: const Color(0xFF6B7280),
                        ),
                      ),
                    ]),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _TopNav extends StatelessWidget {
  const _TopNav();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SizedBox(
      height: 64,
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: const BoxDecoration(
              color: Color(0xFF111111),
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.calendar_month_rounded,
              color: Colors.white,
              size: 20,
            ),
          ),
          const SizedBox(width: 12),
          Text('PlaNU', style: theme.textTheme.titleLarge),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            decoration: BoxDecoration(
              color: const Color(0xFFF8F9FA),
              borderRadius: BorderRadius.circular(999),
            ),
            child: Text(
              '안내',
              style: theme.textTheme.labelLarge?.copyWith(
                color: const Color(0xFF111111),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _HeroBand extends StatelessWidget {
  const _HeroBand({required this.onPrepareFiles, required this.onNext});

  final VoidCallback? onPrepareFiles;
  final VoidCallback? onNext;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isCompact = constraints.maxWidth < 820;
        final copy = _HeroCopy(onPrepareFiles: onPrepareFiles, onNext: onNext);
        const mockup = _DownloadMockup(steps: GuideScreen._downloadSteps);

        if (isCompact) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [copy, const SizedBox(height: 32), mockup],
          );
        }

        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(flex: 7, child: copy),
            const SizedBox(width: 48),
            const Expanded(flex: 5, child: mockup),
          ],
        );
      },
    );
  }
}

class _HeroCopy extends StatelessWidget {
  const _HeroCopy({this.onPrepareFiles, this.onNext});

  final VoidCallback? onPrepareFiles;
  final VoidCallback? onNext;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _Badge(label: '수강편람 다운로드 안내'),
        const SizedBox(height: 24),
        Text(
          'PlaNU 시작 전에 수강편람 파일을 준비하세요',
          style: theme.textTheme.headlineLarge,
        ),
        const SizedBox(height: 24),
        Text(
          'PlaNU를 사용하려면 1학년 전공기초/전공필수 수강편람 파일이 필요합니다.',
          style: theme.textTheme.bodyLarge,
        ),
        const SizedBox(height: 12),
        Text(
          '부산대학교 학생지원시스템에서 수강편람을 조회한 뒤 엑셀 파일로 다운로드해주세요.',
          style: theme.textTheme.bodyLarge,
        ),
        const SizedBox(height: 12),
        Text(
          '교양선택 수강편람은 선택 사항입니다. 업로드하지 않으면 PlaNU가 기본으로 보유한 교양선택 데이터를 사용합니다.',
          style: theme.textTheme.bodyLarge,
        ),
        const SizedBox(height: 32),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            OutlinedButton.icon(
              onPressed: onPrepareFiles ?? () {},
              icon: const Icon(Icons.download_rounded, size: 18),
              label: const Text('파일 준비하러 가기'),
            ),
            ElevatedButton.icon(
              onPressed: onNext ?? () {},
              icon: const Icon(Icons.arrow_forward_rounded, size: 18),
              label: const Text('다음'),
            ),
          ],
        ),
      ],
    );
  }
}

class _DownloadMockup extends StatelessWidget {
  const _DownloadMockup({required this.steps});

  final List<String> steps;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE5E7EB)),
        boxShadow: const [
          BoxShadow(
            color: Color(0x14000000),
            blurRadius: 12,
            offset: Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: const Color(0xFFF5F5F5),
                  borderRadius: BorderRadius.circular(18),
                ),
                child: const Icon(Icons.file_download_outlined, size: 20),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text('다운로드 절차', style: theme.textTheme.titleMedium),
              ),
            ],
          ),
          const SizedBox(height: 20),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFFF5F5F5),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              children: [
                for (var index = 0; index < steps.length; index += 1) ...[
                  _StepRow(number: index + 1, label: steps[index]),
                  if (index != steps.length - 1) const SizedBox(height: 12),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _StepRow extends StatelessWidget {
  const _StepRow({required this.number, required this.label});

  final int number;
  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 28,
          height: 28,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFFE5E7EB)),
          ),
          child: Text('$number', style: theme.textTheme.labelLarge),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(label, style: theme.textTheme.bodyMedium),
          ),
        ),
      ],
    );
  }
}

class _GuideCards extends StatelessWidget {
  const _GuideCards();

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isCompact = constraints.maxWidth < 768;
        final cards = const [
          _InfoCard(
            icon: Icons.assignment_outlined,
            title: '필수 파일',
            description: '1학년 전공기초/전공필수 수강편람 파일을 준비합니다.',
          ),
          _InfoCard(
            icon: Icons.tune_outlined,
            title: '선택 파일',
            description: '교양선택 수강편람은 선택 사항이며 없어도 진행할 수 있습니다.',
          ),
          _InfoCard(
            icon: Icons.verified_outlined,
            title: '검증 위치',
            description: '전공 수강편람 업로드 여부는 파일 업로드 화면에서 검증합니다.',
          ),
        ];

        if (isCompact) {
          return Column(
            children: [
              for (var index = 0; index < cards.length; index += 1) ...[
                cards[index],
                if (index != cards.length - 1) const SizedBox(height: 16),
              ],
            ],
          );
        }

        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
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

class _InfoCard extends StatelessWidget {
  const _InfoCard({
    required this.icon,
    required this.title,
    required this.description,
  });

  final IconData icon;
  final String title;
  final String description;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      constraints: const BoxConstraints(minHeight: 164),
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: const Color(0xFF111111)),
          const SizedBox(height: 20),
          Text(title, style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(description, style: theme.textTheme.bodyMedium),
        ],
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      decoration: BoxDecoration(
        color: const Color(0xFFF5F5F5),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(label, style: Theme.of(context).textTheme.labelLarge),
    );
  }
}
