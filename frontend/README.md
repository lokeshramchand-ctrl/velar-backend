# Velar

A financial analyst in your pocket - a Flutter mobile client for the Velar backend. Add a Google Pay statement PDF and Velar turns it into a period-based overview, ranked signals, recurring-payment detection, and a searchable transaction activity feed. See `docs/DESIGN_SPEC.md` for the full design spec and `docs/API_REFERENCE.md` for the backend contract this app is built against.

## Prerequisites

- Flutter SDK matching `environment.sdk` in `pubspec.yaml` (`^3.12.1`).
- A running instance of the Velar backend (see the repo root `../`) reachable from wherever you run the app.
- An issued `X-Velar-API-Key` value for that backend (see the backend's own docs for issuance - there is no client-facing signup for this key).

## Configuration

The app takes two required values via `--dart-define`, read in `lib/core/config/app_config.dart`:

| Flag | Purpose | Default if omitted |
|---|---|---|
| `VELAR_API_BASE_URL` | Base URL of the Velar backend | `http://10.0.2.2:8000` (the Android emulator's alias for the host machine - i.e. "backend running locally on your dev machine") |
| `VELAR_API_KEY` | The `X-Velar-API-Key` header value sent on every request | empty string (every request will be rejected) |

`VELAR_API_KEY` has no usable default - you must always pass it. `VELAR_API_BASE_URL`'s default only works for an Android emulator talking to a backend on `localhost`; override it for a physical device, iOS simulator (use `http://localhost:8000` or `http://127.0.0.1:8000`), or any non-local backend.

Local HTTP (not HTTPS) traffic to `10.0.2.2`, `localhost`, and `127.0.0.1` is explicitly allowlisted for this reason (Android's network security config and iOS's App Transport Security both block cleartext traffic by default otherwise) - every other host is still required to be HTTPS.

## Running locally

```
flutter pub get
flutter run \
  --dart-define=VELAR_API_BASE_URL=http://10.0.2.2:8000 \
  --dart-define=VELAR_API_KEY=your-api-key-here
```

## Building a release APK

```
flutter build apk --release \
  --dart-define=VELAR_API_BASE_URL=https://your-production-host \
  --dart-define=VELAR_API_KEY=your-production-api-key
```

Before this is Play-Store-publishable, `android/app/build.gradle.kts`'s release `signingConfig` still needs to be pointed at a real upload keystore - it currently signs with the debug keystore (see the `TODO` there and [Flutter's signing guide](https://docs.flutter.dev/deployment/android#sign-the-app)). The release build type already has R8 minification/resource shrinking enabled.

App icons (`android/app/src/main/res/mipmap-*`, `ios/Runner/Assets.xcassets/AppIcon.appiconset`) are still Flutter's default placeholder - swap in Velar's actual mark before shipping.

## Development

```
flutter analyze   # static analysis - should report no issues
flutter test      # widget/unit tests
```

Architecture notes for contributors:
- Clean Architecture, feature-first: `lib/features/<feature>/{data,domain,presentation}`.
- State management is **classic Riverpod** (`Provider`/`FutureProvider`/`NotifierProvider`/`AsyncNotifierProvider`), not the `@riverpod` code-generator - a resolved `riverpod_generator` → `analyzer` version conflict made codegen unusable in this environment, so don't reintroduce it without re-solving that.
- `build.yaml` sets `json_serializable`'s `field_rename: snake` globally to match the backend's snake_case JSON without per-field `@JsonKey` annotations.
