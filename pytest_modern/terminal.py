from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

import pytest
import rich.console
import rich.live
import rich.panel
import rich.progress
import rich.rule
import rich.theme

from _pytest import terminal

from .header import generate_header_group


if TYPE_CHECKING:
    from collections.abc import Collection
    from pathlib import Path
    from typing import Literal

    Status = Literal["collected", "running", "passed", "failed", "skipped", "xfailed"]
    CollectCategory = Literal["selected", "deselected", "error", "skipped"]
    NodeId = str


class ModernTerminalReporter:
    def __init__(
        self, config: pytest.Config, console: rich.console.Console | None = None
    ):
        self.config = config
        self.console = console or rich.console.Console(highlight=False)

        self.total_items_collected = 0
        self.total_items_completed = 0
        self.collect_stats: dict[CollectCategory, list[pytest.Item]] = defaultdict(list)
        self.items_per_file: dict[Path, list[pytest.Item]] = {}
        self.status_per_item: dict[NodeId, Status] = {}
        self.items: dict[NodeId, pytest.Item] = {}
        self.categorized_reports: dict[str, list[pytest.TestReport]] = defaultdict(list)
        self.total_duration: float = 0

        self.collect_progress: rich.progress.Progress | None = None
        self.summary: rich.live.Live | None = None

    def pytest_sessionstart(self, session: pytest.Session) -> None:
        title_msg = "test session starts"
        if self.no_header:
            title = rich.rule.Rule(title_msg, style="default")
        else:
            title = rich.panel.Panel(generate_header_group(session), title=title_msg)
        self.console.print(title)

    def pytest_collection(self) -> None:
        self.collect_progress = rich.progress.Progress(
            "[progress.description]{task.description}",
        )
        self.collect_task = self.collect_progress.add_task("[cyan][bold]Collecting")
        self.collect_progress.start()

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

        if self.collect_progress:
            self.collect_progress.update(
                self.collect_task,
                description=f"[green bold]Collecting[/] [magenta]{report.nodeid}[/magenta] ([bold]{self.total_items_collected}[/] total item{plurals(self.total_items_collected)})",
                refresh=True,
            )

    def pytest_deselected(self, items: list[pytest.Item]) -> None:
        self.collect_stats["deselected"].extend(items)

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        unselected = [item for items in self.collect_stats.values() for item in items]
        self.collect_stats["selected"] = [
            item for item in self.items.values() if item not in unselected
        ]

        if self.collect_progress is None:
            return

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

        self.collect_progress.update(
            self.collect_task,
            description=line,
            completed=True,
        )
        self.collect_progress.stop()
        self.collect_progress = None

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        status = None

        if report.when == "setup":
            if report.outcome == "skipped":
                self.categorized_reports["skipped"].append(report)
            else:
                status = "running"
        elif report.when == "call":
            status = report.outcome
            if status == "skipped":
                status = "xfailed"
            self.categorized_reports[status].append(report)
            self.total_duration += report.duration
        if status:
            self.status_per_item[report.nodeid] = status
            self._update_task(report.nodeid)

    def pytest_sessionfinish(
        self, session: pytest.Session, exitstatus: int | pytest.ExitCode
    ):
        if self.no_summary:
            return

        self.print_summary(session, exitstatus)

    def print_summary(self, session: pytest.Session, exitstatus: int | pytest.ExitCode):
        self.console.print("────────────")
        session_duration = format_node_duration(self.total_duration)
        stat_counts = {
            stat_type: len(self.categorized_reports[stat_type])
            for stat_type in terminal.KNOWN_TYPES
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

    def pytest_runtest_logstart(
        self, nodeid: NodeId, location: tuple[str, int | None, str]
    ) -> None:
        self._update_task(nodeid)

    def _update_task(self, nodeid: NodeId):
        status = self.status_per_item[nodeid]

        if status == "running":
            self.task_live = rich.live.Live(console=rich.console.Console())
            self.task_live.start()
            self.task_live.update(f"[[bold green]RUNNING[/]] {nodeid}")
            self.task_live.refresh()
        elif status == "skipped":
            self.console.print(f"[[bold green]SKIP[/]] {nodeid}")
        elif status in ["error", "failed"]:
            assert self.task_live
            self.task_live.update(f"[[bold red]{status.upper()}[/]] {nodeid}")
            self.task_live.refresh()
            self.task_live.stop()
        elif status == "success":
            assert self.task_live
            self.task_live.update(f"[[bold green]{status.upper()}[/]] {nodeid}")
            self.task_live.refresh()
            self.task_live.stop()

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
