# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration test for script-exporter with a simple script configuration."""

from pathlib import Path

import jubilant
import pytest

TESTS_INTEGRATION_DIR = Path(__file__).parent
SCRIPT_CONFIG = TESTS_INTEGRATION_DIR / "scripts" / "script1.sh"
CONFIG_FILE = TESTS_INTEGRATION_DIR / "config_file.yaml"
PROMETHEUS_CONFIG_FILE = TESTS_INTEGRATION_DIR / "prometheus_config_file.yaml"

APP_NAME = "script-exporter"
PRINCIPAL_APP_NAME = "principal"


@pytest.fixture(scope="module")
def deployed_charm(juju: jubilant.Juju, charm: str):
    """Deploy the charm with a simple script configuration."""
    juju.deploy("ubuntu", app=PRINCIPAL_APP_NAME, base="ubuntu@24.04")
    juju.deploy(charm, app=APP_NAME)
    juju.integrate(APP_NAME, PRINCIPAL_APP_NAME)

    juju.config(
        APP_NAME,
        {
            "script_file": SCRIPT_CONFIG.read_text(),
            "config_file": CONFIG_FILE.read_text(),
            "prometheus_config_file": PROMETHEUS_CONFIG_FILE.read_text(),
        },
    )

    juju.wait(
        lambda status: jubilant.all_active(status, PRINCIPAL_APP_NAME, APP_NAME),
        timeout=600,
    )

    yield juju

    juju.remove_application(APP_NAME, force=True)
    juju.remove_application(PRINCIPAL_APP_NAME, force=True)


def test_metrics(deployed_charm: jubilant.Juju):
    """Test that metrics are available from the script-exporter."""
    juju = deployed_charm
    metrics = juju.ssh(f"{APP_NAME}/0", "curl -s localhost:9469/probe?script=hello")
    assert 'hello_world{param="argument"} 1' in metrics, f"Expected metric not found in: {metrics}"
