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

## Search

`search_index()` writes one entry per `##` and `###` section, and one for a
page's text before its first section: `page`, `title`, `url`, and `text`
(tags stripped, at most 600 characters). The script fetches `search.json` on
the box's first focus, and again on a later focus if that fetch failed. Every
query word must be a prefix of a word in the entry; a title word scores 2, a
text word 1; the first ten show, with the chapter under each when it differs
from the title.

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
