"""Assemble a course into a single self-contained index.html."""

from __future__ import annotations

import html
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List

from . import __version__
from .assets import AssetEmbedder, data_uri
from .config import Chapter, Course, load_course
from .icons import icon
from .labels import RUNTIME_KEYS, format_minutes
from .markdown import create_markdown, inline_env

THEME_DIR = Path(__file__).parent / "theme"
_PLACEHOLDER = re.compile(r"\{\{\s*([\w.-]+)\s*\}\}")

DEV_RELOAD_JS = """
(function () {
  var KEY = 'coursekit:dev-scroll';
  try {
    var y = sessionStorage.getItem(KEY);
    if (y !== null) { sessionStorage.removeItem(KEY); requestAnimationFrame(function () { scrollTo(0, +y); }); }
  } catch (e) {}
  var source = new EventSource('/__coursekit/events');
  source.onmessage = function () {
    try { sessionStorage.setItem(KEY, String(scrollY)); } catch (e) {}
    location.reload();
  };
})();
"""


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def plain(text: str) -> str:
    """Markdown-ish title → plain text (for <title>, tooltips and JSON)."""
    return re.sub(r"[`*_]|<[^>]+>", "", text).strip()


@dataclass
class BuildResult:
    course: Course
    output: Path
    warnings: List[str] = field(default_factory=list)
    seconds: float = 0.0


def _read(path: Path, what: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        raise FileNotFoundError(f"{what} not found: {path}") from None


def fill(template: str, context: Dict[str, str], labels: Dict[str, str],
         warn: Callable[[str], None]) -> str:
    """Replace {{ name }}, {{ label.key }} and {{ icon.name }} in a layout (single pass)."""
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key.startswith("label."):
            return esc(labels.get(key[6:], ""))
        if key.startswith("icon."):
            try:
                return icon(key[5:])
            except KeyError:
                warn(f"layout: unknown icon '{key[5:]}'")
                return ""
        if key in context:
            return context[key]
        warn(f"layout: unknown placeholder '{key}'")
        return ""
    return _PLACEHOLDER.sub(sub, template)


def _style_tag(css: str) -> str:
    return "<style>\n" + re.sub(r"</(style)", r"<\\/\1", css, flags=re.I) + "\n</style>"


def _script_tag(js: str, module: bool = False) -> str:
    kind = ' type="module"' if module else ""
    return f"<script{kind}>\n" + re.sub(r"</(script)", r"<\\/\1", js, flags=re.I) + "\n</script>"


def _letter_icon(title: str, accent: str) -> str:
    letter = esc((plain(title)[:1] or "C").upper())
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
           f'<rect width="64" height="64" rx="6" fill="{esc(accent)}"/>'
           f'<text x="32" y="43" font-family="system-ui,-apple-system,Segoe UI,sans-serif" '
           f'font-size="32" font-weight="700" text-anchor="middle" fill="#fff">{letter}</text></svg>')
    return data_uri(svg.encode("utf-8"), "image/svg+xml")


# ---------------------------------------------------------------------------- fragments

def render_about(course: Course, md) -> str:
    L, cfg = course.labels, course.config
    rows = []
    if course.updated:
        d = course.updated
        rows.append((L["last_updated"],
                     f'<time datetime="{d.isoformat()}" data-date>{d:%B} {d.day}, {d.year}</time>'))
    if course.authors:
        rows.append((L["written_by"], esc(", ".join(course.authors))))
    rows.append((L["duration"], esc(format_minutes(course.total_minutes, L))))
    rows.append((L["chapters"], str(len(course.chapters))))
    meta = "".join(f"<div><dt>{esc(k)}</dt><dd>{v}</dd></div>" for k, v in rows)
    text = cfg.get("description") or cfg.get("subtitle") or ""
    intro = f'<div class="about-text">{md.render(str(text), {"labels": L, "counters": {}, "slugs": set()})}</div>' \
        if text else ""
    return (f'<details class="about"><summary>{icon("book")}<span>{esc(L["about"])}</span>'
            f'{icon("chevron-down", "about-chevron")}</summary><div class="about-body">{intro}'
            f'<dl class="about-meta">{meta}</dl><button class="about-reset" type="button" '
            f'data-reset-progress>{icon("reset")}{esc(L["reset_progress"])}</button></div></details>')


def render_toc(course: Course) -> str:
    L = course.labels
    out = []
    for p_index, part in enumerate(course.parts):
        items = []
        for ch in part.chapters:
            items.append(
                f'<li><a class="toc-link" href="#{esc(ch.id)}" data-index="{ch.index}" '
                f'title="{esc(plain(ch.title))}"><span class="toc-dot">'
                f'<span class="toc-num">{esc(ch.number)}</span>{icon("check")}</span>'
                f'<span class="toc-text">{esc(plain(ch.title))}</span>'
                f'<span class="toc-time">{esc(L["minutes"].format(n=ch.duration))}</span></a></li>')
        list_id = f"toc-part-{p_index}"
        head = ""
        if part.title:
            tip = f' title="{esc(part.description)}"' if part.description else ""
            head = (f'<button class="toc-part-head" type="button" aria-expanded="true" '
                    f'aria-controls="{list_id}"{tip}><span class="toc-part-label">'
                    f'<span class="toc-part-kicker">{esc(L["part"].format(n=part.number))}</span>'
                    f'<span class="toc-part-title">{esc(part.title)}</span></span>'
                    f'<span class="toc-part-count" data-part-count>0/{len(part.chapters)}</span>'
                    f'{icon("chevron-down", "toc-part-chevron")}</button>')
        klass = "toc-part" + ("" if part.title else " is-untitled")
        out.append(f'<section class="{klass}" data-part="{p_index}">{head}'
                   f'<ol class="toc-list" id="{list_id}">{"".join(items)}</ol></section>')
    return "".join(out)


def render_chapter(course: Course, ch: Chapter, md, env: Dict[str, Any]) -> str:
    L, cfg = course.labels, course.config
    part = course.parts[ch.part]
    kicker = []
    if part.title:
        tip = f' title="{esc(part.description)}"' if part.description else ""
        kicker.append(f'<span class="chapter-part"{tip}>{esc(L["part"].format(n=part.number))}'
                      f'<span class="sep" aria-hidden="true">·</span>{esc(part.title)}</span>')
    kicker.append(f'<span class="chapter-time">{icon("clock")}'
                  f'{esc(L["minutes"].format(n=ch.duration))}</span>')
    number = f'<span class="chapter-num">{esc(ch.number)}.</span> ' if ch.number else ""
    title = md.renderInline(ch.title, inline_env(env))
    foot = ""
    if cfg.get("edit_url"):
        url = str(cfg["edit_url"]).replace("{path}", ch.rel).replace("{id}", ch.id)
        foot = (f'<footer class="chapter-foot"><a class="edit-link" href="{esc(url)}" '
                f'target="_blank" rel="noopener">{icon("edit")}{esc(L["edit"])}</a></footer>')
    return (f'<section class="chapter" id="{esc(ch.id)}" data-index="{ch.index}" '
            f'aria-labelledby="{esc(ch.id)}-title">'
            f'<header class="chapter-head"><p class="chapter-kicker">{"".join(kicker)}</p>'
            f'<h1 class="chapter-title" id="{esc(ch.id)}-title" tabindex="-1">{number}{title}</h1>'
            f'</header><div class="prose">\n{ch.html}</div>{foot}</section>\n')


# ---------------------------------------------------------------------------- course

def build_course(course_dir: Path, output: Path, *, cache_dir: Path, dev: bool = False,
                 log: Callable[[str], None] = print) -> BuildResult:
    """Build one course into the single HTML file `output`."""
    started = time.time()
    warnings: List[str] = []

    def warn(msg: str) -> None:
        warnings.append(msg)
        log(f"  ! {msg}")

    course = load_course(course_dir, warn=warn)
    cfg, L = course.config, course.labels
    embedder = AssetEmbedder(cache_dir / "images", embed_local=bool(cfg["embed_images"]),
                             embed_remote=bool(cfg["embed_images"] and cfg["embed_external_images"]),
                             warn=warn)
    md = create_markdown(course)

    slugs = {c.id for c in course.chapters} | {f"{c.id}-title" for c in course.chapters} \
        | {"main", "sidebar", "course-data"}
    base_env: Dict[str, Any] = {
        "course": course, "labels": L, "slugs": slugs, "counters": {}, "warn": warn,
        "chapters_by_path": {c.path: c for c in course.chapters},
    }

    sections = []
    for ch in course.chapters:
        env = dict(base_env, chapter=ch, docId=ch.id)
        rendered = md.render(ch.body, env)
        ch.html = embedder.embed_html(rendered, [ch.path.parent, course.root], course.root,
                                      where=f"{ch.rel}: ")
        sections.append(render_chapter(course, ch, md, env))

    # --- styles
    accent = str(cfg["accent"])
    accent_dark = str(cfg["accent_dark"] or f"color-mix(in oklab, {accent} 58%, white)")
    css = []
    if not cfg["replace_base_styles"]:
        css.append(_read(THEME_DIR / "base.css", "base stylesheet"))
    css.append(f':root{{--accent:{accent}}}\n:root[data-theme="dark"]{{--accent:{accent_dark}}}')
    for entry in cfg["styles"] or []:
        path = course.path(str(entry))
        css.append(f"/* --- {entry} --- */\n" + embedder.embed_css(_read(path, "stylesheet"), path))

    # --- scripts
    scripts = [_script_tag(_read(THEME_DIR / "app.js", "runtime script"))]
    for entry in cfg["scripts"] or []:
        path = course.path(str(entry))
        scripts.append(_script_tag(_read(path, "script"), module=path.suffix == ".mjs"))
    if dev:
        scripts.append(_script_tag(DEV_RELOAD_JS))

    # --- branding
    title = plain(str(cfg["title"]))
    logo_uri = None
    if cfg.get("logo"):
        logo_uri = embedder.file_data_uri(course.path(str(cfg["logo"])), "logo: ")
    favicon_uri = None
    if cfg.get("favicon"):
        favicon_uri = embedder.file_data_uri(course.path(str(cfg["favicon"])), "favicon: ")
    favicon_uri = favicon_uri or logo_uri or _letter_icon(title, accent)
    brand_mark = (f'<img class="brand-logo" src="{logo_uri}" alt="">' if logo_uri else
                  f'<span class="brand-mark" aria-hidden="true">{esc(title[:1].upper())}</span>')
    home = ""
    if cfg.get("home_url"):
        home = (f'<a class="icon-btn home-link" href="{esc(cfg["home_url"])}" '
                f'aria-label="{esc(L["home"])}" title="{esc(L["home"])}">{icon("arrow-left")}</a>')
    head_extra = _read(course.path(str(cfg["head"])), "head include") if cfg.get("head") else ""

    data = {
        "id": course.slug, "title": title, "lang": str(cfg["language"]),
        "transition": cfg["transition"], "finishUrl": cfg.get("finish_url") or None,
        "labels": {k: L[k] for k in RUNTIME_KEYS},
        "chapters": [{"id": c.id, "title": plain(c.title), "duration": c.duration, "part": c.part}
                     for c in course.chapters],
    }
    total = format_minutes(course.total_minutes, L)
    context = {
        "lang": esc(cfg["language"]),
        "title": esc(title),
        "description": esc(plain(str(cfg.get("subtitle") or cfg.get("description") or title))),
        "version": __version__,
        "favicon": f'<link rel="icon" href="{favicon_uri}">',
        "styles": _style_tag("\n\n".join(css)),
        "head": head_extra,
        "home_link": home,
        "brand_mark": brand_mark,
        "course_title": esc(title),
        "first_chapter": esc(course.chapters[0].id),
        "time_total": esc(L["remaining"].format(t=total)),
        "chapter_count": str(len(course.chapters)),
        "about": render_about(course, md),
        "toc": render_toc(course),
        "chapters": "".join(sections),
        "course_data": json.dumps(data, ensure_ascii=False).replace("<", "\\u003c"),
        "scripts": "\n".join(scripts),
    }
    layout_path = course.path(str(cfg["layout"])) if cfg.get("layout") else THEME_DIR / "layout.html"
    page = fill(_read(layout_path, "layout"), context, L, warn)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    return BuildResult(course=course, output=output, warnings=warnings,
                       seconds=time.time() - started)
