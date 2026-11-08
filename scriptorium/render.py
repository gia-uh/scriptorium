"""Markdown → HTML: everything scriptorium does before printing.

`render_pdf` (galley.py) prints the result with WeasyPrint. `render_html`
returns it, so a screen consumer gets every Markdown feature without the PDF
stack.
"""

from dataclasses import dataclass, field
from pathlib import Path

from .emit import _APPEARANCE, emit, resolve_theme_name
from .execute import ExecEnv
from .freeze import Freeze
from .model import Unit
from .tangle import write as tangle_write
from .theme import Theme, load_theme


@dataclass
class Prepared:
    units: list[Unit]
    theme: Theme
    meta: dict
    warnings: list[str] = field(default_factory=list)
    env: ExecEnv | None = None


def prepare(src: str, *, theme_name: str | None = None, cwd: str | None = None,
            execute: bool = True, vars: dict | None = None,
            code_root: str | None = None,
            project_meta: dict | None = None, frozen: bool = False,
            page: dict | None = None, for_screen: bool = False, site_html: bool = False) -> Prepared:
    """Run the preprocessors and the parser: the units, theme and metadata a
    document renders from."""
    from .parse import frontmatter, parse

    theme = load_theme(resolve_theme_name(src, theme_name), Path(cwd) if cwd else None)
    if page:
        # one output's page size and margin; a copy, so no other render sees it
        theme.meta["page"] = {**theme.meta.get("page", {}), **page}
    # theme var defaults, overridden by project vars, then by per-doc frontmatter
    merged = {**theme.vars, **(vars or {})}
    # a project's chapters have had their frontmatter stripped, so project_meta
    # is the only route in for its content keys (bibliography, nocite)
    meta = {**merged, **(project_meta or {}), **frontmatter(src)}
    # a single document carries its vars in a frontmatter `vars:` block — same
    # contract as scriptorium.yaml, and the last word on appearance.
    merged = {**merged, **(meta.get("vars") or {})}

    def _css_val(k, v):
        v = str(v)
        # multi-word font-family names must be quoted to be a valid CSS value
        if k.endswith("-font") and " " in v and v[0] not in "'\"":
            v = f"'{v}'"
        # a label ends up inside a `content:`, which only takes a quoted string
        elif k.endswith("-label") and v[:1] not in ("'", '"'):
            v = '"' + v.replace('"', '\\"') + '"'
        return f"--{k}:{v};"

    overrides = "".join(_css_val(k, merged[k]) for k in _APPEARANCE if k in merged)
    if overrides:
        theme.css += f":root{{{overrides}}}"

    # A project's own stylesheet. load_theme resolves only from scriptorium's
    # themes directory, so without this a book with any custom styling has to
    # author a theme inside this repo. Appended after the theme's own rules, so
    # it wins on equal specificity.
    css_warnings: list[str] = []
    css_spec = meta.get("css")
    for rel in [css_spec] if isinstance(css_spec, str) else list(css_spec or []):
        path = Path(rel)
        if cwd and not path.is_absolute():
            path = Path(cwd) / path
        try:
            theme.css += "\n" + path.read_text(encoding="utf-8")
        except OSError as exc:
            css_warnings.append(f"css file {rel!r} could not be read: {exc}")

    # freeze cache serves both executed code and rendered math
    freeze = Freeze(Path(cwd) / ".scriptorium" / "freeze.json") if cwd else None
    from . import mathrender
    mathrender.set_freeze(freeze)

    env = None
    if execute or frozen:
        # tangle export= blocks first so executed blocks can import them; a
        # frozen render writes nothing and runs nothing
        stem = str(meta.get("stem", "doc"))
        if cwd and not frozen:
            tangle_write(src, cwd, doc_stem=stem)
        pythonpath = []
        if cwd and code_root:
            pythonpath = [str((Path(cwd) / code_root).resolve())]
        env = ExecEnv(cwd=cwd, freeze=freeze, pythonpath=pythonpath, frozen=frozen, site_html=site_html)
        settings = meta.get("execute") if isinstance(meta.get("execute"), dict) else {}
        if settings.get("interpreters"):
            env.interpreters.update(settings["interpreters"])
        if settings.get("timeout"):
            env.timeout = float(settings["timeout"])
        if settings.get("freeze"):
            if settings["freeze"] not in ("block", "file"):
                raise ValueError(f"execute.freeze is {settings['freeze']!r}; it takes block or file")
            env.freeze_scope = settings["freeze"]

    from .parse import fill_toc
    from .footnotes import process_footnotes, resolve_footnote_mode
    from .citations import process_citations
    from .glossary import process_glossary
    from .timeline import process_timeline

    # Citations run after footnotes on purpose: a [@key] written inside a note
    # body has by then been moved to where the note actually renders, so it is
    # numbered by reading order rather than by where its definition happened to
    # sit in the source. The glossary runs last for exactly the same reason.
    mode = resolve_footnote_mode(meta, theme.meta)
    if for_screen and mode == "page":
        # a page-floated note needs paged media; on a screen it ends its chapter
        mode = "chapter"
    src, warnings = process_footnotes(src, mode)
    src, cite_warnings = process_citations(src, meta)
    src, gloss_warnings = process_glossary(src, meta, Path(cwd) if cwd else None)
    src, tl_warnings = process_timeline(src, meta, Path(cwd) if cwd else None)
    warnings = css_warnings + warnings + cite_warnings + gloss_warnings + tl_warnings
    units = parse(src, theme, env, meta=meta)
    from .media import check_audio, link_audio
    if cwd:
        check_audio(units, Path(cwd))
    link_audio(units, str(meta.get("base-url", "")))
    if env is not None:
        warnings = warnings + env.warnings
    if not for_screen:  # the HTML book has its own contents panel
        units = fill_toc(units, depth=int(meta.get("toc_depth", 2)))

    return Prepared(units=units, theme=theme, meta=meta, warnings=warnings, env=env)


def render_html(src: str, **kw) -> tuple[str, list[str]]:
    """The HTML document `src` renders to, and the warnings. Never needs WeasyPrint."""
    p = prepare(src, **kw)
    if str(p.theme.meta.get("mode", "")) == "deck":
        raise ValueError("deck themes are measured by WeasyPrint and have no HTML "
                         "form; render them to PDF (install scriptorium[pdf])")
    return emit(p.units, p.theme, p.meta), p.warnings
