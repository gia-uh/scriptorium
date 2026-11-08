"""A theme loaded from a directory outside scriptorium's themes."""

import pytest

from scriptorium.render import render_html
from scriptorium.theme import load_theme


def _theme(root, extends="report", css=".mine{color:teal}"):
    root.mkdir(parents=True)
    (root / "theme.yml").write_text(f"name: mine\nextends: {extends}\nvars:\n  accent: '#123456'\n"
                                    "components:\n  stamp: {}\n", encoding="utf-8")
    (root / "styles.css").write_text(css, encoding="utf-8")
    (root / "components").mkdir()
    (root / "components" / "stamp.html").write_text('<div class="stamp">{{content}}</div>', encoding="utf-8")
    return root


def test_a_directory_theme_extends_a_builtin(tmp_path):
    root = _theme(tmp_path / "mine")
    theme = load_theme(str(root))
    assert ".mine{color:teal}" in theme.css
    assert theme.vars["accent"] == "#123456"
    assert "kpi" in theme.components and "stamp" in theme.components
    assert theme.name == str(root.resolve())


def test_a_relative_theme_resolves_against_the_document_directory(tmp_path, monkeypatch):
    _theme(tmp_path / "doc" / "themes" / "mine")
    monkeypatch.chdir(tmp_path)
    html, _ = render_html("---\ntheme: ./themes/mine\n---\n\n::: stamp\nhi\n:::\n", cwd=str(tmp_path / "doc"))
    assert '<div class="stamp">' in html and ".mine{color:teal}" in html


def test_extends_by_path_resolves_against_the_naming_theme(tmp_path):
    _theme(tmp_path / "parent", css=".parent{color:red}")
    child = _theme(tmp_path / "child", extends="../parent", css=".child{color:blue}")
    css = load_theme(str(child)).css
    assert css.index(".parent{") < css.index(".child{")


def test_a_bare_name_is_still_a_builtin(tmp_path, monkeypatch):
    _theme(tmp_path / "report", css=".impostor{}")
    monkeypatch.chdir(tmp_path)
    assert ".impostor" not in load_theme("report").css


def test_a_missing_theme_directory_names_the_path(tmp_path):
    with pytest.raises(FileNotFoundError, match="nowhere"):
        load_theme(str(tmp_path / "nowhere"))
