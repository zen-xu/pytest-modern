from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import rich.box
import rich.style

from rich.table import Table
from rich.text import Text
from rich.traceback import PathHighlighter


if TYPE_CHECKING:
    from collections.abc import Generator

    import pytest

    from pytest_cov.plugin import CovPlugin
    from rich.console import Console
    from rich.console import ConsoleOptions
    from rich.console import RenderResult


@dataclass
class FileReport:
    name: str
    stmts: str
    miss: str
    cover: str


@dataclass
class CoverageReport:
    config: pytest.Config
    plugin: CovPlugin

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        if (
            self.plugin._disabled
            or self.plugin.cov_controller is None
            or self.plugin.cov_total is None
        ):
            return

        report = self.plugin.cov_report.getvalue()
        if not report:
            return

        yield "──────────"
        yield Text.from_markup("[bold dark_green]  Coverage[/]")
        table = Table(
            box=rich.box.SIMPLE,
            padding=(0, 2),
            show_footer=True,
        )

        reports = list(self.yield_report(report))
        [total] = [item for item in reports if item.name == "TOTAL"]
        reports = [item for item in reports if item.name != "TOTAL"]
        for column in ["name", "stmts", "miss", "cover"]:
            foot_col_value = getattr(total, column)
            table.add_column(
                header=Text(
                    column.title(), style=rich.style.Style(bold=True, dim=True)
                ),
                footer=Text(
                    foot_col_value,
                    style=rich.style.Style(color="red" if column == "miss" else None),
                ),
                overflow="fold",
                justify="right" if column != "name" else "left",
            )

        path_highlighter = PathHighlighter()
        for file_report in reports:
            table.add_row(
                path_highlighter(
                    Text(file_report.name, style=rich.style.Style(color="yellow"))
                ),
                file_report.stmts,
                Text(file_report.miss, style=rich.style.Style(color="red")),
                file_report.cover,
            )

        yield table

    def yield_report(self, report: str) -> Generator[FileReport, None, None]:
        start = False
        for line in report.splitlines():
            if line.startswith("Name "):
                start = True
                continue
            if not start or line.startswith("---"):
                continue
            file, stmts, miss, cover = line.split()
            yield FileReport(file, stmts, miss, cover)
