import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class DLPRedactor:
    """Data Loss Prevention (DLP) redactor for sensitive PII patterns.
    Redacts SSNs, credit card numbers, account numbers, and other sensitive data
    from logs and response payloads to prevent accidental leakage."""

    # Patterns for common PII
    PATTERNS = {
        "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # XXX-XX-XXXX
        "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),  # 16-digit card
        "account_number": re.compile(r"\b\d{8,12}\b"),  # 8-12 digit account numbers
        "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b"),
        "jwt_token": re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
        "api_key": re.compile(r"(?i)(api[_-]?key|apikey|api_secret|secret|token)[\s:=]+[A-Za-z0-9\-_.]+"),
    }

    @staticmethod
    def redact_string(text: str) -> str:
        """Redact sensitive patterns from a string."""
        if not isinstance(text, str):
            return text

        redacted = text
        for pattern_name, pattern in DLPRedactor.PATTERNS.items():
            redacted = pattern.sub(f"[REDACTED_{pattern_name.upper()}]", redacted)

        return redacted

    @staticmethod
    def redact_dict(obj: dict[str, Any], sensitive_keys: list[str] | None = None) -> dict[str, Any]:
        """Recursively redact sensitive dictionary fields and patterns."""
        if sensitive_keys is None:
            sensitive_keys = [
                "password", "secret", "token", "api_key", "apikey",
                "refresh_token", "access_token", "ssn", "credit_card",
                "account_number", "hashed_password", "private_key"
            ]

        sensitive_keys_lower = {k.lower() for k in sensitive_keys}
        redacted = {}

        for key, value in obj.items():
            key_lower = key.lower()

            # Check if this key name is sensitive
            if any(sensitive in key_lower for sensitive in sensitive_keys_lower):
                redacted[key] = "[REDACTED]"
            elif isinstance(value, dict):
                redacted[key] = DLPRedactor.redact_dict(value, sensitive_keys)
            elif isinstance(value, list):
                redacted[key] = [
                    DLPRedactor.redact_dict(item, sensitive_keys) if isinstance(item, dict)
                    else DLPRedactor.redact_string(str(item))
                    for item in value
                ]
            elif isinstance(value, str):
                redacted[key] = DLPRedactor.redact_string(value)
            else:
                redacted[key] = value

        return redacted

    @staticmethod
    def redact_json(json_str: str) -> str:
        """Redact sensitive patterns from JSON string."""
        try:
            obj = json.loads(json_str)
            redacted_obj = DLPRedactor.redact_dict(obj)
            return json.dumps(redacted_obj)
        except (json.JSONDecodeError, TypeError):
            # If not valid JSON, treat as string and redact patterns
            return DLPRedactor.redact_string(json_str)

    @staticmethod
    def redact_log_message(message: str) -> str:
        """Redact PII from log messages. Applied by audit logging."""
        return DLPRedactor.redact_string(message)

    @staticmethod
    def should_redact_for_role(user_role: str | None) -> bool:
        """Determine if redaction should be applied based on user role.
        For now, always redact. In future, admins/auditors might get unredacted views."""
        return True


dlp_redactor = DLPRedactor()
