from __future__ import annotations

import pytest
import rich.console
import rich.rule
import rich.theme

from _pytest import timing
from _pytest.terminal import TerminalReporter
from rich.panel import Panel

from .header import generate_header_group


class ModernTerminalReporter(TerminalReporter):  # type: ignore[final-class]
    def __init__(self, reporter: TerminalReporter) -> None:
        super().__init__(reporter.config)
        self.console = rich.console.Console()

    @pytest.hookimpl(trylast=True)
    def pytest_sessionstart(self, session: pytest.Session) -> None:
        self._session = session
        self._session_start = timing.Instant()
        if not self.showheader:
            return
        if self.no_header is False:
            header = Panel(generate_header_group(session), title="test session starts")
            self.console.print(header)

    def summary_stats(self) -> None:
        if self.verbosity < -1:
            return
        super().summary_stats()
        self.console.print("────────────")
        self.console.print("     [green]Summary[/green]")
