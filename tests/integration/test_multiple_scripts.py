# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import base64
import io
import os
import tarfile
from pathlib import Path
from types import SimpleNamespace
from typing import List

import pytest
from juju.errors import JujuError
from pytest_operator.plugin import OpsTest

principal = SimpleNamespace(charm="ubuntu", name="principal")

TESTS_INTEGRATION_DIR = Path(__file__).parent

SCRIPT1 = TESTS_INTEGRATION_DIR / "script1.sh"
SCRIPT2 = TESTS_INTEGRATION_DIR / "script2.sh"
CONFIG_FILE = TESTS_INTEGRATION_DIR / "config_multiple.yaml"
PROMETHEUS_CONFIG_FILE = TESTS_INTEGRATION_DIR / "prometheus_config_multiple.yaml"


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    assert ops_test.model
    await ops_test.model.deploy(principal.charm, application_name=principal.name, series="noble")

    if charm_file := os.environ.get("CHARM_PATH"):
        charm = Path(charm_file)
    else:
        charm = await ops_test.build_charm(".")

    await ops_test.model.deploy(
        charm,
        application_name="script-exporter",
        num_units=0,
    )

    await ops_test.model.integrate("script-exporter", principal.name)

    await ops_test.model.applications["script-exporter"].set_config(
        {
            "compressed_script_files": tar_gz_base64([SCRIPT1, SCRIPT2]),
            "config_file": CONFIG_FILE.read_text(),
            "prometheus_config_file": PROMETHEUS_CONFIG_FILE.read_text(),
        }
    )

    await ops_test.model.wait_for_idle()


@pytest.mark.abort_on_fail
async def test_metrics(ops_test: OpsTest):
    assert ops_test.model
    unit = ops_test.model.applications["script-exporter"].units[0]
    try:
        metric_hello = await unit.ssh("curl localhost:9469/probe?script=hello")
        assert 'hello_world{param="diego"} 1' in metric_hello

        metric_bye = await unit.ssh("curl localhost:9469/probe?script=bye")
        assert 'bye_world{param="maradona"} 1' in metric_bye
    except JujuError as e:
        pytest.fail(f"Failed to collect metrics from the script-exporter: {e.message}")


def tar_gz_base64(paths: List[Path]) -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in paths:
            tar.add(path, arcname=path.name)
    buf.seek(0)
    # encodear en base64
    return base64.b64encode(buf.read()).decode("utf-8")
