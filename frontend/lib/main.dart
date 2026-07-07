import 'package:flutter/material.dart';
import 'department_select_screen.dart';

void main() {
  runApp(const PlaNUApp());
}

class PlaNUApp extends StatelessWidget {
  const PlaNUApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'PlaNU',
      home: DepartmentSelectScreen(
        onDepartmentSelected: (department) {
          debugPrint('선택한 학과: $department');
        },
      ),
    );
  }
}