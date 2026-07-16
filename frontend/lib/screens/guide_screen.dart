import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

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
                      const _HeroBand(),
                      const SizedBox(height: 32),
                      _GuideActions(
                        onPrepareFiles: onPrepareFiles,
                        onNext: onNext,
                      ),
                      const SizedBox(height: 32),
                      const _FileCards(),
                      const SizedBox(height: 24),
                      const _UploadConfirmation(),
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
  const _HeroBand();

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isCompact = constraints.maxWidth < 820;
        const copy = _HeroCopy();

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
  const _HeroCopy();

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
      ],
    );
  }
}

class _GuideActions extends StatelessWidget {
  const _GuideActions({this.onPrepareFiles, this.onNext});

  final VoidCallback? onPrepareFiles;
  final VoidCallback? onNext;

  Future<void> _openStudentSupportSystem(BuildContext context) async {
    final url = Uri.parse('https://onestop.pusan.ac.kr/login');

    try {
      final launched = await launchUrl(
        url,
        mode: LaunchMode.externalApplication,
      );
      if (launched || !context.mounted) return;
    } catch (_) {
      if (!context.mounted) return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('페이지를 열 수 없습니다. 잠시 후 다시 시도해 주세요.')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final buttonStyle = ButtonStyle(
      minimumSize: const WidgetStatePropertyAll(Size(0, 48)),
      padding: const WidgetStatePropertyAll(
        EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      ),
    );

    final prepareButton = OutlinedButton.icon(
      style: buttonStyle,
      onPressed: onPrepareFiles ?? () => _openStudentSupportSystem(context),
      icon: const Icon(Icons.download_rounded, size: 18),
      label: const Text('파일 준비하러 가기'),
    );
    final nextButton = ElevatedButton.icon(
      style: buttonStyle,
      onPressed: onNext ?? () {},
      icon: const Icon(Icons.arrow_forward_rounded, size: 18),
      label: const Text('다음'),
    );

    return LayoutBuilder(
      builder: (context, constraints) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            OutlinedButton.icon(
              style: buttonStyle,
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
            const SizedBox(height: 12),
            if (constraints.maxWidth < 300) ...[
              prepareButton,
              const SizedBox(height: 12),
              nextButton,
            ] else
              Row(
                children: [
                  Expanded(flex: 2, child: prepareButton),
                  const SizedBox(width: 12),
                  Expanded(child: nextButton),
                ],
              ),
          ],
        );
      },
    );
  }
}

class _FileCards extends StatelessWidget {
  const _FileCards();

  @override
  Widget build(BuildContext context) {
    const cards = [
      _InfoCard(
        icon: Icons.assignment_outlined,
        title: '필수 파일',
        description: '1학년 전공기초 혹은 전공필수 수강편람 파일을 준비합니다.',
      ),
      _InfoCard(
        icon: Icons.tune_outlined,
        title: '선택 파일',
        description: '교양선택 수강편람은 선택 사항이며 없어도 진행할 수 있습니다.',
      ),
    ];

    return LayoutBuilder(
      builder: (context, constraints) {
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

class _UploadConfirmation extends StatelessWidget {
  const _UploadConfirmation();

  @override
  Widget build(BuildContext context) {
    return const _InfoCard(
      icon: Icons.verified_outlined,
      title: '업로드 확인',
      description: '다운로드한 엑셀 파일은 PlaNU 업로드 화면에서 확인합니다.',
    );
  }
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({
    this.icon,
    required this.title,
    required this.description,
    this.borderColor = const Color(0xFFE5E7EB),
    this.backgroundColor = Colors.white,
    this.minimumHeight = 180,
  });

  final IconData? icon;
  final String title;
  final String description;
  final Color borderColor;
  final Color backgroundColor;
  final double minimumHeight;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      constraints: BoxConstraints(minHeight: minimumHeight),
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (icon != null) ...[
            Icon(icon, color: const Color(0xFF111111)),
            const SizedBox(height: 20),
          ],
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(description, style: Theme.of(context).textTheme.bodyMedium),
        ],
      ),
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
          _GuidanceSection(
            title: '전공 선택 안내',
            cards: [
              _InfoCard(
                title: '전공 과목 직접 선택',
                description: '파일 업로드 후 전공 과목과 분반을 직접 선택해야 합니다.',
                minimumHeight: 0,
              ),
              _InfoCard(
                title: '시간표 작성 기준',
                description: 'PlaNU는 강의실 간의 거리와 교양 필수 과목을 중심으로 시간표를 작성합니다.',
                minimumHeight: 0,
              ),
              _InfoCard(
                title: '전공 시간표 미리 준비',
                description: '에브리타임의 수업 평가와 시간표를 참고해 원하는 전공 과목과 분반을 미리 정해 주세요.',
                minimumHeight: 0,
              ),
            ],
          ),
          _GuidanceSection(
            title: '개인정보 및 세션 안내',
            isWarning: true,
            cards: [
              _InfoCard(
                title: '개인정보 보호',
                description: '업로드한 파일은 시간표 작성에만 사용되며 임시로 보관됩니다.',
                borderColor: Color(0xFFFECACA),
                backgroundColor: Color(0xFFFFFAFA),
                minimumHeight: 0,
              ),
              _InfoCard(
                title: '30분 세션',
                description: '마지막 활동 이후 30분이 지나면 세션이 만료됩니다.',
                borderColor: Color(0xFFFECACA),
                backgroundColor: Color(0xFFFFFAFA),
                minimumHeight: 0,
              ),
              _InfoCard(
                title: '파일 자동 삭제',
                description: '세션이 만료되면 업로드한 파일과 로그인 정보는 다시 사용할 수 없습니다.',
                borderColor: Color(0xFFFECACA),
                backgroundColor: Color(0xFFFFFAFA),
                minimumHeight: 0,
              ),
            ],
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

class _GuidanceSection extends StatelessWidget {
  const _GuidanceSection({
    required this.title,
    required this.cards,
    this.isWarning = false,
  });

  final String title;
  final List<_InfoCard> cards;
  final bool isWarning;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: theme.textTheme.titleLarge?.copyWith(
            color: isWarning ? const Color(0xFFB91C1C) : null,
          ),
        ),
        const SizedBox(height: 16),
        for (var index = 0; index < cards.length; index++) ...[
          cards[index],
          if (index != cards.length - 1) const SizedBox(height: 12),
        ],
      ],
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
