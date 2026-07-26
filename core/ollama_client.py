import httpx
import logging
from core.config import settings

logger = logging.getLogger(__name__)


def resolve_ollama_host(hosts: list[str]) -> str:
    """
    Iterates through provided hosts and returns the first healthy one.
    All hosts come from settings.OLLAMA_HOSTS.
    """
    if not hosts:
        logger.error("No OLLAMA_HOSTS provided in .env")
        raise RuntimeError("OLLAMA_HOSTS is empty. Cannot resolve Ollama host.")

    with httpx.Client(timeout=2.0) as client:
        for host in hosts:
            try:
                response = client.get(host)
                if response.status_code == 200:
                    logger.info(f"Resolved Ollama host: {host}")
                    return host
                else:
                    logger.warning(f"Ollama host responded with {response.status_code}: {host}")
            except httpx.RequestError as e:
                logger.warning(f"Ollama host unreachable: {host} | Error: {e}")

    logger.error("No Ollama hosts available. All hosts failed health check.")
    raise RuntimeError("All OLLAMA_HOSTS failed. Cannot initialize Ollama.")


# Initialize constants from settings
OLLAMA_HOST = (
    settings.OLLAMA_URI
    if settings.OLLAMA_URI
    else resolve_ollama_host(settings.ollama_hosts_list)
)

EMBED_MODEL = settings.EMBED_MODEL
LLM_MODEL = settings.LLM_MODEL
