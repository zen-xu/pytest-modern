import sys

from pathlib import Path

import pytest

from _pytest.main import Session
from _pytest.terminal import _plugin_nameversions
from rich.columns import Columns
from rich.console import Group


def generate_header_group(session: Session) -> Group:
    columns = [
        _generate_sysinfo_col(),
        _generate_plugins_col(session),
        _generate_root_col(session),
        _generate_inifile_col(session),
    ]

    return Group(*columns)


def _generate_sysinfo_col() -> Columns:
    column = Columns(
        [
            f"platform [green]{sys.platform}",
            f"pytest [cyan]{pytest.__version__}",
            f"python [cyan]{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        ]
    )

    pypy_version_info = getattr(sys, "pypy_version_info", None)
    if pypy_version_info is not None:
        column.add_renderable(f"pypy [cyan]{'.'.join(map(str, pypy_version_info[:3]))}")

    return column


def _generate_root_col(session: Session) -> Columns:
    return Columns([f"root [magenta][bold]{session.config.rootpath}"])


def _generate_inifile_col(session: Session) -> Columns:
    return Columns(
        [
            f"configfile [magenta][bold]{Path(session.config.inifile).relative_to(session.config.rootpath)}"  # type: ignore
        ]
    )


def _generate_plugins_col(session: Session) -> Columns:
    plugins = session.config.pluginmanager.list_plugin_distinfo()
    return Columns(
        [
            f"plugins [cyan]{', '.join(_plugin_nameversions(plugins))}",
        ]
        if plugins
        else []
    )
