import 'package:flutter/material.dart';

class TimetableGrid extends StatelessWidget {
  const TimetableGrid({super.key, required this.items});

  final List<Map<String, dynamic>> items;

  static const _days = ['MON', 'TUE', 'WED', 'THU', 'FRI'];
  static const _dayLabels = ['월', '화', '수', '목', '금'];
  static const _timeColumnWidth = 52.0;
  static const _dayColumnWidth = 140.0;
  static const _hourHeight = 52.0;
  static const _startHour = 9;
  static const _endHour = 22;
  static const _gridHeight = (_endHour - _startHour) * _hourHeight;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const Text('표시할 시간표 정보가 없습니다.');
    }

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SizedBox(
        width: _timeColumnWidth + _dayColumnWidth * _days.length,
        child: Column(
          children: [
            Row(
              children: [
                const SizedBox(width: _timeColumnWidth),
                for (final day in _dayLabels)
                  SizedBox(
                    width: _dayColumnWidth,
                    height: 32,
                    child: Center(
                      child: Text(
                        day,
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ),
                  ),
              ],
            ),
            const Divider(height: 1),
            SizedBox(
              height: _gridHeight,
              child: Stack(
                children: [
                  for (var hour = _startHour; hour <= _endHour; hour++) ...[
                    Positioned(
                      top: (hour - _startHour) * _hourHeight,
                      left: 0,
                      width: _timeColumnWidth,
                      child: Text(
                        '${hour.toString().padLeft(2, '0')}:00',
                        style: const TextStyle(
                          color: Color(0xFF6B7280),
                          fontSize: 12,
                        ),
                      ),
                    ),
                    Positioned(
                      top: (hour - _startHour) * _hourHeight,
                      left: _timeColumnWidth,
                      right: 0,
                      child: const Divider(height: 1),
                    ),
                  ],
                  for (final item in items)
                    if (_days.contains('${item['day']}'))
                      Positioned(
                        left:
                            _timeColumnWidth +
                            _days.indexOf('${item['day']}') * _dayColumnWidth +
                            4,
                        top:
                            ((_minutes('${item['start']}') - _startHour * 60) /
                                    60 *
                                    _hourHeight)
                                .clamp(0, _gridHeight - 32)
                                .toDouble(),
                        width: _dayColumnWidth - 8,
                        height:
                            ((_minutes('${item['end']}') -
                                        _minutes('${item['start']}')) /
                                    60 *
                                    _hourHeight)
                                .clamp(34, 260)
                                .toDouble(),
                        child: _ScheduleBlock(item: item),
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

class _ScheduleBlock extends StatelessWidget {
  const _ScheduleBlock({required this.item});

  final Map<String, dynamic> item;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(7),
    decoration: BoxDecoration(
      color: _categoryColor('${item['category']}'),
      borderRadius: BorderRadius.circular(7),
      border: Border.all(color: Colors.white, width: 1.5),
    ),
    child: Text(
      '${item['course_name'] ?? ''}\n${item['division'] ?? ''} · ${item['classroom'] ?? ''}',
      maxLines: 3,
      overflow: TextOverflow.fade,
      style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
    ),
  );
}

int _minutes(String value) {
  final match = RegExp(r'(\d{1,2})(?::(\d{1,2}))?').firstMatch(value.trim());
  if (match == null) return 0;
  final hour = (int.tryParse(match.group(1) ?? '') ?? 0).clamp(0, 24);
  final minute = hour == 24
      ? 0
      : (int.tryParse(match.group(2) ?? '') ?? 0).clamp(0, 59);
  return hour * 60 + minute;
}

Color _categoryColor(String value) => switch (value) {
  'MAJOR_BASIC' || 'major_basic' => const Color(0xFFDDE5FF),
  'MAJOR_REQUIRED' || 'major_required' || 'major' => const Color(0xFFDDE5FF),
  'MAJOR_ELECTIVE' || 'major_elective' => const Color(0xFFE0E7FF),
  'GENERAL_REQUIRED' || 'general_required' => const Color(0xFFCCF5E3),
  'GENERAL_ELECTIVE' || 'general_elective' => const Color(0xFFFFE5C7),
  _ => const Color(0xFFF5F5F5),
};
