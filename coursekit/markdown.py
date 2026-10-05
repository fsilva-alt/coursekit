"""Markdown → HTML for chapters (markdown-it-py + plugins + coursekit elements).

Raw HTML is allowed everywhere. On top of CommonMark you get GFM tables, strikethrough,
autolinks, footnotes, definition lists, task lists, `{#id .class key=value}` attributes,
and the coursekit elements below (`:::` containers; nest by using more colons outside):

    :::note|info|tip|success|important|warning|caution|danger [title]   callouts
    > [!NOTE] / [!TIP] / …                                                 GitHub-style callouts
    :::exercise [title]                                                     exercise box
    :::details summary / :::hint [summary] / :::solution [summary]        collapsibles
    ::::tabs  +  :::tab Label                                               tabs (synced by label)
    ::::columns  +  :::column                                               side-by-side layout
    :::card [title]                                                         card box
    :::steps  (wraps an ordered list)                                       numbered procedure
    :::quiz Question  (task list, [x] = correct, text after = explanation)  knowledge check
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, Dict
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.common.utils import unescapeAll
from mdit_py_plugins.attrs import attrs_block_plugin, attrs_plugin
from mdit_py_plugins.container import container_plugin
from mdit_py_plugins.deflist import deflist_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

from .config import Course, slugify, unique_slug
from .highlight import parse_info, render_code
from .icons import CALLOUT_ICONS, icon

CALLOUTS = {
    # kind: visual style
    "note": "note", "info": "note",
    "tip": "tip", "success": "tip",
    "important": "important",
    "warning": "warning",
    "caution": "danger", "danger": "danger",
    "exercise": "exercise",
}
COLLAPSIBLES = ("details", "hint", "solution")
_ALERT = re.compile(r"^\[!([A-Za-z]+)\][ \t]*([^\n]*)\n?")


def _rest(info: str, name: str) -> str:
    info = info.strip()
    return info[len(name):].strip() if info.startswith(name) else info


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


_FIRST_TAG = re.compile(r"^(\s*<[a-zA-Z][\w-]*)([^>]*)>")


def _apply_attrs(markup: str, tok) -> str:
    """Merge a token's {.class #id key=value} attributes into the first tag of `markup`."""
    if not tok.attrs:
        return markup
    m = _FIRST_TAG.match(markup)
    if not m:
        return markup
    attrs, extra = m.group(2), []
    for key, value in tok.attrs.items():
        existing = re.search(rf'\s{re.escape(key)}="([^"]*)"', attrs)
        if key == "class" and existing:
            attrs = f'{attrs[:existing.start()]} class="{existing.group(1)} {_esc(value)}"' \
                    f'{attrs[existing.end():]}'
        elif existing:
            attrs = f'{attrs[:existing.start()]} {key}="{_esc(value)}"{attrs[existing.end():]}'
        else:
            extra.append(f' {key}="{_esc(value)}"')
    return f"{m.group(1)}{attrs}{''.join(extra)}>{markup[m.end():]}"


def inline_env(env: Dict[str, Any]) -> Dict[str, Any]:
    """Env for rendering a snippet (a title) without re-emitting the chapter's footnotes."""
    return {k: v for k, v in env.items() if k != "footnotes"}


def _next_id(env: Dict[str, Any], prefix: str) -> str:
    counters = env["counters"]
    counters[prefix] = counters.get(prefix, 0) + 1
    return f"{prefix}-{counters[prefix]}"


def create_markdown(course: Course) -> MarkdownIt:
    cfg = course.config
    typographer = bool(cfg["typographer"])
    md = MarkdownIt("commonmark", {"html": True, "linkify": True, "typographer": typographer})
    md.enable(["table", "strikethrough", "linkify"])
    # Only autolink real URLs (https://…): file names such as setup.py or notes.md are not links.
    md.linkify.set({"fuzzy_link": False})
    if typographer:
        md.enable(["replacements", "smartquotes"])
    md.use(footnote_plugin).use(deflist_plugin).use(tasklists_plugin, enabled=True)
    md.use(attrs_plugin).use(attrs_block_plugin)

    def inline(text: str, env) -> str:
        return md.renderInline(text, inline_env(env)) if text else ""

    def container(name: str, render) -> None:
        """Register a ::: container; `{.class #id}` on the line above lands on its outer tag."""
        def wrapped(self, tokens, idx, options, env):
            out = render(self, tokens, idx, options, env)
            return _apply_attrs(out, tokens[idx]) if tokens[idx].nesting == 1 else out
        container_plugin(md, name, render=wrapped)

    # ------------------------------------------------------------------ callouts
    def callout_open(kind: str, title: str, env) -> str:
        style = CALLOUTS[kind]
        label = inline(title, env) if title else _esc(env["labels"].get(kind, kind.title()))
        return (f'<div class="callout callout-{style}" data-kind="{kind}" role="note">'
                f'<div class="callout-title">{icon(CALLOUT_ICONS[kind])}<span>{label}</span></div>'
                f'<div class="callout-body">\n')

    def make_callout(kind: str):
        def render(self, tokens, idx, options, env):
            tok = tokens[idx]
            if tok.nesting == 1:
                return callout_open(kind, _rest(tok.info, kind), env)
            return "</div></div>\n"
        return render

    for kind in CALLOUTS:
        container(kind, make_callout(kind))

    # ------------------------------------------------------------------ collapsibles
    def make_collapsible(kind: str):
        def render(self, tokens, idx, options, env):
            tok = tokens[idx]
            if tok.nesting == -1:
                return "</div></details>\n"
            title = _rest(tok.info, kind)
            summary = inline(title, env) if title else _esc(env["labels"][kind])
            lead = icon("chevron-right", "details-chevron")
            if kind == "hint":
                lead += icon("bulb", "details-kind")
            elif kind == "solution":
                lead += icon("check-circle", "details-kind")
            return (f'<details class="details details-{kind}"><summary>{lead}'
                    f'<span>{summary}</span></summary><div class="details-body">\n')
        return render

    for kind in COLLAPSIBLES:
        container(kind, make_collapsible(kind))

    # ------------------------------------------------------------------ tabs
    def render_tabs(self, tokens, idx, options, env):
        if tokens[idx].nesting == -1:
            return "</div></div>\n"
        base = _next_id(env, "tabs")
        buttons, depth, k = [], 0, 0
        for j in range(idx + 1, len(tokens)):
            t = tokens[j]
            if t.type == "container_tabs_open":
                depth += 1
            elif t.type == "container_tabs_close":
                if depth == 0:
                    break
                depth -= 1
            elif t.type == "container_tab_open" and depth == 0:
                label = _rest(t.info, "tab") or f"Tab {k + 1}"
                t.meta = {"base": base, "k": k, "label": label}
                selected = "true" if k == 0 else "false"
                buttons.append(
                    f'<button type="button" role="tab" id="{base}-tab-{k}" '
                    f'aria-controls="{base}-panel-{k}" aria-selected="{selected}" '
                    f'tabindex="{0 if k == 0 else -1}" data-label="{_esc(label)}">'
                    f'{inline(label, env)}</button>')
                k += 1
        return (f'<div class="tabs" data-tabs><div class="tab-list" role="tablist">'
                f'{"".join(buttons)}</div><div class="tab-panels">\n')

    def render_tab(self, tokens, idx, options, env):
        tok = tokens[idx]
        if tok.nesting == -1:
            return "</div>\n"
        meta = tok.meta or {}
        if not meta:   # a :::tab outside of ::::tabs — show it as a labelled box
            return f'<div class="tab-panel is-active" data-label="{_esc(_rest(tok.info, "tab"))}">\n'
        base, k = meta["base"], meta["k"]
        active = " is-active" if k == 0 else ""
        return (f'<div class="tab-panel{active}" role="tabpanel" id="{base}-panel-{k}" '
                f'aria-labelledby="{base}-tab-{k}" data-label="{_esc(meta["label"])}" tabindex="0">\n')

    container("tabs", render_tabs)
    container("tab", render_tab)

    # ------------------------------------------------------------------ layout boxes
    def simple(open_html: str, close_html: str = "</div>\n"):
        def render(self, tokens, idx, options, env):
            return open_html if tokens[idx].nesting == 1 else close_html
        return render

    container("columns", simple('<div class="columns">\n'))
    container("column", simple('<div class="column">\n'))
    container("steps", simple('<div class="steps">\n'))

    def render_card(self, tokens, idx, options, env):
        tok = tokens[idx]
        if tok.nesting == -1:
            return "</div>\n"
        title = _rest(tok.info, "card")
        head = f'<div class="card-title">{inline(title, env)}</div>' if title else ""
        return f'<div class="card">{head}\n'

    container("card", render_card)

    # ------------------------------------------------------------------ quiz
    def render_quiz(self, tokens, idx, options, env):
        tok = tokens[idx]
        if tok.nesting == -1:
            return "</div></div>\n"
        question = _rest(tok.info, "quiz")
        return (f'<div class="quiz" data-quiz><div class="quiz-head">'
                f'<span class="quiz-badge">{icon("question")}{_esc(env["labels"]["quiz"])}</span>'
                f'<div class="quiz-question">{inline(question, env)}</div></div>'
                f'<div class="quiz-body">\n')

    container("quiz", render_quiz)

    # ------------------------------------------------------------------ core rules
    def github_alerts(state):
        tokens = state.tokens
        for i, tok in enumerate(tokens):
            if tok.type != "blockquote_open" or i + 3 >= len(tokens):
                continue
            if tokens[i + 1].type != "paragraph_open" or tokens[i + 2].type != "inline":
                continue
            m = _ALERT.match(tokens[i + 2].content)
            if not m or m.group(1).lower() not in CALLOUTS:
                continue
            para = tokens[i + 2]
            para.content = para.content[m.end():]
            if not para.content.strip():
                tokens[i + 1].hidden = tokens[i + 3].hidden = True
            for j in range(i + 1, len(tokens)):
                if tokens[j].type == "blockquote_close" and tokens[j].level == tok.level:
                    tokens[j].meta = {"callout": True}
                    break
            tok.meta = {"callout": m.group(1).lower(), "title": m.group(2).strip()}

    def heading_ids(state):
        env = state.env
        tokens = state.tokens
        for i, tok in enumerate(tokens):
            if tok.type != "heading_open":
                continue
            inline_tok = tokens[i + 1]
            text = "".join(c.content for c in (inline_tok.children or [])
                           if c.type in ("text", "code_inline"))
            hid = tok.attrGet("id")
            if hid:
                env["slugs"].add(str(hid))
            else:
                hid = unique_slug(slugify(text), env["slugs"])
                tok.attrSet("id", hid)
            tokens[i + 2].meta = {"anchor": str(hid)}

    def figures(state):
        tokens = state.tokens
        for i in range(len(tokens) - 2):
            p_open, inl, p_close = tokens[i], tokens[i + 1], tokens[i + 2]
            if p_open.type != "paragraph_open" or inl.type != "inline" or p_open.hidden:
                continue
            kids = [c for c in (inl.children or [])
                    if c.type != "softbreak" and not (c.type == "text" and not c.content.strip())]
            if len(kids) == 1 and kids[0].type == "image" and kids[0].attrGet("title"):
                caption = str(kids[0].attrGet("title"))
                kids[0].attrs.pop("title", None)
                p_open.meta = {"figure": True}
                p_close.meta = {"figure": caption}

    md.core.ruler.after("block", "coursekit_alerts", github_alerts)
    md.core.ruler.push("coursekit_headings", heading_ids)
    md.core.ruler.push("coursekit_figures", figures)

    # ------------------------------------------------------------------ renderers
    rules = md.renderer.rules
    default_link_open = rules.get("link_open")

    def blockquote_open(self, tokens, idx, options, env):
        meta = tokens[idx].meta or {}
        if meta.get("callout"):
            return _apply_attrs(callout_open(meta["callout"], meta.get("title", ""), env), tokens[idx])
        return self.renderToken(tokens, idx, options, env)

    def blockquote_close(self, tokens, idx, options, env):
        if (tokens[idx].meta or {}).get("callout"):
            return "</div></div>\n"
        return self.renderToken(tokens, idx, options, env)

    def heading_close(self, tokens, idx, options, env):
        anchor = (tokens[idx].meta or {}).get("anchor")
        if anchor and tokens[idx].tag in ("h2", "h3", "h4"):
            return (f'<a class="heading-anchor" href="#{_esc(anchor)}" '
                    f'aria-label="{_esc(env["labels"]["link_to_section"])}">#</a>'
                    f'</{tokens[idx].tag}>\n')
        return self.renderToken(tokens, idx, options, env)

    def paragraph_open(self, tokens, idx, options, env):
        if (tokens[idx].meta or {}).get("figure"):
            return '<figure class="figure">'
        return self.renderToken(tokens, idx, options, env)

    def paragraph_close(self, tokens, idx, options, env):
        caption = (tokens[idx].meta or {}).get("figure")
        if caption:
            return f"<figcaption>{inline(caption, env)}</figcaption></figure>\n"
        return self.renderToken(tokens, idx, options, env)

    def table_open(self, tokens, idx, options, env):
        return '<div class="table-wrap">' + self.renderToken(tokens, idx, options, env)

    def table_close(self, tokens, idx, options, env):
        return self.renderToken(tokens, idx, options, env) + "</div>\n"

    def link_open(self, tokens, idx, options, env):
        tok = tokens[idx]
        href = str(tok.attrGet("href") or "")
        rewritten = _rewrite_chapter_link(href, env)
        if rewritten is not None:
            tok.attrSet("href", rewritten)
        elif cfg["external_links_new_tab"] and re.match(r"^(https?:)?//", href) \
                and not tok.attrGet("target"):
            tok.attrSet("target", "_blank")
            tok.attrSet("rel", "noopener noreferrer")
        if default_link_open:
            return default_link_open(self, tokens, idx, options, env)
        return self.renderToken(tokens, idx, options, env)

    def fence(self, tokens, idx, options, env):
        tok = tokens[idx]
        lang, opts = parse_info(unescapeAll(tok.info or ""))
        out = render_code(tok.content, lang, opts, highlight=bool(cfg["highlight"]),
                          line_numbers=bool(cfg["line_numbers"]), labels=env["labels"],
                          warn=lambda msg: env["warn"](f"{env['chapter'].rel}: {msg}"))
        return _apply_attrs(out, tok)

    def code_block(self, tokens, idx, options, env):
        return render_code(tokens[idx].content, "", {}, highlight=False,
                           line_numbers=bool(cfg["line_numbers"]), labels=env["labels"])

    md.add_render_rule("blockquote_open", blockquote_open)
    md.add_render_rule("blockquote_close", blockquote_close)
    md.add_render_rule("heading_close", heading_close)
    md.add_render_rule("paragraph_open", paragraph_open)
    md.add_render_rule("paragraph_close", paragraph_close)
    md.add_render_rule("table_open", table_open)
    md.add_render_rule("table_close", table_close)
    md.add_render_rule("link_open", link_open)
    md.add_render_rule("fence", fence)
    md.add_render_rule("code_block", code_block)
    return md


def _rewrite_chapter_link(href: str, env) -> str | None:
    """`other-chapter.md#section` → `#section` (or `#chapter-id`) for in-page navigation."""
    parts = urlsplit(href)
    if parts.scheme or parts.netloc or not parts.path.lower().endswith(".md"):
        return None
    chapter = env["chapter"]
    target = (chapter.path.parent / unquote(parts.path)).resolve()
    if not target.exists():
        target = (env["course"].root / unquote(parts.path).lstrip("/")).resolve()
    other = env["chapters_by_path"].get(target)
    if other is None:
        env["warn"](f"{chapter.rel}: link to unknown chapter '{href}'")
        return None
    return "#" + (parts.fragment or other.id)
