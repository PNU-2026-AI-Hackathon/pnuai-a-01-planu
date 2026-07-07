import 'package:flutter/material.dart';

class GuideScreen extends StatelessWidget {
  const GuideScreen({super.key, this.onPrepareFiles, this.onNext});

  final VoidCallback? onPrepareFiles;
  final VoidCallback? onNext;

  static const _downloadSteps = [
    _DownloadStep(
      imagePath: 'src/img/download-description-1.png',
      description: "① 학지시에서 '수업' 메뉴를 클릭합니다.",
    ),
    _DownloadStep(
      imagePath: 'src/img/download-description-2.png',
      description: "② '수강편람' 메뉴를 클릭합니다.",
    ),
    _DownloadStep(
      imagePath: 'src/img/download-description-3.png',
      description: '③ 해당 학기의 수강편람 다운로드 버튼을 클릭합니다.',
    ),
    _DownloadStep(
      imagePath: 'src/img/download-description-4.png',
      description: '④ 다운로드한 수강편람 파일을 PlaNU에서 업로드합니다.',
    ),
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
                      const SizedBox(height: 56),
                      _HeroBand(onPrepareFiles: onPrepareFiles, onNext: onNext),
                      const SizedBox(height: 40),
                      const _GuideCards(),
                      const SizedBox(height: 24),
                      Text(
                        '교양선택 파일을 업로드하지 않아도 수강지도를 기반으로 시간표를 생성할 수 있습니다. '
                        '하지만, 학지시에서 수강편람을 조회하면 학과에서 실제 수강 가능한 과목만 확인할 수 있어 더 좋은 결과를 얻을 수 있습니다.',
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

class _DownloadStep {
  const _DownloadStep({required this.imagePath, required this.description});

  final String imagePath;
  final String description;
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
        const guide = _DownloadGuideCard(steps: GuideScreen._downloadSteps);

        if (isCompact) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [copy, const SizedBox(height: 32), guide],
          );
        }

        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(flex: 6, child: copy),
            const SizedBox(width: 48),
            const Expanded(flex: 6, child: guide),
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
          '1학년 전공기초 수강편람을 엑셀 파일로 다운로드해 주세요.',
          style: theme.textTheme.bodyLarge,
        ),
        const SizedBox(height: 12),
        Text(
          '교양선택 파일을 업로드하지 않으면 PlaNU가 기본으로 보유한 교양선택 데이터를 사용합니다.',
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

class _DownloadGuideCard extends StatelessWidget {
  const _DownloadGuideCard({required this.steps});

  final List<_DownloadStep> steps;

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
                child: Text('수강편람 준비', style: theme.textTheme.titleMedium),
              ),
            ],
          ),
          const SizedBox(height: 20),
          for (var index = 0; index < steps.length; index += 1) ...[
            _DownloadStepTile(step: steps[index]),
            if (index != steps.length - 1) const SizedBox(height: 16),
          ],
        ],
      ),
    );
  }
}

class _DownloadStepTile extends StatelessWidget {
  const _DownloadStepTile({required this.step});

  final _DownloadStep step;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: const Color(0xFFF8F9FA),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(
            aspectRatio: 16 / 9,
            child: Image.asset(
              step.imagePath,
              fit: BoxFit.cover,
              filterQuality: FilterQuality.medium,
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Text(step.description, style: theme.textTheme.bodyMedium),
          ),
        ],
      ),
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
            description: '1학년 전공기초 수강편람 파일을 준비합니다.',
          ),
          _InfoCard(
            icon: Icons.tune_outlined,
            title: '선택 파일',
            description: '교양선택 수강편람은 선택 사항이며 없어도 진행할 수 있습니다.',
          ),
          _InfoCard(
            icon: Icons.verified_outlined,
            title: '업로드 확인',
            description: '다운로드한 엑셀 파일은 PlaNU 업로드 화면에서 확인합니다.',
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
