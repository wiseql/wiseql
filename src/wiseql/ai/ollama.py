"""Ollama-backed AI provider (S6.1) — Gemma via a local Ollama server.

The ``ollama`` client is an **optional** dependency (``pip install
wiseql[ai]``), so it is imported lazily inside the provider — importing this
module never requires the package, which keeps the base test venv (no extra)
collecting fine. Tests inject a fake client; production builds a real one.

Validation / explanation / narrative only — never in the execution path. All
calls degrade to ``AIResult(available=False)`` on any error (server down, model
missing, package absent): AI only ever *adds* information.
"""

from __future__ import annotations

from wiseql.ai import AIProvider, AIResult


def _validate_prompt(recipe_text: str, context: str) -> str:
    return (
        "You are reviewing a WiseQL SQL recipe for *semantic* problems that a "
        "structural validator cannot catch — e.g. a step referencing a column an "
        "upstream step does not output, or a join key that does not exist.\n"
        "Report concrete issues as a short bullet list, or reply exactly 'OK' if "
        "you find none. Do not restate the recipe.\n\n"
        f"--- schema/context ---\n{context or '(none provided)'}\n\n"
        f"--- recipe ---\n{recipe_text}\n"
    )


def _explain_prompt(report_json: str, recipe_text: str, context: str) -> str:
    return (
        "A WiseQL run failed. Using the run report, the recipe, and the schema "
        "context, explain in 2-4 sentences the most likely cause and name the step "
        "to inspect first. Be concrete; do not dump the inputs back.\n\n"
        f"--- schema/context ---\n{context or '(none provided)'}\n\n"
        f"--- recipe ---\n{recipe_text}\n\n"
        f"--- run report (JSON) ---\n{report_json}\n"
    )


def _narrative_prompt(report_json: str, context: str) -> str:
    return (
        "Summarise this WiseQL run for a teammate who did not see it run: what each "
        "step did, row counts, and any assertion that failed and why it matters. "
        "A few short paragraphs, plain language.\n\n"
        f"--- schema/context ---\n{context or '(none provided)'}\n\n"
        f"--- run report (JSON) ---\n{report_json}\n"
    )


class OllamaProvider(AIProvider):
    """AI backend talking to a local Ollama server running a Gemma model."""

    name = "ollama"

    def __init__(self, model: str, host: str, *, client=None) -> None:
        self.model = model
        self.host = host
        self._client = client  # injected in tests; built lazily otherwise

    def _get_client(self):
        if self._client is None:
            import ollama  # lazy — only needed when AI is actually used

            self._client = ollama.Client(host=self.host)
        return self._client

    def probe(self) -> tuple[bool, bool, str]:
        """``(reachable, model_present, detail)`` — one live check for status displays.

        Network I/O — call off the UI render path (a worker). Never raises.
        """
        try:
            listing = self._get_client().list()
        except Exception as exc:  # noqa: BLE001 — unreachable/uninstalled
            return (False, False, f"not reachable at {self.host}: {str(exc).strip()[:120]}")
        present = any(self._matches(self.model, n) for n in _model_names(listing))
        return (True, present, "ready" if present else f"model '{self.model}' not pulled")

    @property
    def is_available(self) -> bool:
        """True only if Ollama is reachable and the configured model is pulled."""
        reachable, present, _ = self.probe()
        return reachable and present

    @staticmethod
    def _matches(want: str, have: str | None) -> bool:
        # "gemma3" should match a pulled "gemma3:latest" / "gemma3:4b".
        return bool(have) and (have == want or have.startswith(want + ":") or want == have.split(":")[0])

    def _generate(self, prompt: str) -> AIResult:
        try:
            resp = self._get_client().generate(model=self.model, prompt=prompt)
        except Exception as exc:  # noqa: BLE001 — degrade, never block
            return AIResult(available=False, text=f"AI unavailable: {str(exc).strip()}")
        text = (resp.get("response") if isinstance(resp, dict) else getattr(resp, "response", "")) or ""
        return AIResult(available=True, text=text.strip())

    def validate_recipe(self, recipe_text: str, context: str) -> AIResult:
        return self._generate(_validate_prompt(recipe_text, context))

    def explain_failure(self, report_json: str, recipe_text: str, context: str) -> AIResult:
        return self._generate(_explain_prompt(report_json, recipe_text, context))

    def narrative_report(self, report_json: str, context: str) -> AIResult:
        return self._generate(_narrative_prompt(report_json, context))


def _model_names(listing) -> list[str]:
    """Pull model names out of an Ollama list() response (dict or object form)."""
    models = listing.get("models", []) if isinstance(listing, dict) else getattr(listing, "models", [])
    names: list[str] = []
    for m in models:
        if isinstance(m, dict):
            names.append(m.get("model") or m.get("name"))
        else:
            names.append(getattr(m, "model", None) or getattr(m, "name", None))
    return [n for n in names if n]
