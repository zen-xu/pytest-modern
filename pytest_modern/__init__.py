import pytest


IS_MODERN_ENABLED = False


@pytest.hookimpl(trylast=True)
def pytest_configure(config) -> None:
    global IS_MODERN_ENABLED
