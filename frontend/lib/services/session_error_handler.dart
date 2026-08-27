import 'package:flutter/material.dart';

import '../models/app_flow_state.dart';
import '../models/major_models.dart';

bool isSessionExpiredError(ApiError error) =>
    error.code == 'SESSION_NOT_FOUND' || error.code == 'SESSION_NOT_AVAILABLE';

bool handleSessionExpiredError(
  BuildContext context,
  ApiError error, {
  required AppFlowState flow,
  required VoidCallback onSessionExpired,
}) {
  if (!isSessionExpiredError(error)) return false;
  flow.reset();
  ScaffoldMessenger.of(context).showSnackBar(
    const SnackBar(content: Text('세션이 만료되었습니다. 파일을 다시 업로드해 주세요.')),
  );
  onSessionExpired();
  Navigator.of(context).popUntil((route) => route.isFirst);
  return true;
}
