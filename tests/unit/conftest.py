from pathlib import Path
from typing import Union
from unittest.mock import patch

import pytest
from charmlibs.pathops import LocalPath
from ops.testing import Context

from charm import ScriptExporterCharm


@pytest.fixture
def ctx(patch_etc_paths):
    with patch("charms.operator_libs_linux.v2.snap.SnapCache"):
        yield Context(ScriptExporterCharm)


@pytest.fixture(autouse=True)
def patch_etc_paths(tmp_path):
    sandbox = tmp_path / "etc"
    sandbox.mkdir(parents=True, exist_ok=True)

    def redirect_path(original: Union[str, Path]) -> Path:
        original = Path(original)
        if str(original).startswith("/etc"):
            return sandbox / original.relative_to("/etc")
        return original

    def fake_makedirs(path, exist_ok=True):
        redirected = redirect_path(path)
        redirected.mkdir(parents=True, exist_ok=exist_ok)

    module_name = ScriptExporterCharm.__module__

    def localpath_factory(p, *a, **kw):
        return LocalPath(redirect_path(p))

    def path_factory(p, *a, **kw):
        return Path(redirect_path(p))

    with patch(f"{module_name}.os.makedirs", side_effect=fake_makedirs), \
         patch(f"{module_name}.LocalPath", side_effect=localpath_factory), \
         patch(f"{module_name}.Path", side_effect=path_factory):
        yield sandbox
