from __future__ import annotations

import os
import sys
import threading

from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
import rich.live
import rich.padding
import rich.panel
import rich.progress
import rich.rule
import rich.syntax
import rich.text
import rich.theme

from _pytest import terminal
from _pytest._code.code import ExceptionChainRepr
from _pytest._io import TerminalWriter

from .header import generate_header_group
from .traceback import ModernExceptionChainRepr


if TYPE_CHECKING:
    import warnings

    from collections.abc import Collection
    from pathlib import Path
    from typing import IO
    from typing import Literal

    from typing_extensions import TypedDict

    Status = Literal[
        "collected",
        "running",
        "passed",
        "failed",
        "skipped",
        "xfailed",
        "warning",
        "timeout",
    ]
    CollectCategory = Literal["selected", "deselected", "error", "skipped"]
    NodeId = str

    class CategorizedReports(TypedDict):
        running: list[pytest.TestReport]
        failed: list[pytest.TestReport]
        timeout: list[pytest.TestReport]
        passed: list[pytest.TestReport]
        xfailed: list[pytest.TestReport]
        skipped: list[pytest.TestReport]
        warning: list[WarningReport]


@dataclass
class WarningReport:
    message: warnings.WarningMessage
    fslocation: tuple[str, int]
    nodeid: str


class ModernTerminalReporter:
    def __init__(
        self,
        config: pytest.Config,
        color: bool,
        console: rich.console.Console | None = None,
    ):
        self.config = config
        self.console = console or rich.console.Console(
            highlight=False,
            force_terminal=True,
            width=None if sys.stdout.isatty() else 200,
            color_system="auto" if color else None,
        )
        self.console.file = trim_io_space(self.console.file)

        self.total_items_collected = 0
        self.total_items_completed = 0
        self.collect_stats: dict[CollectCategory, list[pytest.Item]] = defaultdict(list)
        self.items_per_file: dict[Path, list[pytest.Item]] = {}
        self.status_per_item: dict[NodeId, Status] = {}
        self.items: dict[NodeId, pytest.Item] = {}
        self.test_reports: dict[NodeId, pytest.TestReport] = {}
        self.categorized_reports: CategorizedReports = defaultdict(list)  # type: ignore
        self.total_duration: float = 0

        # _tw is used by pytest.Config.get_terminal_writer
        # We need to set it to a terminal writer that does nothing
        devnull_path = "nul" if os.name == "nt" else "/dev/null"
        self._tw = TerminalWriter(file=open(devnull_path, "w"))  # noqa: SIM115

        self.default_timeout: float = float(
            self.config.getoption("timeout") or self.config.getini("timeout") or 0
        )

    def pytest_sessionstart(self, session: pytest.Session) -> None:
        title_msg = "test session starts"
        if self.no_header:
            title = rich.rule.Rule(title_msg, style="default")
        else:
            title = rich.panel.Panel(
                generate_header_group(session), title=title_msg, width=120
            )
        self.console.print(title)

    def pytest_collection(self) -> None:
        self.collect_live = new_live(console=self.console)
        self.collect_live.start()

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        items = [x for x in report.result if isinstance(x, pytest.Item)]
        if report.failed:
            self.collect_stats["error"].extend(items)
        elif report.skipped:
            self.collect_stats["skipped"].extend(items)

        for item in items:
            self.items_per_file.setdefault(item.path, []).append(item)
            self.status_per_item[item.nodeid] = "collected"
            self.items[item.nodeid] = item
        self.total_items_collected += len(items)

        self.collect_live.update(
            f"[green bold]Collecting[/] [magenta]{report.nodeid}[/magenta] ([bold]{self.total_items_collected}[/] total item{plurals(self.total_items_collected)})",
        )
        self.collect_live.refresh()

    def pytest_deselected(self, items: list[pytest.Item]) -> None:
        self.collect_stats["deselected"].extend(items)

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        unselected = [item for items in self.collect_stats.values() for item in items]
        self.collect_stats["selected"] = [
            item for item in self.items.values() if item not in unselected
        ]

        line = f"[green bold]Collected[/] [bold]{self.total_items_collected}[/] item{plurals(self.total_items_collected)}"
        extra_line = ""
        if selected := self.collect_stats["selected"]:
            extra_line += f", [bold]{len(selected)}[/] [bold green]selected[/]"
        if deselected := self.collect_stats["deselected"]:
            extra_line += (
                f", [bold]{len(deselected)}[/] [bold bright_black]deselected[/]"
            )
        if skipped := self.collect_stats["skipped"]:
            extra_line += f", [bold]{len(skipped)}[/] [bold yellow]skipped[/]"
        if errors := self.collect_stats["error"]:
            extra_line += (
                f", [bold]{len(errors)}[/] [bold red]error[/]{plurals(errors)}"
            )
        if extra_line:
            line = f"{line} ({extra_line.lstrip(', ')})"

        self.collect_live.update(line)
        self.collect_live.stop()

    def pytest_runtest_logstart(
        self, nodeid: NodeId, location: tuple[str, int | None, str]
    ) -> None:
        self.test_live = new_live(console=self.console)
        self.test_live.start()

    def pytest_warning_recorded(
        self, warning_message: warnings.WarningMessage, nodeid: str
    ) -> None:
        if self.config.getoption("disable_warnings"):
            return

        fslocation = warning_message.filename, warning_message.lineno
        warning_report = WarningReport(
            fslocation=fslocation, message=warning_message, nodeid=nodeid
        )
        self.categorized_reports["warning"].append(warning_report)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        status = None
        self.test_reports[report.nodeid] = report

        if report.when == "setup":
            if report.outcome == "skipped":
                self.categorized_reports["skipped"].append(report)
                status = "skipped"
            else:
                status = "running"
        elif report.when == "call":
            status = report.outcome
            if status == "skipped":
                status = "xfailed"
            elif status == "failed":
                with suppress(Exception):
                    crash_message: str = report.longrepr.reprcrash.message  # type: ignore
                    if crash_message.startswith("Failed: Timeout"):
                        status = "timeout"
            self.categorized_reports[status].append(report)
            self.total_duration += report.duration
        elif report.when == "teardown":
            return

        assert status
        self.status_per_item[report.nodeid] = status
        status_param = {
            "nodeid": report.nodeid,
            "status": {
                "running": "RUNNING",
                "failed": "FAIL",
                "passed": "PASS",
                "xfailed": "XFAIL",
                "skipped": "SKIP",
                "timeout": "TIMEOUT",
            }[status],
            "color": {
                "running": "green",
                "failed": "red",
                "timeout": "red",
                "passed": "green",
                "xfailed": "yellow",
                "skipped": "yellow",
            }[status],
            "duration": report.duration,
        }
        if status in ["xfailed", "skipped"]:
            status_param["reason"] = terminal._get_raw_skip_reason(report)
        self.test_live.update(
            new_test_status(
                report, default_timeout=self.default_timeout, **status_param
            )
        )
        self.test_live.refresh()

        if status in ["failed", "timeout"]:
            self.test_live.stop()
            self.console.print("[red bold]stdout ───[/]")

            if report.capstdout:
                self.console.print(
                    rich.padding.Padding(report.capstdout, pad=(0, 0, 0, 2))
                )
            self.console.print("[red bold]stderr ───[/]")
            if report.capstderr:
                self.console.print(
                    rich.padding.Padding(report.capstderr, pad=(0, 0, 0, 2))
                )
            if isinstance(report.longrepr, str):
                self.console.print(
                    rich.padding.Padding(report.longrepr, pad=(0, 0, 0, 2))
                )
            else:
                assert isinstance(report.longrepr, ExceptionChainRepr)
                tb = ModernExceptionChainRepr(report.nodeid, report.longrepr)
                self.console.print(tb)

    def pytest_runtest_logfinish(
        self, nodeid: NodeId, location: tuple[str, int | None, str]
    ) -> None:
        self.test_live.stop()

    def pytest_sessionfinish(
        self, session: pytest.Session, exitstatus: int | pytest.ExitCode
    ):
        if self.no_summary:
            return

        self.print_summary(session, exitstatus)

    def print_summary(self, session: pytest.Session, exitstatus: int | pytest.ExitCode):
        self.console.print("──────────")
        session_duration = format_node_duration(self.total_duration)
        stat_counts = {
            stat_type: len(self.categorized_reports[stat_type])
            for stat_type in [
                "passed",
                "xfailed",
                "xpassed",
                "failed",
                "skipped",
                "deselected",
                "warning",
                "error",
                "timeout",
            ]
        }
        color_for_type = {
            **terminal._color_for_type,
            "deselected": "bright_black",
            "timeout": "red",
        }
        stats = ", ".join(
            f"[bold]{count}[/] [bold {color_for_type.get(stat_type, terminal._color_for_type_default)}]{stat_type}[/]"
            for stat_type, count in stat_counts.items()
            if count > 0
        )
        summary_color = "green" if exitstatus == 0 else "red"
        self.console.print(
            f"   [{summary_color} bold]Summary[/] [{session_duration}] [bold]{sum(stat_counts.values())}[/] tests run: {stats}"
        )

        for failed_status in ["failed", "timeout"]:
            for failed_report in self.categorized_reports.get(failed_status, []):
                try:
                    crash_message = failed_report.longrepr.reprcrash.message  # type: ignore
                    crash_message = rich.syntax.Syntax(
                        crash_message, "python", theme="ansi_dark"
                    ).highlight(crash_message)
                    crash_message.rstrip()
                except Exception:
                    crash_message = ""
                if failed_status == "failed":
                    duration = format_node_duration(failed_report.duration)
                    self.console.print(
                        f"[red bold]{'FAIL':>10s}[/] [{duration}] [red bold]{failed_report.nodeid}[/]",
                        crash_message,
                    )
                elif failed_status == "timeout":
                    timeout = terminal.format_node_duration(
                        failed_report.keywords.get("timeout", self.default_timeout)
                    )
                    self.console.print(
                        f"[red bold]{'TIMEOUT':>10s}[/] [>{timeout:>9}] [red bold]{failed_report.nodeid}[/]"
                    )

        for warning_report in self.categorized_reports.get("warning", []):
            assert warning_report.nodeid
            test_report = self.test_reports[warning_report.nodeid]
            duration = format_node_duration(test_report.duration)
            warn_message = rich.syntax.Syntax(
                repr(warning_report.message.message), "python", theme="ansi_dark"
            ).highlight(repr(warning_report.message.message))
            warn_message.rstrip()
            self.console.print(
                f"[yellow bold]{'WARN':>10s}[/] [{duration}] [yellow bold]{warning_report.nodeid}[/]",
                warn_message,
            )

    @property
    def no_header(self) -> bool:
        return self.config.getoption("no_header")

    @property
    def no_summary(self) -> bool:
        return self.config.getoption("no_summary")


def format_node_duration(seconds: float) -> str:
    duration = terminal.format_node_duration(seconds).strip()
    if len(duration) < 10:
        return f"{duration:>10s}"
    return duration


def plurals(items: Collection | int) -> str:
    count = items if isinstance(items, int) else len(items)
    return "s" if count > 1 else ""


def new_test_status(
    report: pytest.TestReport,
    nodeid: str,
    status: str,
    color: str,
    duration: float = 0,
    default_timeout: float = 0,
    reason: str | None = None,
) -> rich.text.Text:
    fspath, *extra = nodeid.split("::")
    func = "[blue]::[/]".join(f"[bold blue]{f}[/]" for f in extra)
    nodeid = f"[bold cyan]{fspath}[/][cyan]::[/][bold blue]{func}[/]"
    if status == "TIMEOUT":
        timeout = terminal.format_node_duration(
            report.keywords.get("timeout", default_timeout)
        )
        text = f"[bold {color}]{status:>10s}[/] [>{timeout:>9}] {nodeid}"
    else:
        elapsed = format_node_duration(duration)
        text = f"[bold {color}]{status:>10s}[/] [{elapsed}] {nodeid}"
    if reason:
        text += f" ({reason})"
    return rich.text.Text.from_markup(text)


def node_id_text(nodeid: str) -> str:
    fspath, *extra = nodeid.split("::")
    func = "[blue]::[/]".join(f"[bold blue]{f}[/]" for f in extra)
    return f"[bold cyan]{fspath}[/][cyan]::[/][bold blue]{func}[/]"


class CodeCache:
    def __init__(self):
        self.cache: dict[str, str] = {}

    def read_code(self, filename: str) -> str:
        code = self.cache.get(filename)
        if not code:
            with open(filename, encoding="utf-8", errors="replace") as code_file:
                code = code_file.read()
            self.cache[filename] = code
        return code


def new_live(*args, **kwargs) -> rich.live.Live:
    if sys.stdout.isatty():
        return Live(*args, **kwargs)
    else:
        return NonTTYLive(*args, **kwargs)


class NonTTYLive(rich.live.Live):
    def start(self, refresh: bool = False) -> None:
        self.printed = False
        return

    def refresh(self) -> None:
        return

    def stop(self) -> None:
        if not self.printed:
            # make sure only printed once
            self.console.print(self.renderable)
            self.printed = True


class Live(rich.live.Live):
    def refresh(self) -> None:
        # disable refresh in non-main thread, for example in pytest-timeout
        if threading.current_thread() is not threading.main_thread():
            return
        return super().refresh()


code_cache = CodeCache()


def trim_io_space(f: IO[str]) -> IO[str]:
    class Wrapper:
        def __init__(self, f: IO[str]):
            self.f = f
            self.buffer = ""

        def write(self, data):
            # Accumulate data in buffer
            self.buffer += data

        def flush(self):
            # Split buffer into lines, strip trailing spaces, and write
            if self.buffer:
                lines = self.buffer.splitlines(keepends=True)
                for line in lines:
                    # Remove trailing whitespace before line ending
                    if line.endswith(("\n", "\r")):
                        # Find the line ending
                        line_ending = ""
                        if line.endswith("\r\n"):
                            line_ending = "\r\n"
                            content = line[:-2]
                        elif line.endswith("\n"):
                            line_ending = "\n"
                            content = line[:-1]
                        elif line.endswith("\r"):
                            line_ending = "\r"
                            content = line[:-1]
                        else:
                            content = line
                        self.f.write(content.rstrip() + line_ending)  # type: ignore
                    else:
                        self.f.write(line.rstrip())  # type: ignore
                self.buffer = ""
            self.f.flush()

        def __getattr__(self, name):
            return getattr(self.f, name)

    return Wrapper(f)  # type: ignore
