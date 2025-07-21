from __future__ import annotations

import operator

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

import rich.box
import rich.style

from rich.table import Table
from rich.text import Text


if TYPE_CHECKING:
    import pytest

    from pytest_benchmark.session import BenchmarkSession
    from rich.console import Console
    from rich.console import ConsoleOptions
    from rich.console import RenderResult


@dataclass
class BenchmarkReport:
    session: BenchmarkSession
    config: pytest.Config

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        if not self.session.groups:
            return

        yield "──────────"
        yield Text.from_markup("[bold magenta] Benchmark[/]")

        scale_unit = partial(
            self.config.hook.pytest_benchmark_scale_unit, config=self.config
        )
        compares: dict[str, tuple[str, list[tuple[str, float]]]] = {}

        for group_name, benchmarks in self.session.groups or []:
            group_name: str
            benchmarks = sorted(benchmarks, key=operator.itemgetter(self.session.sort))
            for bench in benchmarks:
                bench["name"] = self.session.name_format(bench)

            worst = {}
            best = {}
            for prop in ("min", "max", "mean", "median", "iqr", "stddev", "ops"):
                if prop == "ops":
                    worst[prop] = min(bench[prop] for bench in benchmarks)
                    best[prop] = max(bench[prop] for bench in benchmarks)
                else:
                    worst[prop] = max(bench[prop] for bench in benchmarks)
                    best[prop] = min(bench[prop] for bench in benchmarks)

            for prop in ("outliers", "rounds", "iterations"):
                worst[prop] = max(benchmark[prop] for benchmark in benchmarks)

            unit, adjustment = scale_unit(
                unit="seconds",
                benchmarks=benchmarks,
                best=best,
                worst=worst,
                sort=self.session.sort,
            )
            ops_unit, ops_adjustment = scale_unit(
                unit="operations",
                benchmarks=benchmarks,
                best=best,
                worst=worst,
                sort=self.session.sort,
            )
            labels = {
                "name": "Name",
                "min": f"Min ({unit}s)",
                "max": f"Max ({unit}s)",
                "mean": f"Mean ({unit}s)",
                "stddev": f"StdDev ({unit}s)",
                "rounds": "Rounds",
                "iterations": "Iterations",
                "iqr": "IQR",
                "median": "Median",
                "outliers": "Outliers",
                "ops": f"OPS ({ops_unit}ops/s)" if ops_unit else "OPS",
            }

            table = Table(
                title=None
                if group_name is None
                else f"[yellow]benchmark: {group_name}[/]",
                box=rich.box.SIMPLE,
                padding=(0, 2),
            )
            for label_header in labels.values():
                table.add_column(
                    Text(label_header, style=rich.style.Style(bold=True, dim=True)),
                    overflow="fold",
                )

            for benchmark in benchmarks:
                ceils: list[Text] = []
                for prop in labels:
                    benchmark_value = benchmark[prop]
                    if prop in ("min", "max", "mean", "stddev", "median", "iqr"):
                        color = None
                        if benchmark_value == best[prop]:
                            color = "green"
                        elif benchmark_value == worst[prop]:
                            color = "red"
                        ceils.append(
                            Text(
                                f"{benchmark_value * adjustment:.4f}",
                                style=rich.style.Style(color=color, bold=True),
                            )
                        )
                    elif prop == "ops":
                        color = None
                        if benchmark_value == best[prop]:
                            color = "green"
                        elif benchmark_value == worst[prop]:
                            color = "red"
                        ceils.append(
                            Text(
                                f"{benchmark_value * ops_adjustment:.4f}",
                                style=rich.style.Style(color=color, bold=True),
                            )
                        )
                    elif prop == "name":
                        ceils.append(
                            Text(
                                benchmark_value,
                                style=rich.style.Style(color="blue"),
                            )
                        )
                    else:
                        ceils.append(Text(str(benchmark_value)))
                table.add_row(*ceils)
            yield table

            if group_name:
                fatest_idx = 0
                for idx, benchmark in enumerate(benchmarks):
                    if benchmark["mean"] < benchmarks[fatest_idx]["mean"]:
                        fatest_idx = idx
                fatest_name: str = benchmarks[fatest_idx]["name"]
                fatest_mean: float = benchmarks[fatest_idx]["mean"]
                compares[group_name] = (
                    fatest_name,
                    [
                        (
                            benchmark["name"],
                            benchmark["mean"] / fatest_mean,
                        )
                        for benchmark in benchmarks
                        if benchmark["name"] != fatest_name
                    ],
                )

        if compares:
            yield Text.from_markup("[magenta bold] Benchmark Summary (by mean)[/]")
            table = Table(
                box=rich.box.SIMPLE,
                padding=(0, 2),
            )
            table.add_column(
                Text("Group", style=rich.style.Style(bold=True, dim=True)),
                style=rich.style.Style(color="yellow"),
            )
            table.add_column(Text("Name", style=rich.style.Style(bold=True, dim=True)))
            table.add_column(
                Text("Ratio", style=rich.style.Style(bold=True, dim=True)),
                justify="right",
            )

            for group_name, (base_name, ratios) in compares.items():
                table.add_row(group_name, f"[blue]{base_name}[/]", "[green]1[/]x")
                for other_name, ratio in ratios:
                    table.add_row("", f"[blue]{other_name}[/]", f"[red]{ratio:.2f}[/]x")
            yield table
