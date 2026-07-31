/// Runtime config, supplied via --dart-define (see frontend/README.md).
///
/// VELAR_API_KEY has no client-facing issuance endpoint (see
/// docs/API_REFERENCE.md §0) - it's a static value the app ships/configures
/// with, the same way the backend operator holds it.
abstract final class AppConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'VELAR_API_BASE_URL',
    defaultValue: 'https://velar.deploy.lokeshrc.me/',
  );

  static const String apiKey = String.fromEnvironment(
    'VELAR_API_KEY',
    defaultValue:
        'velar_test_key_123', // or remove if you don't want a fallback
  );
}
