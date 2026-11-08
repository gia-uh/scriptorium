"""The docs site in Chromium: no script errors, nothing wider than a phone, the
drawer, search and the audio file.

Skipped when no Chromium is found: Playwright's own download, or a system one.
"""

import pytest
from test_docs import build_docs
from test_reader_browser import DESK, PHONE, browser  # noqa: F401 (a fixture)

pytestmark = pytest.mark.browser
playwright = pytest.importorskip("playwright.sync_api")

PAGES = ["index.html", "sound.html", "what.html", "exercises.html", "strings.html", "exercises-2.html"]


@pytest.fixture(scope="module")
def url(tmp_path_factory, serve):
    return serve(build_docs(tmp_path_factory.mktemp("docs")))


def _open(browser, url, device):
    ctx = browser.new_context(**device)
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type in ("error", "warning") else None)
    page.on("response", lambda r: page.errors.append(f"{r.status} {r.url}")
            if r.status >= 400 and not r.url.endswith("/favicon.ico") else None)
    page.goto(url)
    return ctx, page


@pytest.mark.parametrize("device", [PHONE, DESK], ids=["phone", "desktop"])
def test_no_script_errors_on_any_page(browser, url, device):
    for name in PAGES:
        ctx, page = _open(browser, url + name, device)
        page.wait_for_load_state("load")
        assert page.errors == [], name
        ctx.close()


def test_nothing_is_wider_than_the_phone(browser, url):
    for name in PAGES:
        ctx, page = _open(browser, url + name, PHONE)
        assert page.evaluate("document.documentElement.scrollWidth") <= 390, name
        ctx.close()


def test_the_menu_opens_the_sidebar_on_a_phone(browser, url):
    ctx, page = _open(browser, url + "what.html", PHONE)
    assert not page.is_visible(".sidebar a[aria-current]")
    page.click(".topbar .menu")
    page.wait_for_timeout(400)
    assert page.is_visible(".sidebar a[aria-current]")
    ctx.close()


def test_a_long_code_line_scrolls_inside_its_block(browser, url):
    ctx, page = _open(browser, url + "strings.html", PHONE)
    pre = page.evaluate("(() => { const p = document.querySelector('main pre');"
                        " return [p.scrollWidth, p.clientWidth, getComputedStyle(p).whiteSpace]; })()")
    assert pre[0] > pre[1] and pre[2] == "pre"
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    ctx.close()


@pytest.mark.parametrize("how", ["escape", "outside"])
def test_the_drawer_closes_with_escape_or_a_click_outside(browser, url, how):
    ctx, page = _open(browser, url + "what.html", PHONE)
    page.click(".topbar .menu")
    page.wait_for_timeout(400)
    if how == "escape":
        page.keyboard.press("Escape")
    else:
        page.mouse.click(370, 600)
    page.wait_for_timeout(400)
    assert not page.is_visible(".sidebar a[aria-current]") and page.url.endswith("what.html")
    ctx.close()


def test_search_retries_after_a_failed_fetch(browser, url):
    ctx, page = _open(browser, url, DESK)
    page.route("**/search.json", lambda route: route.abort())
    page.click(".topbar .search input")
    page.wait_for_timeout(300)
    page.unroute("**/search.json")
    page.errors.clear()  # the aborted request is the point of the test
    page.click("main")
    page.click(".topbar .search input")
    page.keyboard.type("wav")
    page.wait_for_selector(".search-results a")
    assert page.errors == []
    ctx.close()


@pytest.mark.parametrize("device", [PHONE, DESK], ids=["phone", "desktop"])
def test_search_finds_a_section(browser, url, device):
    ctx, page = _open(browser, url, device)
    page.click(".topbar .search input")
    page.keyboard.type("wav")
    page.wait_for_selector(".search-results a")
    assert page.get_attribute(".search-results a", "href") == "what.html?h=wav#waves"
    assert page.inner_text(".search-results a mark") == "Waves"
    ctx.close()


def test_the_audio_file_loads(browser, url):
    ctx, page = _open(browser, url + "what.html", DESK)
    status = page.evaluate("fetch(document.querySelector('audio').src).then(r => r.status)")
    assert status == 200 and page.get_attribute("audio", "src").startswith("media/")
    ctx.close()


@pytest.fixture(scope="module")
def chrome_url(tmp_path_factory, serve):
    """A site with every header piece: logo, version, a GitHub repository and a palette."""
    from scriptorium.docs import render_docs
    from scriptorium.project import Output

    d = tmp_path_factory.mktemp("chrome")
    (d / "mark.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"/>')
    render_docs("# A rather long chapter title {#one}\n\n## Part {#a}\n\nText.\n", d / "site",
                output=Output(name="site", format="docs", dir="site", logo="mark.svg", version="10.20.30",
                              repo_url="https://github.com/ana/a-library-with-a-long-name",
                              palette={"primary": "#0f766e"}),
                base_dir=d, theme_name="book", execute=False)
    return serve(d / "site")


def _fake_github(route):
    body = '[{"tag_name": "v1.2.1"}]' if "/releases" in route.request.url else '{"stargazers_count": 12}'
    route.fulfill(status=200, content_type="application/json", body=body,
                  headers={"Access-Control-Allow-Origin": "*"})


def test_the_scheme_toggle_cycles_and_is_remembered(browser, chrome_url):
    ctx, page = _open(browser, chrome_url + "one.html", DESK)
    page.route("https://api.github.com/**", _fake_github)
    modes = []
    for _ in range(3):
        page.click(".topbar .scheme")
        modes.append(page.evaluate("[document.documentElement.dataset.schemeMode, document.documentElement.dataset.scheme]"))
    assert modes == [["light", "light"], ["dark", "dark"], ["auto", "light"]]
    page.click(".topbar .scheme")
    page.click(".topbar .scheme")  # dark
    page.reload()
    assert page.evaluate("document.documentElement.dataset.scheme") == "dark"
    ctx.close()


def _open_routed(browser, url, device, init=""):
    """Open with the GitHub API faked from the first request on."""
    ctx = browser.new_context(**device)
    if init:
        ctx.add_init_script(init)
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.route("https://api.github.com/**", _fake_github)
    page.goto(url)
    return ctx, page


def test_a_stored_dark_choice_applies_before_the_first_paint(browser, chrome_url):
    init = ("try { localStorage.setItem('scriptorium-scheme', 'dark') } catch (e) {}"
            "document.addEventListener('DOMContentLoaded', () => { window.seen = ["
            "document.documentElement.dataset.scheme, getComputedStyle(document.body).backgroundColor] });")
    ctx, page = _open_routed(browser, chrome_url + "one.html", DESK, init)
    assert page.evaluate("window.seen") == ["dark", "rgb(22, 24, 29)"]
    ctx.close()


def test_the_repository_shows_its_latest_tag_and_stars(browser, chrome_url):
    ctx, page = _open_routed(browser, chrome_url + "one.html", DESK)
    page.wait_for_selector(".repo-facts:not([hidden])")
    assert page.inner_text(".repo-facts") == "v1.2.1 · ★ 12"
    assert page.errors == []
    ctx.close()


def test_a_failed_api_call_is_not_cached(browser, chrome_url):
    ctx = browser.new_context(**DESK)
    page = ctx.new_page()
    page.route("https://api.github.com/**", lambda route: route.abort())
    page.goto(chrome_url + "one.html")
    page.wait_for_timeout(300)
    assert page.is_hidden(".repo-facts")
    page.unroute("https://api.github.com/**")
    page.route("https://api.github.com/**", _fake_github)
    page.reload()
    page.wait_for_selector(".repo-facts:not([hidden])")
    ctx.close()


def test_the_header_fits_a_phone(browser, chrome_url):
    ctx, page = _open(browser, chrome_url + "one.html", PHONE)
    page.route("https://api.github.com/**", _fake_github)
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    assert page.is_visible(".topbar .scheme") and page.is_visible(".topbar .repo svg")
    assert not page.is_visible(".topbar .version")
    ctx.close()


def test_search_keys_move_and_open_a_result(browser, url):
    ctx, page = _open(browser, url + "index.html", DESK)
    page.keyboard.press("Control+k")
    assert page.evaluate("document.activeElement.matches('.topbar .search input')")
    page.keyboard.type("pluck")
    page.wait_for_selector(".search-results a.selected")
    hrefs = page.eval_on_selector_all(".search-results a", "as => as.map(a => a.getAttribute('href'))")
    assert len(hrefs) >= 2
    page.keyboard.press("ArrowDown")
    assert page.get_attribute(".search-results a.selected", "href") == hrefs[1]
    page.keyboard.press("ArrowUp")
    page.keyboard.press("Enter")
    page.wait_for_url("**/" + hrefs[0].split("?")[0] + "*")
    assert "?h=" not in page.url  # the page reads the words, then drops them from the address
    assert page.inner_text("main mark.search-hit") == "Pluck"
    ctx.close()


def test_the_phone_search_takes_the_whole_bar(browser, url):
    ctx, page = _open(browser, url + "what.html", PHONE)
    page.click(".topbar .search input")
    page.keyboard.type("wav")
    page.wait_for_selector(".search-results a")
    box = page.evaluate("(() => { const r = document.querySelector('.topbar .search').getBoundingClientRect();"
                        " const s = document.querySelector('.search-results').getBoundingClientRect();"
                        " return [r.width, s.width]; })()")
    assert box[0] > 350 and box[1] > 350
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    ctx.close()


@pytest.fixture(scope="module")
def code_url(tmp_path_factory, serve):
    """A page with an executed, exported block: its title, its output, a copy button."""
    from scriptorium.docs import render_docs
    from scriptorium.project import Output

    d = tmp_path_factory.mktemp("code")
    src = ('# Code {#code}\n\n```{python export=examples/hello.py}\nprint("hello")\n```\n\n'
           '```text\n' + "x" * 300 + '\n```\n')
    render_docs(src, d / "site", output=Output(name="site", format="docs", dir="site"),
                base_dir=d, execute=True)
    return serve(d / "site")


def test_copy_takes_the_code_and_not_its_output(browser, code_url):
    ctx = browser.new_context(**DESK, permissions=["clipboard-read", "clipboard-write"])
    page = ctx.new_page()
    page.goto(code_url + "code.html")
    page.hover("main .codeblock")
    page.click("main .codeblock .copy")
    page.wait_for_function("document.querySelector('main .codeblock .copy').textContent === 'Copied'")
    assert page.evaluate("navigator.clipboard.readText()") == 'print("hello")'
    ctx.close()


def test_the_title_bar_and_the_output_label(browser, code_url):
    ctx, page = _open(browser, code_url + "code.html", DESK)
    assert page.inner_text("main .code-file .code-lang") == "python"
    assert page.inner_text("main .code-file").startswith("examples/hello.py")
    label = page.evaluate("getComputedStyle(document.querySelector('main pre.output'), '::before').content")
    assert label == '"Output"'
    assert page.inner_text("main pre.output").strip().endswith("hello")
    joined = page.evaluate("(() => { const o = document.querySelector('main pre.output').getBoundingClientRect();"
                           " const c = document.querySelector('main .codeblock .hl').getBoundingClientRect();"
                           " return [Math.round(o.top - c.bottom),"
                           " getComputedStyle(document.querySelector('main pre.output')).borderTopStyle]; })()")
    assert joined[0] <= 0 and joined[1] == "dashed"
    ctx.close()


def test_code_blocks_fit_a_phone(browser, code_url):
    ctx, page = _open(browser, code_url + "code.html", PHONE)
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    assert page.is_visible("main .codeblock .copy")  # no hover on a phone, so it always shows
    ctx.close()
