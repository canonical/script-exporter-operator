from unittest import mock

import pytest
from ops.testing import Context

from charm import ScriptExporterCharm


@pytest.fixture
def ctx():
    with mock.patch("charms.operator_libs_linux.v2.snap.SnapCache"):
        yield Context(ScriptExporterCharm)
