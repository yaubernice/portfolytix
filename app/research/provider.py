from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WebResearchResult:
    id: str
    title: str
    url: str
    excerpt: str
    publisher: str
    published_at: str = ""


class WebResearchProvider(Protocol):
    name: str

    def search(self, query: str, *, max_results: int) -> list[WebResearchResult]:
        """Return normalized public sources. Never execute model-provided URLs."""
