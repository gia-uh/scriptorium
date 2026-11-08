// The docs page script: the drawer on a phone, the outline entry of the
// section in view, search and its keys, the colour scheme toggle, and the
// repository's latest tag and stars.
(function () {
  "use strict";
  const body = document.body;
  const menu = document.querySelector(".topbar .menu");
  const input = document.querySelector(".topbar .search input");

  if (menu) {
    menu.addEventListener("click", function () {
      const open = body.classList.toggle("drawer-open");
      menu.setAttribute("aria-expanded", String(open));
    });
    const close = function () {
      body.classList.remove("drawer-open");
      menu.setAttribute("aria-expanded", "false");
    };
    document.querySelectorAll(".sidebar a").forEach(function (a) { a.addEventListener("click", close); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && body.classList.contains("drawer-open")) close();
    });
    // a click on the page behind the open drawer closes it and goes no further
    document.addEventListener("click", function (e) {
      if (!body.classList.contains("drawer-open") || e.target.closest(".sidebar, .topbar .menu")) return;
      e.preventDefault();
      e.stopPropagation();
      close();
    }, true);
  }

  const links = new Map();
  document.querySelectorAll(".outline a").forEach(function (a) {
    links.set(decodeURIComponent(a.getAttribute("href").slice(1)), a);
  });
  if (links.size && "IntersectionObserver" in window) {
    const seen = new Set();
    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { e.isIntersecting ? seen.add(e.target.id) : seen.delete(e.target.id); });
      let current = null;
      for (const id of links.keys()) {
        if (seen.has(id)) { current = id; break; }
      }
      if (!current) return;
      links.forEach(function (a, id) { a.classList.toggle("active", id === current); });
    }, { rootMargin: "0px 0px -60% 0px" });
    links.forEach(function (_, id) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
  }

  // Search: the index is fetched on the box's first focus. Every query word
  // must be a prefix of a word in the entry; a word in the title scores 2,
  // one only in the text scores 1. Results show a snippet around the first
  // match, matches are marked, arrow keys move, Enter opens, and the page a
  // result opens marks the words too (?h= in its link).
  const results = document.querySelector(".topbar .search-results");
  const box = document.querySelector(".topbar .search");
  let index = null, loading = false, selected = -1;
  const words = function (s) { return s.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean); };
  const escapeRe = function (s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); };
  const prefixRe = function (query) {
    return new RegExp("(?<![\\p{L}\\p{N}])(" + query.map(escapeRe).join("|") + ")[\\p{L}\\p{N}]*", "giu");
  };

  // Append `text` to `el`, wrapping each match of `re` in <mark>; never innerHTML.
  function marked(el, text, re) {
    let last = 0;
    re.lastIndex = 0;
    for (let m; (m = re.exec(text));) {
      el.appendChild(document.createTextNode(text.slice(last, m.index)));
      const mk = document.createElement("mark");
      mk.textContent = m[0];
      el.appendChild(mk);
      last = m.index + m[0].length;
    }
    el.appendChild(document.createTextNode(text.slice(last)));
  }

  function snippet(text, re) {
    re.lastIndex = 0;
    const m = re.exec(text);
    if (!m) return text.slice(0, 120) + (text.length > 120 ? "…" : "");
    const start = Math.max(0, m.index - 40);
    return (start ? "…" : "") + text.slice(start, start + 140) + (start + 140 < text.length ? "…" : "");
  }

  function select(n) {
    const links = results.querySelectorAll("a");
    if (!links.length) return;
    selected = (n + links.length) % links.length;
    links.forEach(function (a, i) { a.classList.toggle("selected", i === selected); });
    links[selected].scrollIntoView({ block: "nearest" });
  }

  function search() {
    const query = words(input.value);
    results.textContent = "";
    selected = -1;
    if (!query.length || !index) { results.hidden = true; return; }
    const hits = [];
    for (const entry of index) {
      let score = 0;
      for (const q of query) {
        if (entry.titleWords.some(function (w) { return w.startsWith(q); })) score += 2;
        else if (entry.textWords.some(function (w) { return w.startsWith(q); })) score += 1;
        else { score = 0; break; }
      }
      if (score) hits.push([score, entry]);
    }
    hits.sort(function (a, b) { return b[0] - a[0]; });
    if (!hits.length) {
      const none = document.createElement("p");
      none.textContent = results.dataset.none || "No results";
      results.appendChild(none);
    }
    const re = prefixRe(query);
    const h = "?h=" + encodeURIComponent(query.join(" "));
    hits.slice(0, 10).forEach(function (hit) {
      const e = hit[1], a = document.createElement("a");
      const hash = e.url.indexOf("#");
      a.href = hash < 0 ? e.url + h : e.url.slice(0, hash) + h + e.url.slice(hash);
      const title = document.createElement("strong");
      marked(title, e.title, re);
      a.appendChild(title);
      if (e.page !== e.title) {  // a chapter's own text needs no chapter line
        const small = document.createElement("small");
        small.textContent = e.page;
        a.appendChild(small);
      }
      if (e.text) {
        const span = document.createElement("span");
        span.className = "snippet";
        marked(span, snippet(e.text, re), re);
        a.appendChild(span);
      }
      results.appendChild(a);
    });
    if (hits.length) select(0);
    results.hidden = false;
  }

  // The page a result opened marks the searched words in its text.
  (function markPage() {
    const q = new URLSearchParams(location.search).get("h");
    const main = document.querySelector("main");
    if (!q || !main) return;
    const re = prefixRe(words(q));
    const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        return n.parentElement.closest("script, style, .anchor, mark") ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT;
      }
    });
    const nodes = [];
    for (let n; (n = walker.nextNode());) { re.lastIndex = 0; if (re.test(n.nodeValue)) nodes.push(n); }
    nodes.forEach(function (n) {
      const frag = document.createDocumentFragment();
      marked(frag, n.nodeValue, re);
      frag.querySelectorAll("mark").forEach(function (m) { m.className = "search-hit"; });
      n.parentNode.replaceChild(frag, n);
    });
    history.replaceState(null, "", location.pathname + location.hash);
  })();

  function clearPageMarks() {
    document.querySelectorAll("mark.search-hit").forEach(function (m) {
      m.replaceWith(document.createTextNode(m.textContent));
    });
  }

  if (input && results) {
    // a failed fetch (offline, or a site opened from file://) is retried on the next focus
    input.addEventListener("focus", function () {
      box.classList.add("open");
      if (index || loading) return;
      loading = true;
      fetch("search.json").then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      }).then(function (entries) {
        index = entries.map(function (e) {
          return Object.assign({ titleWords: words(e.title), textWords: words(e.text) }, e);
        });
        search();
      }).catch(function () {}).finally(function () { loading = false; });
    });
    input.addEventListener("input", function () { clearPageMarks(); search(); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { results.hidden = true; box.classList.remove("open"); input.blur(); }
      else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        select(selected + (e.key === "ArrowDown" ? 1 : -1));
      } else if (e.key === "Enter") {
        const links = results.querySelectorAll("a");
        const pick = links[selected >= 0 ? selected : 0];
        if (pick) location.href = pick.href;
      }
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".topbar .search")) { results.hidden = true; box.classList.remove("open"); }
    });
  }

  // The scheme toggle cycles auto, light, dark. The inline script in <head>
  // applied the stored choice before the first paint; this keeps it current.
  const root = document.documentElement;
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  function applyScheme(mode) {
    root.dataset.schemeMode = mode;
    root.dataset.scheme = mode === "auto" ? (system.matches ? "dark" : "light") : mode;
  }
  const toggle = document.querySelector(".topbar .scheme");
  if (toggle) {
    toggle.addEventListener("click", function () {
      const order = ["auto", "light", "dark"];
      const mode = order[(order.indexOf(root.dataset.schemeMode || "auto") + 1) % order.length];
      try { localStorage.setItem("scriptorium-scheme", mode); } catch (e) { /* storage off */ }
      applyScheme(mode);
    });
  }
  system.addEventListener("change", function () {
    if ((root.dataset.schemeMode || "auto") === "auto") applyScheme("auto");
  });

  // A GitHub repository shows its latest tag and stars, from the GitHub API,
  // kept for an hour in sessionStorage. When a request fails, only the name shows.
  const repo = document.querySelector(".topbar .repo[data-github]");
  if (repo) {
    const slug = repo.dataset.github, key = "scriptorium-repo:" + slug;
    const show = function (facts) {
      const parts = [];
      if (facts.tag) parts.push(facts.tag);
      if (typeof facts.stars === "number") parts.push("★ " + facts.stars);
      const small = repo.querySelector(".repo-facts");
      if (small && parts.length) { small.textContent = parts.join(" · "); small.hidden = false; }
    };
    let cached = null;
    try { cached = JSON.parse(sessionStorage.getItem(key) || "null"); } catch (e) { /* storage off */ }
    if (cached && Date.now() - cached.at < 3600 * 1000) show(cached);
    else {
      const get = function (path) {
        return fetch("https://api.github.com/repos/" + slug + path).then(function (r) {
          return r.ok ? r.json() : null;
        }).catch(function () { return null; });
      };
      Promise.all([get(""), get("/releases?per_page=1")]).then(function (res) {
        const facts = { at: Date.now(), stars: res[0] ? res[0].stargazers_count : undefined,
                        tag: res[1] && res[1][0] ? res[1][0].tag_name : undefined };
        if (facts.stars === undefined && facts.tag === undefined) return;  // try again next page
        try { sessionStorage.setItem(key, JSON.stringify(facts)); } catch (e) { /* storage off */ }
        show(facts);
      });
    }
  }

  // "/" focuses search outside a text field; Ctrl-K and Cmd-K anywhere.
  document.addEventListener("keydown", function (e) {
    if (!input) return;
    const k = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k";
    if (!k && (e.key !== "/" || e.target.closest("input, textarea, [contenteditable]"))) return;
    e.preventDefault();
    input.focus();
    input.select();
  });
})();
