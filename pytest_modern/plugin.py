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
    group.addoption(
        "--modern-no-color",
        action="store_true",
        default=False,
        help="Disable color output",
    )


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
    if (
        not config.getoption("modern_disable")
        and not getattr(config, "slaveinput", None)
        and not config.getoption("help")
    ):
        standard_reporter: Any = config.pluginmanager.getplugin("terminalreporter")
        modern_reporter = ModernTerminalReporter(
            standard_reporter.config, color=not config.getoption("modern_no_color")
        )
        config.pluginmanager.unregister(standard_reporter)
        config.pluginmanager.register(modern_reporter, "terminalreporter")
