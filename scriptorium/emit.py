"""emit: the document HTML that scriptorium renders to.

Markdown → preprocessors → parse → emit() gives one HTML flow. CSS
Fragmentation paginates it when WeasyPrint prints it; a browser can show it
as is. Nothing here imports WeasyPrint.
"""

import re

from .highlight import css as hl_css
from .model import Unit
from .theme import Theme

PX_PER_MM = 96 / 25.4


PAGE_W, PAGE_H = 210.0, 297.0


FOOTER_RESERVE = 8.0  # mm kept clear for the stamp on body pages


# named page sizes (mm) — landscape slides for decks
_SIZES = {
    "a4": (210.0, 297.0), "a5": (148.0, 210.0), "letter": (215.9, 279.4),
    "16:9": (254.0, 142.875), "4:3": (254.0, 190.5),
}


def _mm(v, default=14.0) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    m = re.match(r"([\d.]+)", str(v or ""))
    return float(m.group(1)) if m else default


def _page_size(theme: Theme) -> tuple[float, float]:
    s = str(theme.meta.get("page", {}).get("size", "A4")).lower().strip()
    if s in _SIZES:
        return _SIZES[s]
    nums = re.findall(r"([\d.]+)mm", s)
    return (float(nums[0]), float(nums[1])) if len(nums) == 2 else _SIZES["a4"]


def _geom(theme: Theme):
    w, h = _page_size(theme)
    margin = _mm(theme.meta.get("page", {}).get("margin", "14mm"))
    return margin, w - 2 * margin, h - 2 * margin - FOOTER_RESERVE


def _tpl_to_css_content(tpl: str, meta: dict) -> str:
    """Translate a running-head template to a CSS content value.

    '{chapter} — {section}' → 'string(chapter) " — " string(section)'
    '{title}'               → '"My Document Title"'   (static, inlined)
    '{page} / {total}'      → 'counter(page) " / " counter(pages)'
    """
    _CSS_TOKENS = {
        "chapter": "string(chapter)",
        "section": "string(section)",
        "page":    "counter(page)",
        "total":   "counter(pages)",
    }
    def quoted(text) -> str:
        # a document's own strings land here, and a bare `"` ends the CSS string
        text = str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        return f'"{text}"'

    parts = re.split(r"(\{[^}]+\})", tpl)
    css_parts = []
    for part in parts:
        if not part:
            continue
        if part.startswith("{") and part.endswith("}"):
            key = part[1:-1]
            css_parts.append(_CSS_TOKENS.get(key) or quoted(meta.get(key, key)))
        else:
            css_parts.append(quoted(part))
    return " ".join(css_parts)


def _furniture_css(theme: Theme, meta: dict) -> list[str]:
    """Header and footer lines a document sets for itself: frontmatter
    `header:` / `footer:`, each a mapping of `left` / `center` / `right`
    templates, falling back to the theme's own top-level keys. `false` removes
    the theme's default. Every page gets the same line, unlike the verso/recto
    running heads of `masters.body.header`."""
    parts: list[str] = []
    for edge, box, align in (("header", "top", "bottom"), ("footer", "bottom", "top")):
        cfg = meta[edge] if edge in meta else theme.meta.get(edge)
        if not cfg:
            continue
        if not isinstance(cfg, dict):
            raise ValueError(f"{edge}: expected a mapping of left/center/right templates "
                             f"or false, got {cfg!r}")
        pad = "padding-bottom" if box == "top" else "padding-top"
        for slot in ("left", "center", "right"):
            if cfg.get(slot):
                parts.append(
                    f"@page{{@{box}-{slot}{{content:{_tpl_to_css_content(str(cfg[slot]), meta)};"
                    f"font-family:var(--body-font),serif;font-size:9pt;color:var(--muted);"
                    f"vertical-align:{align};{pad}:4mm}}}}"
                )
    return parts


def _emit_css(theme: Theme, meta: dict | None = None) -> str:
    meta = meta or {}
    margin, _, _ = _geom(theme)
    w, h = _page_size(theme)
    masters_cfg = theme.meta.get("masters", {})
    body_furniture = theme.master_furniture("body")
    header_cfg = masters_cfg.get("body", {}).get("header")

    parts: list[str] = []

    # ── keep :root custom properties for themes that reference them ──────────
    parts.append(f":root{{--page-margin:{margin}mm}}")
    parts.append(theme.css)
    parts.append(hl_css())

    # ── @page geometry (CSS paged media — replaces fixed .page divs) ─────────
    # deck: .slide is itself page-sized and carries its own padding, so a page
    # margin here would double-count and fragment every slide onto a second page.
    page_margin = 0 if str(theme.meta.get("mode", "")) == "deck" else margin
    parts.append(f"@page{{size:{w}mm {h}mm;margin:{page_margin}mm}}")
    parts.append("html,body{margin:0;padding:0}")

    # ── named pages for full-page masters (margin 0 so element fills page) ───
    for master_name in masters_cfg:
        if master_name not in ("body",):
            parts.append(f"@page master-{master_name}{{margin:0}}")

    # ── full-page master divs: break to own page, fill the full sheet ────────
    parts.append(
        f".page{{break-before:page;break-after:page;"
        f"width:{w}mm;height:{h}mm;box-sizing:border-box;"
        f"position:relative;overflow:hidden}}"
    )
    # suppress the spurious blank page that would precede the very first element
    parts.append(".page:first-child{break-before:auto}")

    furniture = _furniture_css(theme, meta)

    # ── string-set: let WeasyPrint track chapter / section automatically ──────
    if body_furniture == "stamp" or header_cfg or furniture:
        parts.append("h1{string-set:chapter content()}")
        parts.append("h2{string-set:section content()}")

    # ── page furniture: stamp (footer chapter + page number) ─────────────────
    if body_furniture == "stamp":
        font = "font-family:var(--heading-font),sans-serif;font-size:7.5pt;color:var(--muted)"
        parts.append(
            f"@page{{@bottom-left{{content:string(chapter,first);{font};"
            f"vertical-align:top;padding-top:3mm}}"
            f"@bottom-right{{content:counter(page);{font};"
            f"vertical-align:top;padding-top:3mm}}}}",
        )

    # ── page furniture: running header (verso / recto) ────────────────────────
    if header_cfg:
        font = "font-family:var(--heading-font),sans-serif;font-size:7.5pt;color:var(--muted)"
        verso = header_cfg.get("verso", "")
        recto = header_cfg.get("recto", "")
        if verso:
            css_v = _tpl_to_css_content(verso, meta)
            parts.append(
                f"@page:left{{@top-left{{content:{css_v};{font};"
                f"vertical-align:bottom;padding-bottom:3mm}}}}"
            )
        if recto:
            css_r = _tpl_to_css_content(recto, meta)
            parts.append(
                f"@page:right{{@top-right{{content:{css_r};{font};"
                f"vertical-align:bottom;padding-bottom:3mm}}}}"
            )

    # ── page furniture: the document's own header / footer lines ─────────────
    parts.extend(furniture)

    # ── fragmentation rules ───────────────────────────────────────────────────
    parts.extend([
        # headings always stay with the element that follows them
        "h1,h2,h3,h4,h5,h6{break-after:avoid}",
        # author / theme explicit page break
        ".pagebreak{break-before:page;display:block;height:0;margin:0;padding:0}",
        # unit classes
        ".unit{display:flow-root}",
        ".unit.break-before{break-before:page}",
        ".unit.keep{break-inside:avoid}",
        # figures and captions always travel together
        "figure{break-inside:avoid;margin:4mm 0}",
        "figcaption{font-size:8.5pt;color:var(--muted);margin-top:2mm}",
        # images fill the content column width
        ".unit img,figure img{width:100%;height:auto;display:block}",
    ])

    # ── deck: fixed-size slide boxes (unchanged from before) ─────────────────
    parts.extend([
        f".slide{{width:{w}mm;height:{h}mm;box-sizing:border-box;"
        "overflow:hidden;page-break-after:always}",
        ".slide:last-child{page-break-after:auto}",
    ])

    return "".join(parts)


_LANG_TAG = re.compile(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8})*")


def _lang(theme: Theme, meta: dict) -> str:
    """The document language, which picks WeasyPrint's hyphenation dictionary:
    frontmatter or a project's `lang:`, then the theme's, then English."""
    lang = str(meta.get("lang") or theme.meta.get("lang") or "en")
    if not _LANG_TAG.fullmatch(lang):
        raise ValueError(f"lang: expected a language tag like 'es' or 'en-GB', got {lang!r}")
    return lang


def emit(units: list[Unit], theme: Theme, meta: dict | None = None) -> str:
    """Emit a single-flow HTML document; CSS Fragmentation handles page breaks."""
    meta = meta or {}
    out = [
        f"<!DOCTYPE html><html lang='{_lang(theme, meta)}'><head><meta charset='utf-8'><style>",
        _emit_css(theme, meta),
        "</style></head><body class=\"document\">",
    ]

    for u in units:
        if u.is_break:
            out.append('<div class="pagebreak"></div>')
            continue

        if u.full_page:
            # Full-page master (cover, section opener, back cover…): wrap in a
            # fixed-size .page div assigned to the master's named @page rule.
            # u.html is already fully rendered by the parser (template + content
            # substituted); never re-render here or {{content}} gets lost.
            classes = theme.master_classes(u.master)
            master_page = f"master-{u.master}" if u.master else ""
            page_attr = f' style="page:{master_page}"' if master_page else ""
            out.append(f'<div class="page {classes}"{page_attr}>{u.html}</div>')
            continue

        # Regular flow unit
        cls = ["unit"]
        if u.break_before:
            cls.append("break-before")
        if u.keep_together:
            cls.append("keep")
        out.append(f'<div class="{" ".join(cls)}">{u.html}</div>')

    out.append("</body></html>")
    return "".join(out)


# var names that become CSS custom properties (the customization contract)
_APPEARANCE = {
    "accent", "accent-dark", "brand", "brand-dark", "ink", "muted", "rule",
    "body-font", "heading-font", "mono-font",
    "figure-label", "figure-ref-label", "audio-label", "audio-ref-label",
}


DEFAULT_THEME = "report"


def resolve_theme_name(src: str, explicit: str | None = None) -> str:
    """An explicit theme (`--theme`, or a project's `scriptorium.yaml`) wins; then
    the document's own frontmatter `theme:`; then the default."""
    from .parse import frontmatter

    if explicit:
        return explicit
    return str(frontmatter(src).get("theme") or DEFAULT_THEME)
