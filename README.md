# Scriptorium

Write Markdown, get a real document.

Scriptorium is a Markdown-native document engine that renders to **exact-geometry
PDF** — with a pagination engine that places content on physical pages under
rules you control, not whatever the flow happened to do. It executes code in
place, tangles code into real source files, renders LaTeX math without Node, and
ships a family of themes from conference notes to polished books to 16:9 slide
decks.

```bash
scriptorium render report.md              # a single document   -> report.pdf
scriptorium render book.yaml              # a multi-file project -> book.pdf
scriptorium render talk.md --theme deck   # override the declared theme
```

A document picks its own theme in frontmatter (`theme: deck`); `--theme` overrides
it, and a project's `scriptorium.yaml` decides for every file it lists.

## Why

Two ways to make a PDF from text, and neither is quite what you want:

- **Quarto / Typst** — easy to author, but the output is a *plain* document.
- **A hand-woven HTML + CSS design system** — beautiful, but every page is placed
  and balanced by hand.

Scriptorium is both: you author in Markdown (plus a little HTML when you want
it), and the engine places the pages with deterministic geometry — so "print to
PDF" yields real, controlled pages.

## Highlights

- **Exact-geometry PDF.** The `galley` engine measures rendered content and packs
  it into fixed pages: keep-together blocks, headings that don't strand, code and
  tables that split cleanly across a break, and a drift guard that catches any
  page that overflows its box.
- **Themes as project templates.** Themes inherit (`extends:`) and customize by
  `accent`, fonts, and other vars — rebrand a document without touching CSS. The
  default lineup spans **note → article → report → book → deck**.
- **Execute code in place.** Run fenced blocks in a subshell and splice stdout
  back as raw Markdown (or monospace, Quarto-style). Blocks run independently;
  `continue` chains a block onto the ones before it. A freeze cache and cross-file
  imports — no Jupyter, no kernels.
- **Tangle.** `export=` code blocks extract into real source files
  (illiterate-compatible), with per-block provenance labels (file + line range).
- **Math without Node.** Inline `$…$` and display `$$…$$` render to SVG via
  quickjax (MathJax in an embedded QuickJS engine) — pure Python, no Node, no
  LaTeX install.
- **CSS-native numbering and cross-references.** Chapter/section numbering, `@ref`
  cross-references, and TOC page numbers are resolved by CSS counters and
  `target-counter` — no numbering pass in the engine.

## Install

Scriptorium is a Python package. PDFs print through **WeasyPrint**, which needs a
few system libraries (Pango, Cairo, GDK-PixBuf, libffi) — see the
[WeasyPrint install docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation)
for your platform. WeasyPrint is the `pdf` extra:

```bash
uv pip install 'scriptorium[pdf] @ git+https://github.com/apiad/scriptorium'
# or, from a clone:
uv pip install -e '.[pdf]'
```

Without the extra, scriptorium renders HTML only: `scriptorium render doc.md --html`
writes `doc.html`, and `scriptorium.render.render_html(src)` returns the same
document as a string. Decks always need the extra, because their slides are
measured by WeasyPrint.

`render_html(src, cwd=…, frozen=True)` shows cached code outputs without running
anything: a block that never ran shows its source and a warning. A project sets
`execute: {timeout: 600, interpreters: {…}}` in `scriptorium.yaml`.

The freeze cache (`.scriptorium/freeze.json` in the project directory) keys each
block on its own source and the chain it runs on, so editing prose re-runs
nothing. `execute: {freeze: file}` keys each block on its whole file instead:
editing a file re-runs every block in it, and an unchanged file is served from
the cache. Use it when a block reads its own file or the files other blocks
wrote, which a per-block key would serve stale. Neither key sees the code a
block imports, so whatever caches the freeze file (a CI cache, say) must key on
that code too.

Requires Python 3.12+. Vendored fonts (Inter, Source Serif 4, JetBrains Mono)
ship with the themes, so output is self-contained.

## Quickstart

A single document:

````markdown
---
title: A Field Guide to Abstractions
---

# Introduction

Some prose. Inline math like $O(\log n)$ just works, and so do
cross-references — see @sec-detail.

## Detail {#sec-detail}

```python {run}
print("| n | n squared |")
print("|---|-----------|")
for n in range(1, 4):
    print(f"| {n} | {n*n} |")
```
````

```bash
scriptorium render guide.md    # theme from frontmatter -> guide.pdf
```

A multi-file project is a `scriptorium.yaml`:

```yaml
theme: book
css: book.css           # this project's own stylesheet, after the theme's
glossary: glossary.yaml
footnotes: document     # where the notes collect, overriding the theme
vars:
  title: The Book
  author: A. Writer
  accent: "#7c3aed"
files:
  - front.md
  - 01-intro.md
  - 02-body.md
code: { root: src }     # tangle target + PYTHONPATH for executed code
```

`css:` takes a path or a list, resolved against the project file and appended
after the theme's own rules — enough to restyle a book without authoring a theme.

```bash
scriptorium render scriptorium.yaml     # concatenates the files -> book.pdf
scriptorium tangle scriptorium.yaml     # extract export= code into src/
```

### Several outputs

`outputs:` names several renders of the same project. Without it a project
renders one PDF, `book.pdf`, as before.

```yaml
outputs:
  print:                          # the name is what --only takes
    format: pdf                   # file defaults to <name>.pdf
    file: book.pdf
  pocket:
    format: pdf
    file: book-a5.pdf
    page: {size: A5, margin: 14mm}   # overrides the theme's page block
```

`page.size` takes `A4`, `A5`, `letter`, `16:9`, `4:3` or `"<w>mm <h>mm"`; an
output's `vars` override the project's. Paths are relative to the project file.

```bash
scriptorium render scriptorium.yaml                 # every output
scriptorium render scriptorium.yaml --only pocket   # one (repeatable)
```

`-o` works only when a single output is being built.

### The HTML book

An output with `format: html` writes a static directory that reads like an
ebook: swipe or tap to turn on a phone, two facing pages on a wide screen, a
contents panel, three reading modes and font sizes. It installs as an app,
reads offline with every image and font cached, and picks up a new edition by
itself. CSS multi-column layout makes the pages, so a book keeps its theme's
fonts, colours and break rules.

```yaml
outputs:
  web:
    format: html
    dir: web                  # defaults to the output's name
    cover: img/cover.jpg      # cover page and app icons
    image-max-width: 1600     # images become WebP no wider than this
    image-quality: 80         # their WebP quality
    offline-images: true      # false: images load as read, not on install
    offline-media: false      # true: audio is cached on install too
    js: [extras.js]           # loaded after the reader
    css: [web.css]            # appended after the reader's CSS
```

`scriptorium render chapter.md --format html` builds one from a single file.
Scripts can drive the reader through `window.scriptoriumReader` (`go(page)`,
`goTo(element)`, `page`, `pages`, `relayout()`) and listen for `reader:ready`,
`reader:page` and `reader:layout` on `document`. `examples/html-book/` builds
the same book as two PDFs and a web book.

### Publishing an HTML book

Copy the directory to any static host. It needs three things:

- HTTPS (or `localhost`): browsers register service workers only there.
- `sw.js` not cached for long. GitHub Pages' ten minutes is fine, because the
  reader registers the worker with `updateViaCache: 'none'`; a host with long
  cache lifetimes needs `Cache-Control: no-cache` on `sw.js`.
- `.webmanifest` served as `application/manifest+json` (GitHub Pages does).

With Caddy, keep the two `Cache-Control` rules mutually exclusive, or the
general one wins:

```
books.example.org {
	root * /var/www/books
	file_server
	@sw path */sw.js
	header @sw Cache-Control "no-cache"
	@notsw not path */sw.js
	header @notsw Cache-Control "public, max-age=300"
	@manifest path *.webmanifest
	header @manifest Content-Type "application/manifest+json"
}
```

Several books can share one origin, one directory each: each book caches under
its own path and never touches another's cache.

### The docs site

An output with `format: docs` writes a documentation site of scrolling pages:
one page per chapter (`#` heading), a sidebar of parts and chapters, an
outline of the page's sections, previous and next links, and search over an
index built at render time. Below 640 px the sidebar folds into a menu. It
keeps the project's theme, so chapters, figures and references number as in
the PDF; a reference to another chapter links to that page.

```yaml
base-url: https://example.org/book/      # project-level, optional: the PDF links audio here
outputs:
  site:
    format: docs
    dir: site                            # defaults to the output's name
    repo-url: https://github.com/org/repo   # optional: the repository in the top bar
    version: auto                        # optional: "1.2.1", or auto (pyproject.toml, then git tag)
    logo: img/logo.svg                   # optional, shown before the title
    favicon: img/favicon.png             # optional
    palette: {primary: "#0f766e", accent: "#d97706", scheme: auto}   # optional; scheme: auto | light | dark
    typography: docs                     # docs (default): sans, left-aligned; theme: the theme's own
    image-max-width: 1600                # as in the html output
    css: [site.css]
    js: [site.js]
  print:
    format: pdf
```

The top bar carries the logo, the title, the version, search, a light/dark
switch and the repository. The switch cycles auto, light and dark, is
remembered in the browser, and applies before the first paint. Search
marks the words in each result and on the page a result opens; arrow keys,
Enter, `/` and Ctrl-K drive it from the keyboard. Every code block has a copy
button (the code, never its output); a block that tangles (`export=`) or has
`title="…"` shows that name in a title bar with its language, and an executed
block's output joins the box under an "Output" label. A GitHub
repository also shows its latest release tag and star count, fetched by the
reader's browser and kept for an hour; another forge shows its name.
`palette.primary` colours the bar and `palette.accent` the links. The docs
typography sets every page in the theme's heading face (a sans), left-aligned
and without hyphenation, whatever the theme does on paper; the PDF and the
HTML book keep the theme's.

A part heading (`# Part {.part}`) with text under it gets its own page; one
with none is only a label in the sidebar. The site's own words (search, the
outline's title, the source link) follow `lang:`, in English or Spanish, and a
project's `html-refs:` (`fig: "figura {figure}"`) replaces the theme's reference
formats in the HTML outputs. `scriptorium render chapter.md
--format docs` builds a one-page site from a single file.

The site is plain files with relative URLs, no service worker and no server
code: copy the directory to any static host (GitHub Pages, an S3 bucket, a
`file_server`). Set `base-url` to where it lands, so the PDF's audio figures
link to their page. `examples/docs-site/` builds a site and a PDF from two
chapters, one of which writes and plays a tone.

## Themes

Themes are project templates. Point at one and customize with `vars:` — no theme
authoring needed for the common case.

| Theme | For |
|---|---|
| `note` | conference notes, handouts, minutes |
| `article` | essays, whitepapers, papers (title block with authors, affiliations, abstract, keywords) |
| `report` | data-forward briefings — covers, KPI tiles, finding cards, timelines |
| `book` | classic long-form — serif body, chapter numerals, running heads, auto-TOC |
| `deck` | 16:9 slides with report-grade visuals, agenda, section dividers, slide counter |
| `formal` | contracts, official letters — all black, Times-metric serif, open three-rule tables, numbered clauses, signature blocks |

```yaml
theme: report
vars: { accent: "#0d9488", body-font: "Source Serif 4" }
```

All six `extend` a `base` theme; build your own by extending any of them. See
[`themes/README.md`](themes/README.md).

## Authoring

- **Components** — `::: finding amber {title="Risk"}` renders a theme component;
  `::: {.two-col}` is a plain styled div. Themes ship their own vocabulary.
- **Admonitions** — `::: note`, `tip`, `info`, `warning`, `danger` and `example`,
  with an optional `{title="…"}`; without one the box is titled with its kind, in
  English or Spanish (`lang:`). `::: warning collapse` is a closed `<details>` on the
  docs site and prints open.
- **Tabs** — `:::: tabs` around `::: tab {title="pip"}` blocks. The docs site
  switches between them and remembers the choice by title across tab sets and
  pages; print and the HTML book show every tab under its title. Code inside a
  component is highlighted but does not run.
- **Code** — `python {run}` executes; `{export=path}` tangles; `{run export=path}`
  does both; `{python}` is Quarto-compatible. Blocks run independently; mark a
  block `continue` (`{python continue}`, `python {run continue}`) to run it on top
  of the blocks before it, and a failing block shows its traceback in red.
- **Rich display** — a Python block has Jupyter's `display(obj, metadata=None)`,
  and a block whose last line is an expression with a rich repr shows it, as a
  notebook would (a plain value prints nothing). Scriptorium reads the object's
  `_repr_mimebundle_`, or its `_repr_markdown_`, `_repr_svg_`, `_repr_png_` and
  `_repr_html_`. Markdown is spliced; an SVG or PNG and an MP3 or WAV are written
  under `build/img/` and `build/audio/`, named by caption and content, and an image
  with audio becomes one figure with its player under it; HTML goes in raw; plain
  text shows as output. The caption and id come from the bundle's metadata
  (`{"caption": …, "id": "fig-…"}`), or from the block's `caption="…"` and `id=…`
  when it displays exactly one thing. A frozen render writes the files again from
  the cache.

  ````markdown
  ```python {run echo=false}
  class Dot:
      def _repr_svg_(self):
          return '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="10" cy="10" r="8"/></svg>'

  display(Dot(), metadata={"caption": "A dot", "id": "fig-dot"})
  ```
  ````
- **Math** — `$inline$` and `$$display$$`.
- **Audio** — an image link to an audio file (`.mp3` `.ogg` `.opus` `.m4a`
  `.wav` `.flac`, any case) alone in its paragraph is an audio figure: a native
  player with the alt text as its caption.
  `![A plucked A3](pluck.mp3){#aud-pluck}` numbers it on its own counter ("Audio
  1", `audio-label:` sets the word) and `@aud-pluck` refers to it. In running
  text the link is a bare player. A missing local file fails the render and
  names the file and the chapter. The HTML book copies each file as it is into
  `media/`, named by its content, and precaches it only with `offline-media:
  true`. A PDF cannot play, so it prints a box with the caption and the file
  name; set a top-level `base-url:` in `scriptorium.yaml` and the box links to
  `<base-url><chapter id>.html#aud-…`. An executed block's stdout is Markdown,
  so a block that writes a sound and prints one line puts a player under itself:

  ````markdown
  ```python {run}
  import math, os, struct, wave
  os.makedirs("build", exist_ok=True)
  with wave.open("build/a3.wav", "wb") as w:
      w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
      w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * n / 22050)))
                             for n in range(22050)))
  print("![An A3 sine](build/a3.wav)")
  ```
  ````

  A relative path resolves against the project directory. A block times out
  after 30 s unless `execute: {timeout: …}` raises it, and a frozen render
  reuses the cached stdout, so the files it names must still be on disk.
- **Cross-references** — `@type-id` resolves to "Figure 3.2 (p. 41)" via theme
  CSS. The prefix must be one of `fig` `tbl` `sec` `eq` `lst` `thm` `chap` `aud`;
  anything else (`@smith-2020`, a handle) stays literal text.
- **Footnotes** — `A claim.[^a]` with `[^a]: The note.` anywhere in the file.
  Numbering is automatic; a note referenced twice gets two back-links. Set
  `footnotes-label:` to give the section a heading — `Notes`,
  `References and Notes`, whatever fits; unset means no heading.
- **Citations** — `[@key]` and `[@a; @b]` render as `[1]` / `[1, 2]` against a
  `bibliography:` map in frontmatter (or in `scriptorium.yaml` for a project),
  and collect into a references section. Cited works only; add `nocite: [key]`
  for anything you want listed without citing. Entries are Markdown prose. Set
  `references-label:` (a theme var, or a frontmatter key) to give the section a
  heading — `References`, `Bibliografía`, whatever fits; unset means no heading.
  Place `::: references` yourself to control where it lands, e.g. before an
  appendix.
- **Narrative citations** — to put the author's name in the running text, write
  the entry as a mapping and use a sigil: `[+@key]` renders `Tam et al. [1]`
  (`+` adds the name) and `[-@key]` renders `Tam et al.` alone (`−` removes the
  mark). The name is declared, never guessed from the key:

  ```yaml
  bibliography:
    tam-2024:
      author: Tam et al.
      text: 'Tam, Z. R., … *Let Me Speak Freely?* [arXiv:2408.02442](https://arxiv.org/abs/2408.02442).'
  ```

  Two things to know when authoring. A name ending in `et al.` already carries a
  period, so ending a sentence on `[-@key]` yields `Tam et al..` — drop your own
  full stop, because the engine cannot tell sentence punctuation from an
  abbreviation. And `[-@key]` does not number, so it does not affect the order
  of the references list: a work first *named* and later *cited* takes its number
  from the citation.

  Full author-date — `(Tam, 2024)` everywhere, alphabetical ordering — still
  needs CSL, which is not built.
- **Glossary** — `[~key]` renders the term as declared; `[display]{~key}` supplies
  its own text (`[*the AI effect*]{~ai-effect}`). Entries come from `glossary:` —
  a mapping, or a path to a YAML file of one — and collect into a `::: glossary`
  section, alphabetical by term, each carrying the pages where it appears. Every
  declared entry is listed, whether or not the body glosses it; `glossary-label:`
  gives the section a heading, unset means none.

  ```yaml
  glossary: glossary.yaml     # or an inline mapping
  ```
  ```yaml
  ai-effect:
    term: "AI effect"
    definition: "The pattern by which a solved task stops counting."
  ```

  Markers nest — a glossed term inside another's display text — and the inner,
  more specific term keeps the link while the outer keeps only its anchor, since
  an `<a>` inside an `<a>` is not valid HTML. A marker inside `code` or a fenced
  block is code, and is left alone.
- **Book structure** — `# Title {.part}` is a part divider: it takes a part
  numeral, not a chapter one, and starts its own page. `{.unnumbered}` keeps a
  heading out of the chapter count, `{.unlisted}` keeps it out of the contents.
- **Layout** — `::: keep` (keep-together), `::: newpage`.

Where the notes land is the `footnotes:` key — frontmatter (or a project's
`scriptorium.yaml`) wins over the theme:

| Value | Behaviour |
|---|---|
| `document` | one endnotes section at the end (default; `book` overrides) |
| `chapter` | one section before each `#`, numbering restarts (the `book` default) |
| `page` | true bottom-of-page footnotes |

The document's language is `lang:` (frontmatter or `scriptorium.yaml`; a BCP 47
tag such as `es` or `en-GB`). It picks the hyphenation dictionary, so a Spanish
document without it is hyphenated with English patterns (`per-ro`,
`desar-rollo`). The default is `en`; the `uh` theme defaults to `es`.

A header or footer line that repeats on every page — a contract number, "page 2
of 5" — is the `header:` / `footer:` key, in frontmatter or a project's
`scriptorium.yaml`. Each takes `left`, `center` and `right` templates; `{page}`
and `{total}` count pages, and any other `{key}` reads the frontmatter (or a
project's `vars:`). `false` removes the theme's own default.

```yaml
theme: formal
contract: "No. 2026-014"
header: { right: "Contract {contract}" }
footer: { center: "Page {page} of {total}" }
```

The full design is in [`docs/design.md`](docs/design.md).

## Status

Current release: **v0.5.0**. Solid and in use: exact-geometry PDF, the theme
system, code execution, tangle, math, footnotes, citations, and the deck format.
On the roadmap: a lean HTML-book renderer and EPUB output, real floats, and CSL
citations.

## License

MIT © Alejandro Piad
