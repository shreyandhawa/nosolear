from datetime import UTC, datetime

from provider_fakes import FakeCapabilityProbe
from sqlalchemy import Engine

from nosolear.app.probe_capabilities import probe_capabilities
from nosolear.domain.errors import CapExceeded, RequestNotSent
from nosolear.domain.speech import ProviderCapabilities
from nosolear.persistence.capabilities import CapabilityRepository

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)


def caps(adapter: str) -> ProviderCapabilities:
    return ProviderCapabilities(
        provider="azure",
        adapter=adapter,
        adapter_version=1,
        provider_version="1.53.0",
        region="eastus",
        locale="en-US",
        capabilities={"nbest_phonemes": True, "prosody": True},
        probed_at=NOW,
    )


def test_a_cap_failure_is_reported_and_the_next_probe_still_runs(db_engine: Engine):
    failing = FakeCapabilityProbe(errors=[CapExceeded("Azure is at its cap")], adapter="azure_pa")
    working = FakeCapabilityProbe(results=[caps("azure_stt")], adapter="azure_stt")
    outcomes = probe_capabilities(probes=[failing, working], store=CapabilityRepository(db_engine))
    assert [o.ok for o in outcomes] == [False, True]
    assert outcomes[0].message == "Azure is at its cap"
    assert CapabilityRepository(db_engine).latest("azure", "azure_stt") is not None
    assert CapabilityRepository(db_engine).latest("azure", "azure_pa") is None


def test_a_request_that_was_not_sent_says_it_is_not_configured(db_engine: Engine):
    probe = FakeCapabilityProbe(
        errors=[RequestNotSent("Azure Speech isn't configured: set NOSOLEAR_AZURE_SPEECH_KEY")],
        adapter="azure_pa",
    )
    (outcome,) = probe_capabilities(probes=[probe], store=CapabilityRepository(db_engine))
    assert outcome.ok is False and "isn't configured" in outcome.message


def test_a_success_is_stored_and_summarised(db_engine: Engine):
    probe = FakeCapabilityProbe(results=[caps("azure_pa")], adapter="azure_pa")
    (outcome,) = probe_capabilities(probes=[probe], store=CapabilityRepository(db_engine))
    assert outcome.ok and outcome.adapter == "azure_pa"
    assert "nbest_phonemes True" in outcome.message
    stored = CapabilityRepository(db_engine).latest("azure", "azure_pa")
    assert stored == caps("azure_pa")
