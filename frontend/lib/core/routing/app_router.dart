import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/activity/presentation/activity_screen.dart';
import '../../features/analytics/presentation/spending_patterns_screen.dart';
import '../../features/auth/presentation/auth_controller.dart';
import '../../features/auth/presentation/auth_state.dart';
import '../../features/auth/presentation/login_screen.dart';
import '../../features/auth/presentation/register_screen.dart';
import '../../features/auth/presentation/splash_screen.dart';
import '../../features/onboarding/presentation/onboarding_screen.dart';
import '../../features/overview/presentation/category_drilldown_screen.dart';
import '../../features/overview/presentation/overview_screen.dart';
import '../../features/profile/presentation/manage_periods_screen.dart';
import '../../features/profile/presentation/profile_screen.dart';
import '../../features/signals/presentation/recurring_screen.dart';
import '../../features/signals/presentation/signals_screen.dart';
import '../../features/statements/presentation/period_providers.dart';
import '../../features/upload/presentation/analysing_screen.dart';
import '../../features/upload/presentation/rejected_screen.dart';
import 'app_shell.dart';

class _RouterRefreshNotifier extends ChangeNotifier {
  _RouterRefreshNotifier(Ref ref) {
    ref.listen(authControllerProvider, (_, _) => notifyListeners());
    ref.listen(periodsProvider, (_, _) => notifyListeners());
  }
}

final appRouterProvider = Provider<GoRouter>((ref) {
  final refreshNotifier = _RouterRefreshNotifier(ref);
  ref.onDispose(refreshNotifier.dispose);

  return GoRouter(
    initialLocation: '/splash',
    refreshListenable: refreshNotifier,
    redirect: (context, state) {
      final loc = state.matchedLocation;
      final onAuthPages = loc == '/login' || loc == '/register';
      final onSplash = loc == '/splash';

      final authAsync = ref.read(authControllerProvider);
      if (authAsync.isLoading && !authAsync.hasValue) {
        return onSplash ? null : '/splash';
      }

      final authState = authAsync.valueOrNull;
      if (authState == null || authState is AuthUnauthenticated) {
        return onAuthPages ? null : '/login';
      }

      // Authenticated from here on.
      final periodsAsync = ref.read(periodsProvider);
      if (periodsAsync.isLoading && !periodsAsync.hasValue) {
        return (onSplash || onAuthPages) ? null : '/splash';
      }
      final hasPeriods = (periodsAsync.valueOrNull ?? const []).isNotEmpty;

      if (onSplash || onAuthPages) {
        return hasPeriods ? '/shell/overview' : '/onboarding';
      }
      if (loc == '/onboarding' && hasPeriods) return '/shell/overview';
      if (loc.startsWith('/shell') && !hasPeriods) return '/onboarding';
      return null;
    },
    routes: [
      GoRoute(path: '/splash', builder: (context, state) => const SplashScreen()),
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      GoRoute(path: '/register', builder: (context, state) => const RegisterScreen()),
      GoRoute(path: '/onboarding', builder: (context, state) => const OnboardingScreen()),
      GoRoute(
        path: '/upload/analysing/:jobId',
        builder: (context, state) => AnalysingScreen(jobId: state.pathParameters['jobId']!),
      ),
      GoRoute(
        path: '/upload/rejected',
        builder: (context, state) => RejectedScreen(message: state.extra as String?),
      ),
      GoRoute(
        path: '/category/:category',
        builder: (context, state) => CategoryDrilldownScreen(category: Uri.decodeComponent(state.pathParameters['category']!)),
      ),
      GoRoute(path: '/recurring', builder: (context, state) => const RecurringScreen()),
      GoRoute(path: '/profile', builder: (context, state) => const ProfileScreen()),
      GoRoute(path: '/profile/periods', builder: (context, state) => const ManagePeriodsScreen()),
      GoRoute(path: '/profile/analytics', builder: (context, state) => const SpendingPatternsScreen()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) => AppShell(navigationShell: navigationShell),
        branches: [
          StatefulShellBranch(routes: [GoRoute(path: '/shell/overview', builder: (context, state) => const OverviewScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/shell/signals', builder: (context, state) => const SignalsScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/shell/activity', builder: (context, state) => const ActivityScreen())]),
        ],
      ),
    ],
  );
});
