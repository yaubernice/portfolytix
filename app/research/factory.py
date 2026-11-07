from app.core.config import settings
from app.core.exceptions import AppError
from app.research.provider import WebResearchProvider
from app.research.tavily import TavilyResearchProvider


def build_web_research_provider() -> WebResearchProvider:
    chosen = settings.web_research_provider.strip().lower()
    if chosen == "tavily":
        return TavilyResearchProvider(
            settings.web_research_api_key,
            timeout=settings.web_research_timeout_seconds,
        )
    raise AppError(
        "WEB_RESEARCH_PROVIDER must be tavily to use market research",
        status_code=503,
    )


def build_optional_web_research_provider() -> WebResearchProvider | None:
    if settings.web_research_provider.strip().lower() in {"", "none"}:
        return None
    return build_web_research_provider()
