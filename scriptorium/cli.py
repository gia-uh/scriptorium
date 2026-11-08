"""scriptorium CLI: `render` (weave to PDF or HTML) and `tangle` (extract source)."""

import argparse
import sys
from pathlib import Path

from .tangle import test as tangle_test
from .tangle import write as tangle_write


def _warn(report) -> None:
    for w in [*report.oversized, *report.warnings, *report.underfull]:
        print(f"  ⚠ {w}", file=sys.stderr)


def _book_line(name, out, report) -> None:
    version = f", version {report.version}" if report.version else ""
    print(f"{name}: {out}/, {report.files} files, {report.bytes // 1024} KB{version}")
    for w in report.warnings:
        print(f"  ⚠ {w}", file=sys.stderr)


def _render_project(args) -> int:
    """Build every output of a scriptorium.yaml, or the ones --only names."""
    from .galley import render_pdf
    from .project import ProjectError
    from .project import load as load_project

    try:
        proj = load_project(args.input)
    except ProjectError as e:
        print(f"scriptorium: {e}", file=sys.stderr)
        return 2
    outputs = proj.outputs
    if args.only:
        names = [o.name for o in outputs]
        missing = [n for n in args.only if n not in names]
        if missing:
            print(f"scriptorium: no output named {', '.join(missing)}; "
                  f"this project has {', '.join(names)}", file=sys.stderr)
            return 2
        outputs = [o for o in outputs if o.name in args.only]
    if args.output and len(outputs) > 1:
        print(f"scriptorium: -o is ambiguous with {len(outputs)} outputs; "
              "pick one with --only", file=sys.stderr)
        return 2

    base = args.input.resolve().parent
    cwd = str(base)
    for o in outputs:
        if o.format in ("html", "docs"):
            if o.format == "html":
                from .book import render_book as render_site
            else:
                from .docs import render_docs as render_site

            out = args.output or (base / o.dir)
            extra = {"files": proj.files} if o.format == "docs" else {}
            report = render_site(proj.src, out, output=o, base_dir=base, theme_name=proj.theme,
                                 vars=proj.vars, project_meta=proj.meta,
                                 execute=not args.no_execute, code_root=proj.code_root, **extra)
            _book_line(o.name, out, report)
            continue
        out = args.output or (base / o.file)
        report = render_pdf(proj.src, str(out), base_url=cwd + "/",
                            theme_name=proj.theme, cwd=cwd,
                            execute=not args.no_execute, vars={**proj.vars, **o.vars},
                            code_root=proj.code_root, project_meta=proj.meta,
                            page=o.page)
        print(f"{o.name}: {out} — {report.n_pages} page(s)")
        _warn(report)
    return 0


def main(argv=None) -> int:
    from .media import MediaError

    try:
        return _main(argv)
    except MediaError as e:  # a missing audio file: the message is the whole story
        print(f"scriptorium: {e}", file=sys.stderr)
        return 2


def _main(argv) -> int:
    p = argparse.ArgumentParser(prog="scriptorium")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render a Markdown file to PDF or HTML")
    r.add_argument("input", type=Path)
    r.add_argument("-o", "--output", type=Path, default=None)
    r.add_argument("--no-execute", action="store_true", help="do not run code blocks")
    r.add_argument("--theme", default=None,
                   help="override the document's frontmatter `theme:`")
    r.add_argument("--html", action="store_true",
                   help="write the HTML document instead of a PDF (needs no WeasyPrint)")
    r.add_argument("--only", action="append", metavar="NAME", default=None,
                   help="build only this output of a project (repeatable)")
    r.add_argument("--format", choices=("pdf", "html", "docs"), default="pdf",
                   help="for a single file: a PDF (default), an HTML book or a docs site")

    t = sub.add_parser("tangle", help="extract export= code blocks to source files")
    t.add_argument("input", type=Path)
    t.add_argument("-d", "--dir", type=Path, default=Path("."))
    t.add_argument("--test", action="store_true", help="check idempotency, write nothing")

    args = p.parse_args(argv)
    src = args.input.read_text(encoding="utf-8")
    stem = args.input.stem

    if args.cmd == "render" and args.html:
        from .render import render_html

        cwd = str(args.input.resolve().parent)
        if args.input.suffix in (".yaml", ".yml"):  # a project
            from .project import load as load_project

            proj = load_project(args.input)
            out = args.output or (args.input.parent / "book.html")
            html, warnings = render_html(proj.src, theme_name=proj.theme, cwd=cwd,
                                         execute=not args.no_execute, vars=proj.vars,
                                         code_root=proj.code_root,
                                         project_meta=proj.meta)
        else:
            out = args.output or args.input.with_suffix(".html")
            html, warnings = render_html(src, theme_name=args.theme, cwd=cwd,
                                         execute=not args.no_execute)
        Path(out).write_text(html, encoding="utf-8")
        print(f"rendered {out}")
        for w in warnings:
            print(f"  ⚠ {w}", file=sys.stderr)
        return 0

    if args.cmd == "render":
        from .galley import render_pdf

        if args.input.suffix in (".yaml", ".yml"):  # a project
            return _render_project(args)
        if args.format == "html":
            from .book import render_book
            from .project import Output

            out = args.output or args.input.with_suffix("")
            report = render_book(src, out, output=Output(name="html", format="html"),
                                 base_dir=args.input.resolve().parent, theme_name=args.theme,
                                 execute=not args.no_execute)
            _book_line("html", out, report)
            return 0
        if args.format == "docs":
            from .docs import render_docs
            from .project import Output

            out = args.output or args.input.with_suffix("")
            report = render_docs(src, out, output=Output(name="docs", format="docs"),
                                 base_dir=args.input.resolve().parent, theme_name=args.theme,
                                 execute=not args.no_execute)
            _book_line("docs", out, report)
            return 0
        out = args.output or args.input.with_suffix(".pdf")
        cwd = str(args.input.resolve().parent)
        report = render_pdf(src, str(out), base_url=cwd + "/", theme_name=args.theme,
                            cwd=cwd, execute=not args.no_execute)
        print(f"rendered {out} — {report.n_pages} page(s)")
        for w in report.oversized:
            print(f"  ⚠ {w}", file=sys.stderr)
        for w in report.warnings:
            print(f"  ⚠ {w}", file=sys.stderr)
        for w in report.underfull:
            print(f"  ⚠ {w}", file=sys.stderr)
        return 0

    if args.cmd == "tangle":
        if args.test:
            drift = tangle_test(src, args.dir, doc_stem=stem)
            if drift:
                print("tangle drift: " + ", ".join(drift), file=sys.stderr)
                return 1
            print("tangle: up to date")
            return 0
        written = tangle_write(src, args.dir, doc_stem=stem)
        print(f"tangled {len(written)} file(s):")
        for w in written:
            print(f"  {w}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
