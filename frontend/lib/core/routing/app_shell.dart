import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../theme/app_colors.dart';
import '../../shared/widgets/floating_bottom_nav.dart';

/// Hosts the 3-tab shell (Overview/Signals/Activity) with the design's
/// floating pill nav absolutely positioned over the content, matching the
/// mock rather than a standard Material BottomNavigationBar.
class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  static const _tabs = [
    NavTabSpec(label: 'Overview', icon: Icons.dashboard_outlined),
    NavTabSpec(label: 'Signals', icon: Icons.bolt_outlined),
    NavTabSpec(label: 'Activity', icon: Icons.receipt_long_outlined),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.paper,
      body: Stack(
        children: [
          Positioned.fill(child: navigationShell),
          Positioned(
            left: 22,
            right: 22,
            bottom: 12 + MediaQuery.of(context).padding.bottom,
            child: Center(
              child: FloatingBottomNav(
                tabs: _tabs,
                currentIndex: navigationShell.currentIndex,
                onTap: (index) => navigationShell.goBranch(index, initialLocation: index == navigationShell.currentIndex),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
