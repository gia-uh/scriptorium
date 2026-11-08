"""Project model: a scriptorium.yaml is just a theme + vars + a file list.

Assembly = concatenate the listed files (each chapter starts a fresh page) and
merge vars. No structural schema — numbering, cross-references, and the table of
contents live in the theme's CSS (CSS counters, `target-counter`, `target-text`,
`leader()`), which WeasyPrint resolves at render time.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_VAR = re.compile(r"\{\{\s*([\w.-]+)\s*\}\}")


class ProjectError(ValueError):
    """A scriptorium.yaml that cannot be built as written."""


@dataclass
class Output:
    """One render of a project: a PDF (`file`), an HTML book or a docs site (`dir`)."""
    name: str
    format: str
    file: str | None = None
    dir: str | None = None
    page: dict | None = None
    vars: dict = field(default_factory=dict)
    cover: str | None = None
    image_max_width: int = 1600
    image_quality: int = 80
    offline_images: bool = True
    offline_media: bool = False
    js: list[str] = field(default_factory=list)
    css: list[str] = field(default_factory=list)
    repo_url: str | None = None
    logo: str | None = None
    favicon: str | None = None
    version: str | None = None  # a version string, or "auto"
    palette: dict = field(default_factory=dict)  # primary, accent, scheme
    typography: str = "docs"  # "docs" | "theme"
    edit_path: str | None = None  # the docs folder inside the repository, for "Edit this page"
    footer: str | None = None  # text at the foot of every page


# the keys each format accepts; anything else is a typo or a key for the
# other format, and silently ignoring it would render the wrong book
_OUTPUT_KEYS = {
    "pdf": {"format", "file", "page", "vars"},
    "html": {"format", "dir", "vars", "cover", "image-max-width", "image-quality",
             "offline-images", "offline-media", "js", "css"},
    "docs": {"format", "dir", "vars", "image-max-width", "image-quality", "js", "css", "repo-url",
             "logo", "favicon", "version", "palette", "typography", "edit-path", "footer"},
}
_PALETTE_KEYS = {"primary", "accent", "scheme"}
_SCHEMES = ("auto", "light", "dark")


def _outputs(spec) -> list[Output]:
    if spec is None:
        return [Output(name="pdf", format="pdf", file="book.pdf")]
    if not isinstance(spec, dict):
        raise ProjectError("outputs: expected a mapping of output names to settings")
    outs = []
    for name, cfg in spec.items():
        cfg = cfg or {}
        fmt = cfg.get("format")
        if fmt not in _OUTPUT_KEYS:
            raise ProjectError(f"outputs.{name}: format {fmt!r} is not one of pdf, html, docs")
        unknown = sorted(set(cfg) - _OUTPUT_KEYS[fmt])
        if unknown:
            raise ProjectError(f"outputs.{name}: unknown key(s) for a {fmt} output: "
                               + ", ".join(unknown))
        palette = cfg.get("palette") or {}
        if not isinstance(palette, dict) or set(palette) - _PALETTE_KEYS:
            raise ProjectError(f"outputs.{name}.palette: expected a mapping of "
                               + ", ".join(sorted(_PALETTE_KEYS)))
        if palette.get("scheme", "auto") not in _SCHEMES:
            raise ProjectError(f"outputs.{name}.palette.scheme: expected one of " + ", ".join(_SCHEMES))
        if cfg.get("typography", "docs") not in ("docs", "theme"):
            raise ProjectError(f"outputs.{name}.typography: expected docs or theme")
        outs.append(Output(
            name=name, format=fmt,
            file=cfg.get("file", f"{name}.pdf") if fmt == "pdf" else None,
            dir=cfg.get("dir", name) if fmt in ("html", "docs") else None,
            page=cfg.get("page"), vars=cfg.get("vars") or {}, cover=cfg.get("cover"),
            image_max_width=int(cfg.get("image-max-width", 1600)),
            image_quality=int(cfg.get("image-quality", 80)),
            offline_images=bool(cfg.get("offline-images", True)),
            offline_media=bool(cfg.get("offline-media", False)),
            js=list(cfg.get("js") or []), css=list(cfg.get("css") or []),
            repo_url=cfg.get("repo-url"), logo=cfg.get("logo"), favicon=cfg.get("favicon"),
            version=None if cfg.get("version") is None else str(cfg["version"]),
            palette={k: str(v) for k, v in palette.items()},
            typography=cfg.get("typography", "docs"),
            edit_path=cfg.get("edit-path"), footer=cfg.get("footer"),
        ))
    return outs


@dataclass
class Project:
    theme: str
    vars: dict
    src: str  # assembled markdown
    base_dir: Path
    code_root: str | None = None
    meta: dict = field(default_factory=dict)  # content keys: bibliography, nocite
    outputs: list[Output] = field(default_factory=list)
    files: list[str] = field(default_factory=list)  # the chapter files, in order


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---", 3)
        if end >= 0:
            nl = text.find("\n", end + 1)
            return text[nl + 1 :] if nl >= 0 else ""
    return text


def substitute(text: str, vars: dict) -> str:
    return _VAR.sub(lambda m: str(vars.get(m.group(1), m.group(0))), text)


def load(path: str | Path) -> Project:
    path = Path(path)
    spec = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    base = path.parent
    theme = spec.get("theme", "book")
    vars = spec.get("vars", {}) or {}
    # content keys, distinct from `vars` (which is the appearance contract and
    # the target of {{substitution}}): a bibliography is content, not styling,
    # and where the notes collect is structure, not styling either.
    meta = {k: spec[k]
            for k in ("bibliography", "nocite", "glossary", "css", "footnotes",
                      "header", "footer", "lang", "base-url", "html-refs",
                      "timeline", "timeline-group", "timeline-group-max", "execute")
            if k in spec}

    bodies = []
    for i, rel in enumerate(spec.get("files", [])):
        body = _strip_frontmatter((base / rel).read_text(encoding="utf-8"))
        if i > 0:
            bodies.append("\\newpage")  # each file starts a fresh page
        bodies.append(body.strip())
    src = substitute("\n\n".join(bodies), vars)

    code_root = (spec.get("code") or {}).get("root")
    return Project(theme=theme, vars=vars, src=src, base_dir=base,
                   code_root=code_root, meta=meta, outputs=_outputs(spec.get("outputs")),
                   files=[str(f) for f in spec.get("files", [])])
