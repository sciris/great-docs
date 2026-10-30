"""Tests for passing extra arguments to `quarto render`."""

from __future__ import annotations

import pytest

from great_docs._subprocess import QUARTO_ARGS_ENV, join_quarto_args, quarto_render_command


def test_quarto_render_command_without_extra_args():
    """With nothing asked for, the command is a plain `quarto render`."""
    assert quarto_render_command(env={}) == ["quarto", "render"]
    assert quarto_render_command("ref", "--use-freezer", env={}) == [
        "quarto",
        "render",
        "ref",
        "--use-freezer",
    ]


def test_quarto_render_command_adds_extra_args():
    """Extra arguments from the environment go after the command's own."""
    env = {QUARTO_ARGS_ENV: "--jobs 4 --metadata 'title=A B'"}
    assert quarto_render_command("ref", env=env) == [
        "quarto",
        "render",
        "ref",
        "--jobs",
        "4",
        "--metadata",
        "title=A B",
    ]


def test_quarto_render_command_reads_the_environment(monkeypatch: pytest.MonkeyPatch):
    """Without an `env`, the current environment is used."""
    monkeypatch.setenv(QUARTO_ARGS_ENV, "--keep-going")
    assert quarto_render_command() == ["quarto", "render", "--keep-going"]


def test_join_quarto_args():
    """A string is kept as it is and a list is quoted, so both split back the same way."""
    assert join_quarto_args("--jobs 4") == "--jobs 4"
    args = ["--metadata", "title=A B"]
    assert quarto_render_command(env={QUARTO_ARGS_ENV: join_quarto_args(args)})[2:] == args
    with pytest.raises(ValueError):
        join_quarto_args("--metadata 'title")
