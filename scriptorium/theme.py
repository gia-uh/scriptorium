"""Theme loading — directory-backed design systems with inheritance.

A theme is a directory:

    themes/<name>/
      theme.yml          metadata, `extends:`, vars, page geometry, hints, masters
      styles.css         base + component CSS (may @font-face vendored fonts)
      components/*.html   mustache templates ({{prop}} / {{content}})
      masters/*.html      full-page / furniture templates
      assets/…            fonts, images referenced by styles.css (relative urls)

A theme may `extends:` a parent (which may extend its own parent). The chain is
merged base-first: CSS concatenated (child last, so it overrides via the
cascade), components/masters/hints/vars/page merged with the child winning.
Relative `url(assets/…)` in each theme's CSS is rewritten to an absolute
`file://` URL against *that* theme's directory, so vendored fonts resolve
regardless of the document's location.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Installed wheels carry the themes inside the package; a source checkout keeps
# them at the repo root.
_PACKAGED_THEMES = Path(__file__).resolve().parent / "themes"
THEMES_DIR = (_PACKAGED_THEMES if _PACKAGED_THEMES.is_dir()
              else Path(__file__).resolve().parent.parent / "themes")

# Hyphens are allowed in a key because theme vars are kebab-case by convention
# (accent-dark, body-font); without this no var could ever reach a template.
_HOLE = re.compile(r"\{\{\s*([\w.-]+)\s*\}\}")
_SECTION = re.compile(r"\{\{#([\w-]+)\}\}(.*?)\{\{/\1\}\}", re.S)
_URL = re.compile(r"url\(\s*(['\"]?)([^)'\"]+)\1\s*\)")


def _scalar(v) -> str:
    return ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)


def render_template(tpl: str, props: dict) -> str:
    """A small mustache: {{key}} holes and {{#key}}…{{/key}} sections.

    A section iterates when key is a list (each item's fields join the scope, with
    {{_n}} the 1-based index and {{.}} the item itself for scalar lists), renders
    once for a truthy scalar, and drops when empty. Sections nest.
    """
    def section(m):
        key, body = m.group(1), m.group(2)
        val = props.get(key)
        if isinstance(val, list):
            out = []
            for i, item in enumerate(val, 1):
                scope = dict(props)
                scope["_n"] = i
                if isinstance(item, dict):
                    scope.update(item)
                else:
                    scope["."] = item
                out.append(render_template(body, scope))
            return "".join(out)
        return render_template(body, props) if str(val or "").strip() else ""

    tpl = _SECTION.sub(section, tpl)
    return _HOLE.sub(lambda m: _scalar(props.get(m.group(1), "")), tpl)


def _rewrite_urls(css: str, root: Path) -> str:
    """Make relative asset URLs absolute against the theme dir (fonts, images)."""
    def sub(m):
        url = m.group(2).strip()
        if url.startswith(("http:", "https:", "data:", "file:", "/")):
            return m.group(0)
        return f"url('file://{(root / url).resolve()}')"
    return _URL.sub(sub, css)


@dataclass
class Theme:
    name: str
    css: str
    meta: dict = field(default_factory=dict)
    components: dict = field(default_factory=dict)  # name -> template html
    masters: dict = field(default_factory=dict)  # name -> template html
    hints: dict = field(default_factory=dict)  # name -> {keep_together, master, ...}
    vars: dict = field(default_factory=dict)  # theme var defaults

    def is_component(self, name: str) -> bool:
        return name in self.components

    def render(self, name: str, props: dict) -> str:
        return render_template(self.components[name], props)

    def hint(self, name: str, key: str, default=None):
        return self.hints.get(name, {}).get(key, default)

    def master_of(self, name: str) -> str | None:
        return self.hint(name, "master")

    def master_template(self, master: str) -> str:
        return self.masters.get(master, "{{content}}")

    def master_classes(self, master: str) -> str:
        return self.meta.get("masters", {}).get(master, {}).get("classes", "")

    def master_furniture(self, master: str) -> str:
        return self.meta.get("masters", {}).get(master, {}).get("furniture", "none")


def _read_dir(path: Path) -> dict:
    out = {}
    if path.is_dir():
        for f in path.glob("*.html"):
            out[f.stem] = f.read_text(encoding="utf-8").strip()
    return out


def is_theme_path(name: str) -> bool:
    """A theme named with a `/`, or starting with `.` or `~`, is a directory;
    any other name is one of scriptorium's own themes."""
    return "/" in name or name.startswith((".", "~"))


def theme_dir(name: str, base: Path | None = None) -> Path:
    """Where a theme lives: a path resolves against `base` (the document's or
    project's directory), a bare name against scriptorium's themes."""
    if not is_theme_path(name):
        return THEMES_DIR / name
    path = Path(name).expanduser()
    if not path.is_absolute():
        path = (base or Path.cwd()) / path
    return path.resolve()


def _chain(name: str, base: Path | None = None) -> list[Path]:
    """Resolve the extends-chain, base-first, with a cycle guard. A path in
    `extends:` resolves against the directory of the theme that names it."""
    chain, seen, cur = [], set(), theme_dir(name, base)
    while cur and cur not in seen:
        seen.add(cur)
        root = cur
        theme_yml = root / "theme.yml"
        if not theme_yml.is_file():
            raise FileNotFoundError(f"no theme at {root} (no theme.yml)")
        meta = yaml.safe_load(theme_yml.read_text(encoding="utf-8")) or {}
        chain.append((root, meta))
        parent = meta.get("extends")
        cur = theme_dir(str(parent), root) if parent else None
    chain.reverse()
    return chain


def load_theme(name: str = "report", base: Path | None = None) -> Theme:
    """Load a theme by name, or from a directory (see `theme_dir`)."""
    css_parts, components, masters, hints, vars = [], {}, {}, {}, {}
    meta: dict = {}
    if is_theme_path(name):
        # the resolved path, so a later _chain(theme.name) finds the same theme
        name = str(theme_dir(name, base))
    for root, m in _chain(name):
        css_file = root / "styles.css"
        if css_file.exists():
            css_parts.append(_rewrite_urls(css_file.read_text(encoding="utf-8"), root))
        components.update(_read_dir(root / "components"))
        masters.update(_read_dir(root / "masters"))
        hints.update(m.get("components", {}) or {})
        vars.update(m.get("vars", {}) or {})
        for k, v in m.items():
            if k in ("masters", "page", "html-refs") and isinstance(v, dict):
                meta.setdefault(k, {}).update(v)
            elif k not in ("components", "vars", "extends"):
                meta[k] = v
    meta["masters"] = meta.get("masters", {})
    return Theme(name=name, css="\n".join(css_parts), meta=meta,
                 components=components, masters=masters, hints=hints, vars=vars)
