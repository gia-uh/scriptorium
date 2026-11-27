"""A component that executes its body and scopes the headings it prints.

`::: proof` is the consumer: a verifier prints its own Markdown, the chapter
wraps that print in the component, and the derivation stays inside the chapter
instead of becoming the next chapter.
"""
from __future__ import annotations

import textwrap

from scriptorium.execute import ExecEnv
from scriptorium.parse import fill_toc, parse
from scriptorium.theme import load_theme


def _html(units) -> str:
    return "".join(u.html for u in units)


def test_a_run_fence_inside_proof_executes_and_splices_markdown(tmp_path):
    env = ExecEnv(cwd=str(tmp_path))
    src = textwrap.dedent(r"""
        ::: proof
        ```python {run echo=false}
        print("# Checked proof")
        print()
        print("Verified.")
        print()
        print("## Theorem")
        print()
        print("$$")
        print("P")
        print("$$")
        print()
        print("## Proof")
        print()
        print("**(1)** The first step.")
        print("**(2)** The second step.")
        print()
        print("## Conclusion")
        print()
        print("The conclusion follows from (2).")
        ```
        :::
    """)
    units = parse(src, env=env)
    html = _html(units)

    assert '<section class="proof">' in html
    # The exact stdout survives, in source order, as Markdown.
    order = ["Checked proof", "Verified.", "Theorem", "Proof",
             "The first step.", "The second step.", "Conclusion",
             "The conclusion follows from (2)."]
    positions = [html.index(token) for token in order]
    assert positions == sorted(positions)
    # The verifier's H1/H2 are scoped below the chapter and never H1.
    assert "<h1" not in html
    assert '<h3 id="checked-proof" class="unlisted">' in html
    assert '<h4 id="theorem" class="unlisted">' in html
    assert '<h4 id="proof" class="unlisted">' in html
    assert '<h4 id="conclusion" class="unlisted">' in html
    # The derivation is one flow, not one unsplittable box.
    assert units[0].keep_together is False


def test_proof_headings_never_enter_the_toc(tmp_path):
    env = ExecEnv(cwd=str(tmp_path))
    src = textwrap.dedent(r"""
        ::: toc
        :::

        # A Chapter

        Body.

        ::: proof
        ```python {run echo=false}
        print("# Checked proof")
        print("## Theorem")
        ```
        :::
    """)
    units = fill_toc(parse(src, env=env))
    entries = [u.html for u in units if u.name == "toc-entry"]
    assert len(entries) == 1
    assert "A Chapter" in entries[0]
    assert not any("Checked proof" in entry or "Theorem" in entry
                   for entry in entries)


def test_a_component_without_the_hint_keeps_its_static_body(tmp_path):
    env = ExecEnv(cwd=str(tmp_path))
    src = textwrap.dedent(r"""
        ::: note {title="Static"}
        ```python {run}
        print("# never executed")
        ```
        :::
    """)
    html = _html(parse(src, env=env))
    assert '<div class="admonition note ' in html
    assert "print" in html and "never executed" in html
    assert "<h1" not in html


def test_a_failing_run_keeps_its_error_and_stops_the_splice(tmp_path):
    env = ExecEnv(cwd=str(tmp_path))
    src = textwrap.dedent(r"""
        ::: proof
        ```python {run}
        print("before the error")
        raise ValueError("broken reading")
        ```
        :::
    """)
    html = _html(parse(src, env=env))
    assert 'class="output error"' in html
    assert "before the error" in html
    assert "ValueError" in html and "broken reading" in html
    assert "Traceback" in html


def test_without_an_exec_env_the_body_is_shown_not_run():
    src = "::: proof\n```python {run}\nprint('# no env')\n```\n:::"
    html = _html(parse(src))
    assert "print" in html and "# no env" in html
    assert "<h1" not in html


def test_the_proof_panel_is_styled_to_break_across_pages():
    css = load_theme("book").css.replace(" ", "")
    assert ".proof{" in css
    proof = css[css.index(".proof{"):css.index(".proof{") + 300]
    assert "break-inside:auto" in proof
