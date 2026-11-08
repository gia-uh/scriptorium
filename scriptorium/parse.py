"""Parse Markdown + `:::` components + code fences into a flat list of Units.

Base: CommonMark + tables (markdown-it-py). Components and page masters come
from the active theme. Code fences carry directives (run / export= / name=,
see fence.py): a run block executes in a subshell and its stdout is spliced
back — as monospace (Quarto `{lang}`) or as re-parsed markdown (native `{run}`).
An optional ExecEnv enables execution; without it, code is shown, not run.
"""

import hashlib
import re
from pathlib import Path
from html import escape

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.attrs import attrs_block_plugin, attrs_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin

from .bundles import place, split
from .fence import EXT, parse_fence
from .highlight import highlight
from .mathrender import render_display, render_inline
from .media import is_audio
from .model import Unit
from .theme import Theme, load_theme, render_template

_md = (
    MarkdownIt("commonmark")
    .enable("table")
    .use(dollarmath_plugin, allow_space=True, double_inline=True)
    .use(attrs_plugin)
    .use(attrs_block_plugin)
)

# @type-id cross-references -> empty anchors; the theme's CSS fills the text
# via target-counter/target-text. The prefix must be one we know: anything else
# is ordinary prose (a BibTeX key, a handle) and rewriting it would delete it
# from the page, since an anchor with no target renders empty. The free @key
# namespace is reserved for a future citations feature.
_REF_PREFIXES = frozenset({"fig", "tbl", "sec", "eq", "lst", "thm", "chap", "aud"})
_REF = re.compile(r"(?<![\w`])@([a-zA-Z][\w]*)-([\w-]+)")


def _rewrite_refs(text: str) -> str:
    def sub(m):
        kind, target = m.group(1), m.group(2)
        if kind not in _REF_PREFIXES:
            return m.group(0)
        return f'<a class="ref-{kind}" href="#{kind}-{target}"></a>'

    return _REF.sub(sub, text)
_md.renderer.rules["math_inline"] = lambda t, i, o, e: render_inline(t[i].content)
_md.renderer.rules["math_inline_double"] = lambda t, i, o, e: render_display(t[i].content)
_md.renderer.rules["math_block"] = lambda t, i, o, e: render_display(t[i].content)
_md.renderer.rules["math_block_label"] = lambda t, i, o, e: render_display(t[i].content)


def _mark_audio_figures(state):
    """An audio link alone in its paragraph becomes a figure: hide the <p>.

    A <figure> inside a <p> is invalid HTML, so an audio link in running text
    stays a bare player and only a paragraph holding nothing else is unwrapped.
    """
    toks = state.tokens
    for i in range(1, len(toks) - 1):
        kids = toks[i].children or []
        if (toks[i].type == "inline" and toks[i - 1].type == "paragraph_open"
                and len(kids) == 1 and kids[0].type == "image"
                and is_audio(kids[0].attrGet("src") or "")):
            toks[i - 1].hidden = toks[i + 1].hidden = True
            kids[0].meta["figure"] = True


_default_image = _md.renderer.rules["image"]


def _image(tokens, idx, options, env):
    """An audio link renders a player; any other image the default way. An
    audio figure keeps only an `{#id}`: classes are dropped, and so is an id
    on a bare player in running text."""
    tok = tokens[idx]
    src = tok.attrGet("src") or ""
    if not is_audio(src):
        return _default_image(tokens, idx, options, env)
    alt = escape(_md.renderer.renderInlineAsText(tok.children or [], options, env))
    if not tok.meta.get("figure"):
        title = f' title="{alt}"' if alt else ""
        return f'<audio controls preload="none" src="{escape(src)}"{title}></audio>'
    fid = tok.attrGet("id")
    id_attr = f' id="{escape(fid)}"' if fid else ""
    caption = f"<figcaption>{alt}</figcaption>" if alt else ""
    return (f'<figure class="audio"{id_attr}>'
            f'<audio controls preload="none" src="{escape(src)}"></audio>'
            f"{caption}</figure>\n")


_md.core.ruler.after("inline", "audio_figure", _mark_audio_figures)
_md.renderer.rules["image"] = _image

_TRANSPARENT = {"tinted", "group"}
_FENCE = re.compile(r"^(:{3,})\s*(.*?)\s*$")
_CODEFENCE = re.compile(r"^(`{3,}|~{3,})(.*)$")
_ATTR = re.compile(r"""(\#[\w-]+)|(\.[\w-]+)|(\w[\w-]*)=("[^"]*"|'[^']*'|\S+)""")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_HEAD_ATTR = re.compile(r"^(\s{0,3}#{1,6}\s+.*?)\s*\{([^}]*)\}\s*$")


_TAGS = re.compile(r"<[^>]+>")


def _slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_]+", "-", s) or "sec"


def _heading_unit(block: str) -> Unit:
    """Render a heading; assign {#id .class} attrs (auto-slug id if none)."""
    level = len(re.match(r"^\s{0,3}(#{1,6})", block).group(1))
    src, hid, classes = block, None, []
    m = _HEAD_ATTR.match(block)
    if m:
        src = m.group(1)
        idm = re.search(r"#([\w:.-]+)", m.group(2))
        classes = re.findall(r"\.([\w-]+)", m.group(2))
        hid = idm.group(1) if idm else None
    label = _HEADING.match(src).group(1) if _HEADING.match(src) else None
    if label:
        # The label feeds the TOC and every other text consumer, so it has to be
        # text. Inline HTML reaches a heading legitimately — the glossary
        # pre-processor puts an anchor there — and escaping it into the TOC
        # prints the markup instead of the words.
        label = _TAGS.sub("", label)
    if hid is None and label:
        hid = _slug(label)
    attr = (f' id="{hid}"' if hid else "") + (f' class="{" ".join(classes)}"' if classes else "")
    html = _md.render(_rewrite_refs(src))
    if attr:
        html = re.sub(r"^<(h[1-6])(\s|>)", rf"<\1{attr}\2", html, count=1)
    return Unit(html=html, keep_together=False, name="prose",
                heading=label, heading_level=level, heading_id=hid,
                heading_classes=tuple(classes))


def _parse_info(info: str):
    name, mods, attrs = "", [], {}
    brace = info.find("{")
    head, tail = (info[:brace], info[brace:]) if brace >= 0 else (info, "")
    tokens = head.split()
    if tokens:
        name, mods = tokens[0], tokens[1:]
    for m in _ATTR.finditer(tail):
        if m.group(1):
            attrs["id"] = m.group(1)[1:]
        elif m.group(2):
            mods.append(m.group(2)[1:])
        elif m.group(3):
            val = m.group(4)
            if val and val[0] in "\"'":
                val = val[1:-1]
            attrs[m.group(3)] = val
    return name, mods, attrs


def _split_nodes(src: str):
    """Top-level scan into ('md', text) and ('container', name, mods, attrs, inner)."""
    lines = src.split("\n")
    nodes, buf, i = [], [], 0
    while i < len(lines):
        m = _FENCE.match(lines[i])
        if m and m.group(2):
            if buf:
                nodes.append(("md", "\n".join(buf)))
                buf = []
            fence, info = m.group(1), m.group(2)
            name, mods, attrs = _parse_info(info)
            depth, j, inner = 1, i + 1, []
            while j < len(lines):
                m2 = _FENCE.match(lines[j])
                if m2:
                    if not m2.group(2) and len(m2.group(1)) >= len(fence):
                        depth -= 1
                        if depth == 0:
                            break
                    elif m2.group(2):
                        depth += 1
                inner.append(lines[j])
                j += 1
            nodes.append(("container", name, mods, attrs, "\n".join(inner)))
            i = j + 1
        else:
            buf.append(lines[i])
            i += 1
    if buf:
        nodes.append(("md", "\n".join(buf)))
    return nodes


_LIST_ITEM = re.compile(r"^\s{0,3}(?:\d+[.)]|[-*+])\s")
_INDENTED = re.compile(r"^(?: {2,}|\t)\S")


def _regroup_lists(blocks: list[str]) -> list[str]:
    """Re-join blank-line-separated blocks that belong to one list.

    Prose is split on blank lines so each paragraph measures independently, but
    a *loose* list is blank-line separated by definition. Splitting it hands
    markdown-it one item per render call, and each becomes its own `<ol>`
    starting at 1 — so `1. 2. 3.` renders as `1. 1. 1.`, and a continuation
    paragraph detaches from the item it belongs to.

    A run continues while blocks are either list items or indented
    continuations. The joined run is one unit, which is exactly how a *tight*
    list already behaves, so this introduces no new pagination case.
    """
    out: list[str] = []
    run: list[str] = []

    def close():
        if run:
            out.append("\n\n".join(run))
            run.clear()

    for b in blocks:
        if _LIST_ITEM.match(b):
            run.append(b)
        elif run and _INDENTED.match(b):
            run.append(b)
        else:
            close()
            out.append(b)
    close()
    return out


def _split_md(text: str):
    """Split an md region into ('prose', text) and ('code', info, body), keeping
    fenced code blocks whole (they may contain blank lines)."""
    lines = text.split("\n")
    items, buf, i = [], [], 0

    def flush():
        # strip HTML comments across the whole prose run (before blank-splitting)
        # so a multi-line <!-- --> is never cut into unbalanced halves. Code
        # fences are already separated out, so their contents are untouched.
        text = re.sub(r"<!--.*?-->", "", "\n".join(buf), flags=re.S)
        for b in _regroup_lists(re.split(r"\n\s*\n", text)):
            if b.strip():
                items.append(("prose", b))
        buf.clear()

    while i < len(lines):
        m = _CODEFENCE.match(lines[i])
        if m:
            flush()
            fence, info = m.group(1), m.group(2)
            close = re.compile(rf"^{re.escape(fence[0])}{{{len(fence)},}}\s*$")
            j, body = i + 1, []
            while j < len(lines) and not close.match(lines[j]):
                body.append(lines[j])
                j += 1
            items.append(("code", info, "\n".join(body)))
            i = j + 1
        else:
            buf.append(lines[i])
            i += 1
    flush()
    return items


def _unwrap_p(html: str) -> str:
    """Drop the <p> wrapper from a single-paragraph component body.

    Guarded on there being exactly one paragraph. With re.S the greedy `.*`
    spans a multi-paragraph body end to end, so an unguarded sub strips the
    first opening tag and the last closing tag and leaves everything between
    unbalanced — the first paragraph escapes its <p> and stops matching any
    `p` rule the theme wrote for the component.
    """
    html = html.strip()
    if html.count("<p>") != 1:
        return html
    return re.sub(r"^<p>(.*)</p>$", r"\1", html, flags=re.S)


def _scalar(v) -> str:
    return ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)


def _render_fragment(src: str, theme: Theme, meta: dict | None = None) -> str:
    parts = []
    for node in _split_nodes(src):
        if node[0] == "md":
            if node[1].strip():
                parts.append(_md.render(_rewrite_refs(node[1])))
        else:
            _, name, mods, attrs, inner = node
            parts.append(_component_html(name, mods, attrs, inner, theme, meta))
    return "".join(parts)


def _component_html(name, mods, attrs, inner, theme: Theme, meta: dict | None = None) -> str:
    if name == "keep":
        return f'<div class="keep">{_render_fragment(inner, theme, meta)}</div>'
    if theme.is_component(name):
        # component props default to the document's metadata (author, abstract…),
        # overridden by explicit attrs; content is the rendered body. Structured
        # values (author lists) pass through raw for template sections.
        props = dict(meta or {})
        props.update(attrs)
        props.setdefault("variant", " ".join(mods))
        props["content"] = _unwrap_p(_render_fragment(inner, theme, meta))
        return theme.render(name, props)
    classes = " ".join(([name] if name else []) + mods)
    return f'<div class="{classes}">{_render_fragment(inner, theme, meta)}</div>'


def _tangle_target(f, stem: str) -> str:
    return f.export or f"{stem}.{EXT.get(f.lang, 'txt')}"


def _code_units(info, body, theme, env, cursor, stem) -> list[Unit]:
    f = parse_fence(info)
    units: list[Unit] = []
    # advance the per-file line cursor for any block that tangles (even if hidden)
    label = ""
    if f.tangles:
        path = _tangle_target(f, stem)
        n = body.count("\n") + 1 if body else 0
        start = cursor.get(path, 0) + 1
        end = start + n - 1
        cursor[path] = end
        label = f'<span class="code-file">{escape(path)} · L{start}–{end}</span>'
    elif f.title:
        label = f'<span class="code-file">{escape(f.title)}</span>'
    if f.echo:
        block = f'<span class="code-src">{highlight(body, f.lang)}</span>'
        lang = f' data-lang="{escape(f.lang)}"' if f.lang else ""
        units.append(Unit(html=f'<div class="codeblock"{lang}>{label}{block}</div>', name="code",
                          splittable=True, code_src=body, code_lang=f.lang, code_label=label))
    if f.run and env is not None:
        res = env.run(body, f.lang, cont=f.cont)
        if res.failed:
            stdout = "".join(p if isinstance(p, str) else p["data"].get("text/plain", "") + "\n"
                             for p in split(res.stdout))
            stdout = stdout if not stdout or stdout.endswith("\n") else stdout + "\n"
            units.append(Unit(
                html=(f'<pre class="output error">{escape(stdout)}'
                      f'<span class="stderr">{escape(res.stderr)}</span></pre>'),
                name="output"))
        elif res.stdout.strip():
            parts = split(res.stdout)
            shown = [p for p in parts if isinstance(p, dict)]
            if f.output_mode == "code":
                text = "".join(p if isinstance(p, str) else p["data"].get("text/plain", "") + "\n" for p in parts)
                units.append(Unit(html=f'<pre class="output">{escape(text)}</pre>', name="output"))
            else:  # asis: stdout is raw markdown, re-parsed; display bundles become files and figures
                if (f.caption or f.id) and len(shown) != 1:
                    env.warnings.append(f"caption= and id= on a block apply when it displays exactly one "
                                        f"thing; this block displayed {len(shown)}")
                fallback = {"caption": f.caption, "id": f.id} if len(shown) == 1 else {}
                outdir = Path(env.cwd or ".")
                site = getattr(env, "site_html", False)
                text = "".join(p if isinstance(p, str) else place(p, outdir, fallback, site) for p in parts)
                units.extend(parse(text, theme, env, nested=True))
    return units


def frontmatter(src: str) -> dict:
    if src.startswith("---\n"):
        end = src.find("\n---", 3)
        if end >= 0:
            try:
                return yaml.safe_load(src[4:end]) or {}
            except yaml.YAMLError:
                return {}
    return {}


def _body(src: str) -> str:
    if src.startswith("---\n"):
        end = src.find("\n---", 3)
        if end >= 0:
            nl = src.find("\n", end + 1)
            return src[nl + 1 :] if nl >= 0 else ""
    return src


def fill_toc(units: list[Unit], depth: int = 2) -> list[Unit]:
    """Replace each `::: toc` placeholder with one unit per heading (so the TOC
    paginates). Page numbers are added by theme CSS via target-counter, on the
    entry's `.toc-pg` span and not on the link itself: the link is a flex
    container, and WeasyPrint 70 resolves target-counter() to 0 in the
    ::before/::after of a flex container."""
    if not any(u.name == "toc" for u in units):
        return units
    heads = [u for u in units
             if u.heading_id and 1 <= u.heading_level <= depth
             and "unlisted" not in u.heading_classes]
    out: list[Unit] = []
    for u in units:
        if u.name != "toc":
            out.append(u)
            continue
        out.append(Unit(html=f'<div class="toc-h">{escape(u.code_src or "Contents")}</div>', name="toc"))
        for h in heads:
            cls = f"toc-entry toc-l{h.heading_level}"
            out.append(Unit(
                html=(f'<a class="{cls}" href="#{h.heading_id}">'
                      f'<span class="toc-txt">{escape(h.heading)}</span>'
                      f'<span class="toc-lead"></span>'
                      f'<span class="toc-pg" data-ref="#{h.heading_id}"></span></a>'),
                name="toc-entry"))
    return out


def _file_salts(body: str) -> list[str]:
    """The hash of each stretch of `body` between page breaks: one per file of a
    project, which starts each file on a new page. It walks the same splits as
    `parse`, so its breaks are the ones where `parse` resets the session."""
    files, cur = [], []
    for node in _split_nodes(body):
        if node[0] == "md":
            for kind, *rest in _split_md(node[1]):
                if kind != "code" and rest[0].strip() == r"\newpage":
                    files.append(cur)
                    cur = []
                else:
                    cur.append(repr(rest))
        elif node[1] == "newpage":
            files.append(cur)
            cur = []
        else:
            cur.append(repr(node))
    files.append(cur)
    return [hashlib.sha256("\0".join(f).encode()).hexdigest() for f in files]


def parse(src: str, theme: Theme | None = None, env=None, meta: dict | None = None,
          nested: bool = False) -> list[Unit]:
    theme = theme or load_theme()
    meta = frontmatter(src) if meta is None else meta
    stem = str(meta.get("stem", "doc"))
    cursor: dict[str, int] = {}
    units: list[Unit] = []
    # freeze per file: each block's key carries its file's hash; a nested parse
    # (a transparent component) stays inside its file
    salts = None
    if env is not None and env.freeze_scope == "file" and not nested:
        salts = iter(_file_salts(_body(src)))
        env.salt = next(salts)
    for node in _split_nodes(_body(src)):
        if node[0] == "md":
            for kind, *rest in _split_md(node[1]):
                if kind == "code":
                    units.extend(_code_units(rest[0], rest[1], theme, env, cursor, stem))
                    continue
                block = rest[0]
                if block.strip() == r"\newpage":
                    if env is not None:
                        env.reset_session()  # new file/chapter -> fresh exec state
                        if salts is not None:
                            env.salt = next(salts)
                    units.append(Unit(is_break=True, name="newpage"))
                    continue
                if _HEADING.match(block):
                    units.append(_heading_unit(block))
                else:
                    units.append(Unit(html=_md.render(_rewrite_refs(block)),
                                      keep_together=False, name="prose"))
        else:
            _, name, mods, attrs, inner = node
            if name == "newpage":
                if env is not None:
                    env.reset_session()  # new file/chapter -> fresh exec state
                    if salts is not None:
                        env.salt = next(salts)
                units.append(Unit(is_break=True, name="newpage"))
                continue
            if name in _TRANSPARENT:
                units.extend(parse(inner, theme, env, meta=meta, nested=True))
                continue
            if name == "toc":  # filled after the whole doc is parsed (see fill_toc)
                units.append(Unit(name="toc", html="", code_src=attrs.get("title", "Contents")))
                continue
            master = theme.master_of(name)
            if master:
                props = dict(meta)  # all vars/meta reach masters (structured, raw)
                props.update(attrs)
                props.setdefault("variant", " ".join(mods))
                props["content"] = _unwrap_p(_render_fragment(inner, theme, meta))
                html = render_template(theme.master_template(master), props)
                units.append(Unit(html=html, full_page=True, master=master, name=name))
            else:
                keep = name == "keep" or theme.hint(name, "keep_together", bool(name))
                units.append(
                    Unit(html=_component_html(name, mods, attrs, inner, theme, meta),
                         keep_together=bool(keep), name=name or "div")
                )
    return units
