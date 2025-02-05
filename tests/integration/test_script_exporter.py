# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
from types import SimpleNamespace
from pathlib import Path

import pytest
from juju.errors import JujuError
from pytest_operator.plugin import OpsTest

principal = SimpleNamespace(charm="ubuntu", name="principal")

TESTS_INTEGRATION_DIR = Path(__file__).parent

SCRIPT_CONFIG = TESTS_INTEGRATION_DIR / "script.sh"
CONFIG_FILE = TESTS_INTEGRATION_DIR / "config_file.yaml"
PROMETHEUS_CONFIG_FILE = TESTS_INTEGRATION_DIR / "prometheus_config_file.yaml"


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    await ops_test.model.deploy(principal.charm, application_name=principal.name, series="jammy")

    charm = await ops_test.build_charm(".")
    jammy_charm_path = charm.parent / "script-exporter_ubuntu-22.04-amd64.charm"

    await ops_test.model.deploy(
        jammy_charm_path, application_name="script-exporter", num_units=0, series="jammy"
    )

    await ops_test.model.integrate("script-exporter", principal.name)


    await ops_test.model.applications["script-exporter"].set_config(
        {
            "script_file": SCRIPT_CONFIG.read_text(),
            "config_file": CONFIG_FILE.read_text(),
            "prometheus_config_file": PROMETHEUS_CONFIG_FILE.read_text(),
        }
    )

    await ops_test.model.wait_for_idle()


@pytest.mark.abort_on_fail
async def test_metrics(ops_test: OpsTest):
    unit = ops_test.model.applications["script-exporter"].units[0]
    try:
        metrics = await unit.ssh("curl localhost:9469/probe?script=hello")
        assert 'hello_world{param="argument"} 1' in metrics
    except JujuError as e:
        pytest.fail(f"Failed to collect metrics from the script-exporter: {e.message}")
