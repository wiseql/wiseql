"""The AI seam: base app must work with no AI installed (S0), plus the Ollama
provider wiring (S6.1) exercised through an injected fake client — no live
Ollama and no `ollama` package required."""

import sys

from wiseql.ai import AIProvider, AIResult, NullProvider, describe_status, get_provider
from wiseql.ai.ollama import OllamaProvider
from wiseql.ai.settings import AISettings


class FakeClient:
    """Stand-in for ollama.Client: configurable models / failure / response."""

    def __init__(self, models=None, raise_on_list=False, response="the answer"):
        self._models = models or []
        self._raise = raise_on_list
        self._response = response

    def list(self):
        if self._raise:
            raise RuntimeError("connection refused")
        return {"models": [{"model": m} for m in self._models]}

    def generate(self, model, prompt, stream=False):
        if stream:
            return iter([{"response": "step 3 "}, {"response": "is wrong"}])
        return {"response": self._response}


# --- the seam still degrades with no AI (S0 contract) -----------------------


def test_disabled_settings_give_null_provider() -> None:
    provider = get_provider(AISettings(enabled=False))
    assert isinstance(provider, NullProvider)
    assert isinstance(provider, AIProvider)
    assert provider.is_available is False


def test_no_arg_get_provider_is_null_when_unconfigured(tmp_path, monkeypatch) -> None:
    # The production entry point (no args) reads ai.toml from the active config
    # dir; with none present it must be the NullProvider.
    monkeypatch.setenv("WISEQL_CONFIG", str(tmp_path / "config.toml"))
    assert isinstance(get_provider(), NullProvider)


def test_null_provider_degrades_gracefully() -> None:
    provider = NullProvider()
    for result in (
        provider.validate_recipe("", ""),
        provider.explain_failure("", "", ""),
        provider.narrative_report("", ""),
    ):
        assert isinstance(result, AIResult)
        assert result.available is False
        # Never raises, never blocks — AI only ever *adds* information.


def test_enabled_settings_give_ollama_provider() -> None:
    provider = get_provider(AISettings(enabled=True, model="gemma3"))
    assert isinstance(provider, OllamaProvider)


# --- OllamaProvider via injected fake client --------------------------------


def test_available_when_model_present() -> None:
    p = OllamaProvider("gemma3", "http://x", client=FakeClient(models=["gemma3:latest"]))
    reachable, present, _ = p.probe()
    assert reachable and present and p.is_available is True


def test_unavailable_when_model_missing() -> None:
    p = OllamaProvider("gemma3", "http://x", client=FakeClient(models=["llama3"]))
    reachable, present, detail = p.probe()
    assert reachable and not present and "not pulled" in detail
    assert p.is_available is False


def test_unavailable_when_unreachable() -> None:
    p = OllamaProvider("gemma3", "http://x", client=FakeClient(raise_on_list=True))
    reachable, present, detail = p.probe()
    assert not reachable and not present and "not reachable" in detail
    assert p.is_available is False


def test_generate_returns_text() -> None:
    p = OllamaProvider("gemma3", "http://x", client=FakeClient(response="step 3 looks wrong"))
    r = p.validate_recipe("[recipe]\nname='x'", "tables: orders(id)")
    assert r.available is True and r.text == "step 3 looks wrong"


def test_generate_degrades_on_error() -> None:
    class Boom(FakeClient):
        def generate(self, model, prompt, stream=False):
            raise RuntimeError("model crashed")

    p = OllamaProvider("gemma3", "http://x", client=Boom())
    r = p.explain_failure("{}", "", "")
    assert r.available is False and "unavailable" in r.text


def test_stream_yields_chunks() -> None:
    p = OllamaProvider("gemma3", "http://x", client=FakeClient())
    assert list(p.stream("prompt")) == ["step 3 ", "is wrong"]


def test_null_provider_stream_is_empty() -> None:
    assert list(NullProvider().stream("prompt")) == []


# --- describe_status (shared by CLI + TUI) ----------------------------------


def test_describe_status_off() -> None:
    st = describe_status(AISettings(enabled=False))
    assert st.enabled is False and st.ready is False
    assert "off" in st.detail.lower()


def test_describe_status_enabled_but_not_installed(monkeypatch) -> None:
    # Simulate the [ai] extra being absent regardless of the venv's real state,
    # so this is deterministic whether or not `make run` added ollama.
    monkeypatch.setitem(sys.modules, "ollama", None)  # `import ollama` → ImportError
    st = describe_status(AISettings(enabled=True, model="gemma3"))
    assert st.enabled is True and st.installed is False and st.ready is False
