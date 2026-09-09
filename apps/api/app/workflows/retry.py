import asyncio
import functools
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

def retry_async(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0, exceptions=(Exception,)):
    """
    Decorator for retrying async functions with exponential backoff.
    """
    def decorator(func: Callable[..., Any]):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} for {func.__name__} failed with: {e}"
                    )
                    if attempt < max_attempts:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
            raise last_exception
        return wrapper
    return decorator
