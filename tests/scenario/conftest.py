from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def mock_snap():
    with mock.patch("charms.operator_libs_linux.v2.snap.SnapCache") as _fixture:
        yield _fixture
