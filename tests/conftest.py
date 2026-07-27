from unittest import mock

import pytest


class Mocker:
    MagicMock = mock.MagicMock

    def __init__(self):
        self._patchers = []

    def patch(self, target, *args, **kwargs):
        patcher = mock.patch(target, *args, **kwargs)
        self._patchers.append(patcher)
        return patcher.start()

    def stopall(self):
        for patcher in reversed(self._patchers):
            patcher.stop()


@pytest.fixture
def mocker():
    helper = Mocker()
    try:
        yield helper
    finally:
        helper.stopall()
