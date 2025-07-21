from contextlib import suppress
from typing import Any

import pytest

from _pytest.config import Config
from _pytest.config.argparsing import Parser

from .terminal import ModernTerminalReporter


def pytest_addoption(parser: Parser):
    group = parser.getgroup("modern", "pytest-modern", after="terminal reporting")
    group.addoption(
        "--modern-disable",
        action="store_true",
        default=False,
        help="Disable pytest-modern",
    )
    with suppress(ImportError):
        import pytest_rerunfailures as _  # noqa: F401

        parser.addini("reruns_except", "", type="linelist")
        parser.addini("only_rerun", "", type="linelist")


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
    if (
        not config.getoption("modern_disable")
        and not getattr(config, "slaveinput", None)
        and not config.getoption("help")
    ):
        with suppress(ImportError):
            import pytest_rerunfailures as _  # noqa: F401

            if not getattr(config.option, "reruns_except", None) and (
                reruns_except := config.getini("reruns_except")
            ):
                config.option.reruns_except = reruns_except

            if not getattr(config.option, "only_rerun", None) and (
                only_rerun := config.getini("only_rerun")
            ):
                config.option.only_rerun = only_rerun

        standard_reporter: Any = config.pluginmanager.getplugin("terminalreporter")
        modern_reporter = ModernTerminalReporter(standard_reporter.config)
        config.pluginmanager.unregister(standard_reporter)
        config.pluginmanager.register(modern_reporter, "terminalreporter")
