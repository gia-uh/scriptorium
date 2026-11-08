"""The docs output: a static documentation site of scrolling pages.

The units split into pages as the HTML book splits them into chapters, one
page per `#` heading. Each page carries a top bar with search, a sidebar of
parts and chapters, an outline of its sections, and previous and next links.
The theme's CSS is adapted for the browser as the book does; the layout lives
in `themes/base/docs/`.
"""

import json
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from html import unescape
from pathlib import Path

from .book import (BookReport, _carry_counters, _chapters, _esc, _unit_html, browser_css,
                   collect_css_assets, collect_images, html_refs, resolve_refs)
from .media import collect_media, page_units
from .theme import THEMES_DIR

DOCS_DIR = THEMES_DIR / "base" / "docs"

_HREF = re.compile(r'href="#([^"]+)"')
_ID = re.compile(r'\bid="([^"]+)"')
_TAGS = re.compile(r"<[^>]+>")
_BLOCK_END = re.compile(r"</(?:p|li|h\d|td|th|div|pre|figcaption|dt|dd|blockquote)>|<br\s*/?>")
_SUB_HEADING = re.compile(r'(<h([23])\b[^>]*\bid="([^"]+)"[^>]*>.*?)(</h\2>)', re.S)


@dataclass
class Page:
    slug: str
    title: str
    part: str | None
    units: list
    kind: str  # "index" | "part" | "chapter"


def _content(units) -> list:
    return [u for u in units if not u.is_break]


def pages(units) -> tuple[list[Page], list[dict]]:
    """The pages in reading order and the sidebar tree. Units before the first
    `#` heading go to the index page. A part heading with content under it
    gets a page; one with none is only a label in the sidebar."""
    slug_of = {id(u): page for u, page in page_units(units)}
    if not any(u.heading_level == 1 for u in units):
        return [Page("index", "", None, _content(units), "index")], []
    chunks, _ = _chapters(units)
    out = [Page("index", "", None, [], "index")]
    tree: list[dict] = []
    group = None
    for chunk in chunks:
        head = next((u for u in chunk if u.heading_level == 1), None)
        if head is None:  # the front, before the first chapter
            out[0].units = _content(chunk)
            continue
        slug, title = slug_of[id(head)], head.heading or ""
        if "part" in head.heading_classes:
            has_text = any(u is not head for u in _content(chunk))
            group = {"title": title, "slug": slug if has_text else None, "chapters": []}
            tree.append(group)
            if has_text:
                out.append(Page(slug, title, title, _content(chunk), "part"))
            continue
        part = group["title"] if group else None
        out.append(Page(slug, title, part, _content(chunk), "chapter"))
        if "unlisted" in head.heading_classes:
            continue
        if group is None:
            group = {"title": None, "slug": None, "chapters": []}
            tree.append(group)
        sections = [{"title": u.heading, "id": u.heading_id}
                    for u in chunk if u.heading_level == 2 and u.heading_id]
        group["chapters"].append({"title": title, "slug": slug, "sections": sections})
    return out, tree


def _text(units) -> str:
    text = unescape(_TAGS.sub("", _BLOCK_END.sub(" ", " ".join(u.html for u in units))))
    return " ".join(text.split())[:600]


def search_index(pages: list[Page]) -> list[dict]:
    """One entry per `##` and `###` section, and one for each page's text
    before its first section: the chapter, the title, the URL and the plain
    text, cut at 600 characters."""
    entries = []
    for page in pages:
        heads = [i for i, u in enumerate(page.units) if u.heading_level in (2, 3) and u.heading_id]
        lead = [u for u in page.units[:heads[0] if heads else None] if u.heading_level != 1]
        if text := _text(lead):
            entries.append({"page": page.title, "title": page.title, "url": f"{page.slug}.html",
                            "text": text})
        for n, i in enumerate(heads):
            u = page.units[i]
            body = page.units[i + 1:heads[n + 1] if n + 1 < len(heads) else None]
            entries.append({"page": page.title, "title": u.heading or "",
                            "url": f"{page.slug}.html#{u.heading_id}", "text": _text(body)})
    return entries


def _link_pages(html: str, here: str, where: dict[str, str]) -> str:
    """Point each `#id` link whose target is on another page at that page.

    An id defined on this page keeps its link here, even when another page
    defines it too: each formula's SVG names its glyphs `MJX-…` and uses them
    through `xlink:href="#MJX-…"`, and the same names recur from page to page,
    so sending one elsewhere leaves the formula with nothing to draw."""
    local = set(_ID.findall(html))

    def sub(m):
        page = where.get(m.group(1))
        if page in (None, here) or m.group(1) in local:
            return m.group(0)
        return f'href="{page}.html#{m.group(1)}"'
    return _HREF.sub(sub, html)


def _sidebar(tree: list[dict], current: str, outline: list) -> str:
    items = []
    for group in tree:
        chapters = []
        for ch in group["chapters"]:
            mine = ch["slug"] == current
            link = (f'<a href="{_esc(ch["slug"])}.html"'
                    + (' aria-current="page"' if mine else "") + f'>{_esc(ch["title"])}</a>')
            subs = ""
            if mine and outline:
                subs = '<ul class="sections">' + "".join(
                    f'<li><a href="#{_esc(i)}">{_esc(t)}</a></li>' for lvl, i, t in outline if lvl == 2) + "</ul>"
            chapters.append(f"<li>{link}{subs}</li>")
        if group["title"] is None:
            items.append("".join(chapters))
            continue
        if group["slug"]:
            label = (f'<a class="part" href="{_esc(group["slug"])}.html"'
                     + (' aria-current="page"' if group["slug"] == current else "")
                     + f'>{_esc(group["title"])}</a>')
        else:
            label = f'<span class="part">{_esc(group["title"])}</span>'
        items.append(f'<li class="part-group">{label}<ul>{"".join(chapters)}</ul></li>')
    return "<ul>" + "".join(items) + "</ul>"


def _contents(tree: list[dict]) -> str:
    """The index page's list of parts and chapters."""
    items = []
    for group in tree:
        chapters = "".join(f'<li><a href="{_esc(c["slug"])}.html">{_esc(c["title"])}</a></li>'
                           for c in group["chapters"])
        if group["title"] is None:
            items.append(chapters)
            continue
        label = (f'<a href="{_esc(group["slug"])}.html">{_esc(group["title"])}</a>' if group["slug"]
                 else _esc(group["title"]))
        items.append(f'<li class="part-group"><span class="part">{label}</span><ul>{chapters}</ul></li>')
    return f'<nav class="contents"><ul>{"".join(items)}</ul></nav>'


# The site's own words. A site in another language gets the English ones.
STRINGS = {
    "en": {"search": "Search", "on_this_page": "On this page", "source": "Source",
           "menu": "Menu", "contents": "Contents", "no_results": "No results",
           "scheme": "Colour scheme", "version": "Version",
           "copy": "Copy", "copied": "Copied", "output": "Output",
           "updated": "Last updated", "edit": "Edit this page",
           "not_found": "Page not found", "not_found_text": "There is no page at this address. Search, or go to the"},
    "es": {"search": "Buscar", "on_this_page": "En esta página", "source": "Código fuente",
           "menu": "Menú", "contents": "Índice", "no_results": "Sin resultados",
           "scheme": "Esquema de color", "version": "Versión",
           "copy": "Copiar", "copied": "Copiado", "output": "Salida",
           "updated": "Actualizado", "edit": "Editar esta página",
           "not_found": "Página no encontrada", "not_found_text": "No hay ninguna página en esta dirección. Busca, o ve a la"},
}


def _strings(lang: str) -> dict:
    return STRINGS.get(lang.split("-")[0].lower(), STRINGS["en"])


def resolve_version(version: str | None, base_dir: Path) -> str | None:
    """The version the header shows. A literal string is shown as written;
    `auto` reads `[project].version` from the nearest pyproject.toml at or
    above `base_dir`, then the latest git tag; anything else shows none."""
    if version != "auto":
        return version or None
    for d in [base_dir.resolve(), *base_dir.resolve().parents]:
        f = d / "pyproject.toml"
        if f.is_file():
            try:
                found = tomllib.loads(f.read_text(encoding="utf-8")).get("project", {}).get("version")
            except (OSError, tomllib.TOMLDecodeError):
                found = None
            if found:
                return str(found)
            break
    try:
        tag = subprocess.run(["git", "describe", "--tags", "--abbrev=0"], cwd=base_dir,
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return tag.stdout.strip() or None


_H1 = re.compile(r"^#\s+(.*?)\s*(?:\{[^}]*\})?\s*$")
_FENCE_LINE = re.compile(r"^\s*(```|~~~)")


def page_files(pages: list[Page], files: list[str], base_dir: Path) -> dict[str, str]:
    """Each page's source file. The files' `#` headings, outside code fences,
    are matched in order to the pages' titles; the index gets the first file."""
    heads = []
    for rel in files:
        try:
            lines = (base_dir / rel).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        fenced = False
        for line in lines:
            if _FENCE_LINE.match(line):
                fenced = not fenced
            elif not fenced and (m := _H1.match(line)):
                heads.append((m.group(1), rel))
    out = {"index": files[0]} if files else {}
    i = 0
    for page in pages:
        if page.kind == "index":
            continue
        for j in range(i, len(heads)):
            if heads[j][0] == page.title:
                out[page.slug], i = heads[j][1], j + 1
                break
    return out


def _git(base_dir: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=base_dir, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def edit_url(repo_url: str | None, edit_path: str | None, rel: str, base_dir: Path) -> str | None:
    """Where a reader edits a page's file: GitHub and GitLab, on the default branch."""
    if not repo_url:
        return None
    host, slug = repo_parts(repo_url)
    if not slug:
        return None
    prefix = edit_path if edit_path is not None else _git(base_dir, "rev-parse", "--show-prefix")
    if prefix is None:
        return None
    path = (prefix.strip("/") + "/" + rel).lstrip("/")
    root = f"https://{host}/{slug}"
    if host.endswith("github.com"):
        return f"{root}/edit/HEAD/{path}"
    if host.endswith("gitlab.com"):
        return f"{root}/-/edit/HEAD/{path}"
    return None


def _description(units) -> str:
    """The page's first paragraph as plain text, for search engines and link previews."""
    for u in units:
        if u.html.lstrip().startswith("<p"):
            text = " ".join(unescape(_TAGS.sub("", u.html)).split())
            if text:
                return text if len(text) <= 160 else text[:157].rsplit(" ", 1)[0] + "…"
    return ""


_GITHUB_MARK = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 '
                '6.53 5.47 7.59.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17'
                '-.73-.5.06-.49.06-.49.8.06 1.23.83 1.23.83.72 1.22 1.87.87 2.33.66.07-.52.28-.87.5-1.07-1.78-.2'
                '-3.65-.89-3.65-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82A7.6 7.6 0 0 '
                '1 8 3.87c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 '
                '2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42'
                '-3.58-8-8-8z"/></svg>')
# any other forge: a branch, drawn as two commits joined to a third
_FORGE_MARK = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3.25a1.75 1.75 0 1 1-2.5 1.58v6.34a1.75 '
               '1.75 0 1 1-1 0V4.83A1.75 1.75 0 1 1 5 3.25Zm9 0a1.75 1.75 0 0 1-1 1.58V6a3 3 0 0 1-3 3H6.5v2.17a1.75 '
               '1.75 0 1 1-1 0V9a1 1 0 0 1 1-1H10a2 2 0 0 0 2-2V4.83a1.75 1.75 0 1 1 2-1.58Z" transform="translate(.5 .5)"/></svg>')


def repo_parts(url: str) -> tuple[str, str]:
    """The forge's host and the `owner/name` a repository URL points at."""
    m = re.match(r"https?://([^/]+)/([^/]+)/([^/#?]+)", url or "")
    if not m:
        return "", ""
    name = m.group(3)[:-4] if m.group(3).endswith(".git") else m.group(3)
    return m.group(1).lower(), f"{m.group(2)}/{name}"


def _repo_widget(url: str | None, t: dict) -> str:
    if not url:
        return ""
    host, slug = repo_parts(url)
    mark = _GITHUB_MARK if host in ("github.com", "www.github.com") else _FORGE_MARK
    api = f' data-github="{_esc(slug)}"' if mark is _GITHUB_MARK and slug else ""
    label = _esc(slug or url)
    return (f'<a class="source repo" href="{_esc(url)}" title="{t["source"]}"{api}>{mark}'
            f'<span class="repo-name">{label}<small class="repo-facts" hidden></small></span></a>')


def palette_css(palette: dict) -> str:
    """The project's colours as overrides of the layout's variables."""
    rules = []
    if palette.get("primary"):
        rules.append(f"--docs-primary: {palette['primary']};")
    if palette.get("accent"):
        rules.append(f"--docs-accent: {palette['accent']}; --accent: {palette['accent']};")
    if not rules:
        return ""
    sel = ':root, :root[data-scheme="dark"]'
    return f"/* palette from the project */\n{sel} {{ {' '.join(rules)} }}\n"


def _copy_asset(rel: str | None, base_dir: Path, out_dir: Path, stem: str, warnings: list) -> str | None:
    """Copy the logo or favicon next to the pages; return its name there."""
    if not rel:
        return None
    src = base_dir / rel
    if not src.is_file():
        warnings.append(f"{stem} file {rel!r} does not exist")
        return None
    name = f"{stem}{src.suffix.lower()}"
    shutil.copyfile(src, out_dir / name)
    return name


# Runs before the first paint, so a reader who chose dark never sees a light
# frame: the stored choice, else the project's, else the system's.
_SCHEME_SCRIPT = ("<script>(function(){var d=document.documentElement,m=d.dataset.schemeDefault||'auto';"
                  "try{m=localStorage.getItem('scriptorium-scheme')||m}catch(e){}"
                  "d.dataset.schemeMode=m;d.dataset.scheme=m==='auto'?(matchMedia('(prefers-color-scheme: dark)')"
                  ".matches?'dark':'light'):m})()</script>")


def _shell(page: Page, body: str, *, site_title: str, lang: str, tree: list[dict],
           outline: list, prev: Page | None, next: Page | None, output,
           version: str | None = None, logo: str | None = None, favicon: str | None = None,
           foot: str = "", head: str = "") -> str:
    t = _strings(lang)
    title = page.title if page.kind != "index" else site_title
    head_title = _esc(title if title == site_title else f"{title} · {site_title}")
    source = _repo_widget(output.repo_url, t)
    scheme = output.palette.get("scheme", "auto")
    logo_html = f'<img class="logo" src="{_esc(logo)}" alt="">' if logo else ""
    version_html = (f'<span class="version" title="{t["version"]}">{_esc(version)}</span>'
                    if version else "")
    icon = f'\n<link rel="icon" href="{_esc(favicon)}">' if favicon else ""
    body_class = "docs" + (" typo-docs" if output.typography == "docs" else "") + (
        " has-primary" if output.palette.get("primary") else "")
    outline_html = ""
    if outline:
        outline_html = (f'<aside class="outline"><p>{t["on_this_page"]}</p><ul>' + "".join(
            f'<li class="h{lvl}"><a href="#{_esc(i)}">{_esc(t)}</a></li>' for lvl, i, t in outline)
            + "</ul></aside>")
    pager = '<nav class="pager">'
    if prev:
        pager += f'<a rel="prev" href="{prev.slug}.html">← {_esc(prev.title or site_title)}</a>'
    if next:
        pager += f'<a rel="next" href="{next.slug}.html">{_esc(next.title or site_title)} →</a>'
    pager += "</nav>"
    scripts = "".join(f'\n<script src="{_esc(js)}" defer></script>' for js in output.js)
    return f"""<!doctype html>
<html lang="{_esc(lang)}" data-scheme-default="{_esc(scheme)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{head_title}</title>
{_SCHEME_SCRIPT}{icon}{head}
<link rel="stylesheet" href="docs.css">
<script src="docs.js" defer></script>{scripts}
</head>
<body class="{body_class}" data-copy="{t["copy"]}" data-copied="{t["copied"]}" style="--docs-output-label: '{t["output"]}'">
<header class="topbar">
<button class="menu" type="button" aria-label="{t["menu"]}" aria-expanded="false">☰</button>
<a class="site-title" href="index.html">{logo_html}<span>{_esc(site_title)}</span></a>{version_html}
<div class="search"><input type="search" placeholder="{t["search"]}" aria-label="{t["search"]}" autocomplete="off"><div class="search-results" data-none="{t["no_results"]}" hidden></div></div>
<button class="scheme" type="button" aria-label="{t["scheme"]}" title="{t["scheme"]}"></button>
{source}
</header>
<div class="layout">
<nav class="sidebar" aria-label="{t["contents"]}">{_sidebar(tree, page.slug, outline)}</nav>
<main>
{body}
{foot}{pager}
</main>
{outline_html}
</div>
</body>
</html>
"""


def render_docs(src: str, out_dir: Path, *, output, base_dir: Path, theme_name: str | None = None,
                vars: dict | None = None, project_meta: dict | None = None,
                execute: bool = True, code_root: str | None = None,
                files: list[str] | None = None) -> BookReport:
    """Write the docs site for `src` into `out_dir`, replacing what was there."""
    from .emit import _emit_css
    from .render import prepare

    base_dir, out_dir = Path(base_dir), Path(out_dir)
    p = prepare(src, theme_name=theme_name, cwd=str(base_dir), execute=execute,
                vars={**(vars or {}), **output.vars}, code_root=code_root,
                project_meta=project_meta, for_screen=True, site_html=True)
    if str(p.theme.meta.get("mode", "")) == "deck":
        raise ValueError("deck themes have no docs form; render them to PDF")
    warnings = list(p.warnings) + resolve_refs(p.units, html_refs(p), p.meta)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    all_pages, tree = pages(p.units)
    # A part with no text has no page: its ids lead to the page after it, and
    # its heading still counts for the part counter, after the page before it.
    written = {page.slug for page in all_pages}
    where: dict[str, str] = {}
    labels: dict[str, str] = {}  # page slug -> label headings that follow it
    pending, last = [], "index"
    for u, slug in page_units(p.units):
        ids = _ID.findall(u.html)
        if slug not in written:
            pending += ids
            labels[last] = labels.get(last, "") + u.html
            continue
        for ident in pending + ids:
            where.setdefault(ident, slug)
        pending, last = [], slug

    first_h1 = next((u.heading for u in p.units if u.heading_level == 1), "")
    site_title = str(p.meta.get("title") or first_h1 or "Documentation")
    lang = str(p.meta.get("lang") or p.theme.meta.get("lang") or "en")

    version = resolve_version(output.version, base_dir)
    if output.version == "auto" and not version:
        warnings.append("version: auto found no pyproject.toml version and no git tag")
    logo = _copy_asset(output.logo, base_dir, out_dir, "logo", warnings)
    favicon = _copy_asset(output.favicon, base_dir, out_dir, "favicon", warnings)

    t = _strings(str(p.meta.get("lang") or p.theme.meta.get("lang") or "en"))
    sources = page_files(all_pages, files or [], base_dir)
    base_url = str(p.meta.get("base-url") or "").rstrip("/")
    base_url = base_url + "/" if base_url else ""

    def foot_of(page) -> str:
        bits = []
        rel = sources.get(page.slug)
        if rel and (day := _git(base_dir, "log", "-1", "--format=%cs", "--", rel)):
            bits.append(f'{t["updated"]} {_esc(day)}')
        if rel and (url := edit_url(output.repo_url, output.edit_path, rel, base_dir)):
            bits.append(f'<a class="edit" href="{_esc(url)}">{t["edit"]}</a>')
        left = f'<span>{" · ".join(bits)}</span>' if bits else ""
        right = f'<span class="site-footer">{_esc(output.footer)}</span>' if output.footer else ""
        return f'<footer class="page-foot">{left}{right}</footer>\n' if left or right else ""

    def head_of(page, title: str) -> str:
        desc = _description(page.units)
        tags = [f'<meta property="og:title" content="{_esc(title)}">', '<meta property="og:type" content="website">']
        if desc:
            tags[:0] = [f'<meta name="description" content="{_esc(desc)}">']
            tags.append(f'<meta property="og:description" content="{_esc(desc)}">')
        if base_url:
            url = base_url + ("" if page.slug == "index" else f"{page.slug}.html")
            tags += [f'<link rel="canonical" href="{_esc(url)}">', f'<meta property="og:url" content="{_esc(url)}">']
        return "\n" + "\n".join(tags)

    sections = []
    for page in all_pages:
        html = "".join(_unit_html(u, p.theme) for u in page.units)
        html = _link_pages(html, page.slug, where)
        html = _SUB_HEADING.sub(lambda m: f'{m.group(1)}<a class="anchor" href="#{m.group(3)}">#</a>{m.group(4)}', html)
        sections.append(f'<section class="docs-page {page.kind}">{html}</section>')
    counted = _carry_counters([s + labels.get(page.slug, "") for page, s in zip(all_pages, sections)])
    sections = [c[:len(c) - len(labels.get(page.slug, ""))] for page, c in zip(all_pages, counted)]

    for n, (page, section) in enumerate(zip(all_pages, sections)):
        outline = [(u.heading_level, u.heading_id, u.heading or "")
                   for u in page.units if u.heading_level in (2, 3) and u.heading_id]
        body = section
        if page.kind == "index":
            if not any(u.heading_level == 1 for u in page.units):
                body = f'<h1 class="unnumbered docs-title">{_esc(site_title)}</h1>' + body
            body += _contents(tree)
        body, img_warnings = collect_images(body, base_dir, out_dir, output.image_max_width,
                                            output.image_quality)
        warnings += img_warnings
        body = collect_media(body, base_dir, out_dir)
        html = _shell(page, body, site_title=site_title, lang=lang, tree=tree, outline=outline,
                      prev=all_pages[n - 1] if n else None,
                      next=all_pages[n + 1] if n + 1 < len(all_pages) else None, output=output,
                      version=version, logo=logo, favicon=favicon, foot=foot_of(page),
                      head=head_of(page, page.title or site_title))
        (out_dir / f"{page.slug}.html").write_text(html, encoding="utf-8")

    css = [browser_css(collect_css_assets(_emit_css(p.theme, p.meta), out_dir)),
           (DOCS_DIR / "docs.css").read_text(encoding="utf-8"), palette_css(output.palette)]
    for rel in output.css:
        try:
            css.append((base_dir / rel).read_text(encoding="utf-8"))
        except OSError as exc:
            warnings.append(f"css file {rel!r} could not be read: {exc}")
    (out_dir / "docs.css").write_text("\n".join(css), encoding="utf-8")
    shutil.copyfile(DOCS_DIR / "docs.js", out_dir / "docs.js")
    for rel in output.js:
        try:
            dst = out_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(base_dir / rel, dst)
        except OSError as exc:
            warnings.append(f"js file {rel!r} could not be copied: {exc}")
    for page in all_pages:  # the index has no heading of its own
        page.title = page.title or site_title
    (out_dir / "search.json").write_text(json.dumps(search_index(all_pages), ensure_ascii=False),
                                         encoding="utf-8")

    # A host serves 404.html at any missing path, so its links need the site's
    # address: with base-url they are absolute, without it they work at the root.
    lost = Page("404", t["not_found"], None, [], "chapter")
    lost_body = (f'<h1 class="unnumbered">{t["not_found"]}</h1><p>{t["not_found_text"]} '
                 f'<a href="index.html">{_esc(site_title)}</a>.</p>')
    html = _shell(lost, lost_body, site_title=site_title, lang=lang, tree=tree, outline=[],
                  prev=None, next=None, output=output, version=version, logo=logo, favicon=favicon,
                  head=f'\n<base href="{_esc(base_url)}">' if base_url else "")
    (out_dir / "404.html").write_text(html, encoding="utf-8")
    if base_url:
        urls = "".join(f"<url><loc>{_esc(base_url + ('' if pg.slug == 'index' else pg.slug + '.html'))}</loc></url>"
                       for pg in all_pages)
        (out_dir / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n', encoding="utf-8")

    files = [f for f in out_dir.rglob("*") if f.is_file()]
    return BookReport(files=len(files), bytes=sum(f.stat().st_size for f in files),
                      version=version or "", warnings=warnings)
