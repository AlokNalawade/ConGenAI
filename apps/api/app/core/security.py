import secrets
from fastapi import Header, HTTPException, status
from app.core.config import settings


async def require_admin_api_key(x_api_key: str | None = Header(default=None)):
    configured = settings.ADMIN_API_KEY
    if not configured:
        if settings.ENV.lower() == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ADMIN_API_KEY is not configured",
            )
        return True

    if not x_api_key or not secrets.compare_digest(x_api_key, configured):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return True
