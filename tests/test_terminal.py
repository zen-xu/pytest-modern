from __future__ import annotations

import pytest


pytest_plugins = ["pytester"]

PYTEST_MAJOR = int(pytest.__version__.split(".")[0])


@pytest.mark.skipif(PYTEST_MAJOR < 9, reason="built-in subtests need pytest>=9")
def test_passing_subtests_at_verbosity_zero(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Test Scope:
        Reporting of built-in subtests when subtest verbosity is 0.
    Preconditions:
        A project whose ini sets ``-v``, containing a unittest case with two
        passing subtests, a unittest case with one passing and one failing
        subtest, and a ``subtests`` fixture test with two passing subtests.
        Colour output is disabled.
    Events:
        Run pytest with ``-q`` in a subprocess.
    Evaluate:
        The output does not contain ``assert ''``, it shows the real subtest
        failure ``AssertionError: 1 != 0``, it reports ``3 passed, 1 failed``,
        and the exit code is ``TESTS_FAILED``.
    """
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")
    pytester.makeini("[pytest]\naddopts = -v\n")
    pytester.makepyfile(
        test_sub="""
        import unittest

        class T(unittest.TestCase):
            def test_all_pass(self):
                for i in range(2):
                    with self.subTest(i=i):
                        self.assertEqual(i, i)

            def test_one_fails(self):
                for i in range(2):
                    with self.subTest(i=i):
                        self.assertEqual(i, 0)
        """,
        test_fixture="""
        def test_all_pass(subtests):
            for i in range(2):
                with subtests.test(i=i):
                    assert i == i
        """,
    )
    result = pytester.runpytest_subprocess("-q")
    out = result.stdout.str()
    assert "assert ''" not in out
    assert "AssertionError: 1 != 0" in out
    result.stdout.fnmatch_lines(["*3 passed, 1 failed*"])
    assert result.ret == pytest.ExitCode.TESTS_FAILED
