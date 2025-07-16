import warnings

import pytest


def test_passed():
    a = 1
    b = 2
    assert a + b == 3


def test_failed():
    raise RuntimeError("something wrong")


@pytest.mark.skip(reason="skipped")
def test_skipped():
    a = 1
    b = 2
    assert a + b == 2


@pytest.mark.xfail(reason="expected to fail but passed")
def test_xfail():
    a = 1
    b = 2
    assert a + b == 4


@pytest.mark.xfail(reason="expected to fail but passed", strict=True)
def test_xfail_strict():
    a = 1
    b = 2
    assert a + b == 3


def test_warning():
    warnings.warn("this is a warning", UserWarning, stacklevel=1)


@pytest.mark.timeout(1)
def test_timeout():
    import time

    time.sleep(3)


def test_timeout_from_config():
    import time

    time.sleep(3)


class TestGroup:
    def test_ok(self): ...
    def test_fail(self):
        a = 1
        assert a == 2
