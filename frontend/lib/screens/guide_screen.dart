import 'package:flutter/material.dart';

import 'catalog_download_guide_screen.dart';

class GuideScreen extends StatelessWidget {
  const GuideScreen({super.key, this.onPrepareFiles, this.onNext});

  final VoidCallback? onPrepareFiles;
  final VoidCallback? onNext;

  @override
  Widget build(BuildContext context) {
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
                      const SizedBox(height: 24),
                      const _AdditionalGuidance(),
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

        if (isCompact) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [copy],
          );
        }

        return Align(alignment: Alignment.centerLeft, child: copy);
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
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => const CatalogDownloadGuideScreen(),
                  ),
                );
              },
              icon: const Icon(Icons.menu_book_outlined, size: 18),
              label: const Text('수강편람 다운로드 방법 보기'),
            ),
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

class _AdditionalGuidance extends StatelessWidget {
  const _AdditionalGuidance();

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        const cards = [
          _NoticeCard(
            icon: Icons.event_note_outlined,
            title: '전공 선택 안내',
            description:
                '파일 업로드 후 전공 과목과 분반을 직접 선택해야 합니다.\n원활한 진행을 위해 신청할 전공 시간표를 미리 확인해 두는 것을 권장합니다.',
          ),
          _NoticeCard(
            icon: Icons.lock_clock_outlined,
            title: '개인정보 및 세션 안내',
            description:
                '개인정보 보호를 위해 업로드한 정보는 임시로만 보관됩니다.\n마지막 요청 이후 30분이 지나면 세션이 만료되어 파일을 다시 업로드해야 할 수 있습니다.',
          ),
        ];

        if (constraints.maxWidth < 768) {
          return Column(children: [cards[0], SizedBox(height: 16), cards[1]]);
        }

        return IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(child: cards[0]),
              SizedBox(width: 24),
              Expanded(child: cards[1]),
            ],
          ),
        );
      },
    );
  }
}

class _NoticeCard extends StatelessWidget {
  const _NoticeCard({
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
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: const Color(0xFFF5F5F5),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, size: 21, color: const Color(0xFF374151)),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: theme.textTheme.titleMedium),
                const SizedBox(height: 8),
                Text(
                  description,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: const Color(0xFF6B7280),
                    height: 1.55,
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
