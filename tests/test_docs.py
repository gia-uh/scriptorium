"""The docs output: one scrolling page per chapter, cross-page links, sidebar."""

import wave
from pathlib import Path

import pytest

SRC = """# Sound {.part #sound}

Why sound comes first.

# What sound is {#what}

## Waves {#waves}

![A tone](t.wav){#aud-tone}

# Exercises

See @aud-tone and @sec-pluck.

# Instruments {.part}

# Strings {#strings}

## Pluck {#sec-pluck}

```text
a long line that never breaks a long line that never breaks a long line that never breaks a long line that never breaks a long line that never breaks a long line that never breaks 
```

# Exercises
"""


def build_docs(dest: Path) -> Path:
    """Write SRC and a short silent WAV to `dest` and build the docs site."""
    from scriptorium.docs import render_docs
    from scriptorium.project import Output

    dest.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest / "t.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\0\0" * 800)
    out = dest / "site"
    render_docs(SRC, out, output=Output(name="site", format="docs", dir="site"),
                base_dir=dest, execute=False)
    return out


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return build_docs(tmp_path_factory.mktemp("docs"))


def test_one_page_per_chapter_and_part_with_text(site):
    names = sorted(p.name for p in site.glob("*.html"))
    assert names == ["exercises-2.html", "exercises.html", "index.html", "sound.html",
                     "strings.html", "what.html"]


def test_a_part_without_text_is_only_a_label(site):
    side = (site / "what.html").read_text()
    assert "Instruments" in side and not (site / "instruments.html").exists()


def test_a_reference_to_another_page_carries_the_page(site):
    html = (site / "exercises.html").read_text()
    assert 'href="what.html#aud-tone"' in html and 'href="strings.html#sec-pluck"' in html


def test_previous_and_next_follow_reading_order(site):
    html = (site / "what.html").read_text()
    assert 'rel="prev" href="sound.html"' in html and 'rel="next" href="exercises.html"' in html


def test_the_sidebar_marks_the_current_page_and_lists_its_sections(site):
    html = (site / "what.html").read_text()
    assert 'aria-current="page"' in html and 'href="#waves"' in html


def test_media_search_and_no_service_worker(site):
    assert any((site / "media").iterdir()) and (site / "search.json").is_file()
    assert not (site / "sw.js").exists() and not (site / "manifest.webmanifest").exists()


def test_a_single_file_builds_a_one_page_site(tmp_path):
    from scriptorium.cli import main
    (tmp_path / "one.md").write_text("# Only\n\n## A section\n\ntext")
    assert main(["render", str(tmp_path / "one.md"), "--format", "docs", "--no-execute"]) == 0
    assert (tmp_path / "one" / "index.html").is_file()


def test_a_project_declares_a_docs_output(tmp_path):
    from scriptorium.project import ProjectError, load
    (tmp_path / "scriptorium.yaml").write_text(
        "outputs:\n  site:\n    format: docs\n    repo-url: https://example.org/repo\n")
    out = load(tmp_path / "scriptorium.yaml").outputs[0]
    assert (out.format, out.dir, out.repo_url) == ("docs", "site", "https://example.org/repo")
    (tmp_path / "scriptorium.yaml").write_text("outputs:\n  site:\n    format: web\n")
    with pytest.raises(ProjectError, match="is not one of pdf, html, docs"):
        load(tmp_path / "scriptorium.yaml")


def test_search_has_one_entry_per_section(site):
    import json
    entries = json.loads((site / "search.json").read_text())
    waves = [e for e in entries if e["title"] == "Waves"]
    assert waves == [{"page": "What sound is", "title": "Waves", "url": "what.html#waves",
                      "text": waves[0]["text"]}]
    assert all("<" not in e["text"] and len(e["text"]) <= 600 for e in entries)


def test_a_chapter_named_index_does_not_replace_the_front_page(tmp_path):
    from scriptorium.docs import render_docs
    from scriptorium.project import Output
    out = tmp_path / "site"
    render_docs("Front text\n\n# Index\n\n## Terms\n\n# Other", out,
                output=Output(name="site", format="docs"), base_dir=tmp_path, execute=False)
    assert "Front text" in (out / "index.html").read_text()
    html = (out / "index-2.html").read_text()
    assert 'rel="prev" href="index.html"' in html and 'rel="next" href="other.html"' in html


def test_a_formula_keeps_its_glyphs_on_its_own_page(tmp_path):
    from scriptorium.docs import render_docs
    from scriptorium.project import Output

    # The same formula on two pages: MathJax names its glyphs the same on both.
    src = "# One {#one}\n\nIt costs $n^2$.\n\n# Two {#two}\n\nAgain $n^2$.\n"
    out = tmp_path / "site"
    render_docs(src, out, output=Output(name="site", format="docs", dir="site"),
                base_dir=tmp_path, execute=False)
    two = (out / "two.html").read_text(encoding="utf-8")
    assert "MJX" in two
    assert ".html#MJX" not in two

