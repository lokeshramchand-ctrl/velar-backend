/// Runtime config, supplied via --dart-define (see frontend/README.md).
///
/// VELAR_API_KEY has no client-facing issuance endpoint (see
/// docs/API_REFERENCE.md §0) - it's a static value the app ships/configures
/// with, the same way the backend operator holds it.
abstract final class AppConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'VELAR_API_BASE_URL',
    // Deployed host (velar.deploy.lokeshrc.me) is running an older backend
    // build missing /users/me, /statements, and /jobs - point at local until
    // it's redeployed with the current code.
    defaultValue: 'http://localhost:9850/',
  );

  static const String apiKey = String.fromEnvironment(
    'VELAR_API_KEY',
    defaultValue:
        'velar_test_key_123', // or remove if you don't want a fallback
  );

  /// Pre-fills the login form with a seeded local test account
  /// (test@velar.dev) so sign-in during development is one tap. Debug-only:
  /// kDebugMode is compiled out of release builds, so this never ships.
  static const String devEmail = 'test@velar.dev';
  static const String devPassword = 'TestPass123!';
}
