"""The HTML book: a static, installable ebook directory built from the units.

The same units a PDF prints from are laid out by a browser's multi-column
layout instead of WeasyPrint's paged media. This module turns the theme's CSS
into what a browser runs, resolves the cross-references that paged media
numbered, collects images and fonts into the site, and writes the reader.
"""

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from .media import collect_media
from .theme import THEMES_DIR

# Declarations only paged media understands. In a browser an unknown function
# invalidates the whole declaration, so a `content: "Chapter " target-counter()`
# would leave the reference empty rather than half-filled.
_PAGED_VALUE = re.compile(r"target-counter\(|target-text\(|counter\(pages?\b|leader\(|string\(")
_PAGED_PROPS = {"string-set", "bookmark-level", "bookmark-label", "page"}
# fixed-size page and slide boxes; the reader has its own full-page block
_DROP_SELECTORS = {".page", ".page:first-child", ".slide", ".slide:last-child"}
# at-rules whose body is more rules, filtered the same way
_NESTED = ("@media", "@supports", "@layer", "@container", "@document")
_BREAK_PAGE = re.compile(r"\b((?:page-)?break-(?:before|after)\s*:\s*)(?:page|always|left|right|recto|verso)\b")


def _strip_comments(css: str) -> str:
    out, i = [], 0
    while i < len(css):
        if css.startswith("/*", i):
            end = css.find("*/", i + 2)
            i = len(css) if end < 0 else end + 2
            continue
        if css[i] in "\"'":
            j = _string_end(css, i)
            out.append(css[i:j])
            i = j
            continue
        out.append(css[i])
        i += 1
    return "".join(out)


def _string_end(css: str, i: int) -> int:
    q, j = css[i], i + 1
    while j < len(css) and css[j] != q:
        j += 2 if css[j] == "\\" else 1
    return j + 1


def _items(css: str):
    """Top-level (prelude, body) pairs; body is None for a `@import …;` statement."""
    i, n = 0, len(css)
    while i < n:
        start, depth, paren = i, 0, 0
        while i < n:
            c = css[i]
            if c in "\"'":
                i = _string_end(css, i)
                continue
            if c == "(":
                paren += 1
            elif c == ")":
                paren -= 1
            elif c == ";" and depth == 0 and paren == 0:
                stmt = css[start:i].strip()
                i += 1
                if stmt:
                    yield stmt, None
                break
            elif c == "{" and paren == 0:
                if depth == 0:
                    open_at = i
                depth += 1
            elif c == "}" and paren == 0:
                depth -= 1
                if depth == 0:
                    yield css[start:open_at].strip(), css[open_at + 1:i]
                    i += 1
                    break
            i += 1
        else:
            rest = css[start:].strip()
            if rest:
                yield rest, None


def _declarations(body: str) -> list[str]:
    decls, cur, paren, i = [], [], 0, 0
    while i < len(body):
        c = body[i]
        if c in "\"'":
            j = _string_end(body, i)
            cur.append(body[i:j])
            i = j
            continue
        if c == "(":
            paren += 1
        elif c == ")":
            paren -= 1
        if c == ";" and paren == 0:
            decls.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    decls.append("".join(cur))
    return [d for d in decls if d.strip()]


def _filter_rule(body: str) -> str:
    kept = []
    for d in _declarations(body):
        prop, _, value = d.partition(":")
        if prop.strip().lower() in _PAGED_PROPS or _PAGED_VALUE.search(value):
            continue
        kept.append(_BREAK_PAGE.sub(r"\1column", d))
    return ";".join(kept)


def browser_css(css: str) -> str:
    """The theme CSS without what only paged media understands: `@page` rules
    and their margin boxes, page and slide boxes, `string-set`, and contents
    built with `target-counter()` / `target-text()` / `counter(page)`. Page
    breaks become column breaks, since a page of the book is a column."""
    out = []
    for prelude, body in _items(_strip_comments(css)):
        if body is None:
            out.append(prelude + ";")
            continue
        at = re.match(r"@[\w-]*", prelude).group(0).lower() if prelude.startswith("@") else ""
        if at == "@page":
            continue
        if at in _NESTED:
            out.append(f"{prelude}{{{browser_css(body)}}}")
        elif at:  # @font-face, @keyframes, …: untouched
            out.append(f"{prelude}{{{body}}}")
        elif {s.strip() for s in prelude.split(",")} <= _DROP_SELECTORS:
            continue
        else:
            kept = _filter_rule(body)
            if kept.strip():
                out.append(f"{prelude}{{{kept}}}")
    return "\n".join(out)


_ID_TAG = re.compile(r'<(\w+)\b([^>]*?)\bid="([^"]+)"([^>]*)>')
_REF_A = re.compile(r'<a class="ref-(\w+)" href="#([^"]+)"></a>')
_TAGS = re.compile(r"<[^>]+>")
_FIELD = re.compile(r"\{([\w-]+)\}")


def _inner_text(html: str, start: int, tag: str) -> str:
    end = html.find(f"</{tag}>", start)
    return _TAGS.sub("", html[start:end if end >= 0 else start]).strip()


def html_refs(p) -> dict:
    """The reference formats for an HTML output: the theme's `html-refs:`, with
    the document's or project's own `html-refs:` on top, so a Spanish book can
    say "figura 3" where the theme quotes the caption."""
    return {**(p.theme.meta.get("html-refs") or {}), **(p.meta.get("html-refs") or {})}


def resolve_refs(units, formats: dict, vars: dict) -> list[str]:
    """Write each `@kind-id` reference's text into its empty anchor.

    Paged media fills these with `target-counter()`, which browsers do not
    implement. The counting follows the themes' CSS: a chapter is an `h1` that
    is neither `.unnumbered` nor `.part` and restarts the sections, a section
    is an `h2`, a figure is a `<figure id="fig-…">`, an audio figure is a
    `<figure id="aud-…">`. The strings come from the
    theme's `html-refs:`; a kind without one shows the target's own text."""
    counters = {"chapter": 0, "section": 0, "figure": 0, "audio": 0}
    targets: dict[str, dict] = {}
    for u in units:
        for m in _ID_TAG.finditer(u.html):
            tag, attrs, ident = m.group(1).lower(), m.group(2) + m.group(4), m.group(3)
            classes = re.search(r'class="([^"]*)"', attrs)
            classes = classes.group(1).split() if classes else []
            if tag == "h1" and not {"unnumbered", "part"} & set(classes):
                counters["chapter"] += 1
                counters["section"] = 0
            elif tag == "h2":
                counters["section"] += 1
            elif tag == "figure" and ident.startswith("fig-"):
                counters["figure"] += 1
            elif tag == "figure" and ident.startswith("aud-"):
                counters["audio"] += 1
            if tag == "figure":
                cap = u.html.find("<figcaption", m.end())
                text = _inner_text(u.html, u.html.find(">", cap) + 1, "figcaption") if cap >= 0 else ""
            elif tag == "img":
                alt = re.search(r'alt="([^"]*)"', attrs)
                text = alt.group(1) if alt else ""
            else:
                text = _inner_text(u.html, m.end(), tag)
            targets[ident] = {**counters, "text": text}

    def label(key):
        v = vars.get(key)
        if v is None and key in ("figure-ref-label", "audio-ref-label"):
            v = vars.get(key.replace("-ref-", "-"))
        return str(v if v is not None else "").strip("\"'")

    warnings = []

    def fill(m):
        kind, ident = m.group(1), m.group(2)
        t = targets.get(ident)
        if t is None:
            warnings.append(f"unresolved reference @{ident}")
            return m.group(0)
        fmt = formats.get(kind, "{text}")
        text = _FIELD.sub(lambda f: str(t[f.group(1)]) if f.group(1) in t else label(f.group(1)), fmt)
        return f'<a class="ref-{kind}" href="#{ident}">{text.strip()}</a>'

    for u in units:
        u.html = _REF_A.sub(fill, u.html)
    return warnings


_IMG = re.compile(r"<img\b[^>]*>")
_SRC = re.compile(r'\bsrc="([^"]*)"')
_SIZE_ATTR = re.compile(r'\s(?:width|height)="[^"]*"')
_RASTER = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_FONT = {".woff2", ".woff", ".ttf", ".otf"}
_CSS_FILE_URL = re.compile(r"url\(\s*(['\"]?)file://([^)'\"]+)\1\s*\)")


def _is_local(url: str) -> bool:
    return not url.startswith(("http:", "https:", "data:", "//", "#"))


def _webp(src: Path, dst: Path, max_width: int, quality: int) -> tuple[int, int]:
    from PIL import Image

    with Image.open(src) as im:
        alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
        im = im.convert("RGBA" if alpha else "RGB")
        if im.width > max_width:
            im = im.resize((max_width, round(im.height * max_width / im.width)), Image.LANCZOS)
        im.save(dst, "WEBP", quality=quality, method=6)
        return im.size


def _svg_size(path: Path) -> tuple[int, int] | None:
    head = path.read_text(encoding="utf-8", errors="replace")[:2000]
    w, h = re.search(r'\bwidth="([\d.]+)', head), re.search(r'\bheight="([\d.]+)', head)
    return (round(float(w.group(1))), round(float(h.group(1)))) if w and h else None


def collect_images(html: str, base_dir: Path, out_dir: Path, max_width: int,
                   quality: int = 80, lazy: bool = False) -> tuple[str, list[str]]:
    """Copy every local image into `out_dir/img/`, rasters as WebP no wider
    than `max_width`, and rewrite each tag to point there with its intrinsic
    `width` and `height`: an image without them reflows every column after it
    when it loads. Files are named by content, so a build is deterministic and
    an image used twice is stored once. With `lazy`, each tag also gets
    `loading="lazy"`: the reader's hidden counting strip then never fetches
    the images of the chapters it measures."""
    done: dict[Path, tuple[str, tuple[int, int] | None]] = {}
    warnings: list[str] = []

    def sub(m):
        tag = m.group(0)
        src = _SRC.search(tag)
        if not src or not _is_local(src.group(1)):
            return tag
        path = (base_dir / unquote(src.group(1))).resolve()
        if path not in done:
            if not path.is_file():
                warnings.append(f"image {src.group(1)!r} not found")
                return tag
            data = path.read_bytes()
            # the default quality keeps the old names, so existing books keep their edition
            key = str(max_width) if quality == 80 else f"{max_width}/{quality}"
            digest = hashlib.sha256(data + key.encode()).hexdigest()[:12]
            (out_dir / "img").mkdir(parents=True, exist_ok=True)
            ext = path.suffix.lower()
            if ext in _RASTER:
                name = f"img/{digest}.webp"
                size = _webp(path, out_dir / name, max_width, quality)
            else:
                name = f"img/{digest}{ext}"
                shutil.copyfile(path, out_dir / name)
                size = _svg_size(path) if ext == ".svg" else None
            done[path] = (name, size)
        name, size = done[path]
        tag = _SIZE_ATTR.sub("", tag)
        dims = f' width="{size[0]}" height="{size[1]}"' if size else ""
        if lazy and "loading=" not in tag:
            dims += ' loading="lazy" decoding="async"'
        return tag.replace(src.group(0), f'src="{name}"{dims}', 1)

    return _IMG.sub(sub, html), warnings


def collect_css_assets(css: str, out_dir: Path) -> str:
    """Copy what the theme CSS loads from disk (fonts, a logo) into the site
    and point the CSS at the copies. Themes reach their assets through
    `file://` URLs (theme.py makes them absolute for WeasyPrint)."""
    taken: dict[str, Path] = {}

    def sub(m):
        path = Path(unquote(m.group(2)))
        if not path.is_file():
            return m.group(0)
        folder = "fonts" if path.suffix.lower() in _FONT else "assets"
        name = f"{folder}/{path.name}"
        if taken.get(name, path) != path:  # two themes, one file name
            name = f"{folder}/{hashlib.sha256(str(path).encode()).hexdigest()[:8]}-{path.name}"
        if name not in taken:
            (out_dir / folder).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, out_dir / name)
            taken[name] = path
        return f"url('{name}')"

    return _CSS_FILE_URL.sub(sub, css)


READER_DIR = THEMES_DIR / "base" / "reader"

# The reader's own words. A book in another language gets the English ones.
STRINGS = {
    "en": {"contents": "Contents", "reading": "Reading", "size": "Size", "mode": "Mode",
           "light": "Light", "sepia": "Sepia", "dark": "Night", "install": "Install",
           "go_to_page": "Go to page", "offline": "✓ offline",
           "ios_hint": "To install it on an iPhone or iPad: the Share button, then “Add to Home Screen”.",
           "update": "A new edition of this book is available.", "update_button": "Update"},
    "es": {"contents": "Índice", "reading": "Lectura", "size": "Letra", "mode": "Tema",
           "light": "Claro", "sepia": "Sepia", "dark": "Noche", "install": "Instalar",
           "go_to_page": "Ir a página", "offline": "✓ sin conexión",
           "ios_hint": "Para instalarlo en iPhone o iPad: botón Compartir y luego «Añadir a pantalla de inicio».",
           "update": "Hay una edición nueva de este libro.", "update_button": "Actualizar"},
}

_PT_SIZE = re.compile(r"(font-size\s*:\s*)([\d.]+)pt\b")


def relative_sizes(css: str, base_pt: float = 11.0) -> str:
    """Font sizes in points become shares of the reader's size, so the theme's
    proportions hold and A−/A+ scales the headings with the text."""
    return _PT_SIZE.sub(lambda m: f"{m.group(1)}calc(var(--reader-size) * {float(m.group(2)) / base_pt:.4g})", css)


def _esc(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _chapters(units):
    """Split the units into chapters at h1, or at h2 in a book without h1. A
    full page right before a chapter heading opens that chapter, as an
    illustration facing the chapter's first page does."""
    level = 1 if any(u.heading_level == 1 for u in units) else 2
    kept = [u for u in units if u.name != "toc"]
    chapters, toc = [[]], []
    for i, u in enumerate(kept):
        starts = u.heading_level == level
        opener = _is_fullpage(u) and i + 1 < len(kept) and kept[i + 1].heading_level == level
        prev_opener = i > 0 and _is_fullpage(kept[i - 1]) and starts
        if (starts and not prev_opener) or opener:
            chapters.append([])
        if starts and "unlisted" not in u.heading_classes:
            entry = {"id": u.heading_id, "title": u.heading}
            if "part" in u.heading_classes:
                entry["part"] = True
            toc.append(entry)
        chapters[-1].append(u)
    return [c for c in chapters if c], toc


_PART_BEFORE = re.compile(r"h1\.part::before\s*\{([^}]*)\}")
_CONTENT = re.compile(r"(?:^|;)\s*content\s*:\s*([^;]+)")


def toc_part_css(css: str) -> str:
    """The table of contents labels each part as the theme's `h1.part::before`
    does, counting parts with the same counter. A theme that does not number
    parts gets no label."""
    content = None
    for m in _PART_BEFORE.finditer(css):
        c = _CONTENT.search(m.group(1))
        if c:
            content = c.group(1).strip()
    if not content or "counter(part" not in content:
        return ""
    return f"#toc-list .toc-part-label::before {{ content: {content}; }}\n"


def _is_fullpage(u) -> bool:
    return u.full_page or bool(re.match(r'\s*<figure\b[^>]*class="[^"]*\bfullpage\b', u.html))


def _unit_html(u, theme) -> str:
    if _is_fullpage(u):
        classes = " ".join(["fullpage", theme.master_classes(u.master) if u.full_page else ""]).strip()
        return f'<div class="{classes}">{u.html}</div>'
    cls = ["unit"] + (["break-before"] if u.break_before else []) + (["keep"] if u.keep_together else [])
    return f'<div class="{" ".join(cls)}">{u.html}</div>'


def _carry_counters(sections: list[str]) -> list[str]:
    """Each chapter is laid out on its own, so the CSS counters the themes
    number with would restart at every chapter. Each section starts its own
    instances at the values the chapters before it reached, counted as
    `resolve_refs` counts them."""
    chapter = part = figure = audio = 0
    out = []
    for html in sections:
        start = f"counter-reset: chapter {chapter} part {part} figure {figure} audio {audio}"
        out.append(html.replace("<section ", f'<section style="{start}" ', 1))
        for m in re.finditer(r"<(h1|figure)\b([^>]*)>", html):
            classes = re.search(r'class="([^"]*)"', m.group(2))
            classes = set(classes.group(1).split()) if classes else set()
            if m.group(1) == "h1":
                if "part" in classes:
                    part += 1
                elif "unnumbered" not in classes:
                    chapter += 1
            elif re.search(r'\bid="fig-', m.group(2)):
                figure += 1
            elif re.search(r'\bid="aud-', m.group(2)):
                audio += 1
    return out


def emit_book(units, theme, meta: dict, output, strings: dict) -> tuple[str, list[str]]:
    """The book's index.html and one HTML fragment per chapter. Chapter 0 is
    the front: the cover and the title page. The reader loads and lays out one
    chapter at a time, so a long book opens as fast as a short one."""
    chapters, toc = _chapters(units)
    title = meta.get("title", "")
    front = []
    if output.cover:
        front.append(f'<div class="fullpage cover"><img src="{_esc(output.cover)}" alt="{_esc(title)}"></div>')
    front.append('<section class="titlepage">'
                 f'<p class="book-title">{_esc(title)}</p>'
                 + (f'<p class="book-subtitle">{_esc(meta["subtitle"])}</p>' if meta.get("subtitle") else "")
                 + (f'<p class="book-author">{_esc(meta["author"])}</p>' if meta.get("author") else "")
                 + "</section>")
    sections = ['<section class="chapter front">' + "".join(front) + "</section>"]
    for chapter in chapters:
        parts, dropcap_done = [], False
        for i, u in enumerate(chapter):
            if u.is_break:
                # a file boundary at a chapter's edge is already a new page
                if i == len(chapter) - 1 or i == 0:
                    continue
                parts.append('<div class="pagebreak"></div>')
                continue
            if not dropcap_done and u.html.startswith("<p>"):
                dropcap_done = True
                if re.match(r"<p>\w", u.html):
                    u.html = '<p class="dropcap">' + u.html[3:]
            parts.append(_unit_html(u, theme))
        chapter_starts = any(u.heading_level and u.heading_id for u in chapter[:2]) or _is_fullpage(chapter[0])
        cls = "chapter recto" if chapter_starts else "chapter"
        sections.append(f'<section class="{cls}">{"".join(parts)}</section>')

    sections = _carry_counters(sections)

    # which chapter holds each id, so a link or a #hash can load it first
    ids = {}
    for n, html in enumerate(sections):
        for ident in re.findall(r'\bid="([^"]+)"', html):
            ids.setdefault(ident, n)
    for entry in toc:
        entry["chapter"] = ids.get(entry["id"], 0)
    book = {
        "toc": toc, "ids": ids, "strings": strings,
        "chapters": [{"file": f"chapters/{n:03d}.html", "chars": len(_TAGS.sub("", h))}
                     for n, h in enumerate(sections)],
        "edition": hashlib.sha256("".join(sections).encode()).hexdigest()[:12],
    }
    fills = {
        "lang": _esc(meta.get("lang") or theme.meta.get("lang") or "en"),
        "title": _esc(title), "subtitle": _esc(meta.get("subtitle", "")),
        "book": json.dumps(book, ensure_ascii=False).replace("</", "<\\/"),
        "head": _HEAD, "scripts": "\n".join(f'<script src="{_esc(js)}" defer></script>' for js in output.js),
    }
    page = (READER_DIR / "index.html").read_text(encoding="utf-8")
    page = re.sub(r"\{\{s\.(\w+)\}\}", lambda m: _esc(strings[m.group(1)]), page)
    return re.sub(r"\{\{(\w+)\}\}", lambda m: fills[m.group(1)], page), sections


@dataclass
class BookReport:
    files: int
    bytes: int
    version: str
    warnings: list[str] = field(default_factory=list)


def render_book(src: str, out_dir: Path, *, output, base_dir: Path, theme_name: str | None = None,
                vars: dict | None = None, project_meta: dict | None = None,
                execute: bool = True, code_root: str | None = None) -> BookReport:
    """Write the HTML book for `src` into `out_dir`, replacing what was there."""
    from .emit import _emit_css
    from .render import prepare
    from .theme import _chain

    base_dir, out_dir = Path(base_dir), Path(out_dir)
    p = prepare(src, theme_name=theme_name, cwd=str(base_dir), execute=execute,
                vars={**(vars or {}), **output.vars}, code_root=code_root,
                project_meta=project_meta, for_screen=True)
    if str(p.theme.meta.get("mode", "")) == "deck":
        raise ValueError("deck themes have no book form; render them to PDF")
    warnings = list(p.warnings) + resolve_refs(p.units, html_refs(p), p.meta)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    lang = str(p.meta.get("lang") or p.theme.meta.get("lang") or "en").split("-")[0]
    strings = STRINGS.get(lang, STRINGS["en"])
    html, sections = emit_book(p.units, p.theme, p.meta, output, strings)
    (out_dir / "chapters").mkdir()
    for n, section in enumerate(sections):
        section, img_warnings = collect_images(section, base_dir, out_dir, output.image_max_width,
                                               output.image_quality, not output.offline_images)
        warnings += img_warnings
        section = collect_media(section, base_dir, out_dir)
        (out_dir / f"chapters/{n:03d}.html").write_text(section, encoding="utf-8")

    css = [relative_sizes(browser_css(collect_css_assets(_emit_css(p.theme, p.meta), out_dir))),
           (READER_DIR / "reader.css").read_text(encoding="utf-8")]
    for root, _ in _chain(p.theme.name):
        if (root / "reader.css").is_file():
            css.append(collect_css_assets((root / "reader.css").read_text(encoding="utf-8"), out_dir))
    for rel in output.css:
        try:
            css.append((base_dir / rel).read_text(encoding="utf-8"))
        except OSError as exc:
            warnings.append(f"css file {rel!r} could not be read: {exc}")
    if part_css := toc_part_css("\n".join(css)):
        css.append(part_css)
    (out_dir / "book.css").write_text("\n".join(css), encoding="utf-8")
    shutil.copyfile(READER_DIR / "reader.js", out_dir / "reader.js")
    for rel in output.js:
        try:
            dst = out_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(base_dir / rel, dst)
        except OSError as exc:
            warnings.append(f"js file {rel!r} could not be copied: {exc}")
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    make_icons(base_dir / output.cover if output.cover else None, str(p.meta.get("title") or ""),
               str(p.meta.get("brand") or ""), out_dir)
    write_manifest(p.meta, str(p.meta.get("lang") or p.theme.meta.get("lang") or "en"), out_dir)
    version = write_service_worker(out_dir, output.offline_images, output.offline_media)

    files = [f for f in out_dir.rglob("*") if f.is_file()]
    return BookReport(files=len(files), bytes=sum(f.stat().st_size for f in files),
                      version=version, warnings=warnings)


_HEAD = ('<link rel="manifest" href="manifest.webmanifest">\n'
         '<link rel="icon" href="icons/icon-192.png">\n'
         '<link rel="apple-touch-icon" href="icons/icon-192.png">\n'
         '<meta name="apple-mobile-web-app-capable" content="yes">\n'
         '<meta name="mobile-web-app-capable" content="yes">')


def make_icons(cover: Path | None, title: str, brand: str, out_dir: Path) -> None:
    """The app icons: the cover cropped to a square from its top, or, without a
    cover, the title's first letter on the brand colour. The maskable icon
    keeps the art inside the safe zone (80%) on the brand colour."""
    from PIL import Image, ImageColor, ImageDraw, ImageFont

    try:
        bg = ImageColor.getrgb(brand)
    except ValueError:
        bg = (43, 33, 24)
    if cover and cover.is_file():
        with Image.open(cover) as im:
            im = im.convert("RGB")
            side = min(im.size)
            art = im.crop(((im.width - side) // 2, 0, (im.width - side) // 2 + side, side))
            art = art.resize((512, 512), Image.LANCZOS)
    else:
        art = Image.new("RGB", (512, 512), bg)
        letter = (title.strip()[:1] or "·").upper()
        font = ImageFont.load_default(size=300)
        ImageDraw.Draw(art).text((256, 256), letter, fill=(255, 255, 255), font=font, anchor="mm")
    icons = out_dir / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    art.save(icons / "icon-512.png", optimize=True)
    art.resize((192, 192), Image.LANCZOS).save(icons / "icon-192.png", optimize=True)
    mask = Image.new("RGB", (512, 512), bg)
    mask.paste(art.resize((410, 410), Image.LANCZOS), (51, 51))
    mask.save(icons / "icon-maskable-512.png", optimize=True)


def write_manifest(meta: dict, lang: str, out_dir: Path) -> None:
    title = str(meta.get("title") or "Book")
    manifest = {
        "name": title, "short_name": title if len(title) <= 24 else title[:23] + "…",
        "description": str(meta.get("subtitle") or ""), "lang": lang,
        "start_url": "./", "scope": "./", "display": "standalone",
        "background_color": "#2b2118", "theme_color": "#2b2118",
        "icons": [
            {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    (out_dir / "manifest.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                                                  encoding="utf-8")


def site_version(out_dir: Path) -> str:
    """The first 12 hex digits of sha256 over every file but sw.js, in path
    order, hashing each path and then its bytes."""
    digest = hashlib.sha256()
    for f in sorted(p for p in out_dir.rglob("*") if p.is_file() and p.name != "sw.js"):
        digest.update(f.relative_to(out_dir).as_posix().encode() + b"\0" + f.read_bytes())
    return digest.hexdigest()[:12]


def write_service_worker(out_dir: Path, offline_images: bool = True,
                         offline_media: bool = False) -> str:
    """Without `offline_images`, `img/` stays out of the precache: the worker
    caches each image the first time it is fetched instead. Without
    `offline_media`, `media/` stays out too, and the worker leaves audio
    requests to the network: a player asks for byte ranges, which a cache
    does not answer."""
    skip = tuple(d for d, keep in (("img/", offline_images), ("media/", offline_media)) if not keep)
    assets = ["./"] + sorted(p.relative_to(out_dir).as_posix()
                             for p in out_dir.rglob("*") if p.is_file() and p.name != "sw.js"
                             and not p.relative_to(out_dir).as_posix().startswith(skip))
    version = site_version(out_dir)
    sw = (READER_DIR / "sw.js").read_text(encoding="utf-8")
    sw = (sw.replace("__VERSION__", version).replace("__ASSETS__", json.dumps(assets, indent=1))
          .replace("__LAZY_IMAGES__", "false" if offline_images else "true")
          .replace("__PRECACHE_MEDIA__", "true" if offline_media else "false"))
    (out_dir / "sw.js").write_text(sw, encoding="utf-8")
    return version
