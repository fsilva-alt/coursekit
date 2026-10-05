"""Code blocks: build-time syntax highlighting with Pygments, rendered line by line.

Fence info string:   ```python title="hello.py" hl_lines="2 4-6" linenums="10"
  - first word            language (any Pygments alias; `text` or nothing = plain)
  - title="…"             caption shown in the block header (e.g. a file name)
  - hl_lines="…" / {2,4-6} lines to emphasise (1-based, relative to the block)
  - linenums[="N"]        show line numbers (optionally starting at N); `nolinenums` hides them
"""

from __future__ import annotations

import html
import re
from typing import Dict, List, Optional, Set, Tuple

from pygments.lexers import get_lexer_by_name
from pygments.token import STANDARD_TYPES
from pygments.util import ClassNotFound

from .icons import icon

PLAIN = {"", "text", "txt", "plain", "plaintext", "none", "nohighlight", "output"}

# Friendly names for the block header; anything else falls back to Pygments' lexer name.
LANG_NAMES = {
    "python": "Python", "py": "Python", "python3": "Python", "pycon": "Python REPL",
    "console": "Terminal", "shell-session": "Terminal", "sh-session": "Terminal",
    "bash": "Bash", "sh": "Shell", "shell": "Shell", "zsh": "Zsh",
    "powershell": "PowerShell", "pwsh": "PowerShell", "ps1": "PowerShell",
    "ps1con": "PowerShell", "pwsh-session": "PowerShell", "doscon": "Command Prompt",
    "bat": "Batch", "batch": "Batch", "js": "JavaScript", "javascript": "JavaScript",
    "ts": "TypeScript", "typescript": "TypeScript", "json": "JSON", "yaml": "YAML",
    "yml": "YAML", "toml": "TOML", "ini": "INI", "html": "HTML", "css": "CSS", "xml": "XML",
    "md": "Markdown", "markdown": "Markdown", "sql": "SQL", "c": "C", "cpp": "C++",
    "c++": "C++", "java": "Java", "r": "R", "julia": "Julia", "jl": "Julia", "go": "Go",
    "rust": "Rust", "rs": "Rust", "fortran": "Fortran", "f90": "Fortran", "diff": "Diff",
    "dockerfile": "Dockerfile", "docker": "Dockerfile", "make": "Makefile",
    "makefile": "Makefile", "matlab": "MATLAB", "ruby": "Ruby", "php": "PHP",
}

_INFO_ITEM = re.compile(r'''([\w-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|(\S+)))?|\{([^}]*)\}''')

_lexers: Dict[str, object] = {}


def parse_info(info: str) -> Tuple[str, Dict[str, str]]:
    info = info.strip()
    lang = ""
    if info and "=" not in info.split(None, 1)[0] and not info.startswith("{"):
        lang, _, info = info.partition(" ")
        lang = lang.strip().lower()
    opts: Dict[str, str] = {}
    for m in _INFO_ITEM.finditer(info):
        if m.group(5) is not None:                     # {2,4-6}
            opts["hl_lines"] = m.group(5)
            continue
        key = m.group(1).lower()
        value = next((g for g in m.group(2, 3, 4) if g is not None), "")
        opts[key] = value
    return lang, opts


def parse_ranges(spec: str) -> Set[int]:
    lines: Set[int] = set()
    for part in re.split(r"[\s,]+", spec or ""):
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            if a.isdigit() and b.isdigit():
                lines.update(range(int(a), int(b) + 1))
        elif part.isdigit():
            lines.add(int(part))
    return lines


def _css_class(ttype) -> str:
    while ttype not in STANDARD_TYPES:
        ttype = ttype.parent
    return STANDARD_TYPES[ttype]


def _lexer(lang: str):
    if lang not in _lexers:
        try:
            # ensurenl must stay on: session lexers (console, pycon) drop a final line without "\n"
            _lexers[lang] = get_lexer_by_name(lang, stripnl=False)
        except ClassNotFound:
            _lexers[lang] = None
    return _lexers[lang]


def highlight_lines(code: str, lang: str, enabled: bool, warn=None) -> List[str]:
    lexer = _lexer(lang) if enabled and lang not in PLAIN else None
    if enabled and lang and lang not in PLAIN and lexer is None and warn:
        warn(f"unknown code language '{lang}' (rendered as plain text)")
    source_lines = code.split("\n")
    if lexer is None:
        return [html.escape(line, quote=False) for line in source_lines]
    lines: List[List[str]] = [[]]
    for ttype, value in lexer.get_tokens(code):
        cls = _css_class(ttype)
        for k, piece in enumerate(value.split("\n")):
            if k:
                lines.append([])
            if piece:
                text = html.escape(piece, quote=False)
                lines[-1].append(f'<span class="{cls}">{text}</span>' if cls else text)
    rendered = ["".join(parts) for parts in lines][:len(source_lines)]
    return rendered + [""] * (len(source_lines) - len(rendered))


def language_name(lang: str) -> str:
    if lang in PLAIN:
        return ""
    if lang in LANG_NAMES:
        return LANG_NAMES[lang]
    lexer = _lexer(lang)
    return getattr(lexer, "name", lang) if lexer else lang


def render_code(code: str, lang: str, opts: Dict[str, str], *, highlight: bool = True,
                line_numbers: bool = False, labels: Optional[Dict[str, str]] = None,
                warn=None) -> str:
    labels = labels or {}
    if code.endswith("\n"):
        code = code[:-1]
    lines = highlight_lines(code, lang, highlight, warn)
    marked = parse_ranges(opts.get("hl_lines", "") or opts.get("highlight", ""))

    start: Optional[int] = None
    if "linenums" in opts:
        start = int(opts["linenums"]) if opts["linenums"].isdigit() else 1
    elif line_numbers and "nolinenums" not in opts and len(lines) > 1:
        start = 1

    title = opts.get("title", "")
    name = language_name(lang)
    head = []
    if title:
        head.append(f'<span class="code-title">{icon("file")}'
                    f'<span>{html.escape(title)}</span></span>')
        if name:
            head.append(f'<span class="code-lang code-lang-muted">{html.escape(name)}</span>')
    elif name:
        head.append(f'<span class="code-lang">{html.escape(name)}</span>')
    head.append(
        f'<button class="code-copy" type="button" aria-label="{html.escape(labels.get("copy_code", "Copy code"))}">'
        f'{icon("copy")}{icon("check")}<span class="code-copy-text">{html.escape(labels.get("copy", "Copy"))}</span></button>'
    )

    body = "\n".join(
        f'<span class="line{" hl" if n in marked else ""}">{line}</span>'
        for n, line in enumerate(lines, 1)
    )
    classes = "code" + (" has-linenums" if start is not None else "")
    style = f' style="--ln-start:{start - 1}"' if start is not None else ""
    lang_attr = html.escape(lang or "text")
    return (
        f'<div class="{classes}" data-lang="{lang_attr}"{style}>'
        f'<div class="code-head">{"".join(head)}</div>'
        f'<pre><code class="language-{lang_attr}">{body}</code></pre></div>\n'
    )
