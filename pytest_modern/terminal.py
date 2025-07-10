from __future__ import annotations

import pytest
import rich.console
import rich.live
import rich.rule
import rich.theme

from _pytest import terminal
from _pytest import timing
from _pytest.pathlib import bestrelpath
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

    def pytest_collection(self) -> None:
        if self.isatty():
            if self.config.option.verbose >= 0:
                self.live = rich.live.Live(console=self.console)
                self.live.start()
                self.live.update("[bold]Collecting ...[/]")
        elif self.config.option.verbose >= 1:
            self.console.print("Collecting ... ", style="bold")

    def report_collect(self, final: bool = False) -> None:
        if self.config.option.verbose < 0:
            return

        if not final:
            # Only write the "collecting" report every `REPORT_COLLECTING_RESOLUTION`.
            if (
                self._collect_report_last_write.elapsed().seconds
                < terminal.REPORT_COLLECTING_RESOLUTION
            ):
                return
            self._collect_report_last_write = timing.Instant()

        errors = len(self.stats.get("error", []))
        skipped = len(self.stats.get("skipped", []))
        deselected = len(self.stats.get("deselected", []))
        selected = self._numcollected - deselected
        line = "[green]Collected[/] " if final else "[green]Collecting[/] "
        line += (
            f"[bold]{self._numcollected}[/]"
            + " item"
            + ("" if self._numcollected == 1 else "s")
        )
        extra_line = ""
        if self._numcollected > selected:
            extra_line += f", [bold]{selected}[/] [bold green]selected[/]"
        if deselected:
            extra_line += f", [bold]{deselected}[/] [bold bright_black]deselected[/]"
        if skipped:
            extra_line += f", [bold]{skipped}[/] [bold yellow]skipped[/]"
        if errors:
            extra_line += (
                f", [bold]{errors}[/] [bold red]error[/]{'s' if errors != 1 else ''}"
            )
        if extra_line:
            line = f"{line} ({extra_line.lstrip(', ')})"

        if self.isatty():
            self.live.update(line, refresh=True)
            self.live.stop()
        else:
            self.console.print(line)

    def write_fspath_result(self, nodeid: str, res: str, **markup: bool) -> None:
        fspath = self.config.rootpath / nodeid.split("::")[0]
        if self.currentfspath is None or fspath != self.currentfspath:
            self.currentfspath = fspath
            relfspath = bestrelpath(self.startpath, fspath)
            self.console.print(relfspath, style="magenta", end=" ")

    def summary_stats(self) -> None:
        if self.verbosity < -1:
            return
        self.console.print("────────────")
        session_duration = format_node_duration(self._session_start.elapsed().seconds)
        stat_counts = {
            stat_type: len(self._get_reports_to_display(stat_type))
            for stat_type in self._known_types or []
        }
        color_for_type = {**terminal._color_for_type, "deselected": "bright_black"}
        stats = ", ".join(
            f"[bold]{count}[/] [bold {color_for_type.get(stat_type, terminal._color_for_type_default)}]{stat_type}[/]"
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
