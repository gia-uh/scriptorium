# Scriptorium — Design

**Status:** design (pre-implementation) · **Date:** 2026-07-28 · **Author:** Alex + Claude

A Markdown-native document engine that replaces Quarto for everything except
scientific papers (where LaTeX still wins). One source document fans out to a
lean **HTML book**, an **exact-geometry paginated PDF**, and an **EPUB**; it
**tangles** code to real source files (subsuming [illiterate](https://github.com/apiad/illiterate));
and it **executes** code blocks in place. Its distinguishing capability is exact page geometry: per-page masters,
components that never split, and break rules the author controls.

> **Status note (2026-09-27).** Sections 7.1 and 7.2 below describe a Python
> bin-packer that **no longer runs for documents**. Since `b99dc6a` (2026-08-02)
> document themes paginate through WeasyPrint's CSS Fragmentation Module, and
> `measure`/`pack` are reserved for `deck` themes. The text is kept because it
> still describes the deck path; read it with that restriction, and see §7.4.

The reference bar for output quality is a hand-crafted, design-system report —
~100 hand-placed A4 pages with covers, section openers, KPI tiles, finding
cards, and the rest of a rich component vocabulary. The goal: author that with
pure Markdown + a little HTML, and let the engine place the pages.

---

## 0. Table of contents

1. Vision and scope
2. Architecture: one model, three renderers, an execution stage
3. Authoring language (the component grammar)
4. Themes and the component contract
5. Execution runtime
6. Tangle (illiterate subsumed)
7. The `galley` pagination engine
8. Page masters and PDF furniture
9. Cross-references and numbering
10. Math pipeline
11. Project / book model
12. Renderers: HTML, PDF, EPUB
13. Citations and bibliography
14. CLI and build workflow
15. Extensibility
16. Technology stack and repo layout
17. Phased delivery (vertical slices)
18. Open questions / defaults to confirm

---

## 1. Vision and scope

Scriptorium is the successor to a split toolchain we want to unify:

- **Markdown → Quarto/Typst** — a *plain* PDF. Easy to author, ordinary-looking.
- **Hand-woven HTML → WeasyPrint** — a gorgeous design system, but every page
  hand-placed and hand-balanced to fit 297 mm.
- **A Rust tangle tool** (`illiterate`-style) — `export=`, noweb fragments, `--test`.
- **Quarto `type: book`** — HTML website first, then PDF, then EPUB, with
  executable code and cross-references.

Scriptorium fuses these into one tool. **In scope:** design-system reports,
paginated PDF with exact geometry, HTML books (lean), EPUB, executable code,
tangle, cross-references, math, citations-as-endnotes. **Out of scope:**
scientific papers destined for LaTeX/journal submission — those stay in LaTeX.

**Non-negotiables** (our conventions):

- Markdown is canonical; every output is regenerable from it.
- Citations render as **numbered endnotes with clickable anchors** by default
  (never per-page footnotes — Typst mis-places them).
- English is the artifact default; per-document `lang:` localizes generated
  labels ("Figure" → "Figura", "Algorithm" → "Algoritmo").

---

## 2. Architecture: one model, three renderers, an execution stage

```
Markdown + ::: components + math + fenced blocks (run / export= / name=)
        │
   [parse]  ──────────────►  one AST  (markdown-it-py + plugins)
        │
   [assemble]  noweb <<frag>> expansion   (feeds tangle AND execute)
        ├──► [tangle]   export= → real source files            (illiterate's job)
        └──► [execute]  run → subshell → stdout spliced raw → re-parsed
                 │  (enriched AST: outputs inline, so heights are knowable)
                 ├──► [HTML book]   lean: content + nav + theme + vendored search
                 ├──► [document PDF]  emit → CSS Fragmentation (no pack)
                 ├──► [deck PDF]      measure → pack → emit_deck
                 └──► [EPUB]        reflowable
```

**Ordering matters:** execution enriches the AST *before* any renderer runs,
because an executed figure's height is unknown until it runs, and `galley`'s
measure pass needs final heights. There is no lazy execution during layout.

`scriptorium` is the system; `galley` is its pagination pass; tangle is absorbed
illiterate; execute is the subshell-splice model.

---

## 3. Authoring language (the component grammar)

### 3.1 Base layer — everything Markdown has today

CommonMark + GFM + scholarly extensions, assembled from `markdown-it-py`
plugins (we assemble a parser, we do not write one):

- Headings, emphasis/strong, blockquotes, HR, links, images
- Lists: ordered, unordered, task lists (`- [ ]`)
- Tables (GFM), footnotes, definition lists, strikethrough, autolinks
- Fenced + inline code
- Math: inline `$…$`, display `$$…$$`
- Attributes on any element (Pandoc-style): `# Title {#intro .no-toc}`,
  `![](f.png){width=8cm}`, ` ```python {run export=x.py} `

### 3.2 Escape hatch — raw HTML

Raw HTML passes through verbatim (CommonMark already permits it). Added rule for
**galley**: a raw-HTML block is one **opaque atomic unit** — measured as-is,
**kept together** by default (we don't understand its internals), unless it
carries `{splittable}`. This is the graceful-degradation valve when the
component grammar isn't enough.

### 3.3 Inline components — spans

`[text]{.class}` → `<span class="class">text</span>`. If the theme registers the
name as an inline component (`badge`), it gets the component template; otherwise
it's a plain styled span. Example:

```
risk is [elevated]{.rose} this quarter, see [§3]{.ref}, tagged [NEW]{.badge .amber}
```

### 3.4 Block components — the `:::` grammar

One unified header:

```
::: <name> <modifier…> {#id key=val key="quoted val"}
markdown body  ← the content slot
:::
```

- **`<name>`** — a component the theme must define. Bare `:::` with only
  `{.class}` and no name = a plain classed div.
- **`<modifier…>`** — bare words = variant classes (`amber`, `three`).
- **`{…}`** — explicit scalar props / attributes (plain text).
- **body** — full Markdown → the `{{content}}` slot.
- **nesting** — deeper fences with more colons (`::::` wraps `:::`).

**Three power levels** (each drawn from the report theme's vocabulary):

**Level 0 — pure CSS group** (theme ships only CSS):
```
::: {.two-col}
long prose that flows into two columns…
:::
```

**Level 1 — scalar props + one content slot** (the 90 % case):
```
::: finding-card amber {icon=A title="Regulatory risk"}
The import framework does not yet cover the relevant hardware.
:::
```
Template:
```html
<div class="finding-card {{variant}}">
  <div class="x">{{icon}}</div>
  <div><span class="name">{{title}}</span>
       <span class="reason">{{content}}</span></div>
</div>
```

**Level 2 — containers + named slots** (rare: multi-region components like
`cover`, `section-opener`):
```
::: cover
::: slot wordmarks
![](assets/logo.png){.di}
:::
::: slot tag
Market Brief — June 2026
:::
:::
```
`::: slot <name>` fills a named slot; everything outside a slot is `{{content}}`.

**Decisions locked:** props are scalar plain-text + one Markdown content slot,
with `::: slot` as the escape for multi-region components (not every prop holds
Markdown); modifiers map straight to CSS classes (no whitelist ceremony).

### 3.5 Built-in layout primitives (engine-level, always available)

Independent of any theme, because they are layout mechanics, not design:

- `::: newpage` (or `\newpage`) — hard page break
- `::: keep` — keep-together wrapper for ad-hoc (non-component) blocks
- `::: columns {n=2}` — column flow
- `::: float {to=top}` — float a figure (hook designed now; full float logic
  deferred past v1, see §7)

Everything else is theme-supplied.

---

## 4. Themes and the component contract

A theme is a directory scriptorium loads:

```
themes/report/
  theme.yml            # metadata, extends: base, fonts, page geometry
  styles.css           # design tokens + component CSS (lifted from the reports)
  components/
    finding-card.html  # template: {{prop}} / {{content}} / {{slot:name}} holes
    kpi-tile.html
    cover.html         # a page-master component
  page-masters/        # cover, section-opener, running header/footer
```

Each component declares **layout hints the galley engine consumes**, as a
sidecar or front-matter on the template:

```yaml
# kpi-dash
variants: [two, three, four]
keep_together: true      # never split across a page
break_before: false
splittable: false
```

`keep_together: true` on `finding-card` / `kpi-dash` is exactly what makes
galley move the whole tile to the next page instead of orphaning it — the author
never thinks about it. This is the join between the component system and the
pagination engine.

**Template language: dumb mustache over HTML** (`{{prop}}`, `{{content}}`,
`{{slot:name}}`) — deliberately not a real templating engine. The existing
design system *is already HTML*; a theme author lifts their hand-written
component HTML almost verbatim and pokes a few holes. Lowest friction, matches
the artifacts we already have.

Themes **extend** a base (default: the `base` theme's tokens) so reports and books
share a coherent visual language. A book theme ships `callout` / `aside` /
`theorem` / `exercise`; the report theme ships `finding-card` /
`kpi-tile` / `timeline` / `compare-table`. Same engine, different vocabulary —
"custom tags shipped with themes."

### 4.1 The theme is a project template

A theme is not just styling — it carries everything that makes a document a
*book* vs a *report* vs an *article*: masters, components, CSS numbering
(counters), cross-reference formats (`target-counter`/`target-text`), page
furniture, and a documented **`vars`** block (identity vars the masters
interpolate + appearance vars bound to CSS custom properties). The project
supplies files + var overrides; the theme supplies the shape. Swap the theme,
same content becomes a different kind of document. See §11.

---

## 5. Execution runtime

### 5.1 The model

A runnable block is executed in a **subshell**; its **stdout is captured,
spliced back into the document as raw source text, then re-parsed as Markdown.**
That is the whole contract. Zero magic — no `__repr__`, no figure protocol, no
kernels, no dependencies. A block emits its own renderable text: a figure → the
block writes `fig.png` and prints `![](fig.png)`; a table → prints a Markdown
table; a component → prints `::: finding-card …`. Any language works, because
stdout is just text.

### 5.2 State flows through source assembly, not a live process

A fresh subshell per block shares no state. State flows via the **noweb model**
(the same `<<...>>` assembly illiterate uses for tangle), extended to execution:
a runnable block includes the fragments it needs and runs the assembled whole.

```
```python {name=setup}
class FenwickTree: ...
```

```python {run <<setup>>}     ← assembles setup + this body, runs as one program
t = FenwickTree(8); print(t.prefix(5))
```
```

`<<...>>` assembly feeds **all three** consumers uniformly — shown source,
`export=` tangle file, executed program. No hidden kernel, fully reproducible,
deterministic. The cost (re-running assembled setup repeats imports/compute) is
absorbed by the freeze cache.

**Locked:** blocks are independent by default. Shared state is explicit and local:
a block marked `continue` runs on top of the chain of successful blocks before it,
and a chain never crosses a file boundary or includes a failing block. Noweb
assembly remains the way to share code without replaying it. (Revised 2026-09-16;
see `docs/superpowers/specs/2026-09-16-independent-cells-design.md`.)

**Rich display (2026-10-26).** A Python block has a `display()` builtin and shows
a rich last expression, so code written for Jupyter runs unchanged. The driver
prints each displayed object's MIME bundle as JSON between sentinels in stdout;
the parent splits stdout and places each bundle in order (`bundles.py`): Markdown
spliced, image and audio written as files and turned into a figure, HTML raw, text
as output. Because the bundles live in stdout, the freeze cache holds them and a
frozen render recreates the files.

### 5.3 Mechanics

- **Interpreter map:** language tag → command (`python`→`python -`,
  `bash`→`bash`, `node`→`node -`), plus `{.exec cmd="…"}` raw escape. Body → stdin.
- **Freeze cache:** content-hash of *(assembled source + interpreter)* →
  captured stdout, stored in **beaver**. Unchanged blocks never re-run (Quarto
  `freeze: auto` semantics, no kernel).
- **Working directory:** the document's directory (natural relative asset
  read/write); configurable per project.
- **Errors:** a nonzero exit renders as a red `output error` block holding any
  stdout and the traceback. Python tracebacks number lines from the block's first
  line (the block compiles as `<cell>`). `ExecEnv(allow_error=False)` fails the
  build instead.
- **Timeout:** per block, default 30 s, overridable.
- **Display control:** `echo=false` hides source and keeps output; `output=false`
  runs but suppresses the splice (side-effect-only, e.g. a block that only writes
  a figure file referenced elsewhere).
- **Executable components:** a theme component with `execute: true` runs a
  `{run}` fence in its body in the same session and parses the stdout as
  Markdown. `heading_offset` demotes the headings it prints and `scoped` keeps
  them out of the TOC, so `::: proof` can hold a verifier's whole document
  without starting new chapters. The static body path is unchanged for every
  component that does not opt in.

---

## 6. Tangle (illiterate subsumed)

Scriptorium reimplements illiterate's tangle stage in Python (tangle is string
assembly; we lose the Rust single-binary but gain one fence parser for the whole
system). Features carried over verbatim:

- `{export=path}` — concatenate block body into a real file, in document order.
- `{export}` — headless magic: filename from the Markdown file name + language.
- `{name=frag}` + `<<frag>>` — noweb fragments (define out of order, assemble
  correctly). Same assembly used by execution (§5.2).
- `scriptorium tangle --test` — CI idempotency check; nonzero exit if regenerated
  files would differ.

`illiterate` the repo becomes the archived predecessor; its README points here.

---

## 7. The `galley` pagination engine

**Deck themes only.** For documents WeasyPrint paginates and none of §7.1-§7.3
runs; see the status note in §1 and the document path in §7.4.

Three passes, one shared rendering path so measurement never drifts from output.

### 7.1 Measure

Render the **post-execution** content stream into a single WeasyPrint page of
`size: 210mm auto` (unbounded height) at the true body width, each block already
wrapped in its final component HTML. Walk `document.pages[0]._page_box` and read
every **atomic unit's** `position_y` + border-box height (px → mm at 96 dpi).

Atomic units = paragraph, heading, list, table, figure, themed component. Per
unit we also carry: `keep_together`, `break_before`, `keep_with_next` (headings),
`splittable` + child-boundary offsets (list items / table rows / line boxes),
float directives.

**Measure pass = emit pass minus the page-boxing** — literally one code path, so
heights are exact.

### 7.2 Pack (greedy + one-unit lookahead)

`content_h = page_h − margins − header/footer reserve`. Walk units, track fill `y`:

- `break_before` / `::: newpage` → flush page, start new.
- Fits (`y + h ≤ content_h`) → place, `y += h`.
- Doesn't fit:
  - **heading (keep-with-next):** if heading + next unit won't co-fit in the
    remaining space, break *before* the heading — no heading orphaned at a page
    foot.
  - **keep_together, ≤ one page:** flush, place whole on a fresh page.
  - **keep_together, > one page:** *oversized* → emit a diagnostic and
    **overflow** (do not silently scale or clip). Theme may opt into split.
  - **splittable:** break at the last child boundary (row / list item / line box)
    that fits; carry the remainder. Enforce **widow/orphan minimums** (≥ 2 lines
    each side); tables **repeat the header row** on continuation.
- **Floats** (`::: float {to=top}`): pulled from linear flow, assigned to the
  top/bottom band of the page their anchor lands on; body fills the remainder.
  Hook designed now; full float logic lands post-v1.

**Locked:** oversized keep-together → warn + overflow (never silent scale);
floats deferred past v1.

### 7.3 Emit

Wrap each computed page's units in `<div class="page" data-master="…">`, apply
its page master, final render with `@page { size: A4; margin: 0 }` and each
`.page` a fixed 297 mm box — i.e. we generate exactly the hand-woven structure
the reports use today. Geometry matches the plan to a sub-pixel epsilon (reserve
~1 mm slack).

### 7.4 Footnotes — endnotes by default

`[^a]` markers with `[^a]: body` definitions, collected into an endnotes section
at the end of the **document** or of each **chapter**, or floated to the foot of
the **page**. The `footnotes:` key selects the mode, frontmatter over theme;
`book` defaults to `chapter`, everything else to `document`. Implemented in
`footnotes.py`.

It is a **source-to-source pre-processor**, not a markdown-it plugin, and this is
forced: `parse()` renders block by block, so a plugin never sees a marker and its
definition in the same render call — the marker survives as literal text and the
definition renders to nothing. The pre-processor rewrites markers to inline
`<sup>` HTML and re-emits note bodies as a `::: footnotes` component, so the real
Markdown renderer handles the links and emphasis in author prose.

**Per-page footnotes are implemented, and the circularity objection is retired.**
This section previously rejected them as circular — footnote height changes
`content_h`, which changes which page the reference lands on. That was true of
the Python bin-packer it was written against. v0.3.0 handed document pagination
to WeasyPrint, so the circularity is WeasyPrint's to resolve, and CSS GCPM
(`float: footnote`) resolves it. `page` mode is still engine work rather than a
stylesheet: GCPM wants the note's content inline at the anchor, so the
pre-processor inlines the body there and emits no marker of its own — WeasyPrint
generates the call number. A note referenced more than once has one body and
therefore one page; later references get a plain superscript.

---

### 7.5 Citations — numbered, prose entries

`[@key]` and `[@a; @b]` resolve against a `bibliography:` map the author declares
in frontmatter (or, for a project, as a top-level key in `scriptorium.yaml`).
They render as a bracketed `[1]` / `[1, 2]`; `[+@key]` renders `Tam et al. [1]`
and `[-@key]` renders `Tam et al.` alone. All of them collect into a generated
`<section class="references">` — cited works only, in order of first appearance,
plus anything listed under `nocite:`. Implemented in `citations.py`, which runs
right after `footnotes.py` so a citation inside a note body is numbered by where
the note renders rather than where its definition sat.

The generated section carries a heading only when the `references-label` theme
var is set — empty by default, and empty means no heading at all. The engine has
no i18n, and the label's language is the document's business rather than the
engine's, so baking in `"References"` would be wrong for every Spanish document
scriptorium renders. Set it in `theme.yml` or in frontmatter. When the label is
present the section drops its top rule: the rule exists to separate an
unlabelled block from the prose above it, and a heading already does that.

Notes and references are **separate apparatuses**: distinct sections, distinct
counters, and distinct marks — footnotes are bare superscripts, citations are
bracketed and on the baseline — so a document may carry both without ambiguity.

**Entries are opaque Markdown prose, and that is the defining trade.** The engine
numbers, orders and links them; it never inspects them for an author or a year.

What that rules out is *extraction*, not *declaration*. An entry may be written
as an `{author, text}` mapping, and the declared name is what the narrative forms
`[+@key]` (name, then mark) and `[-@key]` (name alone) emit — the engine reads a
field, never the prose beside it. Full author-date — `(Tam, 2024)` at every site,
alphabetical ordering, `2026a` / `2026b` disambiguation — does still need a real
bibliography parser (`.bib` / CSL-JSON) and a style engine, and remains a separate
feature tracked in `tasks.md`. The trade is unchanged: entry *formatting* is
exactly what CSL exists to do, and doing it halfway produces output that reads as
a worse IEEE.

There is deliberately no command that emits a year. In a numeric scheme the
number does the identifying, so a year would duplicate what the entry already
says while resolving nothing.

The name is emitted as `<span class="cite-author">`, which is the theming hook;
the base stylesheet gives it no rule, because body prose is what it should be.

Bare `@key` is deliberately **not** a citation. §7.4's neighbouring fix narrowed
`@type-id` to a known prefix set precisely because a loose `@word` rule was
rewriting prose into empty anchors; requiring brackets keeps citations and
cross-references separable at the parser rather than by convention.

---

### 7.4 Documents: CSS Fragmentation

`emit()` produces a single HTML flow with every block in a `.unit`, and the
theme CSS decides the breaks with `break-inside: avoid`, `break-before`,
`orphans` and `widows`. WeasyPrint paginates. Full-page masters (cover, section
opener, back cover) are the one exception: they stay as fixed `.page` divs bound
to a named `@page` rule.

What this costs: **there are no page floats.** WeasyPrint does not implement
GCPM page floats, so an unsplittable block that does not fit in the space left
moves whole to the next page and leaves a gap. Nothing reflows the body around
it. The diagnostic is `page_fills(doc)`, which measures the real fill of every
page off the already-rendered box tree; resolving a gap is the author's job, by
resizing the block or reordering the text.

## 8. Page masters and PDF furniture

Because we emit our own `.page` divs under `@page { margin: 0 }`, we draw
furniture *inside* each page div (as the hand-crafted reports do), not via
WeasyPrint margin-boxes. A **page master** is a named (geometry + furniture) set
the theme ships:

| Master | Furniture | Use |
|---|---|---|
| `cover` | none, full-bleed, `no-padding` | title page |
| `section-opener` | none | full-page chapter/section opener |
| `body` | running header + footer + page number | default content |
| `blank` | number only | spacers |

- **Furniture = theme partials** rendered per page with resolved tokens:
  `{{page_number}}`, `{{page_total}}`, `{{chapter_title}}`, `{{section_title}}`.
  **Running heads resolve in the emit pass** — the pack pass already knows which
  section each page falls in, so "current chapter" per page is free.
- **Master selection:** structure + theme rules (`level-1 heading →
  section-opener then body`), overridable per element (`# Title {.master=body}`);
  front matter picks the cover master.
- **Geometry:** theme declares page size and margins; `@page { size: A4;
  margin: 0 }` + `.page` padding produce margins; full-bleed elements escape
  padding via the `no-padding` master.

**Locked:** bleed / crop-marks for real print deferred; screen-PDF first.

---

## 9. Numbering and cross-references — pure CSS

**The engine owns no numbering.** Chapter/section numbers, cross-reference text,
and TOC page numbers are all generated by the *theme's stylesheet* and resolved
by WeasyPrint at render time. This was verified to work through galley's own
`.page`-div structure (`@page{margin:0}` + explicit page boxes).

- **Numbering: CSS counters.** `h1{counter-increment:chapter} h1::before{content:"Chapter " counter(chapter)}`.
  Counters increment in document order, so they compose with measure-pack for
  free. `number_depth` and localized labels ("Figure"/"Figura") are just which
  levels the theme's CSS numbers and what text it emits.
- **References: `target-counter` / `target-text`.** The engine turns `@type-id`
  into an *empty* anchor `<a class="ref-type" href="#type-id"></a>` and assigns
  the target's id; the theme's CSS fills it:
  `a.ref-chap::after { content: "Chapter " target-counter(attr(href url), chapter) " (p. " target-counter(attr(href url), page) ")" }`.
  Number *and* page are WeasyPrint-resolved. Format/prefix per type is the
  theme's choice; hierarchical "3.2" is two `target-counter`s.
- **TOC page numbers:** a TOC entry is a link; theme CSS adds
  `content: leader('.') target-counter(attr(href url), page)`. The engine only
  emits the heading link-list; the dotted page numbers are CSS.

So the engine's whole job here is: **assign ids to headings/figures, and rewrite
`@type-id` into type-classed anchors.** No numbering pass, no ref-resolution
pass. Verified: `@chap-trees` → "Chapter 2 (p. 3)" with zero engine numbering.

The one book-craft item that *isn't* pure CSS in our architecture is **running
heads** (we use `@page{margin:0}` and draw furniture inside `.page` divs, so
`string-set`/`@page @top` don't apply): the theme supplies a template string +
CSS class, and galley fills it per page at emit — the same mechanism as the
stamp footer.

---

## 10. Math pipeline

- Parse `$…$` / `$$…$$` (markdown-it `dollarmath` plugin).
- **Renderer: quickjax** — real MathJax v4 running inside an embedded QuickJS
  engine, **in-process, pure Python, no Node and no LaTeX install**. Each call
  returns a self-contained SVG (own glyph paths + a computed `vertical-align`,
  so inline math baselines and scales with font-size). Used for both PDF (SVG
  embedded directly) and HTML.
- **No Node dependency.** The earlier plan (Node + KaTeX) is dropped: quickjax
  gives MathJax-grade fidelity with zero external runtime, which keeps the whole
  toolchain Python-only and reproducible. WeasyPrint has no native MathML, so
  SVG is the path regardless. (ziamath, a pure-Python STIX-font renderer, was
  evaluated and rejected — it needs a baseline heuristic and collides on shared
  SVG glyph IDs under WeasyPrint.)
- **Cache:** rendered SVGs are memoized in-process and persisted in the freeze
  store (keyed `math\0<display>\0<latex>`), so a math-dense book renders each
  equation once, then serves it from cache on rebuild.
- **Equation numbering:** display equations get `@eq` counters and a number
  gutter (later slice).

---

## 11. Project model — concat + vars (the theme is the template)

There is **no `kind: book|report|article`** and no structural role schema. A
project is just a **theme + variables + a list of files**; the theme (its CSS,
masters, and components) *is* the template that makes the same content render as
a book, a report, or an article. Structure lives in theme CSS (counters,
`break-before`, `h1`-as-chapter-opener), not in the engine.

```yaml
# scriptorium.yaml
theme: book
vars:
  title: A Field Guide to Algorithms
  author: Alejandro Piad-Morffis
  brand: "#7c3aed"
code: { root: src }          # tangle target + PYTHONPATH for execution
files:
  - front/index.md
  - 01_search.md
  - 02_binary.md
  - appendix-python.md
```

- **Assembly** = concatenate the listed files (each file starts a fresh page),
  strip per-file frontmatter, and substitute `{{var}}` over the result. A single
  file with no project still renders against the theme's default flow — today's
  behavior, unchanged.
- **Vars are theme-specific and flow two ways:** into masters via `{{var}}`
  (title page, running heads) and into CSS as custom properties (`:root{--brand:…}`)
  so a project rethemes without editing CSS. The theme declares its vars +
  defaults in `theme.yml`; the project overrides. Nothing is engine-hardcoded.
- **Engine additions over single-doc:** file concat + `{{var}}` substitution,
  heading-id assignment + `@ref` rewriting, TOC link-list emission, running-head
  emit-fill. That's it.

A `book`, `report`, and `article` differ only in *which theme* they point at.
Verified with `examples/book/` (2-chapter project → 3-page PDF, CSS numbering,
`@chap-trees` → "Chapter 2 (p. 3)").

---

## 12. Renderers: HTML, PDF, EPUB

### 12.1 HTML book (lean — the fork-1 call)

Multipage (one HTML per chapter) or single-page, theme-selectable. Sidebar nav
from structure, TOC, prev/next, anchors, dark/light toggle, and vendored
client-side **search** (a prebuilt index + a small lib like MiniSearch —
*not* a clone of Quarto's website infra). Math via server-side KaTeX. Components
render through the same theme templates (HTML target). Responsive; assets copied
to the output tree. Deliberately lean: if it can carry books.apiad.net, great;
if not, Quarto stays for HTML-only while scriptorium still wins on PDF.

### 12.2 PDF

`galley` (§7) + page masters (§8). The differentiated output.

### 12.3 EPUB

Reflowable: chapters → XHTML, `package.opf`, `nav.xhtml`, embedded fonts, cover.
Components render to an EPUB-safe HTML+CSS subset (no `@page` geometry). Math as
MathML with SVG fallback. Lowest priority; built last.

---

## 13. Citations and bibliography

- Syntax: `[@key]` / `@key`, with a `.bib` or CSL-JSON source.
- **Default mode:** citations resolve to **numbered endnotes with clickable
  anchors**, matching a common report convention (a `# References` section, anchors
  `{#ref-N}`, superscript links). This automates what is currently done by hand.
- **Academic mode:** CSL author-date + a formatted bibliography, for books that
  want it.

---

## 13b. Glossary

A third member of the apparatus family, alongside footnotes and references, and
built the same way: a source-to-source pre-processor over the raw text, not a
markdown-it plugin, because `parse()` renders block by block and would never see
a marker and its entry in one call.

- **Syntax.** `[~key]` takes the entry's declared `term`; `[display]{~key}`
  supplies its own text. Both are consumed before Markdown parsing, so neither
  collides with a reference link.
- **Data.** `glossary:` is a mapping of `key → {term, definition}`, or a path to
  a YAML file of one, resolved against the project. Definitions are opaque
  Markdown prose on the same contract as a bibliography entry: the engine sorts
  and links them, never inspects them.
- **Emission.** A `::: glossary` placeholder is replaced by one block per entry,
  sorted case-insensitively by term. Every declared entry appears, mentioned or
  not — a glossary is a reader's apparatus, not an attribution record, which is
  where it deliberately parts company with citations.
- **Back-references** are empty anchors filled by CSS `target-counter`, exactly
  as citation back-links are. Two mentions on one page yield a repeated number;
  measured at 2 entries in 505 on a real book, which is not worth a second
  render pass to dedupe.
- **Order.** Runs last, after footnotes and citations, so a term glossed inside a
  note body is paged where the note actually renders.
- **Nesting.** Only the innermost marker matches, and both patterns sweep every
  pass to a joint fixpoint. The outer of a nested pair keeps its anchor but not
  its link: an `<a>` inside an `<a>` is invalid and strands a `</a>` mid-sentence.

---

## 14. CLI and build workflow

- `scriptorium render [target]` — all outputs or one (`pdf` / `html` / `epub`).
- `scriptorium watch` — rebuild on change (replaces the `entr`-based makefile).
- `scriptorium tangle [--test]` — illiterate mode: write `export=` files; `--test`
  is the CI idempotency check.
- `scriptorium new <kind>` — scaffold a document / report / book.
- **Incremental:** freeze cache for execution + math SVG + measured heights,
  keyed by content hash in beaver → fast rebuilds. `--no-cache` to force.

---

## 15. Extensibility

Themes are the primary extension surface. Beyond them, a minimal **filter** seam:
Python functions that run over the AST (a Pandoc-Lua-filter analog, in Python).
Kept small for v1; the seam is documented so custom directives/transforms have a
home without forking the engine.

---

## 16. Technology stack and repo layout

- **Python 3.12+**, `markdown-it-py` (parse), **WeasyPrint** (measure + PDF),
  **Node + KaTeX** (math → SVG, build-time only), **beaver** (freeze/measure
  cache), a tiny mustache renderer for component templates, `typer`/`click` (CLI).

```
scriptorium/
  scriptorium/
    parse/            # markdown-it-py assembly, ::: directives, attrs
    model/            # the document AST
    assemble.py       # noweb <<frag>> expansion
    exec/             # subshell execution + freeze cache
    tangle/           # export= / name= / --test  (illiterate subsumed)
    galley/           # measure → pack → emit  (the pagination engine)
    math/             # KaTeX → SVG / HTML
    xref/             # numbering + reference resolution
    themes/           # theme loading, mustache, layout hints
    render/
      html.py
      pdf.py
      epub.py
    cli.py
  themes/
    base/             # foundation: var contract + vendored fonts + base styling
    note/             # utilitarian notes/handouts
    article/          # polished single document (serif body, sans display)
    report/           # data-forward report (cover, KPI tiles, finding cards…)
    book/             # classic long-form book (serif, chapter numerals, TOC)
  docs/
    design.md         # this document
  tests/
```

---

## 17. Phased delivery (vertical slices)

Each slice is a thin end-to-end path with a concrete acceptance artifact.

- **VS1 — the engine loop.** ✅ measure → pack → emit → exact-geometry A4 PDF;
  `::: keep` / `::: newpage`. Verified 2-page PDF.
- **VS2 — the design system.** ✅ directory-backed theme system + `marketing`
  report theme (cover, KPI tiles, finding cards, timelines), page masters, drift guard.
  Verified 11-page report from Markdown.
- **VS3 — execute + tangle.** ✅ subshell execute (Quarto-monospace vs native
  raw-splice) + freeze cache + tangle (`export=`, illiterate-compatible,
  reproduces `fenwick.py` byte-exact) + Pygments + **export provenance labels**
  (file + exact line range).
- **VS4 — math.** ✅ quickjax (MathJax-in-QuickJS, **no Node**), inline + display,
  freeze-cached. Real `22_fenwick.qmd` renders to an 11-page PDF.
- **Pagination polish.** ✅ keep-with-next headings; code line-splitting (code is
  narrative, not a float).
- **Project model.** ✅ `scriptorium.yaml` = theme + vars + files; `book` theme
  with CSS-native numbering + `target-counter` cross-refs. Verified 2-chapter
  book, `@chap-trees` → "Chapter 2 (p. 3)".
- **Next — running heads + auto-TOC** (emit-fill + `::: toc` link-list), then the
  a full multi-chapter book build (PYTHONPATH wiring for cross-chapter imports).
- **Later — VS5 HTML book** (lean renderer + search); **VS6** EPUB, CSL citations,
  opt-in `::: float` for figures, per-page footnotes.

---

## 18. Open questions / defaults to confirm

Locked in conversation: component grammar (§3), theme contract (§4), execution
model + assembly-only state (§5), tangle scope (§6), galley passes + oversized
warn-overflow + deferred floats (§7), page masters + deferred bleed (§8).

Defaults set here in the lighter layers, open to veto on review:

1. **Cross-ref prefixes** (`sec`/`fig`/`tbl`/`lst`/`eq`) and chapter-scoped
   numbering (§9) — Quarto-compatible; confirm the prefix set.
2. ~~Node+KaTeX for math~~ — **resolved: quickjax** (MathJax in QuickJS,
   pure-Python, no Node). Toolchain stays Python-only. See §10.
3. **`scriptorium.yml`** as the project file with `document`/`report`/`book`
   kinds (§11) — confirm the name and the `structure:` shape.
4. **Lean HTML search** via a vendored JS index lib (§12.1) — confirm we're not
   chasing Quarto's full website search.
5. **Citations default to numbered endnotes**, CSL as opt-in (§13) — confirm.
6. **EPUB is genuinely last** (§17 VS6) — confirm it's not needed earlier for any
   book.
