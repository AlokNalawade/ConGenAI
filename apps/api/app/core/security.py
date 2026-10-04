import secrets
from fastapi import Header, HTTPException, status
from app.core.config import settings


def _require_configured_key(configured_key: str, supplied_key: str | None, label: str) -> None:
    if not configured_key:
        if settings.ENV.lower() == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"{label} is not configured",
            )
        return
    if not supplied_key or not secrets.compare_digest(supplied_key, configured_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


async def require_admin_api_key(x_api_key: str | None = Header(default=None)):
    _require_configured_key(settings.ADMIN_API_KEY, x_api_key, "ADMIN_API_KEY")
    return True


async def require_ws_api_key(x_api_key: str | None = None):
    _require_configured_key(settings.ADMIN_API_KEY, x_api_key, "ADMIN_API_KEY")
    return True
