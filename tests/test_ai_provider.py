"""The AI seam: base app must work with no AI installed."""

from wiseql.ai import AIProvider, AIResult, NullProvider, get_provider


def test_default_provider_is_null() -> None:
    provider = get_provider()
    assert isinstance(provider, NullProvider)
    assert isinstance(provider, AIProvider)
    assert provider.is_available is False


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
