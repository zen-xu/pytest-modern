"""
This implementation is inspired by https://github.com/nicoddemus/pytest-rich/blob/main/src/pytest_rich/traceback.py
"""

from __future__ import annotations

import ast

from contextlib import suppress
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Generic
from typing import TypeVar

import rich.highlighter
import rich.padding

from _pytest._code.code import ExceptionChainRepr
from _pytest._code.code import ExceptionInfo
from _pytest._code.code import ReprEntry
from pygments.token import Comment
from pygments.token import Keyword
from pygments.token import Name
from pygments.token import Number
from pygments.token import Operator
from pygments.token import String
from pygments.token import Text as TextToken
from pygments.token import Token
from rich._loop import loop_last
from rich.console import Console
from rich.console import ConsoleOptions
from rich.console import RenderResult
from rich.console import group
from rich.highlighter import ReprHighlighter
from rich.style import Style
from rich.syntax import Syntax
from rich.syntax import SyntaxTheme
from rich.text import Text
from rich.theme import Theme
from rich.traceback import PathHighlighter


if TYPE_CHECKING:
    from collections.abc import Sequence

_ErrT = TypeVar("_ErrT")


@dataclass
class ModernErrorRepr(Generic[_ErrT]):
    nodeid: str
    error: _ErrT
    extra_lines: int = 3
    theme: str = "ansi_dark"
    no_syntax: bool = False
    word_wrap: bool = True
    indent_guides: bool = True
    error_messages: list[str] = field(default_factory=list)
    code_cache: dict[str, str | None] = field(default_factory=dict)

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        theme = self.get_theme()
        token_style = theme.get_style_for_token

        traceback_theme = Theme(
            {
                "pretty": token_style(TextToken),
                "pygments.text": token_style(Token),
                "pygments.string": token_style(String),
                "pygments.function": token_style(Name.Function),
                "pygments.number": token_style(Number),
                "repr.indent": token_style(Comment) + Style(dim=True),
                "repr.str": token_style(String),
                "repr.brace": token_style(TextToken) + Style(bold=True),
                "repr.number": token_style(Number),
                "repr.bool_true": token_style(Keyword.Constant),
                "repr.bool_false": token_style(Keyword.Constant),
                "repr.none": token_style(Keyword.Constant),
                "scope.equals": token_style(Operator),
                "scope.key": token_style(Name),
                "scope.key.special": token_style(Name.Constant) + Style(dim=True),
            },
            inherit=False,
        )

        with console.use_theme(traceback_theme):
            yield rich.padding.Padding(self._render(self.error, options), (0, 0, 0, 2))

    @group()
    def _render(self, chain: _ErrT, options: ConsoleOptions) -> RenderResult:
        raise NotImplementedError

    @property
    def highlighter(self) -> rich.highlighter.Highlighter:
        return (
            ReprHighlighter()
            if not self.no_syntax
            else rich.highlighter.NullHighlighter()
        )

    def read_code(self, filename: str) -> str | None:
        """
        Read files and cache results on filename.

        Args:
            filename (str): Filename to read

        Returns:
            str: Contents of file
        """
        code = self.code_cache.get(filename)

        if not code:
            with suppress(OSError):
                code = Path(filename).read_text("utf-8", "replace")
            self.code_cache[filename] = code
        return code

    def get_funcname(self, lineno: int, filename: str) -> str:
        """
        Given a line number in a file, using `ast.parse` walk backwards
        until we find the function name.

        Args:
            lineno (int): Line number to start searching from
            filename (str): Filename to read

        Returns:
            str: Function name
        """
        if code := self.read_code(filename):
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.FunctionDef)
                    and node.end_lineno is not None
                    and node.lineno <= lineno <= node.end_lineno
                ):
                    return node.name
        return "???"

    def get_args(self, reprfuncargs: Sequence) -> Text:
        args = Text("")
        for arg in reprfuncargs:
            assert isinstance(arg[1], str)
            args.append(
                Text.assemble(
                    (arg[0], "name.variable"),
                    (" = ", "repr.equals"),
                    (arg[1], self.get_lexer("token")),
                )
            )
            if reprfuncargs[-1] != arg:
                args.append(Text(", "))
        return args

    def get_error_source(self, lines: Sequence[str]) -> str:
        for line in lines:
            if line.startswith(">"):
                return line.split(">")[1].strip()
        return ""

    def get_err_msgs(self, lines: Sequence[str]) -> list[str]:
        err_lines = []
        for line in lines:
            if line.startswith("E"):
                err_lines.append(line[1:].strip())
        return err_lines

    def get_theme(self) -> SyntaxTheme:
        """
        Get SyntaxTheme from `theme` class attribute.

        Theme is set via a string attribute option. We need to pass the
        string through Rich's Syntax class to get the actual SyntaxTheme
        object.
        """
        return Syntax.get_theme(self.theme)

    def get_lexer(self, lexer: str) -> str:
        return "text" if self.no_syntax else lexer


@dataclass
class ModernExceptionChainRepr(ModernErrorRepr[ExceptionChainRepr]):
    @group()
    def _render(
        self, chain: ExceptionChainRepr, options: ConsoleOptions
    ) -> RenderResult:
        path_highlighter = PathHighlighter()
        repr_highlighter = self.highlighter
        theme = self.get_theme()

        for _, entry in loop_last(chain.reprtraceback.reprentries):
            assert isinstance(entry, ReprEntry)

            assert entry.reprfileloc is not None
            filename = entry.reprfileloc.path
            lineno = entry.reprfileloc.lineno
            funcname = self.get_funcname(lineno, filename)
            message = entry.reprfileloc.message

            text = Text.assemble(
                path_highlighter(Text(filename, style="pygments.string")),
                (":", "pygments.text"),
                (str(lineno), "pygments.number"),
                " in ",
                (funcname, "pygments.function"),
                style="pygments.text",
            )
            yield text

            if entry.reprfuncargs is not None:
                args = self.get_args(entry.reprfuncargs.args)
                if args:
                    yield args

            if code := self.read_code(filename):
                syntax = Syntax(
                    code,
                    self.get_lexer("python"),
                    theme=theme,
                    line_numbers=True,
                    line_range=(
                        lineno - self.extra_lines,
                        lineno + self.extra_lines,
                    ),
                    highlight_lines={lineno},
                    word_wrap=self.word_wrap,
                    code_width=120,
                    indent_guides=self.indent_guides,
                    dedent=False,
                )
                yield ""
                yield syntax

            if message:
                line_pointer = "> " if options.legacy_windows else "❱ "
                yield ""
                yield Text.assemble(
                    (str(lineno), "pygments.number"),
                    ": ",
                    (message, self.get_lexer("traceback.exc_type")),
                )
                yield Text.assemble(
                    (line_pointer, Style(color="red")),
                    repr_highlighter(self.get_error_source(entry.lines)),
                )
                for err_msg in self.get_err_msgs(entry.lines):
                    self.error_messages.append(err_msg)
                    yield Text.assemble(
                        ("E ", Style(color="red")),
                        repr_highlighter(err_msg),
                    )


@dataclass
class ModernExceptionInfoRepr(ModernErrorRepr[ExceptionInfo]):
    @group()
    def _render(self, error: ExceptionInfo, options: ConsoleOptions) -> RenderResult:
        from rich.traceback import Traceback

        traceback = Traceback.from_exception(
            type(error.value),
            error.value,
            None,
            show_locals=False,
            locals_hide_sunder=True,
        )

        path_highlighter = PathHighlighter()
        theme = self.get_theme()

        for last, stack in loop_last(reversed(traceback.trace.stacks)):
            for frame in stack.frames:
                filename = frame.filename
                lineno = frame.lineno
                funcname = self.get_funcname(lineno, filename)

                text = Text.assemble(
                    path_highlighter(Text(filename, style="pygments.string")),
                    (":", "pygments.text"),
                    (str(lineno), "pygments.number"),
                    " in ",
                    (funcname, "pygments.function"),
                    style="pygments.text",
                )
                yield text

                if code := self.read_code(filename):
                    syntax = Syntax(
                        code,
                        self.get_lexer("python"),
                        theme=theme,
                        line_numbers=True,
                        line_range=(
                            lineno - self.extra_lines,
                            lineno + self.extra_lines,
                        ),
                        highlight_lines={lineno},
                        word_wrap=self.word_wrap,
                        code_width=120,
                        indent_guides=self.indent_guides,
                        dedent=False,
                    )
                    yield ""
                    yield syntax

            if last:
                yield Text(stack.exc_value, "red")
