from __future__ import annotations

import pytest
import rich.console
import rich.rule
import rich.theme

from _pytest import terminal
from _pytest import timing
from rich.panel import Panel

from .header import generate_header_group


class ModernTerminalReporter(terminal.TerminalReporter):  # type: ignore[final-class]
    def __init__(self, reporter: terminal.TerminalReporter) -> None:
        super().__init__(reporter.config)
        self.console = rich.console.Console(highlight=False)

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
        self.console.print("────────────")
        session_duration = format_node_duration(self._session_start.elapsed().seconds)
        stat_counts = {
            stat_type: len(self._get_reports_to_display(stat_type))
            for stat_type in self._known_types or []
        }
        stats = ", ".join(
            f"[bold]{count}[/] [bold {terminal._color_for_type.get(stat_type, terminal._color_for_type_default)}]{stat_type}[/]"
            for stat_type, count in stat_counts.items()
            if count > 0
        )

        self.console.print(
            f"     [green]Summary[/] [{session_duration}] [bold]{sum(stat_counts.values())}[/] tests run: {stats}"
        )


def format_node_duration(seconds: float) -> str:
    duration = terminal.format_node_duration(seconds).strip()
    if len(duration) < 10:
        return f"{duration:>10s}"
    return duration
