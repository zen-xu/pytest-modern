import sys

from typing import Any

import pytest

from _pytest.config import Config
from _pytest.config.argparsing import Parser

from .terminal import ModernTerminalReporter


IS_MODERN_ENABLED = False


def pytest_addoption(parser: Parser):
    group = parser.getgroup("modern", "pytest-modern", after="terminal reporting")
    group.addoption(
        "--modern",
        action="store_true",
        default=False,
        help="Enable modern terminal report using pytest-modern",
    )


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
    global IS_MODERN_ENABLED

    if sys.stdout.isatty():
        IS_MODERN_ENABLED = True

    if IS_MODERN_ENABLED and not getattr(config, "slaveinput", None):
        standard_reporter: Any = config.pluginmanager.getplugin("terminalreporter")
        modern_reporter = ModernTerminalReporter(standard_reporter.config)
        config.pluginmanager.unregister(standard_reporter)
        config.pluginmanager.register(modern_reporter, "terminalreporter")
