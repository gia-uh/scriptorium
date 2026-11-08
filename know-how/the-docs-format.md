# The docs format

*When to reach for it: changing the `docs` output, its layout or search in
`themes/base/docs/`, or debugging a docs site whose pages, links or search come
out wrong.*

`render_docs()` (`scriptorium/docs.py`) writes a static site from the same
units a PDF prints from: `index.html`, one `<slug>.html` per page, `docs.css`,
`docs.js`, `search.json`, `media/`, `img/`, `fonts/`. Every URL is relative.
There is no service worker and no manifest: documentation is read online.

## How pages are split

`pages()` cuts the units with `book._chapters()`, at each `#` heading, so
chapters, parts and full-page openers split as in the HTML book. Each page is
named by `media.page_units()`: the chapter heading's id, made unique with `-2`,
`-3`… (two chapters titled "Exercises" become `exercises.html` and
`exercises-2.html`). `index` is reserved for the front page, so a chapter
titled "Index" becomes `index-2.html`. The PDF's audio links use the same
function, so a PDF link and the site always agree on a page's name.

- Units before the first `#` heading go to `index.html`, which always exists
  and also lists the parts and chapters.
- A part heading (`{.part}`) with text under it is a page of kind `part`.
- A part heading with nothing under it is only a label in the sidebar and
  not in `pages()`. `render_docs()` finds it as a unit whose slug has no page:
  its ids link to the page after it, and its heading is counted after the
  page before it, so later parts keep their numbers.
- A document without any `#` heading is one index page.

Each page is wrapped in a `<section>` and passed through
`book._carry_counters()`, as the book does, so chapter, part, figure and audio
numbers continue from page to page.

## How cross-page links are rewritten

`resolve_refs()` first writes each `@ref` text, exactly as for the book. Then
every `href="#id"` whose id lives on another page becomes
`href="<slug>.html#id"`; links to ids on the same page stay as they are, and
so does a link to an id that this page defines even if another page defines it
too. That rule is what keeps formulas drawing: MathJax names each formula's
glyphs `MJX-<n>-…` and points at them with `xlink:href="#MJX-…"`, and the same
names recur on every page that has formulas. Each
`##` and `###` gets a trailing `<a class="anchor">#</a>` after the references
are resolved, so a reference to a section reads its title without the `#`.

## Where the layout lives

- `themes/base/docs/docs.css`: the grid (sidebar 240 px, content up to 72ch,
  outline 200 px) above 1100 px, two columns down to 640 px, one column with
  the sidebar as a drawer (`body.drawer-open`) below. Colours come from the
  theme's `--ink`, `--muted`, `--rule` and `--accent`; the dark scheme
  overrides them and makes headings inherit the text colour, because themes
  darken headings from their own scales. The themes wrap code for paper
  (`.hl pre { white-space: pre-wrap }`); the docs layout sets `white-space:
  pre` so a long line scrolls inside its block. Nothing clips overflow on
  `body`: content wider than the screen must show up, and fail the tests.
- On a phone the drawer closes on a link, on Escape and on a click on the
  dimmed page behind it, which does nothing else.
- `themes/base/docs/docs.js`: the menu button, the outline entry of the
  section in view (an `IntersectionObserver`), the `/` key, and search.
- The page shell (top bar, sidebar, outline, pager) is built in `_shell()`.

The site's `docs.css` is the theme's CSS through `browser_css()`, then the
layout, then the output's own `css:` files, so a project can restyle anything.

## The top bar and the scheme

`_shell()` builds the bar: logo (`logo.<ext>` copied next to the pages),
title, version (`resolve_version()`: a literal, or `auto` from the nearest
`pyproject.toml`, then `git describe --tags`), search, the scheme button and
`_repo_widget()`. Only a `github.com` URL gets `data-github`, which makes
`docs.js` ask the GitHub API for the stars and the latest release; a failed
request is not cached, so the next page tries again.

The scheme is `<html data-scheme="light|dark">` with `data-scheme-mode`
(`auto|light|dark`). `_SCHEME_SCRIPT` sets both inline in `<head>`, before the
stylesheet, from `localStorage["scriptorium-scheme"]`, the project's
`palette.scheme`, or `prefers-color-scheme`. Every dark rule in `docs.css` is
keyed on `[data-scheme="dark"]`, not on the media query: a media query would
ignore the reader's choice. `palette_css()` appends the palette after the
layout, on both `:root` and `:root[data-scheme="dark"]`, so it wins in both.

`typography: docs` adds `typo-docs` to `<body>`; the rule sits on `body.docs`
so it outranks a theme's bare `body` font, and on the text blocks for
alignment and hyphenation.

When you preview a change on a real project, install the working tree
editable (`uv run --with-editable <scriptorium>`): `--with <path>` installs a
cached copy and the site keeps the old `docs.css`.

## Search

`search_index()` writes one entry per `##` and `###` section, and one for a
page's text before its first section: `page`, `title`, `url`, and `text`
(tags stripped, at most 600 characters). The script fetches `search.json` on
the box's first focus, and again on a later focus if that fetch failed. Every
query word must be a prefix of a word in the entry; a title word scores 2, a
text word 1; the first ten show, with the chapter under each when it differs
from the title.

Results show the chapter under the section title and a snippet of about 140
characters around the first match, with every match in `<mark>`; all of it is
built with text nodes, never `innerHTML`, because the index holds page text.
Arrow keys move `.selected`, Enter opens it, Escape closes, and `/` (outside a
text field), Ctrl-K and Cmd-K focus the box. A result's link carries `?h=<the
words>`; the page it opens wraps prefix matches in `main` in
`mark.search-hit` and drops `?h=` from the address with `replaceState`. Below
640 px the focused box (`.search.open`) covers the bar and the results take the
screen's width.

## Code blocks

`parse._code_units()` gives every echoed block `data-lang` and, when it
tangles or has `title=`, a `.code-file` label; `docs.js` adds the language to
that label and a `.copy` button that copies `.code-src` only. Every unit is
wrapped in `div.unit`, so the rule that joins an output to its code is
`.unit:has(> .codeblock) + .unit > pre.output`, and the theme's `.unit` bottom
margin has to go too; a plain `.codeblock + pre.output` never matches. The
"Output" label is `pre.output::before { content: var(--docs-output-label) }`,
set on `<body>` from the site's language.

## The page foot and the site files

`page_files()` maps each page to its chapter file by matching the files' `#`
headings (outside code fences) to the page titles in order; the CLI passes the
project's `files:` for this. Files are joined with `\newpage`, but counting
breaks would fail on a chapter that has its own. From the file come the date
(`git log -1 --format=%cs`) and `edit_url()` (`/edit/HEAD/<prefix><file>` on
GitHub, `/-/edit/HEAD/…` on GitLab, where the prefix is `edit-path` or `git
rev-parse --show-prefix`). `404.html` has a `<base href>` only when `base-url`
is set; `sitemap.xml` is written only then.

## Testing

`tests/test_docs.py` builds a small site (two parts, one without text, two
chapters with the same title, an audio figure) and checks the files, links and
index. `tests/test_docs_browser.py` serves the same site in Chromium:

```bash
uv run pytest tests/test_docs_browser.py -q
```

It is skipped when no Chromium is found (Playwright's own, or
`SCRIPTORIUM_CHROMIUM`). The width check fails only when something widens the
page itself: the drawer is fixed and off-screen, so a wider drawer does not,
and the theme's code box has `overflow: hidden`. To see it fail, give `main`
a `min-width: 500px`; to see the code check fail, set `white-space: pre-wrap`
back on `pre`. Look at a layout change at 1440 px and 390 px as well; the tests check
behaviour, not looks.
