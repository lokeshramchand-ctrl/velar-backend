import httpx
import logging
from typing import List
from core.ollama_client import OLLAMA_HOST, EMBED_MODEL

logger = logging.getLogger(__name__)

class EmbeddingGenerator:
    def __init__(self):
        self.api_url = f"{OLLAMA_HOST}/api/embeddings"

    async def generate(self, text: str) -> List[float]:
        """Calls the Ollama API to generate vector embeddings."""
        payload = {
            "model": EMBED_MODEL,
            "prompt": text
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.api_url, json=payload, timeout=15.0)
                response.raise_for_status()
                data = response.json()
                return data["embedding"]
            except httpx.HTTPError as e:
                logger.error(f"Ollama Embedding Error: {e}")
                raise

embedding_generator = EmbeddingGenerator()
