"""Live web search adapters used by the opportunity discovery engine.

Only provider-returned URLs and snippets are treated as source evidence. No
synthetic results are generated when credentials are absent or a provider fails.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings


class SearchProviderError(RuntimeError):
    """Raised when live search is unavailable or returns an invalid response."""


def _valid_http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class WebSearchProvider:
    """Small adapter supporting Tavily and Brave Search APIs."""

    def __init__(self, provider: str | None = None):
        self.provider = (provider or settings.DISCOVERY_SEARCH_PROVIDER).strip().lower()

    async def search(self, query: str, limit: int = 10, domains: list[str] | None = None) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        if self.provider == "tavily":
            return await self._search_tavily(query, limit, domains)
        if self.provider == "brave":
            return await self._search_brave(query, limit, domains)
        raise SearchProviderError(
            f"Unsupported discovery search provider '{self.provider}'. "
            "Choose 'tavily' or 'brave'."
        )

    async def _search_tavily(self, query: str, limit: int, domains: list[str] | None = None) -> list[dict[str, Any]]:
        if not settings.TAVILY_API_KEY:
            raise SearchProviderError(
                "TAVILY_API_KEY is not configured. Add it to the API environment "
                "or select Brave Search with BRAVE_SEARCH_API_KEY."
            )
        payload = {
            "api_key": settings.TAVILY_API_KEY,
            "query": query,
            "topic": "general",
            "search_depth": "advanced",
            "max_results": max(1, min(limit, 20)),
            "include_answer": False,
            "include_raw_content": False,
        }
        if domains:
            payload["include_domains"] = domains[:10]
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                response = await client.post("https://api.tavily.com/search", json=payload)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SearchProviderError(f"Tavily search failed: {exc.__class__.__name__}") from exc

        normalized = []
        for item in data.get("results", []):
            url = item.get("url")
            if not _valid_http_url(url):
                continue
            normalized.append({
                "title": str(item.get("title") or "").strip(),
                "url": url,
                "snippet": str(item.get("content") or "").strip()[:3000],
                "published_at": item.get("published_date"),
                "provider": "tavily",
                "query": query,
            })
        return normalized

    async def _search_brave(self, query: str, limit: int, domains: list[str] | None = None) -> list[dict[str, Any]]:
        if not settings.BRAVE_SEARCH_API_KEY:
            raise SearchProviderError(
                "BRAVE_SEARCH_API_KEY is not configured. Add it to the API environment "
                "or select Tavily with TAVILY_API_KEY."
            )
        if domains:
            domain_filter = " OR ".join(f"site:{domain}" for domain in domains[:10])
            query = f"{query} ({domain_filter})"
        params = {"q": query, "count": max(1, min(limit, 20)), "safesearch": "moderate"}
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": settings.BRAVE_SEARCH_API_KEY,
        }
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SearchProviderError(f"Brave Search failed: {exc.__class__.__name__}") from exc

        web = data.get("web") or {}
        normalized = []
        for item in web.get("results", []):
            url = item.get("url")
            if not _valid_http_url(url):
                continue
            normalized.append({
                "title": str(item.get("title") or "").strip(),
                "url": url,
                "snippet": str(item.get("description") or "").strip()[:3000],
                "published_at": item.get("page_age") or item.get("age"),
                "provider": "brave",
                "query": query,
            })
        return normalized
