"""Subprocess helpers for consistent UTF-8 text-mode I/O, and for running Quarto."""

from __future__ import annotations

import os
import shlex
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import TypedDict


class TextModeKwargs(TypedDict):
    """Subprocess options for decoding child process output as UTF-8 text"""

    text: bool
    encoding: str
    errors: str


# Windows text-mode pipes default to the locale codec (e.g. cp1252). Quarto and
# Python pre-render scripts emit UTF-8, so parent readers must not rely on
# locale.getpreferredencoding(False).
TEXT_MODE_KWARGS: TextModeKwargs = {
    "text": True,
    "encoding": "utf-8",
    "errors": "replace",
}


QUARTO_ARGS_ENV = "GREAT_DOCS_QUARTO_ARGS"
"""Environment variable giving extra arguments for each `quarto render` of the site"""


def join_quarto_args(quarto_args: str | Sequence[str]) -> str:
    """
    Turn extra `quarto render` arguments into the text of `GREAT_DOCS_QUARTO_ARGS`

    Parameters
    ----------
    quarto_args
        The arguments, as one string (`"--jobs 8 --keep-going"`) or a list of them.

    Returns
    -------
    :
        The arguments as one string.

    Raises
    ------
    ValueError
        If the string has unbalanced quotes.
    """
    if isinstance(quarto_args, str):
        shlex.split(quarto_args)  # Fail fast on unbalanced quotes
        return quarto_args
    return shlex.join(quarto_args)


def quarto_render_command(*args: str, env: Mapping[str, str] | None = None) -> list[str]:
    """
    Build a `quarto render` command for the site, with any extra arguments asked for

    The extra arguments come from `GREAT_DOCS_QUARTO_ARGS` in `env` (by default, the current
    environment), which `great-docs build --quarto-args` sets. They travel in the environment
    because every render of the site, including parallel and versioned ones, is already given it.

    Parameters
    ----------
    *args
        Arguments to put after `quarto render`, such as the path to render.
    env
        The environment Quarto will run in.

    Returns
    -------
    :
        The command, as a list.
    """
    if env is None:
        env = os.environ
    extra = shlex.split(env.get(QUARTO_ARGS_ENV, ""))
    return ["quarto", "render", *args, *extra]


@contextmanager
def quarto_args_set(quarto_args: str | Sequence[str] | None) -> Iterator[None]:
    """
    Set `GREAT_DOCS_QUARTO_ARGS` for the duration of a build, then restore it

    Every environment a build gives Quarto starts from this process's, so setting it here
    reaches each render of the site, including parallel and versioned ones.

    Parameters
    ----------
    quarto_args
        The arguments, as one string or a list. `None` leaves the environment as it is.
    """
    if quarto_args is None:
        yield
        return
    previous = os.environ.get(QUARTO_ARGS_ENV)
    os.environ[QUARTO_ARGS_ENV] = join_quarto_args(quarto_args)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(QUARTO_ARGS_ENV, None)
        else:
            os.environ[QUARTO_ARGS_ENV] = previous
