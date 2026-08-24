# Mobile Security Requirements (Tier 2)

This document specifies the mobile app (frontend/) implementation requirements for Tier 2 security features that complement the backend security implementation.

## Overview

Tier 2 adds device-level hardening and request integrity verification. While the backend provides server-side enforcement points, the mobile app must implement the client-side cryptographic operations and security controls.

## 1. Certificate Pinning

**Purpose**: Prevent man-in-the-middle (MITM) attacks by pinning the server's SSL certificate.

### Implementation

**Android (Flutter)**:
```dart
// In frontend/android/app/build.gradle
dependencies {
    implementation 'com.network-security.pinning:network-security:1.0.0'
}

// In lib/core/network/api_client.dart
import 'dart:io';
import 'package:flutter/services.dart';

SecurityContext context = SecurityContext.defaultContext;
// Load certificate public key
final certBytes = await rootBundle.load('assets/certs/server_cert.pem');
context.setTrustedCertificates(certBytes);

// Pin certificate in HTTP client
var client = HttpClient(context: context);
```

**iOS (Flutter)**:
```dart
// In frontend/ios/Runner/Info.plist
<dict>
    <key>NSTransportSecurity</key>
    <dict>
        <key>NSExceptionDomains</key>
        <dict>
            <key>api.velar.local</key>
            <dict>
                <key>NSIncludesSubdomains</key>
                <true/>
                <key>NSExceptionAllowsInsecureHTTPLoads</key>
                <false/>
                <key>NSExceptionMinimumTLSVersion</key>
                <string>TLSv1.2</string>
            </dict>
        </dict>
    </dict>
</dict>

// In lib/core/network/api_client.dart
// Use dart:io SecurityContext with pinned certificate
```

## 2. Biometric App Lock

**Purpose**: Protect app access with biometric authentication (fingerprint/face).

### Implementation

**Flutter Package**: `local_auth`

```dart
import 'package:local_auth/local_auth.dart';

class BiometricLock {
    final LocalAuthentication auth = LocalAuthentication();

    Future<bool> canUseBiometrics() async {
        final canCheck = await auth.canCheckBiometrics;
        return canCheck;
    }

    Future<bool> authenticate() async {
        try {
            return await auth.authenticate(
                localizedReason: 'Authenticate to access Velar',
                options: const AuthenticationOptions(
                    stickyAuth: true,
                    biometricOnly: true,
                ),
            );
        } catch (e) {
            print('Biometric auth error: $e');
            return false;
        }
    }
}

// Usage in main.dart
void main() {
    final biometric = BiometricLock();
    if (await biometric.canUseBiometrics()) {
        bool authenticated = await biometric.authenticate();
        if (!authenticated) {
            exit(0);
        }
    }
    runApp(MyApp());
}
```

## 3. Screenshot Protection

**Purpose**: Prevent sensitive data from appearing in app screenshots.

### Implementation

**Android**:
```dart
import 'package:flutter_windowmanager/flutter_windowmanager.dart';

Future<void> disableScreenshots() async {
    await FlutterWindowManager.addFlags(FlutterWindowManager.FLAG_SECURE);
}

// In main.dart onCreate
void main() {
    disableScreenshots();
    runApp(MyApp());
}
```

**iOS**:
```dart
import 'package:flutter/services.dart';

const platform = MethodChannel('com.velar.app/screenshot');

Future<void> disableScreenshots() async {
    try {
        await platform.invokeMethod('disableScreenshots');
    } catch (e) {
        print('Error disabling screenshots: $e');
    }
}

// In SwiftUI (ios/Runner/GeneratedPluginRegistrant.m)
- (void)disableScreenshots {
    [[UIApplication sharedApplication] delegate].window.windowScene.screen;
    // Set snapshot view to hide sensitive content
}
```

## 4. Root/Jailbreak Detection

**Purpose**: Detect if device is rooted (Android) or jailbroken (iOS), and warn/block if needed.

### Implementation

**Flutter Package**: `flutter_jailbreak_detection`

```dart
import 'package:flutter_jailbreak_detection/flutter_jailbreak_detection.dart';

class DeviceSecurityCheck {
    static Future<bool> isDeviceSecure() async {
        bool jailbroken = await FlutterJailbreakDetection.jailbroken;
        bool developerMode = await FlutterJailbreakDetection.developerMode;
        
        if (jailbroken || developerMode) {
            print('WARNING: Device is rooted/jailbroken or in developer mode');
            return false;
        }
        return true;
    }
}

// Usage
void main() {
    final isSecure = await DeviceSecurityCheck.isDeviceSecure();
    if (!isSecure) {
        // Show warning to user or block app
        showDialog(
            context: context,
            builder: (context) => AlertDialog(
                title: Text('Unsecured Device'),
                content: Text('For security, Velar cannot run on rooted devices.'),
                actions: [
                    TextButton(onPressed: () => exit(0), child: Text('Exit'))
                ],
            ),
        );
    }
}
```

## 5. Device Attestation

**Purpose**: Prove to the server that requests come from a genuine, unmodified app on a real device.

### Implementation

**Android - Play Integrity API**:
```dart
import 'package:google_play_services/google_play_services.dart';

class PlayIntegrityAttestationProvider {
    static Future<String?> getAttestationToken() async {
        try {
            final integrityTokenProvider = await PlayIntegrityManager()
                .requestIntegrityToken(nonce: generateNonce());
            return integrityTokenProvider;
        } catch (e) {
            print('Play Integrity error: $e');
            return null;
        }
    }

    static String generateNonce() {
        // Generate random 32-byte nonce for this request
        final random = Random.secure();
        final values = List<int>.generate(32, (i) => random.nextInt(256));
        return base64Url.encode(values).replaceAll('=', '');
    }
}
```

**iOS - App Attest**:
```dart
import 'package:app_attest/app_attest.dart';

class AppAttestProvider {
    static Future<String?> getAttestationToken(String challenge) async {
        try {
            if (!await AppAttest.isSupported) {
                return null;
            }
            
            final keyId = await AppAttest.generateKey();
            final attestationObject = await AppAttest.attestKey(
                keyId: keyId,
                challenge: challenge.codeUnits,
            );
            
            return base64Encode(attestationObject);
        } catch (e) {
            print('App Attest error: $e');
            return null;
        }
    }
}
```

### Usage in Login Flow

```dart
Future<void> login(String email, String password) async {
    // Generate device identifiers
    final deviceId = await _getDeviceId();
    final deviceName = await _getDeviceName();
    
    // Get attestation token
    String? attestationToken;
    String attestationType = '';
    String nonce = '';
    
    if (Platform.isAndroid) {
        attestationToken = await PlayIntegrityAttestationProvider.getAttestationToken();
        attestationType = 'play_integrity';
        nonce = PlayIntegrityAttestationProvider.generateNonce();
    } else if (Platform.isIOS) {
        nonce = generateNonce(); // Random 32-byte challenge
        attestationToken = await AppAttestProvider.getAttestationToken(nonce);
        attestationType = 'app_attest';
    }
    
    // Send to backend with device info and attestation
    final response = await apiClient.post(
        '/auth/login',
        body: {
            'email': email,
            'password': password,
            'device_id': deviceId,
            'device_name': deviceName,
            'user_agent': userAgent,
            'ip_address': clientIp,
            'attestation_token': attestationToken,
            'attestation_type': attestationType,
            'attestation_nonce': nonce,
        },
    );
}
```

## 6. Request Signing

**Purpose**: Cryptographically sign all requests to detect tampering and prevent replays.

### Implementation

```dart
import 'package:crypto/crypto.dart';
import 'package:convert/convert.dart';
import 'dart:convert';

class RequestSigner {
    // Device-specific signing key (issued by backend at registration)
    String signingKey;

    RequestSigner(this.signingKey);

    String generateNonce() {
        // Unique nonce for each request
        return Random.secure()
            .nextBytes(16)
            .map((byte) => byte.toRadixString(16).padLeft(2, '0'))
            .join();
    }

    String generateSignature(
        String method,
        String path,
        String timestamp,
        String nonce,
        String bodyHash,
    ) {
        // Compute HMAC-SHA256 over: method|path|timestamp|nonce|bodyHash
        final message = '$method|$path|$timestamp|$nonce|$bodyHash';
        final key = utf8.encode(signingKey);
        final bytes = utf8.encode(message);
        final hmac = Hmac(sha256, key).convert(bytes);
        return hex.encode(hmac.bytes);
    }

    Map<String, String> signRequest(
        String method,
        String path,
        String body,
    ) {
        final timestamp = DateTime.now().toIso8601String();
        final nonce = generateNonce();
        
        // Hash the body
        final bodyHash = sha256.convert(utf8.encode(body)).toString();
        
        // Compute signature
        final signature = generateSignature(method, path, timestamp, nonce, bodyHash);
        
        // Return headers to add to request
        return {
            'X-Signature': signature,
            'X-Timestamp': timestamp,
            'X-Nonce': nonce,
        };
    }
}

// Usage in HTTP interceptor
class SigningInterceptor extends Interceptor {
    final RequestSigner signer;

    SigningInterceptor(this.signer);

    @override
    Future<void> onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
        final body = options.data ?? '';
        final signatureHeaders = signer.signRequest(
            options.method,
            options.path,
            body is String ? body : jsonEncode(body),
        );
        
        options.headers.addAll(signatureHeaders);
        handler.next(options);
    }
}
```

## 7. Device Registration Flow

Devices should be registered with the backend on first login:

```dart
Future<void> registerDevice() async {
    final deviceId = await _getDeviceId();
    final deviceName = await _getDeviceName() ?? 'Unknown Device';
    
    await apiClient.post(
        '/devices',
        body: {
            'device_id': deviceId,
            'device_name': deviceName,
        },
    );
}
```

## 8. Security Recommendations

### General Best Practices

- **Key Storage**: Use platform-specific secure storage (Keychain on iOS, Keystore on Android)
- **Token Handling**: Never log tokens; always use secure storage
- **Dependency Updates**: Keep `local_auth`, `app_attest`, and other security packages updated
- **Error Handling**: Fail securely; don't expose implementation details in error messages
- **Testing**: Test on real devices; emulator/simulator may not enforce all security controls

### Configuration in pubspec.yaml

```yaml
dependencies:
  flutter:
    sdk: flutter
  local_auth: ^2.1.0
  flutter_windowmanager: ^1.0.0
  flutter_jailbreak_detection: ^1.11.0
  google_play_services: ^1.0.0
  app_attest: ^0.1.0
  crypto: ^3.0.0
  convert: ^3.0.0
```

### Graddle Configuration (Android)

```gradle
android {
    compileSdk 34

    defaultConfig {
        minSdkVersion 21
        targetSdkVersion 34
    }

    // Enable security scanning
    lintOptions {
        checkReleaseBuilds true
        abortOnError false
    }
}
```

## Testing Checklist

- [ ] Certificate pinning blocks MITM attempts (test with proxy)
- [ ] Biometric auth can be toggled on/off in settings
- [ ] Screenshots are blocked when sensitive data is on screen
- [ ] Root/jailbreak detection alerts user appropriately
- [ ] Device attestation tokens are sent with login and refresh
- [ ] Requests are properly signed with headers and nonces
- [ ] Device registration succeeds on first login
- [ ] Device can be revoked from settings
- [ ] App handles network failures gracefully
- [ ] All security features work on real devices

## Compatibility

| Feature | Min SDK | iOS | Android | Status |
|---------|---------|-----|---------|--------|
| Certificate Pinning | 19 | 11.0 | 5.0 | Supported |
| Biometric Lock | 16 | 11.0 | 6.0 | Supported |
| Screenshot Protection | 16 | 11.0 | 5.0 | Supported |
| Root/Jailbreak Detection | 16 | 11.0 | 5.0 | Supported |
| Play Integrity | N/A | N/A | 12.0 | Android Only |
| App Attest | N/A | 14.0 | N/A | iOS Only |

## Support

For implementation questions, refer to:
- `frontend/lib/core/network/api_client.dart` - HTTP client setup
- `frontend/lib/core/security/` - Security helpers
- Backend `docs/SECURITY_TIER2_CHECKLIST.md` - Server-side counterparts
