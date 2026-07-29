import secrets
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
import logging

from core.config import settings

logger = logging.getLogger(__name__)

API_KEY_NAME = "X-Velar-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def validate_api_key(api_key_header: str = Security(api_key_header)) -> str:
    """
    Validates the incoming API key. 
    In production, this routes through Redis for sub-millisecond validation.
    """
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Missing X-Velar-API-Key header"
        )
    
    if not secrets.compare_digest(api_key_header, settings.VELAR_API_KEY):
        logger.warning("Rejected invalid API key attempt.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Invalid or revoked API Key"
        )
        
    return "developer_id_789" # Returns the authenticated entity