from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from app.ai.grounding import figures_in_text_are_grounded
from app.ai.provider import AssistantModel
from app.core.config import settings
from app.core.exceptions import AppError
from app.research.provider import WebResearchProvider, WebResearchResult
from app.schemas.assistant import MarketResearchAnswer, MarketResearchSource

_DISCLAIMER = (
    "Not investment advice. External claims come from the linked search "
    "results and may change. Verify important facts with primary sources."
)


class MarketResearchService:
    def __init__(
        self,
        model: AssistantModel,
        provider: WebResearchProvider,
    ) -> None:
        self.model = model
        self.provider = provider

    def ask(self, question: str) -> MarketResearchAnswer:
        try:
            results = self.provider.search(
                question,
                max_results=settings.web_research_max_results,
            )
        except AppError:
            return self._answer(
                question,
                "Web research is currently unavailable. "
                "No uncited answer was generated.",
                [],
                "template",
            )
        results = _recent_first(results)
        if not results:
            return self._answer(
                question,
                "No relevant web sources were returned. "
                "No uncited answer was generated.",
                [],
                "template",
            )
        evidence = _evidence(results)
        try:
            interpretation = self.model.interpret(question, evidence)
            source = self.model.interpretation_source
            if not figures_in_text_are_grounded(interpretation, str(evidence)):
                raise ValueError("interpretation used a figure that was not supplied")
        except Exception:
            interpretation = _source_digest(results)
            source = "template"
        if interpretation == "The retrieved sources do not support a cited answer.":
            interpretation = _source_digest(results)
            source = "template"
        return self._answer(question, interpretation, results, source)

    def _answer(
        self,
        question: str,
        interpretation: str,
        results: list[WebResearchResult],
        source: str,
    ) -> MarketResearchAnswer:
        return MarketResearchAnswer(
            question=question,
            interpretation=interpretation,
            interpretation_source=source,
            research_provider=self.provider.name,
            model=settings.ai_model if source == "llm" else "none",
            sources=[
                MarketResearchSource(
                    id=row.id,
                    title=row.title,
                    url=row.url,
                    publisher=row.publisher,
                    published_at=row.published_at,
                )
                for row in results
            ],
            disclaimer=_DISCLAIMER,
        )


def _recent_first(results: list[WebResearchResult]) -> list[WebResearchResult]:
    ordered = sorted(results, key=lambda row: _stamp(row.published_at), reverse=True)
    return [replace(row, id=f"e{index}") for index, row in enumerate(ordered, start=1)]


def _stamp(value: str) -> datetime:
    text = (value or "").strip()
    if not text:
        return datetime.min
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.min


def _evidence(results: list[WebResearchResult]) -> dict:
    facts = [
        {
            "kind": "fact",
            "id": row.id,
            "name": f"web:{row.publisher}",
            "label": row.title,
            "value": row.excerpt,
            "source": "provider",
            "method": f"Public web result from {row.url}",
            "as_of": row.published_at,
            "unit": "",
            "availability": "available",
        }
        for row in results
    ]
    return {
        "facts": facts,
        "metrics": [],
        "research_scope": "public web sources",
        "citation_required": True,
    }


def _source_digest(results: list[WebResearchResult]) -> str:
    lines = ["The configured model did not produce a fully cited synthesis."]
    lines.extend(f"- {row.title} [{row.id}]" for row in results[:5])
    return "\n".join(lines)
