import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class ExplanationOutput(BaseModel):
    """Validated schema for LLM explanation output."""
    explanation: str = Field(..., min_length=1, max_length=2000)
    confidence_in_explanation: str = Field(...)
    primary_data_source: str = Field(..., max_length=500)

    class Config:
        validate_assignment = True

    def __init__(self, **data):
        # Normalize confidence level
        if "confidence_in_explanation" in data:
            confidence = data["confidence_in_explanation"].upper()
            if confidence not in ("HIGH", "MEDIUM", "LOW"):
                confidence = "LOW"
            data["confidence_in_explanation"] = confidence
        super().__init__(**data)


class LLMSafetyValidator:
    """Input sanitization and output validation for LLM calls."""

    # Prompt injection patterns - flag or block suspicious input
    INJECTION_PATTERNS = [
        re.compile(r"ignore.*?previous.*?instructions", re.IGNORECASE),
        re.compile(r"forget.*?your.*?instructions", re.IGNORECASE),
        re.compile(r"system.*?prompt", re.IGNORECASE),
        re.compile(r"you.*?are.*?now", re.IGNORECASE),
        re.compile(r"act as.*?instead", re.IGNORECASE),
        re.compile(r"new.*?instructions", re.IGNORECASE),
        re.compile(r"json\s*import|python\s*import", re.IGNORECASE),
    ]

    @staticmethod
    def sanitize_prompt_input(user_input: str, max_length: int = 2000) -> str:
        """Sanitize user input before including in prompts.

        Args:
            user_input: User-provided text to sanitize
            max_length: Maximum length (truncate if exceeded)

        Returns:
            Sanitized input safe for prompt inclusion
        """
        if not isinstance(user_input, str):
            return ""

        # Truncate to max length
        sanitized = user_input[:max_length]

        # Flag suspicious patterns (log but don't block - let the LLM handle it)
        for pattern in LLMSafetyValidator.INJECTION_PATTERNS:
            if pattern.search(sanitized):
                logger.warning(f"Potential prompt injection pattern detected: {pattern.pattern}")

        # Escape special characters that could break prompt structure
        # Use delimiters to separate user input from instructions
        sanitized = sanitized.replace("```", "")  # Remove code block delimiters
        sanitized = sanitized.replace("\n\n\n", "\n")  # Collapse excessive newlines

        return sanitized

    @staticmethod
    def sanitize_context(context: str, max_length: int = 5000) -> str:
        """Sanitize context data before including in prompts.

        Args:
            context: Context/document text to sanitize
            max_length: Maximum length (truncate if exceeded)

        Returns:
            Sanitized context safe for prompt inclusion
        """
        if not isinstance(context, str):
            return ""

        # Truncate to max length
        sanitized = context[:max_length]

        # Remove code blocks that might escape the prompt
        sanitized = sanitized.replace("```", "")

        # Remove system prompt hints
        sanitized = re.sub(r"system.*?prompt", "[FILTERED]", sanitized, flags=re.IGNORECASE)

        return sanitized

    @staticmethod
    def validate_llm_output(output: dict[str, Any], schema: type[BaseModel] = ExplanationOutput) -> dict[str, Any]:
        """Validate LLM output against expected schema.

        Args:
            output: Parsed JSON output from LLM
            schema: Pydantic model to validate against

        Returns:
            Validated output dict, or error dict if validation fails

        Raises:
            ValueError if validation fails
        """
        try:
            # Validate against schema
            validated = schema(**output)
            return validated.model_dump()
        except ValidationError as e:
            logger.error(f"LLM output validation failed: {e}")
            error_messages = "; ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
            raise ValueError(f"LLM output does not match expected schema: {error_messages}") from e
        except Exception as e:
            logger.error(f"Unexpected error validating LLM output: {e}")
            raise ValueError(f"Failed to validate LLM output: {e}") from e

    @staticmethod
    def wrap_in_delimiters(content: str, delimiter: str = "---") -> str:
        """Wrap content in delimiters to prevent prompt injection through structure.

        Args:
            content: Content to wrap
            delimiter: Delimiter string

        Returns:
            Wrapped content
        """
        return f"{delimiter}\n{content}\n{delimiter}"

    @staticmethod
    def validate_json_safety(json_response: str) -> dict[str, Any] | None:
        """Parse JSON and check for suspicious patterns in the output.

        Args:
            json_response: JSON string from LLM

        Returns:
            Parsed JSON if safe, None if suspicious
        """
        import json

        try:
            parsed = json.loads(json_response)

            # Check for suspicious keys that shouldn't be in the output
            suspicious_keys = ["execute", "eval", "exec", "import", "__code__", "command"]
            for key in parsed.keys() if isinstance(parsed, dict) else []:
                if any(sus in key.lower() for sus in suspicious_keys):
                    logger.warning(f"Suspicious key in LLM output: {key}")
                    return None

            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON output: {e}")
            return None


llm_safety_validator = LLMSafetyValidator()
