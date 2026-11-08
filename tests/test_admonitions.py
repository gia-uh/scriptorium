"""Admonitions and tabs: base-theme components for every output."""

import shutil
import subprocess

import pytest

from scriptorium.render import render_html

SRC = """---
title: The Book
---

# One

::: note
Plain note.
:::

::: warning collapse {title="Careful"}
Body **bold**.
:::

:::: tabs
::: tab {title="pip"}
```bash
pip install purely
```
:::
::: tab {title="uv"}
```bash
uv add purely
```
:::
::::

After the tabs.
"""


def _html(src=SRC) -> str:
    r = render_html(src)
    return r[0] if isinstance(r, tuple) else r


def test_an_admonition_without_a_title_does_not_take_the_documents():
    html = _html()
    assert '<div class="admonition note "><p class="admonition-title"></p>' in html
    assert '<div class="admonition warning collapse"><p class="admonition-title">Careful</p>' in html


def test_four_colons_hold_three_colon_blocks():
    html = _html()
    body = html[html.index("<body"):]
    assert "::::" not in body and body.count('<section class="tab">') == 2
    assert body.index('class="tabs') < body.index("After the tabs.")


def test_a_code_fence_inside_a_component_is_highlighted():
    html = _html()
    assert '<div class="codeblock" data-lang="bash"><span class="code-src"><div class="hl">' in html


def test_every_kind_has_a_default_title_in_english_and_spanish():
    css = (__import__("scriptorium.theme", fromlist=["THEMES_DIR"]).THEMES_DIR / "base" / "styles.css").read_text()
    for kind, en, es in [("note", "Note", "Nota"), ("tip", "Tip", "Consejo"), ("info", "Info", "Información"),
                         ("warning", "Warning", "Advertencia"), ("danger", "Danger", "Peligro"),
                         ("example", "Example", "Ejemplo")]:
        assert f'.admonition.{kind} .admonition-title:empty::before {{ content:"{en}"; }}' in css
        assert f':lang(es) .admonition.{kind} .admonition-title:empty::before {{ content:"{es}"; }}' in css


@pytest.mark.skipif(not shutil.which("pdftotext"), reason="needs pdftotext")
def test_the_pdf_prints_every_tab_and_the_open_collapsed_note(tmp_path):
    pytest.importorskip("weasyprint")
    from scriptorium.galley import render_pdf
    out = tmp_path / "a.pdf"
    render_pdf(SRC, str(out), execute=False)
    text = subprocess.run(["pdftotext", str(out), "-"], capture_output=True, text=True).stdout
    for want in ["Note", "Plain note.", "Careful", "Body bold.", "pip", "pip install purely", "uv add purely"]:
        assert want in text, want
