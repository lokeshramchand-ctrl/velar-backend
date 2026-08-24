import json
import logging
from typing import Any

import httpx

from core.llm_safety import llm_safety_validator, ExplanationOutput
from core.ollama_client import LLM_MODEL, get_ollama_host

logger = logging.getLogger(__name__)

class ExplanationGenerator:
    def __init__(self):
        self.system_prompt = """
You are the Velar Transaction Intelligence Reasoning Engine.
Your ONLY purpose is to explain transaction categorizations or recommend financial insights based STRICTLY on the provided XML context.

RULES:
1. DO NOT act like a chatbot. Do not say "Hello", "Sure", or "I can help with that."
2. DO NOT hallucinate. If the context does not contain the answer, output: {"error": "Insufficient data to explain."}
3. ALWAYS output your response in valid JSON format matching this schema:
{
    "explanation": "Concise reasoning here...",
    "confidence_in_explanation": "HIGH|MEDIUM|LOW",
    "primary_data_source": "Merchant Name or ID"
}
"""

    async def generate_explanation(self, query: str, context_string: str) -> dict[str, Any]:
        if context_string == "NO_CONTEXT_AVAILABLE":
            return {"error": "No historical behavior found to explain this transaction."}

        # Sanitize inputs to prevent prompt injection
        sanitized_query = llm_safety_validator.sanitize_prompt_input(query)
        sanitized_context = llm_safety_validator.sanitize_context(context_string)

        # Wrap user input in delimiters to prevent prompt escape
        delimited_query = llm_safety_validator.wrap_in_delimiters(sanitized_query)
        delimited_context = llm_safety_validator.wrap_in_delimiters(sanitized_context)

        full_prompt = f"CONTEXT:\n{delimited_context}\n\nUSER QUERY: {delimited_query}\n\nOUTPUT STRICT JSON:"

        payload = {
            "model": LLM_MODEL,
            "system": self.system_prompt,
            "prompt": full_prompt,
            "stream": False,
            "format": "json" # Forces Ollama to output valid JSON
        }

        async with httpx.AsyncClient() as client:
            try:
                api_url = f"{get_ollama_host()}/api/generate"
                response = await client.post(api_url, json=payload, timeout=30.0)
                response.raise_for_status()
                data = response.json()

                # Parse and validate the JSON string returned by the LLM
                raw_response = data["response"]

                # Validate JSON structure for safety
                parsed = llm_safety_validator.validate_json_safety(raw_response)
                if parsed is None:
                    logger.error("LLM output failed safety checks")
                    return {"error": "LLM output validation failed"}

                # Validate against expected schema
                validated = llm_safety_validator.validate_llm_output(parsed, ExplanationOutput)
                return validated

            except ValueError as e:
                logger.error(f"LLM Output Validation Error: {e}")
                return {"error": f"Output validation failed: {str(e)}"}
            except Exception as e:
                logger.error(f"LLM Generation Error: {e}")
                return {"error": "Failed to generate explanation due to internal model error."}

explanation_generator = ExplanationGenerator()
