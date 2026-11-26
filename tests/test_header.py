from __future__ import annotations

import pytest


pytest_plugins = ["pytester"]


def test_inifile_outside_rootdir(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Test Scope:
        Session header when the config file lies outside the rootdir.
    Preconditions:
        A ``root`` directory and a separate ``outside`` directory containing a
        ``pytest.ini`` and one passing test. Colour output is disabled.
    Events:
        Run pytest in a subprocess with ``-c`` pointing at the outside
        ``pytest.ini`` and ``--rootdir`` pointing at ``root``.
    Evaluate:
        stdout and stderr contain no ``INTERNALERROR`` and the exit code is
        ``OK``.
    """
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")
    rootdir = pytester.mkdir("root")
    outside = pytester.mkdir("outside")
    (outside / "pytest.ini").write_text("[pytest]\n")
    (outside / "test_trivial.py").write_text("def test_ok():\n    assert True\n")
    result = pytester.runpytest_subprocess(
        "-c",
        str(outside / "pytest.ini"),
        f"--rootdir={rootdir}",
        str(outside / "test_trivial.py"),
    )
    assert "INTERNALERROR" not in result.stdout.str() + result.stderr.str()
    assert result.ret == pytest.ExitCode.OK
