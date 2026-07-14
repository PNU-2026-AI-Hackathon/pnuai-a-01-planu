import 'package:flutter/material.dart';

class CatalogDownloadGuideScreen extends StatelessWidget {
  const CatalogDownloadGuideScreen({super.key});

  static const _steps = [
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
      description:
          "③ 로그인 후 수강편람에 들어가면 소속 학과가 자동으로 선택됩니다. 조회한 뒤 '출력' 버튼을 눌러 파일을 다운로드합니다.",
    ),
    _DownloadStep(
      imagePath: 'src/img/download-description-4.png',
      description: '④ 다운로드한 엑셀 파일을 PlaNU의 파일 업로드 화면에서 선택합니다.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.white,
        title: const Text('수강편람 다운로드 방법'),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 48),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1200),
              child: const Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _DownloadGuideCard(steps: _steps),
                  SizedBox(height: 24),
                  _GuideCards(),
                ],
              ),
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
          for (var index = 0; index < steps.length; index++) ...[
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
            child: ColoredBox(
              color: Colors.white,
              child: Image.asset(
                step.imagePath,
                fit: BoxFit.contain,
                filterQuality: FilterQuality.medium,
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Text(
              step.description,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
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
        const cards = [
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
        if (constraints.maxWidth < 768) {
          return Column(
            children: [
              for (var index = 0; index < cards.length; index++) ...[
                cards[index],
                if (index != cards.length - 1) const SizedBox(height: 16),
              ],
            ],
          );
        }
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (var index = 0; index < cards.length; index++) ...[
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
    return Container(
      width: double.infinity,
      constraints: const BoxConstraints(minHeight: 180),
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
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(description, style: Theme.of(context).textTheme.bodyMedium),
        ],
      ),
    );
  }
}
