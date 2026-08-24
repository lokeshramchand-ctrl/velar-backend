import re
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


class ValidationRule(str, Enum):
    """Input validation rules."""
    EMAIL = "email"
    PASSWORD = "password"
    USERNAME = "username"
    URL = "url"
    IP_ADDRESS = "ip_address"
    PHONE = "phone"
    CURRENCY = "currency"
    ALPHANUMERIC = "alphanumeric"
    NO_SQL_INJECTION = "no_sql_injection"
    NO_XSS = "no_xss"


class InputValidator:
    """Comprehensive input validation for security and data integrity."""

    # Regex patterns for common validations
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    PHONE_PATTERN = re.compile(r'^\+?1?\d{9,15}$')
    ALPHANUMERIC_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
    IP_PATTERN = re.compile(
        r'^(\d{1,3}\.){3}\d{1,3}$'
    )
    URL_PATTERN = re.compile(
        r'^https?://[^\s/$.?#].[^\s]*$', re.IGNORECASE
    )

    SQL_INJECTION_KEYWORDS = {
        "union", "select", "insert", "update", "delete", "drop",
        "create", "alter", "exec", "execute", "script", "javascript"
    }

    @staticmethod
    def validate_email(email: str, max_length: int = 254) -> str:
        """Validate email address format and length.

        Args:
            email: Email string to validate
            max_length: Maximum email length (RFC 5321)

        Returns:
            Normalized (lowercased) email

        Raises:
            ValidationError: If email is invalid
        """
        if not email or len(email) > max_length:
            raise ValidationError("Invalid email format or length")

        email = email.lower().strip()
        if not InputValidator.EMAIL_PATTERN.match(email):
            raise ValidationError("Invalid email format")

        return email

    @staticmethod
    def validate_password(password: str, min_length: int = 8, max_length: int = 128) -> None:
        """Validate password strength and requirements.

        Args:
            password: Password to validate
            min_length: Minimum password length
            max_length: Maximum password length

        Raises:
            ValidationError: If password doesn't meet requirements
        """
        if not password:
            raise ValidationError("Password cannot be empty")

        if len(password) < min_length or len(password) > max_length:
            raise ValidationError(
                f"Password must be between {min_length} and {max_length} characters"
            )

        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)

        if not (has_upper and has_lower and has_digit):
            raise ValidationError(
                "Password must contain uppercase, lowercase, and numeric characters"
            )

    @staticmethod
    def validate_no_sql_injection(input_str: str) -> str:
        """Check for common SQL injection patterns.

        Args:
            input_str: String to validate

        Returns:
            The input string if clean

        Raises:
            ValidationError: If SQL injection pattern detected
        """
        if not isinstance(input_str, str):
            return input_str

        input_lower = input_str.lower()
        for keyword in InputValidator.SQL_INJECTION_KEYWORDS:
            if keyword in input_lower:
                logger.warning(f"Potential SQL injection detected: {input_lower[:50]}")
                raise ValidationError(f"Invalid characters detected in input")

        if any(char in input_str for char in ["'", '"', ";", "--", "/*", "*/"]):
            logger.warning(f"Suspicious SQL characters detected: {input_str[:50]}")
            raise ValidationError("Invalid characters in input")

        return input_str

    @staticmethod
    def validate_no_xss(input_str: str) -> str:
        """Check for common XSS patterns.

        Args:
            input_str: String to validate

        Returns:
            The input string if clean

        Raises:
            ValidationError: If XSS pattern detected
        """
        if not isinstance(input_str, str):
            return input_str

        xss_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'on\w+\s*=',
            r'<iframe',
            r'<embed',
            r'<object',
        ]

        for pattern in xss_patterns:
            if re.search(pattern, input_str, re.IGNORECASE):
                logger.warning(f"Potential XSS detected: {input_str[:50]}")
                raise ValidationError("Invalid HTML/script content detected")

        return input_str

    @staticmethod
    def validate_alphanumeric(input_str: str, allow_spaces: bool = False) -> str:
        """Validate string contains only alphanumeric characters.

        Args:
            input_str: String to validate
            allow_spaces: Whether to allow spaces

        Returns:
            The input string if valid

        Raises:
            ValidationError: If non-alphanumeric characters found
        """
        if allow_spaces:
            if not re.match(r'^[a-zA-Z0-9\s_-]+$', input_str):
                raise ValidationError("Invalid characters in string")
        else:
            if not InputValidator.ALPHANUMERIC_PATTERN.match(input_str):
                raise ValidationError("String must be alphanumeric")

        return input_str

    @staticmethod
    def validate_url(url: str) -> str:
        """Validate URL format.

        Args:
            url: URL string to validate

        Returns:
            The URL if valid

        Raises:
            ValidationError: If URL is invalid
        """
        url = url.strip()
        if not InputValidator.URL_PATTERN.match(url):
            raise ValidationError("Invalid URL format")

        if len(url) > 2048:
            raise ValidationError("URL exceeds maximum length")

        return url

    @staticmethod
    def validate_currency(amount: float | str, min_amount: float = 0, max_amount: float = 1_000_000_000) -> float:
        """Validate currency amount.

        Args:
            amount: Amount to validate
            min_amount: Minimum allowed amount
            max_amount: Maximum allowed amount

        Returns:
            Validated amount as float

        Raises:
            ValidationError: If amount is invalid
        """
        try:
            if isinstance(amount, str):
                amount = float(amount)

            if amount < min_amount or amount > max_amount:
                raise ValidationError(
                    f"Amount must be between {min_amount} and {max_amount}"
                )

            if amount != round(amount, 2):
                raise ValidationError("Amount must have at most 2 decimal places")

            return amount
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Invalid currency amount: {str(e)}") from e

    @staticmethod
    def sanitize_string(input_str: str, max_length: int = 500) -> str:
        """Sanitize string by removing suspicious content and enforcing length limits.

        Args:
            input_str: String to sanitize
            max_length: Maximum allowed length

        Returns:
            Sanitized string

        Raises:
            ValidationError: If sanitization fails
        """
        if not isinstance(input_str, str):
            raise ValidationError("Input must be a string")

        input_str = input_str.strip()

        if len(input_str) == 0:
            raise ValidationError("Input cannot be empty")

        if len(input_str) > max_length:
            raise ValidationError(f"Input exceeds maximum length of {max_length}")

        InputValidator.validate_no_xss(input_str)
        InputValidator.validate_no_sql_injection(input_str)

        return input_str

    @staticmethod
    def validate_batch(data: dict, rules: dict[str, list[ValidationRule]]) -> dict:
        """Validate multiple fields with specified rules.

        Args:
            data: Dictionary of field names to values
            rules: Dictionary of field names to list of validation rules

        Returns:
            Validated data dictionary

        Raises:
            ValidationError: If any validation fails
        """
        validated = {}

        for field, value in data.items():
            if field not in rules:
                continue

            for rule in rules[field]:
                try:
                    if rule == ValidationRule.EMAIL:
                        value = InputValidator.validate_email(value)
                    elif rule == ValidationRule.PASSWORD:
                        InputValidator.validate_password(value)
                    elif rule == ValidationRule.NO_SQL_INJECTION:
                        value = InputValidator.validate_no_sql_injection(str(value))
                    elif rule == ValidationRule.NO_XSS:
                        value = InputValidator.validate_no_xss(str(value))
                    elif rule == ValidationRule.URL:
                        value = InputValidator.validate_url(value)
                    elif rule == ValidationRule.ALPHANUMERIC:
                        value = InputValidator.validate_alphanumeric(value)
                except ValidationError as e:
                    raise ValidationError(f"Field '{field}' validation failed: {str(e)}") from e

            validated[field] = value

        return validated


# Singleton instance
validator = InputValidator()
