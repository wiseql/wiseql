"""AI provider seam.

WiseQL's AI features (semantic validation, failure explanation, narrative
reports) are an OPTIONAL add-on. The engine and TUI are built against the
``AIProvider`` interface; ``NullProvider`` is the default when no AI backend
is installed or enabled.

Architecture rule (see BACKLOG "AI rule"): nothing in the base app may
require an AI backend. AI only ever *adds* information.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AIResult:
    """Result of an AI request.

    ``available`` is False when no real provider is active — callers must
    degrade gracefully (hide/disable the feature, never fail).
    """

    available: bool
    text: str = ""


class AIProvider(ABC):
    """Interface every AI backend implements (Sprint 6: OllamaProvider)."""

    name: str = "abstract"

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """True if the backend is installed, reachable, and enabled."""

    @abstractmethod
    def validate_recipe(self, recipe_text: str, context: str) -> AIResult:
        """Semantic recipe validation beyond structural checks."""

    @abstractmethod
    def explain_failure(self, report_json: str, recipe_text: str, context: str) -> AIResult:
        """Explain a failed run; suggest which step to inspect first."""

    @abstractmethod
    def narrative_report(self, report_json: str, context: str) -> AIResult:
        """Generate a human-readable narrative of a run."""


class NullProvider(AIProvider):
    """Default provider when no AI add-on is installed/enabled.

    Returns ``available=False`` for everything; the UI shows AI features
    as disabled with a hint ("Enable AI in Settings").
    """

    name = "null"

    @property
    def is_available(self) -> bool:
        return False

    def validate_recipe(self, recipe_text: str, context: str) -> AIResult:
        return AIResult(available=False)

    def explain_failure(self, report_json: str, recipe_text: str, context: str) -> AIResult:
        return AIResult(available=False)

    def narrative_report(self, report_json: str, context: str) -> AIResult:
        return AIResult(available=False)


def get_provider() -> AIProvider:
    """Return the active AI provider.

    Sprint 6 will detect the ``[ai]`` extra + Ollama and return an
    ``OllamaProvider``; until then this is always the NullProvider.
    """
    return NullProvider()
