import 'package:flutter/material.dart';
import 'package:shimmer/shimmer.dart';

import '../../core/theme/app_colors.dart';

/// A shimmering placeholder block, matching the design's `vshimmer` sweep
/// (1.4s linear infinite) used for loading avatars/text lines/rows.
class SkeletonBox extends StatelessWidget {
  const SkeletonBox({super.key, required this.width, required this.height, this.radius = 8});

  final double width;
  final double height;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return Shimmer.fromColors(
      baseColor: AppColors.skeletonBase,
      highlightColor: AppColors.skeletonHighlight,
      period: const Duration(milliseconds: 1400),
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(color: AppColors.skeletonBase, borderRadius: BorderRadius.circular(radius)),
      ),
    );
  }
}

/// A skeleton transaction/list row: circular avatar + two text bars.
class SkeletonListRow extends StatelessWidget {
  const SkeletonListRow({super.key});

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: 0.5,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(
          children: [
            const SkeletonBox(width: 38, height: 38, radius: 12),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SkeletonBox(width: MediaQuery.of(context).size.width * 0.42, height: 13),
                  const SizedBox(height: 6),
                  SkeletonBox(width: MediaQuery.of(context).size.width * 0.28, height: 11),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
