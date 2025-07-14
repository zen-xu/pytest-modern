import pytest


def test_passed():
    a = 1
    b = 2
    assert a + b == 3


def test_failed():
    a = 1
    b = 2
    assert a + b == 2


@pytest.mark.skip(reason="skipped")
def test_skipped():
    a = 1
    b = 2
    assert a + b == 2


@pytest.mark.xfail(reason="expected to fail but passed")
def test_xpassed():
    a = 1
    b = 2
    assert a + b == 2


class TestIt:
    def test_ok(self): ...
    def test_fail(self):
        assert 1 == 2
