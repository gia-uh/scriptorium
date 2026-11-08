"""Parse a fenced code block's info string into a Fence directive.

Recognized forms (attributes combine freely):

    ```python                     shown source, not run
    ```python {run}               run in a subshell, splice stdout (native: asis)
    ```{python}                   Quarto-compat: run, output as monospace code
    ```python {export=src/x.py}   tangle body into a file
    ```python {name=frag}         named noweb fragment (definition)
    ```python {run echo=false}    run but hide the source
    ```python {run output=code}   force monospace output (default asis for native)
    ```python {run caption=".." id=fig-x}  caption and id for the one bundle it displays

Default output mode differs by syntax: Quarto `{lang}` blocks default to `code`
(monospace, matching Quarto), native `{run}` blocks default to `asis` (stdout
spliced as raw markdown and re-parsed — the house model).
"""

import re
from dataclasses import dataclass

_KV = re.compile(r"""(\w[\w-]*)=("[^"]*"|'[^']*'|\S+)""")

# language -> tangled-file extension (for headless {export})
EXT = {"python": "py", "py": "py", "bash": "sh", "sh": "sh", "node": "js", "js": "js"}


@dataclass
class Fence:
    lang: str = ""
    run: bool = False
    export: str | None = None  # explicit path
    export_headless: bool = False  # bare {export}
    name: str | None = None  # noweb fragment name
    echo: bool = True  # show the source?
    output_mode: str = "asis"  # "asis" | "code"
    cont: bool = False  # `continue`: run on top of the previous block's chain
    caption: str | None = None  # caption for the one thing the block displays
    title: str | None = None  # a label over the code, e.g. a file name
    id: str | None = None  # its id, e.g. fig-x

    @property
    def tangles(self) -> bool:
        return self.export is not None or self.export_headless


def _attrs(text: str):
    kv = {m.group(1): m.group(2).strip("\"'") for m in _KV.finditer(text)}
    consumed = _KV.sub(" ", text)
    flags = {t for t in consumed.split() if re.fullmatch(r"[\w-]+", t)}
    return flags, kv


def parse_fence(info: str) -> Fence:
    info = info.strip()
    f = Fence()
    if info.startswith("{"):  # Quarto-style ```{python ...}
        inner = info[1 : info.rfind("}")] if "}" in info else info[1:]
        parts = inner.split(None, 1)
        f.lang = parts[0] if parts else ""
        attr_text = parts[1] if len(parts) > 1 else ""
        f.run = True
        f.output_mode = "code"
    else:  # ```python {..}
        b = info.find("{")
        head = (info[:b] if b >= 0 else info).split()
        f.lang = head[0] if head else ""
        attr_text = info[b + 1 : info.rfind("}")] if b >= 0 else ""

    flags, kv = _attrs(attr_text)
    if "run" in flags:
        f.run = True
    if "continue" in flags:
        f.cont = True
    f.export = kv.get("export")
    if "export" in flags and f.export is None:
        f.export_headless = True
    f.name = kv.get("name")
    if kv.get("echo") == "false" or "echo=false" in attr_text:
        f.echo = False
    f.output_mode = kv.get("output", f.output_mode)
    f.caption = kv.get("caption")
    f.title = kv.get("title")
    f.id = kv.get("id")
    return f
