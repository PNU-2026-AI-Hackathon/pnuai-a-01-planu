import 'package:flutter/material.dart';
import '../widgets/flow_step_badge.dart';

class CatalogDownloadGuideScreen extends StatelessWidget {
  const CatalogDownloadGuideScreen({super.key});

  static const _steps = [
    _DownloadStep(
      imagePath: 'src/img/download-description-1.png',
      aspectRatio: 1399 / 449,
      description: "① 학지시에서 '수업' 메뉴를 클릭합니다.",
    ),
    _DownloadStep(
      imagePath: 'src/img/download-description-2.png',
      aspectRatio: 1370 / 961,
      description: "② '수강편람' 메뉴를 클릭합니다.",
    ),
    _DownloadStep(
      imagePath: 'src/img/download-description-3.png',
      aspectRatio: 1080 / 2115,
      leadingLabel: '③',
      description: '로그인 후 수강편람에 들어가면 소속 학과가 자동으로 선택됩니다. 조회 버튼을 눌러주세요.',
    ),
    _DownloadStep(
      imagePath: 'src/img/download-description-4.png',
      aspectRatio: 1080 / 2023,
      leadingLabel: '④',
      description: '아래 엑셀 버튼을 누르고 다운받은 엑셀 파일을 업로드 합니다.',
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
                  FlowStepBadge(label: '이용 안내', current: 1),
                  SizedBox(height: 24),
                  _DownloadGuideCard(steps: _steps),
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
  const _DownloadStep({
    required this.imagePath,
    required this.aspectRatio,
    required this.description,
    this.leadingLabel,
  });

  final String imagePath;
  final double aspectRatio;
  final String description;
  final String? leadingLabel;
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
          LayoutBuilder(
            builder: (context, constraints) {
              final naturalHeight = constraints.maxWidth / step.aspectRatio;
              return SizedBox(
                width: double.infinity,
                height: naturalHeight.clamp(0, 720).toDouble(),
                child: ColoredBox(
                  color: Colors.white,
                  child: Image.asset(
                    step.imagePath,
                    fit: BoxFit.contain,
                    filterQuality: FilterQuality.medium,
                  ),
                ),
              );
            },
          ),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (step.leadingLabel != null) ...[
                  Text(
                    step.leadingLabel!,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(width: 4),
                ],
                Expanded(
                  child: Text(
                    step.description,
                    style: Theme.of(context).textTheme.bodyMedium,
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
