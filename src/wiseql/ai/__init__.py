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
from collections.abc import Iterator
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

    @abstractmethod
    def stream(self, prompt: str) -> Iterator[str]:
        """Yield response chunks for a raw prompt (TUI streaming). Empty when
        the backend is unavailable — never raises for being off."""


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

    def stream(self, prompt: str) -> Iterator[str]:
        return iter(())  # nothing to stream when AI is off


@dataclass(frozen=True)
class AIStatus:
    """A human-facing snapshot of the AI add-on, shared by the CLI and TUI."""

    enabled: bool
    installed: bool
    reachable: bool
    model_present: bool
    model: str
    host: str
    detail: str

    @property
    def ready(self) -> bool:
        return self.enabled and self.installed and self.reachable and self.model_present


def describe_status(settings=None) -> AIStatus:
    """Probe the AI add-on for display. Network I/O when enabled — call off the
    UI render path (a worker)."""
    from wiseql.ai.settings import AISettings, load_ai_settings

    s = settings if isinstance(settings, AISettings) else load_ai_settings()
    if not s.enabled:
        return AIStatus(False, False, False, False, s.model, s.host,
                        "AI is off — run `wiseql ai setup` to enable.")
    try:
        import ollama  # noqa: F401 — presence check only
    except Exception:  # noqa: BLE001
        return AIStatus(True, False, False, False, s.model, s.host,
                        "the [ai] extra isn't installed — pip install 'wiseql[ai]'")
    from wiseql.ai.ollama import OllamaProvider

    reachable, present, detail = OllamaProvider(s.model, s.host).probe()
    return AIStatus(True, True, reachable, present, s.model, s.host, detail)


def get_provider(settings=None) -> AIProvider:
    """Return the active AI provider.

    ``NullProvider`` unless AI is *enabled* (``wiseql ai setup`` wrote
    ``ai.toml``); when enabled, an ``OllamaProvider`` — whose ``is_available``
    still gates on a live check, so "enabled but Ollama down / package missing"
    degrades to a disabled feature rather than an error. ``settings`` may be
    passed to skip re-reading the state file.
    """
    from wiseql.ai.settings import AISettings, load_ai_settings

    s = settings if isinstance(settings, AISettings) else load_ai_settings()
    if not s.enabled:
        return NullProvider()
    from wiseql.ai.ollama import OllamaProvider

    return OllamaProvider(s.model, s.host)
