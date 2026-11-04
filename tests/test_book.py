"""Running-heads + auto-TOC + project assembly (the book layer)."""

import re

from scriptorium.parse import parse, fill_toc
from scriptorium.project import load


def _hrefs(units):
    return [re.search(r'href="([^"]+)"', u.html).group(1) for u in units if u.name == "toc-entry"]


def test_heading_gets_autoslug_id():
    (u,) = parse("## The Linear Scan")
    assert u.heading_id == "the-linear-scan" and u.heading_level == 2


def test_explicit_heading_id_wins():
    (u,) = parse("# Trees {#chap-trees}")
    assert u.heading_id == "chap-trees" and u.heading_level == 1


def test_fill_toc_lists_headings_with_ids():
    src = "::: toc\n:::\n\n# Ch One {#chap-one}\n\n## Sec A\n\n# Ch Two {#chap-two}"
    hrefs = _hrefs(fill_toc(parse(src)))
    assert hrefs == ["#chap-one", "#sec-a", "#chap-two"]


def test_toc_entry_carries_its_page_number_span():
    (entry,) = [u.html for u in fill_toc(parse("::: toc\n:::\n\n# One {#one}"))
                if u.name == "toc-entry"]
    assert '<span class="toc-pg" data-ref="#one"></span>' in entry


def test_toc_prints_real_page_numbers(tmp_path):
    import subprocess

    from scriptorium.galley import render_pdf

    # WeasyPrint 70 resolves target-counter() to 0 in a pseudo-element of a flex
    # container, which the TOC entry is; the number must still come out.
    src = ("---\ntheme: book\ntitle: T\n---\n\n::: toc\n:::\n\n\\newpage\n\n"
           "# First {#first}\n\nBody.\n\n\\newpage\n\n# Second {#second}\n\nBody.\n")
    out = tmp_path / "toc.pdf"
    render_pdf(src, str(out), execute=False)
    first = subprocess.run(["pdftotext", "-f", "1", "-l", "1", str(out), "-"],
                           capture_output=True, text=True).stdout
    numbers = re.findall(r"^\s*(\d+)\s*$", first, re.M)
    assert numbers and "0" not in numbers, first


def test_toc_depth_limits_levels():
    src = "::: toc\n:::\n\n# A {#a}\n\n### Deep {#deep}"
    hrefs = _hrefs(fill_toc(parse(src), depth=1))
    assert "#a" in hrefs and not any("deep" in h for h in hrefs)


def test_project_concatenates_and_substitutes_vars(tmp_path):
    (tmp_path / "a.md").write_text("# {{title}}\n\nbody one")
    (tmp_path / "b.md").write_text("# second")
    (tmp_path / "scriptorium.yaml").write_text(
        "theme: book\nvars: {title: Hello}\nfiles: [a.md, b.md]")
    p = load(tmp_path / "scriptorium.yaml")
    assert p.theme == "book"
    assert "# Hello" in p.src  # var substituted
    assert "\\newpage" in p.src  # files separated by a page break
    assert "# second" in p.src


# --- parts and unnumbered front matter ------------------------------------

def test_front_matter_and_parts_do_not_consume_chapter_numbers(tmp_path):
    import subprocess

    from scriptorium.galley import render_pdf

    src = ("---\ntheme: book\ntitle: T\n---\n\n"
           "# Preface {.unnumbered}\n\nBody.\n\n"
           "# Foundations {.part}\n\nBody.\n\n"
           "# Classical AI\n\nBody.\n")
    out = tmp_path / "b.pdf"
    render_pdf(src, str(out), execute=False)

    text = subprocess.run(["pdftotext", str(out), "-"],
                          capture_output=True, text=True).stdout
    # Compare whitespace- and case-insensitively: pdftotext sees the styled
    # glyphs, so letter-spacing splits "PART" into "PA R T" and text-transform
    # upper-cases it. Both are theme styling, not the thing under test — what is
    # under test is which counter each heading increments.
    compact = "".join(text.split()).upper()
    # The first real chapter is 1, not 3: neither the preface nor the part
    # increments the chapter counter.
    assert "1CLASSICALAI" in compact
    assert "PARTIFOUNDATIONS" in compact
    assert "1PREFACE" not in compact and "2PREFACE" not in compact


def test_cover_master_renders_a_full_page(tmp_path):
    import base64

    from scriptorium.galley import render_pdf

    # The canonical 1x1 transparent PNG — a real decodable image, because
    # WeasyPrint drops one it cannot parse and the page count would still be 2.
    (tmp_path / "c.png").write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGA"
        "hKmMIQAAAABJRU5ErkJggg=="))
    src = ("---\ntheme: book\ntitle: T\ncover-image: c.png\n---\n\n"
           "::: cover\n:::\n\n# One\n\nBody.\n")
    out = tmp_path / "cov.pdf"
    report = render_pdf(src, str(out), base_url=str(tmp_path) + "/",
                        cwd=str(tmp_path), execute=False)

    assert report.n_pages == 2      # the cover is its own page
    assert report.warnings == []


def test_a_part_divider_starts_its_own_page(tmp_path):
    # A part landing at the foot of the previous chapter's endnotes is not a
    # divider. Parts I and II of the manuscript only looked right by luck.
    from scriptorium.galley import render_pdf

    src = ("---\ntheme: book\ntitle: T\n---\n\n"
           "# One\n\n" + ("Filler prose. " * 40 + "\n\n") * 2
           + "# Dangers {.part}\n\nPart blurb.\n")
    out = tmp_path / "part.pdf"
    render_pdf(src, str(out), execute=False)

    import subprocess
    per_page = [subprocess.run(["pdftotext", "-f", str(n), "-l", str(n),
                                str(out), "-"], capture_output=True,
                               text=True).stdout for n in (1, 2)]
    assert "Dangers" not in per_page[0]      # not crammed under chapter one
    assert "Dangers" in per_page[1]
