import httpx

from app.research.provider import WebResearchResult
from app.research.tavily import TavilyResearchProvider
from app.services.market_research_service import MarketResearchService


class _Model:
    interpretation_source = "llm"

    def interpret(self, question: str, evidence: dict) -> str:
        assert question
        assert evidence["citation_required"] is True
        assert evidence["facts"][0]["id"] == "e1"
        return "The supplied source reports a development. [e1]"


class _Provider:
    name = "test-search"

    def search(self, query: str, *, max_results: int):
        assert query == "What changed?"
        assert max_results >= 1
        return [
            WebResearchResult(
                id="e1",
                title="Primary result",
                url="https://example.test/report",
                excerpt="The report describes the change.",
                publisher="example.test",
                published_at="2026-10-24",
            )
        ]


def test_tavily_normalizes_and_deduplicates_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret-key"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": " Result one ",
                        "url": "https://www.example.com/a",
                        "content": "Useful excerpt",
                        "published_date": "2026-10-24",
                    },
                    {
                        "title": "Duplicate",
                        "url": "https://www.example.com/a",
                        "content": "Duplicate excerpt",
                    },
                    {
                        "title": "Unsafe",
                        "url": "file:///etc/passwd",
                        "content": "No",
                    },
                ]
            },
        )

    provider = TavilyResearchProvider(
        "secret-key",
        timeout=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    results = provider.search("latest result", max_results=5)
    assert len(results) == 1
    assert results[0].id == "e1"
    assert results[0].publisher == "example.com"


def test_market_research_returns_sources_and_model_provenance() -> None:
    answer = MarketResearchService(_Model(), _Provider()).ask("What changed?")
    assert answer.interpretation_source == "llm"
    assert answer.interpretation.endswith("[e1]")
    assert answer.sources[0].url == "https://example.test/report"
    assert answer.research_provider == "test-search"
