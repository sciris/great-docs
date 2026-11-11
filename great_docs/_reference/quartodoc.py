"""
Write the API reference with quartodoc instead of great-docs

With a `quartodoc` block in great-docs.yml, great-docs still analyzes the package (for
llms.txt and the like), but quartodoc writes the reference pages. The site then links to
quartodoc's pages: the reference sidebar is quartodoc's, links to the reference index follow
its `dir`, and interlinks and llms.txt use its inventory.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from .._interlinks import AliasClaims

__all__ = ["SIDEBAR", "build", "configure", "page_url"]

SIDEBAR = "_quartodoc-sidebar.yml"
"""The file quartodoc writes the API reference sidebar to, unless configured"""


def configure(quarto_config: dict[str, Any], settings: Mapping[str, Any]) -> None:
    """
    Add the `quartodoc` block to the site's Quarto configuration

    `package` defaults to the API reference's package and `dir` to "reference". quartodoc is
    always asked for a sidebar (with any of the user's `sidebar` options), which `build` puts
    in the site's configuration.

    Parameters
    ----------
    quarto_config
        The site's Quarto configuration, with its `api-reference` block; updated in place.
    settings
        The `quartodoc` block of great-docs.yml.
    """
    block = dict(settings)
    block.setdefault("package", quarto_config["api-reference"]["package"])
    block.setdefault("dir", "reference")
    sidebar = block.get("sidebar")
    sidebar = {"file": sidebar} if isinstance(sidebar, str) else dict(sidebar or {})
    sidebar.setdefault("file", SIDEBAR)
    sidebar.setdefault("id", "reference")
    block["sidebar"] = sidebar
    quarto_config["quartodoc"] = block
    print(f"Using quartodoc for the API reference pages of package: {block['package']}")


def build(
    quarto_config: dict[str, Any], build_dir: Path, exports: list[str] | None
) -> tuple[dict[str, str], AliasClaims]:
    """
    Write the API reference pages with quartodoc, and point the site at them

    Writes `objects.inv` from quartodoc's inventory for interlinks, swaps quartodoc's sidebar
    in for the reference sidebar, and moves links to the reference index to quartodoc's `dir`.

    Parameters
    ----------
    quarto_config
        The site's Quarto configuration, with its `quartodoc` block; updated in place.
    build_dir
        The build directory, where quartodoc writes its pages.
    exports
        The names the package exports, so that objects it re-exports from submodules claim
        their short names (`package.name`) too.

    Returns
    -------
    :
        The page of each documented object, by full name, and the short names they claim.

    Raises
    ------
    RuntimeError
        If quartodoc isn't installed.
    """
    try:
        from quartodoc import Builder
    except ImportError:
        raise RuntimeError(
            "The `quartodoc` option in great-docs.yml needs quartodoc installed; "
            "install it with `pip install great-docs[quartodoc]`"
        ) from None
    import sphobjinv as soi
    from yaml12 import read_yaml

    from .._interlinks import AliasClaims

    builder = Builder.from_quarto_config(quarto_config)
    with contextlib.chdir(build_dir):  # quartodoc writes relative to the project
        builder.build()

    # Interlinks read the inventory as objects.inv; llms.txt links by URI
    inventory = builder.create_inventory(builder.items)
    _ = (build_dir / "objects.inv").write_bytes(soi.compress(inventory.data_file()))
    uris = {obj.name: obj.uri.replace("$", obj.name) for obj in inventory.objects}

    website = quarto_config.setdefault("website", {})
    ref_dir = str(builder.dir).strip("/")
    if ref_dir != "reference":
        _replace_values(website, "reference/index.qmd", f"{ref_dir}/index.qmd")

    with open(build_dir / builder.sidebar["file"], encoding="utf-8") as f:
        qd_sidebar = (read_yaml(f) or {})["website"]["sidebar"][0]
    sidebars = website.setdefault("sidebar", [])
    for i, sidebar in enumerate(sidebars):
        if isinstance(sidebar, dict) and sidebar.get("id") == qd_sidebar["id"]:
            sidebars[i] = qd_sidebar
            break
    else:
        sidebars.append(qd_sidebar)

    return uris, _claims(builder.package, uris, inventory.objects, set(exports or ()))


def page_url(uris: Mapping[str, str], package: str, name: str) -> str | None:
    """
    Find the page quartodoc wrote for an object named in the API reference config

    Parameters
    ----------
    uris
        The page of each object quartodoc documented, by full name.
    package
        The documented package.
    name
        The object's name, as listed in the API reference config.

    Returns
    -------
    :
        Its page: that of the full name, else of the shortest name ending in it. `None` if
        quartodoc doesn't document it.
    """
    if f"{package}.{name}" in uris:
        return uris[f"{package}.{name}"]
    matches = sorted((n for n in uris if n.endswith(f".{name}")), key=len)
    return uris[matches[0]] if matches else None


def _claims(package: str, uris: Mapping[str, str], objects: Any, exports: set[str]) -> AliasClaims:
    """
    Collect the short names quartodoc's documented objects claim

    Each object claims its own name; a class member, `Class.member`; and an object the
    package re-exports from a submodule, `package.name` (with its members,
    `package.Class.member`).
    """
    from .._interlinks import AliasClaims

    classes = {obj.name for obj in objects if obj.role == "class"}
    modules = {obj.name for obj in objects if obj.role == "module"} - {package}

    def reexported(name: str) -> str | None:
        parent, _, short = name.rpartition(".")
        return f"{package}.{short}" if parent in modules and short in exports else None

    claimed = []
    for name in uris:
        parent, _, short = name.rpartition(".")
        claimed.append((short, name))
        if parent in classes:
            claimed.append((f"{parent.rpartition('.')[2]}.{short}", name))
            if reexported_class := reexported(parent):
                claimed.append((f"{reexported_class}.{short}", name))
        elif reexported_name := reexported(name):
            claimed.append((reexported_name, name))
    return AliasClaims(claimed=tuple(sorted(claimed)), published=frozenset(uris))


def _replace_values(node: Any, old: str, new: str) -> None:
    """Replace every string value `old` in a nested config with `new`, in place"""
    items = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else ()
    for key, value in list(items):
        if value == old:
            node[key] = new
        else:
            _replace_values(value, old, new)
