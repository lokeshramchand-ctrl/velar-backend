import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_radius.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/theme/app_typography.dart';
import '../../../core/utils/formatters.dart';
import '../../../shared/widgets/avatar_chip.dart';
import '../../../shared/widgets/regularity_strip.dart';
import '../../statements/domain/statement_analytics.dart';
import '../../statements/presentation/period_providers.dart';

class RecurringScreen extends ConsumerWidget {
  const RecurringScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final analyticsAsync = ref.watch(currentPeriodAnalyticsProvider);

    return Scaffold(
      backgroundColor: AppColors.paper,
      body: SafeArea(
        child: analyticsAsync.when(
          loading: () => Center(child: CircularProgressIndicator(color: AppColors.accent)),
          error: (e, _) => Center(child: Text('Could not load recurring payments.', style: AppTypography.footnote12.copyWith(color: AppColors.onLightMuted))),
          data: (analytics) {
            final payments = [...?analytics?.recurringPayments]..sort((a, b) => b.estimatedMonthlyCost.compareTo(a.estimatedMonthlyCost));
            final totalMonthly = payments.fold<double>(0, (sum, p) => sum + p.estimatedMonthlyCost);
            final shareOfOutflow = (analytics == null || analytics.totalSpend == 0) ? 0 : (totalMonthly / analytics.totalSpend * 100);
            final avgRegularity = payments.isEmpty ? 0 : (payments.fold<double>(0, (s, p) => s + p.periodicityScore) / payments.length * 100);

            return ListView(
              children: [
                Container(
                  color: AppColors.ink900,
                  padding: const EdgeInsets.fromLTRB(AppSpacing.gutter, 6, AppSpacing.gutter, 26),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          IconButton(padding: EdgeInsets.zero, icon: Icon(Icons.arrow_back_ios_new_rounded, size: 18, color: AppColors.onDark), onPressed: () => context.pop()),
                          const SizedBox(width: 4),
                          Text('Recurring', style: AppTypography.navTitle15.copyWith(color: AppColors.onDark)),
                        ],
                      ),
                      const SizedBox(height: 14),
                      Text('COMMITTED EVERY MONTH', style: AppTypography.microLabel11.copyWith(color: AppColors.onDarkFaint)),
                      const SizedBox(height: 4),
                      Text(formatCurrency(totalMonthly), style: AppTypography.heroAmount40.copyWith(color: AppColors.onDark)),
                      const SizedBox(height: 20),
                      Row(
                        children: [
                          _stat('DETECTED', '${payments.length}'),
                          _stat('SHARE OF OUTFLOW', '${shareOfOutflow.round()}%'),
                          _stat('AVG REGULARITY', '${avgRegularity.round()}%', color: AppColors.amber),
                        ],
                      ),
                    ],
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.all(AppSpacing.gutter),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (payments.isEmpty)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 20),
                          child: Text('No recurring payments detected in this period yet.', style: AppTypography.footnote12.copyWith(color: AppColors.onLightMuted)),
                        )
                      else
                        for (final payment in payments) ...[
                          _SubscriptionCard(payment: payment),
                          const SizedBox(height: 12),
                        ],
                      const SizedBox(height: 8),
                      Text(
                        'Detected from payment regularity in your statements - no bank connection, no card access.',
                        textAlign: TextAlign.center,
                        style: AppTypography.footnote12.copyWith(color: AppColors.onLightFaint),
                      ),
                    ],
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _stat(String label, String value, {Color? color}) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: AppTypography.microLabel11.copyWith(color: AppColors.onDarkFaint)),
          const SizedBox(height: 4),
          Text(value, style: AppTypography.amountMedium15.copyWith(color: color ?? AppColors.onDark)),
        ],
      ),
    );
  }
}

class _SubscriptionCard extends StatelessWidget {
  const _SubscriptionCard({required this.payment});
  final RecurringPaymentEntry payment;

  @override
  Widget build(BuildContext context) {
    final color = AppColors.violet;
    final filledSegments = (payment.periodicityScore.clamp(0, 1) * 7).round();
    final states = [
      for (var i = 0; i < 7; i++) i < filledSegments ? RegularitySegmentState.paid : RegularitySegmentState.upcoming,
    ];

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: AppColors.card, border: Border.all(color: AppColors.hairlineLight), borderRadius: BorderRadius.circular(AppRadius.card)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              AvatarChip(
                initials: payment.merchant.isNotEmpty ? payment.merchant[0].toUpperCase() : '?',
                size: 40,
                radius: 12,
                backgroundColor: color.withValues(alpha: 0.16),
                foregroundColor: color,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(payment.merchant, style: AppTypography.rowLabel145.copyWith(color: AppColors.onLight)),
                    Text('${payment.occurrences} occurrences this period', style: AppTypography.meta115.copyWith(color: AppColors.onLightFaint)),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(formatCurrency(payment.estimatedMonthlyCost), style: AppTypography.amountMedium16.copyWith(color: AppColors.onLight)),
                  Text('per month', style: AppTypography.microLabel11.copyWith(color: AppColors.onLightFaint)),
                ],
              ),
            ],
          ),
          const SizedBox(height: 14),
          RegularityStrip(
            states: states,
            color: color,
            startLabel: '',
            endLabel: '',
            centerLabel: '${(payment.periodicityScore * 100).round()}% REGULAR',
          ),
        ],
      ),
    );
  }
}
