from pathlib import Path
from typing import Union
from unittest import mock
from unittest.mock import patch

import pytest
from ops.testing import Context

from charm import ScriptExporterCharm


@pytest.fixture
def ctx():
    with mock.patch("charms.operator_libs_linux.v2.snap.SnapCache"):
        yield Context(ScriptExporterCharm)


@pytest.fixture(autouse=True)
def patch_etc_paths(tmp_path):
    sandbox = tmp_path / "etc"
    sandbox.mkdir()

    def redirect_path(original: Union[str, Path]) -> Path:
        original = Path(original)
        if str(original).startswith("/etc"):
            return sandbox / original.relative_to("/etc")
        return original

    # patch os.makedirs → create dirs in tmp_path
    def fake_makedirs(path, exist_ok=True):
        redirected = redirect_path(path)
        redirected.mkdir(parents=True, exist_ok=exist_ok)

    with patch("src.charm.os.makedirs", side_effect=fake_makedirs), \
         patch("src.charm.Path", side_effect=lambda p: Path(redirect_path(p))):
        yield sandbox
