# Changelog

All notable changes to this project are documented here. Format: Keep a Changelog.

## [Unreleased]

## [v0.14.0] - 2026-11-08

### Features

- **A docs site on par with MkDocs Material** (#43, #44). The top bar carries a
  logo, the version (`version: auto` reads `pyproject.toml`), the repository
  (with a GitHub repository's latest release and stars), a light/dark/auto
  switch that applies before the first paint, and a `palette:` for the bar and
  links. Docs pages set text in the theme's sans, left-aligned, unless
  `typography: theme`.
- **Search** shows a snippet with every match marked, moves with the arrow
  keys, opens on Enter and focuses on Ctrl-K or Cmd-K; the page a result opens
  marks the words. On a phone the box covers the bar.
- **Code blocks** on the site get a copy button (the code, never its output), a
  title bar from `export=` or the new `title=` with the language, and their
  output joined underneath under an "Output" label.
- **Admonitions and tabs** in the base theme, for every output: `::: note`,
  `tip`, `info`, `warning`, `danger`, `example` (default titles in English and
  Spanish, `collapse` for a closed box on the site) and `:::: tabs` around
  `::: tab {title="…"}`, linked by title on the site and printed one after
  another.
- **Page foot and site files**: last updated from git, "Edit this page" on
  GitHub or GitLab, a `footer:` line, a description and Open Graph tags on every
  page, and `404.html`; with `base-url`, canonical links and `sitemap.xml`.

### Fixes

- `::::` around `:::` blocks no longer leaks the outer close into the content.
- A component sees the block's own attributes as `attr.<key>`, so a title the
  block did not set is not taken from the document's metadata.

## [v0.13.0] - 2026-11-04

### Features

- **The docs site speaks the book's language.** Its own words (search, "On this
  page", the source link, the menu, "No results") follow `lang:`, in English or
  Spanish. A project or document can set `html-refs:` over the theme's, so a
  Spanish book's references can read "figura 3" in the HTML outputs (#37).

### Fixes

- **Contents page numbers under WeasyPrint 70.** WeasyPrint 70 resolves
  `target-counter()` to 0 in a pseudo-element of a flex container, so every TOC
  entry of the `book` and `deck` themes read 0. The number now sits on a
  `.toc-pg` span inside the entry (#36).
- **Formulas on docs pages.** The cross-page link rewrite sent each formula's
  `xlink:href="#MJX-…"` glyph references to another page that used the same
  names, and the formula drew nothing. An id defined on the page keeps its link
  there (#38).

## [v0.12.0] - 2026-10-29

### Features

- **Freeze per file.** `execute: {freeze: file}` keys each block's cached output
  on its whole file, so editing a file re-runs all its blocks and an unchanged
  file is served from the cache. The default, `block`, keeps today's keys.

## [v0.11.0] - 2026-10-29

### Features

- **Rich display in Python blocks.** The Python driver defines `display()` and
  shows a block's last expression when it has a rich repr (`_repr_mimebundle_`
  or a `_repr_*_` method). Images and audio are written under `build/img` and
  `build/audio`; an image with audio becomes one figure with its player. A
  fence's `caption=` and `id=` name a block that displays one thing. Frozen
  renders recreate the files from the cache.
- **A bundle can bring its own HTML to the docs site.** A bundle whose metadata
  says `"site": "html"` and that carries `text/html` is spliced as that HTML on
  the docs site, with its audio written to a file and the bundle's id on its
  outer figure. The PDF and the HTML book ignore the key.
- **The docs site.** An output with `format: docs` writes a documentation site:
  one scrolling page per chapter, a sidebar of parts and chapters, an outline
  of the page, previous and next links, search over an index built at render
  time, and a drawer on phones. References to another chapter link to its
  page; `repo-url` adds a "Source" link. `--format docs` builds one from a
  single file. `examples/docs-site/` builds a site and a PDF.
- **Audio figures.** `![caption](file.mp3)` alone in its paragraph renders a
  native player with a caption, numbered on its own counter and referenced as
  `@aud-name`. A missing local file fails the render. The HTML book copies
  audio into `media/` by content hash and precaches it only with
  `offline-media`; a PDF prints a box with the file name, linked to the
  figure on the site when the project sets `base-url`.
- **The HTML book.** An `html` output writes a static, installable ebook:
  CSS columns make the pages (swipe on phones, two facing pages on wide
  screens), the theme's fonts and colours carry over, references become text,
  images become WebP, and a content-versioned service worker makes it read
  offline and update itself. `--format html` builds one from a single file.
- **Several outputs per project.** `outputs:` in `scriptorium.yaml` names
  several renders of one source, each PDF with its own page size (`page:`) and
  vars. `scriptorium render` builds them all; `--only NAME` picks. A project
  without `outputs:` still renders `book.pdf`.
- **`render_html()` and `scriptorium render --html` return the document HTML.**
  Everything a PDF goes through (footnotes, citations, glossary, timeline, the
  parser, `emit()`) without the printing, so a screen consumer gets every
  Markdown feature. `render_pdf()` is now `render_html`'s pipeline plus
  WeasyPrint.
- **Frozen renders.** `render_html(..., frozen=True)` serves cached code outputs and
  never runs code; a miss shows the source and warns.
- **`execute:` in `scriptorium.yaml`.** Projects can set interpreters and a run
  `timeout` (default 30 s).
- **WeasyPrint moved to the `pdf` extra.** `pip install scriptorium` renders
  HTML; `pip install 'scriptorium[pdf]'` prints PDFs and decks.

### Fixes

- **Code blocks read in the docs site's dark mode.** Code blocks and their
  output kept a light frame and paper colours on the dark page; they now take
  the dark code background and dark-mode token colours.
- **The HTML book and the docs site find their assets in an installed wheel.**
  Both looked for them at the repo root, which a wheel does not have.
- **Wheels ship the themes.** The wheel packaged only `scriptorium/` and looked
  for themes at the repo root, so a non-editable install had none.

- **A `stat-strip` of four stats no longer wraps.** The strip defaulted to three
  columns, so a fourth stat dropped onto a second row carrying a dangling
  divider (the rule that removes the last divider assumes a single row). It now
  takes one column per stat, whatever the count; `two` / `three` / `four` still
  force a wrapping grid when that is what you want.

### Features

- **`lang:` sets the document language.** Every document used to be emitted as
  `<html lang='en'>`, so Spanish text was hyphenated with English patterns
  (`per-ro`, `desar-rollo`, `guer-ril-la`). Frontmatter or `scriptorium.yaml`
  `lang:` now sets it, a theme can default it (`uh` defaults to `es`), and the
  fallback stays `en`. A value that is not a language tag is a hard error,
  since it lands in an HTML attribute.
- **A `formal` theme for contracts and official letters.** All black,
  Liberation Serif at 12pt (Times New Roman metrics, vendored as unsubsetted
  WOFF2 under the OFL), 2.5 cm margins, justified without hyphenation. Tables
  are open: a heavy rule above and below, a light one under the header, no grid.
  `::: clauses` numbers its `##` headings as clauses and the ordered lists under
  them as sub-clauses (1.1, 1.2); `::: signatures` lays out `::: signature
  {name=… role=…}` blocks side by side; `::: right` and `::: center` align a
  date line or a seal line. A page-number footer is the default.
  `examples/formal.md` is a two-page services agreement.
- **Per-document `header:` / `footer:` lines.** Frontmatter or a project's
  `scriptorium.yaml` sets `left` / `center` / `right` templates that repeat on
  every page; `{page}` and `{total}` count pages, any other `{key}` reads the
  frontmatter. A theme can ship defaults under the same keys, and `false`
  removes them. Running-head values are now escaped, so a party name with a
  double quote no longer drops the whole margin box.
- **Numbered figures in `base`, opted into by the markup.** `parse.py` has always
  rewritten `@fig-name` into `<a class="ref-fig" href="#fig-name">` and left the
  text to theme CSS, and no theme supplied it, so every document that wanted a
  numbered figure hand-rolled the counters in its own stylesheet. `base` now
  numbers a `<figure>` that carries `id="fig-…"` — the same id the reference
  points at — and fills the reference in both directions. A plain `<figure>` is
  untouched, and since the engine never emits one, nothing that exists today
  changes. Two new vars carry the word, on the same contract as
  `references-label`: `figure-label` for the caption ("Figure", "Figura") and
  `figure-ref-label` for the mid-sentence form, which falls back to the first
  and exists because Spanish writes "la figura 4" but "Figura 4." to open a
  caption. The counter resets on `html`, not `body`, because `book` already
  resets its own there and a second `counter-reset` on one element replaces the
  first. An inline `<figure> svg` also gets the sizing `figure img` already had,
  so a wide generated figure shrinks to the column instead of overflowing it.

- **`syalia` theme.** SYALIA's brand identity over `report`: the ink-navy ramp
  from syalia.com, syalia blue as the accent, amber for eyebrows and kickers,
  Space Grotesk headings (vendored), and a cover master with the gradient S mark
  and the wordmark. The `report` component vocabulary is written against
  `--slate-*`, so remapping that ramp onto the ink ramp tints every KPI tile,
  card and callout without touching a component rule.

## [v0.10.0] - 2026-09-16

### Breaking

- **Executed blocks are independent; `continue` chains them.** Blocks no longer
  share one accumulated session per file. A block that needs names from an earlier
  one carries `continue` (`{python continue}`, `python {run continue}`). The shared
  session let one failing block re-raise in every later block of the file and
  leak their earlier output; a failing block now never joins a chain. Python
  tracebacks number lines from the block's first line and show the source line,
  and failing blocks render in red (`--error` in the base theme).

### Features

- **`unmarked:` timeline entries.** A `timeline.yaml` entry can now set
  `unmarked: true` to join the chronology with no marker in the prose. A
  timeline correlates a book's own events against the history that conditioned
  them, and that history has no natural place in the text — nobody writes "the
  Mongols sacked Baghdad" mid-argument just to register it, so before this such
  an event could not appear at all. Opt-in: rendering every declared entry would
  silently resurrect keys that a marker mistypes.

- **Timeline auto-grouping.** The chronology groups its entries automatically,
  cascading from century down to day. `timeline-group` and `timeline-group-max`
  in the project file control it.

### Fixes

- **Timeline ordinals past the third.** The century and millennium group labels
  used a lookup that knew only 1, 2 and 3, so a book reaching the present
  rendered "21th Century". Now derived from the last digit, with the teens
  handled — 11th, 21st, 22nd, 23rd, 112th. Found by reading a rendered
  chronology, which no test or lint rule would have caught.

- **Four front-matter defects in the `book` theme.** No blank cover page when a
  book has no `cover-image`, no mid-word hyphenation in the title page, a separator
  between title and subtitle on the copyright line, and no doubled period after an
  author name that ends in one.

## [v0.9.0] - 2026-08-18

### Features

- **Timeline.** `[>YEAR: Label]` markers and a `:::timeline` section build a
  back-of-book chronological index, with optional `timeline.yaml` enrichment.

- **`footnotes-label`.** The generated endnotes section can carry a heading, the
  last of the three apparatus components to get one — `references` and `glossary`
  already had theirs. Unset means no heading, so nothing changes for a document
  that does not ask.

### Fixes

- **The `book` theme's table of contents is half as tall.** 190 entries took 8
  pages against LaTeX's 5, mostly because `fill_toc` emits each entry as its own
  Unit and `.unit` carries the paragraph rhythm — 3.5mm under a one-line link.
  Zeroed for TOC entries, plus tighter leading. Now 5 pages.
- **`footnotes:` in a `scriptorium.yaml` is no longer ignored.** It was missing
  from `project.py`'s content-key tuple, so a project asking for
  `footnotes: document` silently got the theme's default instead — for `book`,
  per-chapter endnotes. A wrong apparatus that renders cleanly is worse than a
  crash. Where notes collect is structure, so the key sits beside `glossary:`
  and `css:` rather than under `vars:`.

## [v0.8.0] - 2026-08-12

The book apparatus: a glossary, part dividers, unnumbered front matter, a cover,
and a stylesheet a project can call its own. Everything *Mostly Harmless AI*
needed to leave Quarto — it renders in 50 s over 307 pages with no warnings.

### Features

- **Glossary.** `[~key]` and `[display]{~key}` mark a glossed term; entries come
  from `glossary:` (a mapping, or a path to a YAML file of one) and collect into
  a `::: glossary` section, alphabetical by term, each with the pages where it
  appears. `glossary-label:` names the section; unset means no heading. Joins the
  footnotes/references apparatus contract rather than starting its own.
- **`css:`** — a path or list, resolved against the project file and appended
  after the theme's rules. A book can now carry a stylesheet without authoring a
  theme inside this repo.
- **`{.part}` and `{.unnumbered}`** in the `book` theme. A part divider takes a
  part numeral, not a chapter one, and starts its own page; unnumbered front
  matter no longer consumes chapters 1–3. `{.unlisted}` keeps a heading out of
  the table of contents.
- **A cover master** for `book`: full-bleed artwork from a `cover-image` var.

### Fixes

- **A heading label is text.** `fill_toc` escaped the raw source of a heading, so
  any inline HTML in one printed as markup in the table of contents. Stripped
  where the label is built, so every consumer of `Unit.heading` benefits.
- **`_unwrap_p` only unwraps a single paragraph.** The greedy `.*` under `re.S`
  spanned a multi-paragraph component body end to end, stripping the first `<p>`
  and the last `</p>` and leaving the rest unbalanced — the first paragraph
  escaped its wrapper and stopped matching its theme's `p` rules.
- **Inline code is code.** The glossary pre-processor protected fenced blocks but
  not `` `code` `` spans, and injected raw `<a>` markup into a literal.

## [v0.7.0] - 2026-08-12

A readable references apparatus: a heading you name, back-links that say which
page, and tables that stop mangling their own labels.

### Features
- **`references-label`.** The generated references section can carry a heading.
  The var is empty by default and empty means no heading, so nothing changes for
  an existing document; set it in `theme.yml` or frontmatter to `References`,
  `Bibliografía`, or whatever the venue wants. No string is baked into the
  engine, because the label's language belongs to the document.
- **Template keys may contain hyphens.** `{{accent-dark}}` and
  `{{#references-label}}…{{/references-label}}` resolve now. Theme vars have
  always been kebab-case, so until this no var could reach a template at all.

### Fixes
- **A labelled references section drops its top rule.** The rule separates an
  unlabelled block from the prose above it; with a heading the two read as a
  doubled divider.
- **Back-links carry the page they point at.** A reference cited four times used
  to end in four identical `↩` marks, which told the reader nothing about where
  the citations were. The apparatus is now one arrow followed by the page number
  of each call site (`↩ 4, 7, 12`), resolved by CSS `target-counter` — the same
  mechanism the `book` theme already uses for cross-references and its TOC.
- **Table headers and bold row labels never hyphenate.** Narrow columns turned
  `APPROACH / SYSTEM` into `AP-PROACH / SYSTEM` and `CodeAct (Python)` into
  `CodeAct (Py-thon)`. Both are labels rather than prose, so the same rule that
  already protects headings and inline code now covers them; wrapping at spaces
  is still allowed.
- **A table row moves whole.** The tallest cell used to drag a page break
  through its own row, leaving a label on one page and its cells on the next.

## [v0.6.0] - 2026-08-12

Narrative citations: the author's name in the running text, declared rather
than parsed.

### Features
- **Narrative citations.** `[+@key]` renders the author's name before the
  numbered mark (`Tam et al. [1]`); `[-@key]` renders the name alone, with no
  mark and no references entry. Both read a declared `author:` from an
  `{author, text}` bibliography entry — the engine never parses a name out of
  entry prose, and never derives one from the key. Prose-string entries and bare
  `[@key]` are unchanged. A sigil on an entry with no `author:`, or on a
  multi-key span, leaves the span literal and warns.
- **Bibliography entries take a mapping.** A value may stay a prose string or
  become `{author, text}`. `text:` is the prose that reaches the references
  section; `author:` is the literal name the narrative forms emit, so "et al."
  versus "and" versus a single surname is the author's decision rather than a
  heuristic on the key.

### Fixes
- **A loose list is one block, so its numbering survives.** Prose is split on
  blank lines to measure paragraphs independently, but a loose list is
  blank-line separated by definition, so each item became its own `<ol>` and
  "1. 2. 3." rendered as "1. 1. 1.", with continuation paragraphs detached from
  their item.
- **Inline code never hyphenates.** `FechaRetiro` broken across a narrow table
  column came out as `FechaRe-tiro`; in a document whose subject is the exact
  column names that is a wrong answer, not a blemish. Wrapping is still allowed
  — the token splits without a character being invented.

### Other
- The claim that author-date was "impossible by construction" is retired from
  the module docstring, `docs/design.md` §7.5, `tasks.md` and the README. What
  is impossible is *extraction* from prose; *declaration* was never ruled out.
  The open CSL item is narrowed to what still needs structured entries and a
  style engine: author-date marks everywhere, alphabetical ordering, and
  `2026a` / `2026b` disambiguation.

## [v0.5.0] - 2026-08-11

Citations: `[@key]` against an author-declared bibliography, collected into
a references section distinct from the footnote apparatus.

### Features
- **Numbered citations.** `[@key]` and `[@a; @b]` resolve against a
  `bibliography:` map declared in frontmatter — or, for a multi-file project, as
  a top-level key in `scriptorium.yaml` — and render as `[1]` / `[1, 2]`,
  collecting into a generated references section. Cited works only, numbered by
  first appearance, with `nocite:` for anything to be listed without citing.
  Entries are Markdown prose, so their links and emphasis survive to the page.
  Notes and references are separate apparatuses: distinct sections, distinct
  counters, bracketed `[1]` versus a bare superscript.
- **`Report.warnings`**, printed by the CLI beside the oversize warnings.
  Document renders previously emitted no warnings at all.

### Fixes
- **Footnote problems are now actually reported.** The v0.4.0 design said an
  unresolved `[^marker]` was reported; it was silently skipped, because there
  was no channel to report it on. A marker with no definition and a definition
  nobody references both warn now.
- **No more empty notes section.** A document whose only footnote definition was
  never cited emitted a bare `::: footnotes` block, which rendered as an empty
  ruled band.

## [v0.4.0] - 2026-08-11

Footnotes: real Markdown `[^id]` notes as endnotes or page-bottom floats,
replacing the hand-numbered house convention.

### Features
- **Markdown footnotes.** `[^a]` markers with `[^a]: body` definitions, numbered
  automatically, collected into an endnotes section at the end of the document
  or of each chapter — or floated to the foot of the page. The mode is the
  `footnotes:` key (`document` | `chapter` | `page`), frontmatter over theme;
  `book` defaults to `chapter`. Note bodies keep their Markdown, and a note
  referenced twice gets a back-link per call site.
- **Per-page footnotes**, via WeasyPrint's CSS GCPM `float: footnote`. The
  design previously rejected these as circular; that applied to the Python
  bin-packer v0.3.0 replaced.

### Fixes
- **Cross-references no longer delete prose.** `@type-id` matched *any*
  hyphenated prefix and rewrote it to an anchor with no target, which renders
  empty — so `@smith-2020`, `@piad-morffis-2024` or a GitHub handle silently
  vanished from the PDF. Only `fig` `tbl` `sec` `eq` `lst` `thm` `chap` are
  rewritten now; everything else stays literal text, which also frees the `@key`
  namespace for a future citations feature.

### Removed
- `citations.py` and the hand-numbered `^[N](#ref-N)^` / `### N {#ref-N}` house
  convention it served, with its `.cite-*` and `.bib-*` CSS. Markdown footnotes
  replace it outright. Documents still written the old way degrade to visible
  literal text, not a crash.

## [v0.3.1] - 2026-08-11

### Fixes
- **A document can declare its own theme.** `theme:` in frontmatter was ignored —
  the theme was loaded before the frontmatter was read, so every single-file
  render used `--theme` or fell back to `report`. `scriptorium render talk.md`
  on a deck therefore produced a flowed report, not slides. Resolution order is
  now explicit (`--theme`, or a project's `scriptorium.yaml`) → frontmatter
  `theme:` → default.
- Every file in `examples/` declares its theme, so the examples render correctly
  straight from the README with no flag.

## [v0.3.0] - 2026-08-11

Slides and scholarship: a 16:9 deck format, LaTeX-style citations, and a
pagination engine rebuilt on CSS Fragmentation instead of Python bin-packing.

### Features
- **Deck format** — a theme with `mode: deck` renders 16:9 (or 4:3, or explicit
  `WxH`) slides instead of flowing pages, split at section (`#` → divider) and
  slide (`##` → content) boundaries. Page geometry is theme-driven. Oversized
  slides warn rather than auto-shrink.
- **Deck masters** — `::: toc` becomes an agenda slide listing sections with
  their slide numbers; `statement` gives a full-bleed single-line slide;
  `closing` a final slide with a contact line. The `deck` theme extends
  `report`, so KPI tiles, finding cards, and stat strips drop straight onto
  slides.
- **Citations** — `^[N](#ref-N)^` and `[N](#ref-N)` render as true superscript
  links and gain double-sided hyperlinks: each bibliography entry carries
  back-links (↑ 1, 2, …) to every place it is cited.
- **CSS Fragmentation pagination** — document themes now emit one continuous
  flow and let WeasyPrint break it: `break-after: avoid` on headings,
  `break-inside: avoid` on keep blocks and figures, named `@page` rules for
  full-page masters, `@page` margin boxes for running heads and stamps, and
  `string-set` for automatic running chapter/section titles. Prose flows across
  page boundaries instead of leaving gaps. The deck path keeps the measure/pack
  pipeline.
- **Article typography** — justified text with real hyphenation (`lang` reaches
  pyphen), orphan/widow control, and compact full-width tables that never
  overflow the margin.
- **Frontmatter `vars:`** — a single document can override `accent`, fonts, and
  other theme vars from its own frontmatter, same contract as `scriptorium.yaml`.

### Fixes
- Deck slides no longer fragment onto a second page each — `@page` was adding
  the theme margin on top of the slide's own padding. The reported page count is
  now the PDF's real page count, not the slide count.
- A five-section agenda fits on one slide again (stacked unit gap and entry
  margins were compounding).
- `report`: bold text is visible on dark surfaces (`.cta`, `.page.dark`), `.tier`
  owns its body colour, and `.sec-title` does not hyphenate.
- Headings never hyphenate, with a `.no-hyphen` utility for inline spans.
- Bibliography entries lay out with flexbox, so back-links stay right-aligned on
  the entry's first line instead of wrapping to their own row.
- Full-page masters render from the pre-rendered template HTML.

### Other
- Public README, `AGENTS.md`, and `know-how/` (galley engine, theme authoring,
  deck format, releasing).

## [v0.2.0] - 2026-07-28

The theme system — a small set of archetypes you customize and inherit from,
spanning conference notes to polished books.

### Features
- **Theme inheritance** — `extends:` in `theme.yml` merges a parent's CSS,
  components, masters, and var-defaults (child wins), so a theme is a diff.
- **`base` + a default lineup** (simple → gorgeous): `note` (handouts),
  `article` (essays/whitepapers), `report` (data-forward briefings), `book`
  (classic long-form). Each has a distinct point of view.
- **Customization contract** — `accent`, `body-font`, `heading-font`,
  `mono-font`, etc. injected as CSS custom properties; rebrand a document with
  `vars:` alone, no theme authoring.
- **Vendored fonts that actually embed** — Inter, Source Serif 4, JetBrains Mono
  ship as woff2; relative `@font-face` urls are rewritten to absolute at load
  (they were silently falling back to system fonts before).
- **Template loops** — `{{#list}}…{{/list}}` iterates with per-item scope,
  `{{_n}}` index, and `{{.}}` for scalar lists; sections nest and drop when empty.
- **Academic title block** (article) — title, subtitle, multiple authors with
  numbered affiliations, date, abstract, and keywords, driven from frontmatter.

### Fixes
- The page margin is a single value: galley injects it and `base` applies it as
  `.page` padding, so the visual inset can't disagree with the measured content
  width (some themes were rendering with no margin).

### Other
- Scrubbed all project-specific references — scriptorium is a generic tool.

## [v0.1.0] - 2026-07-28

First release. A Markdown-native document engine that weaves to exact-geometry
paginated PDF, executes code in place, and tangles code to source — validated by
rendering a full 440-page technical book (title/copyright pages, dozens of
chapters and appendices, with every `{python}` cell executed).

### Features
- **galley pagination engine** — measure → pack → emit to exact-geometry A4 pages,
  with a drift guard, keep-with-next headings, and line-splitting for code and
  tables so listings never overflow.
- **Themes as project templates** — directory-backed themes (CSS + components +
  masters); a `marketing` report theme and a `book` theme. Numbering,
  cross-references, and TOC page numbers are pure theme CSS (counters,
  `target-counter`/`target-text`).
- **Execution** — run fenced code in a subshell and splice stdout back
  (Quarto-`{python}` monospace or native `{run}` raw-markdown); shared-kernel
  session state, `PYTHONPATH`, and a freeze cache.
- **Tangle** — `export=` code extraction (illiterate-compatible, byte-exact),
  with provenance labels showing each block's file and line range.
- **Math** — LaTeX `$…$` / `$$…$$` to SVG via quickjax (MathJax in QuickJS,
  pure Python, no Node), freeze-cached.
- **Projects** — `scriptorium.yaml` (theme + vars + file list) with `{{var}}`
  substitution; running heads and auto-TOC.
- **CLI** — `scriptorium render` (document or project) and `scriptorium tangle [--test]`.
