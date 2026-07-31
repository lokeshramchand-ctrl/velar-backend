import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:velar/core/providers/settings_providers.dart';
import 'package:velar/main.dart';

void main() {
  testWidgets('VelarApp boots to the splash screen', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [sharedPreferencesProvider.overrideWithValue(prefs)],
        child: const VelarApp(),
      ),
    );

    // The auth check is in flight (no reachable backend in tests), so the
    // app should render the splash/loading screen rather than crash.
    expect(find.text('Velar'), findsOneWidget);
  });
}
