"""Tests for the fork's options: raw Quarto settings, quartodoc and `styles`"""

import io
from pathlib import Path

import pytest

from great_docs import GreatDocs
from great_docs._build import reference
from great_docs._build.log import BuildLog
from great_docs._reference import quartodoc
from great_docs._website import quarto_overrides
from tests.support import StubRemote, make_run, prepare_build_directory, write_config, write_pyproject

# --- Raw Quarto settings ------------------------------------------------------


def test_merge_rules():
    config = {
        "format": {"html": {"theme": "flatly", "toc": True, "css": ["a.css"]}},
        "website": {"title": "Pkg"},
    }
    overrides = {
        "format": {"html": {"theme": {"light": ["flatly", "custom.scss"]}, "toc": None, "css": ["b.css"]}},
        "execute": {"freeze": "auto"},
    }
    result = quarto_overrides.merge(config, overrides)

    assert result == {
        "format": {"html": {"theme": {"light": ["flatly", "custom.scss"]}, "css": ["b.css"]}},
        "website": {"title": "Pkg"},
        "execute": {"freeze": "auto"},
    }
    assert config["format"]["html"]["toc"] is True  # not mutated


def _generated() -> dict:
    return {
        "project": {"type": "website"},
        "website": {"title": "mypkg", "page-footer": {"left": "GD"}},
        "format": {"html": {"theme": "flatly", "toc-depth": 2}},
    }


def test_quarto_block_merges_into_generated_config(tmp_path):
    config = write_config(
        tmp_path,
        "quarto:\n"
        "  format:\n"
        "    html:\n"
        "      theme:\n"
        "        light: [flatly, custom.scss]\n"
        "        dark: [darkly, custom.scss]\n"
        "      mainfont: Source Sans Pro\n"
        "  website:\n"
        "    page-footer: null\n",
    )
    result = _generated()

    assert quarto_overrides.apply(result, config, tmp_path) == ["great-docs.yml `quarto`"]
    assert result["format"]["html"] == {
        "theme": {
            "light": ["flatly", "great-docs.scss", "custom.scss"],
            "dark": ["darkly", "great-docs.scss", "custom.scss"],
        },
        "toc-depth": 2,
        "mainfont": "Source Sans Pro",
    }
    assert result["website"] == {"title": "mypkg"}


def test_user_file_merges_last(tmp_path):
    config = write_config(tmp_path, "quarto:\n  format:\n    html:\n      toc-depth: 3\n")
    (tmp_path / "_quarto.user.yml").write_text(
        "format:\n  html:\n    toc-depth: 4\nwebsite:\n  title: Custom\n", encoding="utf-8"
    )
    result = _generated()

    assert quarto_overrides.apply(result, config, tmp_path) == [
        "great-docs.yml `quarto`",
        "_quarto.user.yml",
    ]
    assert result["format"]["html"]["toc-depth"] == 4
    assert result["website"]["title"] == "Custom"


def test_no_overrides_leaves_config_untouched(tmp_path):
    config = write_config(tmp_path, "display_name: Pkg\n")
    result = _generated()

    assert quarto_overrides.apply(result, config, tmp_path) == []
    assert result == _generated()


def test_quarto_block_must_be_mapping(tmp_path):
    config = write_config(tmp_path, "quarto: [not, a, mapping]\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        quarto_overrides.apply(_generated(), config, tmp_path)


def test_user_file_must_be_mapping(tmp_path):
    config = write_config(tmp_path, "")
    (tmp_path / "_quarto.user.yml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a mapping"):
        quarto_overrides.apply(_generated(), config, tmp_path)


def test_theme_override_keeps_great_docs_scss(tmp_path):
    config = write_config(
        tmp_path,
        "quarto:\n  format:\n    html:\n      theme:\n        light: [cosmo, a.scss]\n        dark: cosmo\n",
    )
    result = _generated()
    quarto_overrides.apply(result, config, tmp_path)
    assert result["format"]["html"]["theme"] == {
        "light": ["cosmo", "great-docs.scss", "a.scss"],
        "dark": ["cosmo", "great-docs.scss"],
    }


# --- quartodoc ---------------------------------------------------------------

QUARTODOC_YML = (
    "quartodoc:\n"
    "  style: pkgdown\n"
    "  sections:\n"
    "    - title: Greetings\n"
    "      desc: Ways to say hello\n"
    "      contents:\n"
    "        - hello\n"
)

HELLO = (
    '"""Demo."""\n\n__all__ = ["hello"]\n\n\ndef hello(name: str) -> str:\n'
    '    """Say hello.\n\n    Parameters\n    ----------\n'
    '    name\n        Who to greet.\n    """\n    return name\n'
)


def _quarto_config() -> dict:
    return {
        "project": {"type": "website"},
        "website": {"navbar": {"left": []}, "sidebar": []},
        "format": {"html": {"theme": "flatly"}},
        "api-reference": {"package": "mypkg", "dir": "reference", "sections": []},
    }


def _package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(HELLO, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    return build_dir


def _settings(yml: str) -> dict:
    import yaml

    return yaml.safe_load(yml)["quartodoc"]


def test_configure():
    config = _quarto_config()
    quartodoc.configure(config, _settings(QUARTODOC_YML + "  dir: api\n"))

    qd = config["quartodoc"]
    assert qd["package"] == "mypkg"
    assert qd["dir"] == "api"
    assert qd["sidebar"] == {"file": "_quartodoc-sidebar.yml", "id": "reference"}
    assert qd["sections"][0]["title"] == "Greetings"


def test_build(tmp_path, monkeypatch):
    pytest.importorskip("quartodoc")
    build_dir = _package(tmp_path, monkeypatch)
    config = _quarto_config()
    config["website"]["navbar"]["left"] = [{"text": "Reference", "href": "reference/index.qmd"}]
    config["website"]["sidebar"] = [{"id": "reference", "contents": ["reference/index.qmd"]}]
    quartodoc.configure(config, _settings(QUARTODOC_YML + "  dir: api\n"))
    uris, claims = quartodoc.build(config, build_dir, ["hello"])

    assert "Say hello." in (build_dir / "api" / "hello.qmd").read_text()
    assert config["website"]["navbar"]["left"] == [{"text": "Reference", "href": "api/index.qmd"}]
    assert config["website"]["sidebar"] == [
        {
            "id": "reference",
            "contents": ["api/index.qmd", {"section": "Greetings", "contents": ["api/hello.qmd"]}],
        }
    ]

    # Interlinks and llms.txt use quartodoc's pages
    from great_docs._interlinks.sphinx_inventory import decode

    inventory = decode((build_dir / "objects.inv").read_bytes())
    assert any(e.name == "mypkg.hello" for e in inventory.entries)
    assert ("hello", "mypkg.hello") in claims.claimed
    assert quartodoc.page_url(uris, "mypkg", "hello") == uris["mypkg.hello"]
    assert quartodoc.page_url(uris, "mypkg", "hello.missing") is None
    assert quartodoc.page_url(uris, "mypkg", "nothing") is None


def test_build_claims_reexported_names(tmp_path, monkeypatch):
    """`mypkg.greet.Greeter` is also `mypkg.Greeter`, so a `pkg.` alias reaches it."""
    pytest.importorskip("quartodoc")
    build_dir = _package(tmp_path, monkeypatch)
    pkg = tmp_path / "mypkg"
    (pkg / "__init__.py").write_text(
        '"""Demo."""\n\nfrom .greet import Greeter\n\n__all__ = ["Greeter"]\n', encoding="utf-8"
    )
    (pkg / "greet.py").write_text(
        '"""Greetings."""\n\n\nclass Greeter:\n    """Greets."""\n\n'
        '    def wave(self):\n        """Wave."""\n\n\ndef _private():\n    """No."""\n',
        encoding="utf-8",
    )
    config = _quarto_config()
    config["website"]["sidebar"] = [{"id": "reference", "contents": ["reference/index.qmd"]}]
    quartodoc.configure(
        config, _settings("quartodoc:\n  sections:\n    - title: All\n      contents:\n        - greet\n")
    )
    _, claims = quartodoc.build(config, build_dir, ["Greeter"])

    assert ("mypkg.Greeter", "mypkg.greet.Greeter") in claims.claimed
    assert ("mypkg.Greeter.wave", "mypkg.greet.Greeter.wave") in claims.claimed
    assert ("Greeter.wave", "mypkg.greet.Greeter.wave") in claims.claimed


def test_api_step_uses_quartodoc(tmp_path, monkeypatch):
    """The build's API reference step runs quartodoc, and llms.txt links to its pages."""
    pytest.importorskip("quartodoc")
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(HELLO, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    write_pyproject(tmp_path, "mypkg")
    write_config(tmp_path, QUARTODOC_YML)
    docs = GreatDocs(project_path=str(tmp_path))
    docs._remote = StubRemote()
    monkeypatch.chdir(tmp_path)
    run = make_run(docs)
    prepare_build_directory(docs, run)
    assert run.quarto_config["quartodoc"]["package"] == "mypkg"

    outcome, ref = reference.api(run, docs._config, docs.layout, BuildLog(stream=io.StringIO()))

    assert outcome == "API reference generated with quartodoc"
    assert ref is None
    assert run.quartodoc_uris is not None and "mypkg.hello" in run.quartodoc_uris
    assert ("hello", "mypkg.hello") in run.quartodoc_claims.claimed
    llms = (docs.layout.build_dir / "llms.txt").read_text()
    assert f"- [hello]({run.quartodoc_uris['mypkg.hello']})" in llms


def test_llms_txt_lists_only_what_quartodoc_documents(tmp_path):
    from great_docs._website.ai_agents import llms_txt

    write_pyproject(tmp_path, "mypkg")
    write_config(tmp_path, "")
    docs = GreatDocs(project_path=str(tmp_path))
    docs.layout.build_dir.mkdir(parents=True)
    api_block = {
        "package": "mypkg",
        "sections": [
            {"title": "Documented", "contents": ["hello"]},
            {"title": "Left out", "contents": ["other"]},
        ],
    }
    uris = {"mypkg.hello": "reference/hello.html#mypkg.hello"}
    path = llms_txt.write_index(
        docs.layout,
        api_block,
        {},
        site_url=None,
        report=lambda _: None,
        page_url=lambda name, _page: quartodoc.page_url(uris, "mypkg", name),
    )

    llms = path.read_text()
    assert "- [hello](reference/hello.html#mypkg.hello)" in llms
    assert "other" not in llms
    assert "Left out" not in llms


# --- styles ------------------------------------------------------------------


@pytest.mark.parametrize("styles, flag", [("all", "true"), ("widgets", "false")])
def test_styles_sets_the_content_styles_flag(tmp_path, monkeypatch, styles, flag):
    write_pyproject(tmp_path, "mypkg")
    write_config(tmp_path, f"styles: {styles}\nreference: false\n")
    docs = GreatDocs(project_path=str(tmp_path))
    docs._remote = StubRemote()
    monkeypatch.chdir(tmp_path)
    prepare_build_directory(docs, make_run(docs))
    scss = (docs.layout.build_dir / "great-docs.scss").read_text()
    assert f"$gd-content-styles: {flag} !default;" in scss


def test_styles_must_be_all_or_widgets(tmp_path):
    with pytest.raises(ValueError, match="must be"):
        _ = write_config(tmp_path, "styles: none\n").styles
