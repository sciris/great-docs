"""
Raw Quarto settings that override the generated `_quarto.yml`

The `quarto` block of great-docs.yml merges into the site's Quarto configuration first, then
a `_quarto.user.yml` file beside great-docs.yml, if present. They merge just before the
configuration is written, after every other step has changed it, so the user's settings win.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yaml12 import read_yaml

from .quarto_defaults import _with_great_docs_theme  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from pathlib import Path

    from ..config import Config

__all__ = ["USER_FILE", "apply", "merge"]

USER_FILE = "_quarto.user.yml"
"""The file beside great-docs.yml whose settings merge into `_quarto.yml` last"""


def apply(quarto_config: dict[str, Any], config: Config, config_dir: Path) -> list[str]:
    """
    Merge the user's raw Quarto settings into the site's Quarto configuration

    A replaced theme keeps great-docs' stylesheet, which its widgets need, placed before the
    user's own stylesheets so theirs win.

    Parameters
    ----------
    quarto_config
        The site's Quarto configuration; updated in place.
    config
        The project's configuration, with its `quarto` block.
    config_dir
        The directory holding great-docs.yml, where `_quarto.user.yml` is looked for.

    Returns
    -------
    :
        The sources that were applied, for the build log.

    Raises
    ------
    ValueError
        If `_quarto.user.yml` doesn't hold a mapping.
    """
    layers: list[tuple[str, dict[str, Any]]] = []
    settings = getattr(config, "quarto", None)  # Absent from configurations made by hand
    if settings:
        layers.append(("great-docs.yml `quarto`", dict(settings)))

    user_yml = config_dir / USER_FILE
    if user_yml.is_file():
        with open(user_yml, encoding="utf-8") as f:
            overlay = read_yaml(f)
        if overlay is not None and not isinstance(overlay, dict):
            raise ValueError(f"{USER_FILE} must contain a mapping of `_quarto.yml` settings")
        if overlay:
            layers.append((USER_FILE, overlay))

    if not layers:
        return []

    merged = quarto_config
    for _, overrides in layers:
        merged = merge(merged, overrides)
    html = merged.get("format", {}).get("html", {})
    if theme := html.get("theme"):
        if isinstance(theme, dict):
            html["theme"] = {mode: _with_great_docs_theme(entry) for mode, entry in theme.items()}
        else:
            html["theme"] = _with_great_docs_theme(theme)
    quarto_config.clear()
    quarto_config.update(merged)
    return [name for name, _ in layers]


def merge(config: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """
    Deep merge user overrides into a Quarto configuration

    Mappings present on both sides merge key by key; any other value (a list, a scalar)
    replaces the original; a `None` value removes the key. Neither argument is mutated.

    Parameters
    ----------
    config
        The generated Quarto configuration.
    overrides
        The user's settings, which take precedence.

    Returns
    -------
    :
        The merged configuration.
    """
    result = dict(config)
    for key, value in overrides.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result
