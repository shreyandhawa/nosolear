"""The live capability probe: paid calls to Azure, so it runs only when the owner asks
(`make test-live`). Never run in CI or unit tests."""

import pytest

from nosolear.adapters.system_clock import SystemClock
from nosolear.api.deps import build_capability_probes, build_providers
from nosolear.app.probe_capabilities import probe_capabilities
from nosolear.persistence.capabilities import CapabilityRepository
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.ports.ledger import UsageLedger
from nosolear.settings import Settings


@pytest.mark.live
def test_probe_on_this_resource(require_azure, live_settings: Settings, real_ledger: UsageLedger):
    engine = create_engine_for(live_settings.database_url)
    upgrade_to_head(engine)
    clock = SystemClock()
    providers = build_providers(live_settings, engine=engine, ledger=real_ledger, clock=clock)
    store = CapabilityRepository(engine)
    outcomes = probe_capabilities(
        probes=build_capability_probes(live_settings, providers, engine=engine, clock=clock),
        store=store,
    )
    assert all(outcome.ok for outcome in outcomes), outcomes
    print(store.latest_all())  # the n-best, prosody and speed figures go into HANDOFF
