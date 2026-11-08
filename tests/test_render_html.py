import pytest

from scriptorium.render import prepare, render_html


DOC = """---
theme: book
---

# Embeddings

Words are symbols.[^a] Math $x^2$ too.

1. one

2. two

::: note
inside
:::

[^a]: A footnote body.
"""


def test_render_html_returns_a_whole_document():
    html, warnings = render_html(DOC, execute=False)
    assert html.startswith("<!DOCTYPE html>")
    assert "<style>" in html and "</body></html>" in html
    assert '<h1 id="embeddings">Embeddings</h1>' in html
    assert 'class="footnote-ref"' in html          # preprocessors ran
    assert "<svg" in html                           # math rendered
    assert '<div class="admonition note ' in html   # component rendered (note is an admonition)
    assert warnings == []


def test_render_html_keeps_raw_html_blocks_in_order():
    src = ('# T\n\nA.\n\n<span class="m" data-b="1"></span>\n\n'
           'B.\n\n<span class="m" data-b="2"></span>\n')
    html, _ = render_html(src, execute=False)
    a, m1, b, m2 = (html.index(s) for s in ("<p>A.</p>", 'data-b="1"', "<p>B.</p>", 'data-b="2"'))
    assert a < m1 < b < m2


def test_render_html_drops_html_comments():
    html, _ = render_html("# T\n\nA.\n\n<!-- @alex\nnote\n-->\n", execute=False)
    assert "@alex" not in html


def test_render_html_refuses_deck_themes():
    with pytest.raises(ValueError, match="deck"):
        render_html("---\ntheme: deck\n---\n\n# Slide\n", execute=False)


def test_prepare_exposes_units_and_theme():
    p = prepare(DOC, execute=False)
    assert p.theme.name == "book"
    assert any(u.heading == "Embeddings" for u in p.units)


import subprocess
import sys


def _run_without_weasyprint(code: str) -> subprocess.CompletedProcess:
    # sys.modules[name] = None makes `import name` raise ImportError.
    prelude = "import sys; sys.modules['weasyprint'] = None\n"
    return subprocess.run([sys.executable, "-c", prelude + code],
                          capture_output=True, text=True)


def test_render_html_works_without_weasyprint():
    r = _run_without_weasyprint(
        "from scriptorium.render import render_html\n"
        "html, _ = render_html('# Hi\\n\\nText.\\n', execute=False)\n"
        "print('ok' if '<h1' in html else 'bad')")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "ok"


def test_render_pdf_without_weasyprint_names_the_extra(tmp_path):
    r = _run_without_weasyprint(
        "from scriptorium.galley import render_pdf\n"
        f"render_pdf('# Hi\\n', {str(tmp_path / 'x.pdf')!r})")
    assert r.returncode != 0
    assert "scriptorium[pdf]" in r.stderr


def test_cli_render_html_without_weasyprint(tmp_path):
    src = tmp_path / "doc.md"
    src.write_text("# Hi\n\nText.\n")
    r = _run_without_weasyprint(
        "from scriptorium.cli import main\n"
        f"raise SystemExit(main(['render', {str(src)!r}, '--html', '--no-execute']))")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "doc.html").read_text().startswith("<!DOCTYPE html>")


# --- frozen mode: show cached outputs, never execute -------------------------

RUN_DOC = """# T

```python {run}
import pathlib
pathlib.Path("ran.txt").write_text("x")
print("hello from the block")
```
"""


def test_frozen_mode_serves_the_cache_without_running(tmp_path):
    render_html(RUN_DOC, cwd=str(tmp_path))                 # a real run fills the cache
    (tmp_path / "ran.txt").unlink()
    html, warnings = render_html(RUN_DOC, cwd=str(tmp_path), frozen=True)
    assert "<p>hello from the block</p>" in html     # the output, not just the source
    assert not (tmp_path / "ran.txt").exists()
    assert warnings == []


def test_frozen_mode_never_runs_an_uncached_block(tmp_path):
    html, warnings = render_html(RUN_DOC, cwd=str(tmp_path), frozen=True)
    assert not (tmp_path / "ran.txt").exists()
    assert "<p>hello from the block</p>" not in html
    assert any("not run yet" in w for w in warnings)


def test_frozen_mode_never_tangles(tmp_path):
    src = "# T\n\n```python {export=out.py}\nx = 1\n```\n"
    render_html(src, cwd=str(tmp_path), frozen=True)
    assert not (tmp_path / "out.py").exists()


def test_execute_settings_reach_a_project(tmp_path):
    from scriptorium.project import load
    (tmp_path / "ch.md").write_text("# T\n")
    (tmp_path / "scriptorium.yaml").write_text(
        "files: [ch.md]\nexecute:\n  timeout: 600\n")
    proj = load(tmp_path / "scriptorium.yaml")
    p = prepare(proj.src, cwd=str(tmp_path), project_meta=proj.meta)
    assert p.env.timeout == 600
