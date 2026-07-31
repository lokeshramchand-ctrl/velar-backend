import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers/feature_providers.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_radius.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/theme/app_typography.dart';
import '../../../core/utils/formatters.dart';
import '../../statements/domain/statement.dart';
import '../../statements/presentation/period_providers.dart';

class ManagePeriodsScreen extends ConsumerWidget {
  const ManagePeriodsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final periodsAsync = ref.watch(periodsProvider);

    return Scaffold(
      backgroundColor: AppColors.ink900,
      appBar: AppBar(
        backgroundColor: AppColors.ink900,
        iconTheme: IconThemeData(color: AppColors.onDark),
        title: Text('Manage periods', style: AppTypography.navTitle15.copyWith(color: AppColors.onDark)),
      ),
      body: periodsAsync.when(
        loading: () => Center(child: CircularProgressIndicator(color: AppColors.accent)),
        error: (e, _) => Center(child: Text('Could not load periods.', style: AppTypography.footnote12.copyWith(color: AppColors.onDarkMuted))),
        data: (periods) => ListView.separated(
          padding: const EdgeInsets.all(AppSpacing.gutter),
          itemCount: periods.length,
          separatorBuilder: (_, __) => const SizedBox(height: 10),
          itemBuilder: (context, index) => _PeriodTile(period: periods[index]),
        ),
      ),
    );
  }
}

class _PeriodTile extends ConsumerWidget {
  const _PeriodTile({required this.period});
  final Statement period;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: AppColors.ink850, border: Border.all(color: AppColors.hairlineDark), borderRadius: BorderRadius.circular(AppRadius.card)),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(formatPeriodRange(period.periodStart, period.periodEnd), style: AppTypography.rowLabel145.copyWith(color: AppColors.onDark)),
                const SizedBox(height: 4),
                Text('${period.originalFilename} · ${period.transactionCount} txns', style: AppTypography.meta115.copyWith(color: AppColors.onDarkFaint)),
              ],
            ),
          ),
          IconButton(
            icon: Icon(Icons.delete_outline_rounded, color: AppColors.rose, size: 20),
            onPressed: () => _confirmDelete(context, ref),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmDelete(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.ink850,
        title: Text('Delete this period?', style: AppTypography.rowLabel14.copyWith(color: AppColors.onDark)),
        content: Text(
          'This permanently deletes ${period.originalFilename} and all ${period.transactionCount} of its transactions. This cannot be undone.',
          style: AppTypography.footnote12.copyWith(color: AppColors.onDarkMuted),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: Text('Cancel', style: TextStyle(color: AppColors.onDarkMuted))),
          TextButton(onPressed: () => Navigator.of(context).pop(true), child: Text('Delete', style: TextStyle(color: AppColors.rose))),
        ],
      ),
    );
    if (confirmed != true) return;
    await ref.read(statementsRepositoryProvider).delete(period.id);
    ref.invalidate(periodsProvider);
  }
}
