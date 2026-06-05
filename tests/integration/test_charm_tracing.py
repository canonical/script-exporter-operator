#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for charm tracing via cos-agent."""

import jubilant
import pytest
from assertions import assert_pattern_in_snap_logs
from conftest import (
    APP_BASE,
    APP_NAME,
    OTEL_COLLECTOR_APP_NAME,
    PRINCIPAL_APP_NAME,
    patch_otel_collector_log_level,
)
from jubilant import Juju
from tenacity import retry, stop_after_attempt, wait_fixed

pytestmark = pytest.mark.usefixtures("patch_update_status_interval")


def _trigger_update_status_event(juju: Juju, unit_name: str):
    """Manually trigger an update-status hook on a charm unit via SSH."""
    juju.ssh(
        unit_name,
        f"sudo /usr/bin/juju-exec -u {unit_name} "
        "JUJU_DISPATCH_PATH=hooks/update-status "
        f"JUJU_MODEL_NAME={juju.model} "
        f"JUJU_UNIT_NAME={unit_name} "
        f"/var/lib/juju/agents/unit-{unit_name.replace('/', '-')}/charm/dispatch",
    )


@pytest.fixture(scope="module")
def deployed_with_tracing(juju: Juju, charm: str):
    """Deploy the script-exporter charm integrated with otel-collector for tracing."""
    # Deploy the principal charm first (script-exporter is subordinate)
    juju.deploy(PRINCIPAL_APP_NAME, base=APP_BASE)
    juju.wait(
        lambda status: jubilant.all_active(status, PRINCIPAL_APP_NAME),
        timeout=10 * 60,
        delay=10,
        successes=3,
    )

    # Deploy the subordinate script-exporter
    juju.deploy(charm, APP_NAME)

    # Integrate subordinate with principal
    juju.integrate(APP_NAME, PRINCIPAL_APP_NAME)
    juju.wait(
        lambda status: jubilant.all_blocked(status, APP_NAME),
        timeout=10 * 60,
        delay=10,
        successes=3,
    )

    # Deploy opentelemetry-collector
    config = {
        "tracing_sampling_rate_workload": 100,
        "debug_exporter_for_traces": True,
    }
    juju.deploy(OTEL_COLLECTOR_APP_NAME, channel="dev/edge", base=APP_BASE, config=config)
    juju.wait(
        lambda status: jubilant.all_agents_idle(status, OTEL_COLLECTOR_APP_NAME),
        timeout=10 * 60,
    )

    # Integrate with cos-agent
    juju.integrate(
        APP_NAME + ":cos-agent",
        OTEL_COLLECTOR_APP_NAME + ":cos-agent",
    )
    juju.wait(
        lambda status: jubilant.all_agents_idle(status, OTEL_COLLECTOR_APP_NAME, APP_NAME),
        timeout=10 * 60,
    )

    patch_otel_collector_log_level(juju)

    yield juju


@retry(stop=stop_after_attempt(10), wait=wait_fixed(10))
def test_charm_traces_are_pushed(deployed_with_tracing: Juju):
    """Verify charm traces are pushed to the collector."""
    juju = deployed_with_tracing
    _trigger_update_status_event(juju, f"{APP_NAME}/0")
    grep_filters = ["ResourceTraces", f"service.name={APP_NAME}", "charm=script-exporter"]
    assert_pattern_in_snap_logs(juju, grep_filters)
