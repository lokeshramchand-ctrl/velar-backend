import 'package:flutter/material.dart';

import '../../core/theme/app_radius.dart';
import '../../core/theme/app_typography.dart';

/// Pill: tinted background + colored text + direction arrow, e.g. "▲ 12%".
class DeltaChip extends StatelessWidget {
  const DeltaChip({
    super.key,
    required this.label,
    required this.up,
    required this.tint,
    required this.foreground,
  });

  final String label;
  final bool up;
  final Color tint;
  final Color foreground;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(color: tint, borderRadius: BorderRadius.circular(AppRadius.chip)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(up ? Icons.arrow_upward_rounded : Icons.arrow_downward_rounded, size: 12, color: foreground),
          const SizedBox(width: 3),
          Text(label, style: AppTypography.buttonLabel12.copyWith(color: foreground)),
        ],
      ),
    );
  }
}
