from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.core.exceptions import AppError
from app.research.provider import WebResearchResult

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class TavilyResearchProvider:
    name = "tavily"

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self._client = client or httpx.Client(timeout=timeout, trust_env=False)

    def search(self, query: str, *, max_results: int) -> list[WebResearchResult]:
        cleaned = " ".join(query.split())[:500]
        if not cleaned:
            return []
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        else:
            headers["X-Tavily-Access-Mode"] = "keyless"
        try:
            response = self._client.post(
                TAVILY_SEARCH_URL,
                headers=headers,
                json={
                    "query": cleaned,
                    "search_depth": "basic",
                    "max_results": min(max(1, max_results), 8),
                    "include_answer": False,
                    "include_raw_content": False,
                },
            )
        except httpx.HTTPError as exc:
            raise AppError("Web research provider is unavailable", 502) from exc
        if response.status_code != 200:
            raise AppError("Web research provider is unavailable", 502)
        try:
            payload = response.json()
        except ValueError as exc:
            raise AppError("Web research provider returned invalid data", 502) from exc
        rows = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise AppError("Web research provider returned invalid data", 502)
        results: list[WebResearchResult] = []
        seen: set[str] = set()
        for row in rows:
            normalized = _normalize_result(row, len(results) + 1)
            if normalized is None or normalized.url in seen:
                continue
            seen.add(normalized.url)
            results.append(normalized)
            if len(results) >= max_results:
                break
        return results


def _normalize_result(row: object, position: int) -> WebResearchResult | None:
    if not isinstance(row, dict):
        return None
    title = " ".join(str(row.get("title") or "").split())[:240]
    excerpt = " ".join(str(row.get("content") or "").split())[:1200]
    url = str(row.get("url") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if not title or not excerpt:
        return None
    return WebResearchResult(
        id=f"e{position}",
        title=title,
        url=url,
        excerpt=excerpt,
        publisher=parsed.netloc.removeprefix("www.")[:120],
        published_at=str(row.get("published_date") or "")[:40],
    )
