# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration test for script-exporter with multiple scripts via archive."""

import base64
import io
import tarfile
from pathlib import Path

import jubilant
import pytest

TESTS_INTEGRATION_DIR = Path(__file__).parent
SCRIPTS_DIR = TESTS_INTEGRATION_DIR / "scripts"
SCRIPT1 = SCRIPTS_DIR / "script1.sh"
SCRIPT2 = SCRIPTS_DIR / "subdir" / "script2.sh"
CONFIG_FILE = TESTS_INTEGRATION_DIR / "config_multiple.yaml"
PROMETHEUS_CONFIG_FILE = TESTS_INTEGRATION_DIR / "prometheus_config_multiple.yaml"

APP_NAME = "script-exporter"
PRINCIPAL_APP_NAME = "principal"


def tar_lzma_base64(paths: list[Path]) -> str:
    """Create a base64-encoded LZMA tar archive from the given paths."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tar:
        for path in paths:
            arcname = path.relative_to(SCRIPTS_DIR)
            tar.add(path, arcname=arcname)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


@pytest.fixture(scope="module")
def deployed_charm(juju: jubilant.Juju, charm: str):
    """Deploy the charm with multiple scripts via archive."""
    juju.deploy("ubuntu", app=PRINCIPAL_APP_NAME, base="ubuntu@24.04")
    juju.deploy(charm, app=APP_NAME)
    juju.integrate(APP_NAME, PRINCIPAL_APP_NAME)

    juju.config(
        APP_NAME,
        {
            "scripts_archive": tar_lzma_base64([SCRIPT1, SCRIPT2]),
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


def test_metrics_hello(deployed_charm: jubilant.Juju):
    """Test hello script metrics."""
    juju = deployed_charm
    task = juju.ssh(f"{APP_NAME}/0", "curl -s localhost:9469/probe?script=hello")
    metrics = task.stdout
    assert 'hello_world{param="diego"} 1' in metrics, f"Expected metric not found in: {metrics}"


def test_metrics_bye(deployed_charm: jubilant.Juju):
    """Test bye script metrics."""
    juju = deployed_charm
    task = juju.ssh(f"{APP_NAME}/0", "curl -s localhost:9469/probe?script=bye")
    metrics = task.stdout
    assert 'bye_world{param="maradona"} 1' in metrics, f"Expected metric not found in: {metrics}"


def test_metrics_abspath(deployed_charm: jubilant.Juju):
    """Test abspath script metrics."""
    juju = deployed_charm
    task = juju.ssh(f"{APP_NAME}/0", "curl -s localhost:9469/probe?script=abspath")
    metrics = task.stdout
    assert 'champion{param="me"} 1' in metrics, f"Expected metric not found in: {metrics}"
