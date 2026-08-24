import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel

from core.config import settings

logger = logging.getLogger(__name__)


class AttestationResult(BaseModel):
    is_valid: bool
    device_id: str | None = None
    timestamp: datetime
    attestation_type: str  # "play_integrity" or "app_attest"
    risk_level: str | None = None  # "GREEN", "YELLOW", "RED" for Play Integrity
    error: str | None = None


class DeviceAttestationVerifier:
    """Verify device attestation tokens from Play Integrity API (Android)
    and App Attest (iOS). Stores verification result on DeviceSession."""

    PLAY_INTEGRITY_URL = "https://www.googleapis.com/androidcheck/v1/attestationServiceAccount:verify"
    APP_ATTEST_CHALLENGE_URL = "https://api.development.devicecheck.apple.com/v1/attestationChallenge"
    APP_ATTEST_VALIDATE_URL = "https://api.development.devicecheck.apple.com/v1/attestationServiceAccount"

    def __init__(self):
        self.play_integrity_token = settings.GOOGLE_PLAY_INTEGRITY_API_KEY
        self.apple_team_id = settings.APPLE_TEAM_ID
        self.apple_bundle_id = settings.APPLE_BUNDLE_ID
        self.apple_key_id = settings.APPLE_KEY_ID
        self.apple_private_key = settings.APPLE_PRIVATE_KEY

    async def verify_play_integrity(self, token: str, nonce: str) -> AttestationResult:
        """Verify Android Play Integrity API token.

        Args:
            token: The Play Integrity token from Google Play Services
            nonce: The nonce that was used to generate the token

        Returns:
            AttestationResult with verification status
        """
        if not self.play_integrity_token:
            logger.warning("Play Integrity API key not configured")
            return AttestationResult(
                is_valid=False,
                timestamp=datetime.now(UTC),
                attestation_type="play_integrity",
                error="API key not configured",
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.PLAY_INTEGRITY_URL,
                    json={"token": token},
                    headers={"Authorization": f"Bearer {self.play_integrity_token}"},
                    timeout=5.0,
                )

            if response.status_code != 200:
                logger.warning(f"Play Integrity verification failed: {response.status_code}")
                return AttestationResult(
                    is_valid=False,
                    timestamp=datetime.now(UTC),
                    attestation_type="play_integrity",
                    error=f"HTTP {response.status_code}",
                )

            data = response.json()
            payload = data.get("payload", {})

            # Verify nonce matches
            if payload.get("requestDetails", {}).get("nonce") != nonce:
                logger.warning("Play Integrity nonce mismatch")
                return AttestationResult(
                    is_valid=False,
                    timestamp=datetime.now(UTC),
                    attestation_type="play_integrity",
                    error="Nonce mismatch",
                )

            # Check verdict
            device_integrity = payload.get("deviceIntegrity", {}).get("deviceRecognitionVerdict")
            app_integrity = payload.get("appIntegrity", {}).get("appRecognitionVerdict")

            # Map to risk level: PLAY_RECOGNIZED -> GREEN, UNRECOGNIZED_VERSION -> YELLOW, etc.
            is_valid = device_integrity == "RECOGNIZED" and app_integrity == "RECOGNIZED"
            risk_level = "GREEN" if is_valid else "YELLOW"

            return AttestationResult(
                is_valid=is_valid,
                device_id=payload.get("deviceDetails", {}).get("deviceId"),
                timestamp=datetime.now(UTC),
                attestation_type="play_integrity",
                risk_level=risk_level,
            )

        except Exception as e:
            logger.error(f"Play Integrity verification error: {e}")
            return AttestationResult(
                is_valid=False,
                timestamp=datetime.now(UTC),
                attestation_type="play_integrity",
                error=str(e),
            )

    async def verify_app_attest(self, token: str, challenge: str) -> AttestationResult:
        """Verify iOS App Attest token.

        Args:
            token: The attestation object from App Attest
            challenge: The challenge that was used during attestation

        Returns:
            AttestationResult with verification status
        """
        if not all([self.apple_team_id, self.apple_key_id, self.apple_private_key]):
            logger.warning("Apple App Attest credentials not configured")
            return AttestationResult(
                is_valid=False,
                timestamp=datetime.now(UTC),
                attestation_type="app_attest",
                error="Credentials not configured",
            )

        try:
            # In production, you would:
            # 1. Verify the attestation object structure and certificate chain
            # 2. Check certificate validity and pinning
            # 3. Verify the challenge matches
            # 4. Validate the signature
            #
            # For now, we accept the token if it's well-formed and the challenge matches
            # This is a simplified implementation - production should use Apple's SDK or
            # thoroughly validate the attestation object structure.

            attestation_data = json.loads(token) if isinstance(token, str) else token
            provided_challenge = attestation_data.get("challenge")

            if provided_challenge != challenge:
                logger.warning("App Attest challenge mismatch")
                return AttestationResult(
                    is_valid=False,
                    timestamp=datetime.now(UTC),
                    attestation_type="app_attest",
                    error="Challenge mismatch",
                )

            # Simplified: if structure is valid and challenge matches, accept it
            # Production should implement full certificate chain validation
            return AttestationResult(
                is_valid=True,
                device_id=attestation_data.get("device_id"),
                timestamp=datetime.now(UTC),
                attestation_type="app_attest",
                risk_level="GREEN",
            )

        except Exception as e:
            logger.error(f"App Attest verification error: {e}")
            return AttestationResult(
                is_valid=False,
                timestamp=datetime.now(UTC),
                attestation_type="app_attest",
                error=str(e),
            )


device_attestation_verifier = DeviceAttestationVerifier()
