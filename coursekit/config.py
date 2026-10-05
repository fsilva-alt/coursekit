"""Load a course folder: `course.yml`, its parts and its chapters.

A course is a folder containing `course.yml`. Chapters are Markdown files (one chapter per
file). Parts are optional groups of chapters and can be declared in three ways:

1. explicitly in course.yml:      parts: [{title, description, chapters: [paths or globs]}]
2. a flat chapter list:           chapters: [paths or globs]          (no parts)
3. auto-discovery (default):      chapters/<part-folder>/<chapter>.md (one sub-folder per part,
                                  optional `_part.yml` with title/description) or simply
                                  chapters/<chapter>.md for a course without parts.
"""

from __future__ import annotations

import datetime as dt
import glob
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from .labels import resolve_labels

CONFIG_NAMES = ("course.yml", "course.yaml")
PART_META_NAMES = ("_part.yml", "_part.yaml")

DEFAULTS: Dict[str, Any] = {
    "title": "Untitled course",
    "subtitle": "",
    "description": "",
    "authors": [],
    "updated": "auto",
    "language": "en",
    "accent": "#5b50e6",
    "accent_dark": None,
    "logo": None,
    "favicon": None,
    "home_url": None,
    "finish_url": None,
    "edit_url": None,
    "numbering": "course",          # course | part | none
    "transition": "slide",          # slide | fade | none
    "highlight": True,
    "line_numbers": False,
    "embed_images": True,
    "embed_external_images": True,
    "external_links_new_tab": True,
    "typographer": True,
    "chapters_dir": "chapters",
    "parts": None,
    "chapters": None,
    "styles": [],
    "replace_base_styles": False,
    "scripts": [],
    "head": None,
    "layout": None,
    "labels": {},
    "slug": None,
}


class CourseError(Exception):
    """A problem in a course's configuration or files."""


@dataclass
class Chapter:
    path: Path
    rel: str                    # path relative to the course root (posix style)
    id: str
    title: str
    body: str                   # Markdown without front matter and without the title heading
    duration: int               # minutes
    meta: Dict[str, Any]
    index: int = 0              # position in the whole course (0-based)
    part: int = 0               # index of its part in Course.parts
    number: str = ""            # displayed number: "3", "2.1" or ""
    html: str = ""


@dataclass
class Part:
    title: str = ""             # empty title = an untitled group (not shown as a part)
    description: str = ""
    number: int = 0             # 1-based among titled parts, 0 for untitled groups
    chapters: List[Chapter] = field(default_factory=list)


@dataclass
class Course:
    root: Path
    config: Dict[str, Any]
    parts: List[Part]
    labels: Dict[str, str]
    updated: Optional[dt.date]
    authors: List[str]

    @property
    def chapters(self) -> List[Chapter]:
        return [c for p in self.parts for c in p.chapters]

    @property
    def slug(self) -> str:
        return self.config.get("slug") or slugify(self.root.name)

    @property
    def has_parts(self) -> bool:
        return any(p.title for p in self.parts)

    @property
    def total_minutes(self) -> int:
        return sum(c.duration for c in self.chapters)

    def path(self, value: str) -> Path:
        """Resolve a path from course.yml (relative to the course root)."""
        p = Path(value).expanduser()
        return p if p.is_absolute() else (self.root / p)


# ---------------------------------------------------------------------------- helpers

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text


def unique_slug(base: str, used: set) -> str:
    base = base or "section"
    slug, n = base, 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


_FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", re.S)
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_H1 = re.compile(r"^ {0,3}#[ \t]+(.+?)[ \t]*$")


def split_front_matter(text: str, where: str) -> tuple:
    text = text.lstrip("﻿")
    m = _FRONT_MATTER.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        raise CourseError(f"{where}: invalid front matter: {exc}") from None
    if not isinstance(meta, dict):
        raise CourseError(f"{where}: front matter must be a mapping (key: value)")
    return meta, text[m.end():]


def _iter_prose_lines(lines):
    """Yield (index, line, in_code) while tracking fenced code blocks."""
    fence = None
    for i, line in enumerate(lines):
        m = _FENCE.match(line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                    and not line.strip()[len(m.group(1)):].strip():
                fence = None
            yield i, line, True
            continue
        if m:
            fence = m.group(1)
            yield i, line, True
            continue
        yield i, line, False


def extract_title(body: str):
    """Return (title, body_without_it) using the first `# Heading` outside code blocks."""
    lines = body.splitlines(keepends=True)
    for i, line, in_code in _iter_prose_lines(lines):
        if in_code:
            continue
        m = _H1.match(line.rstrip("\r\n"))
        if m:
            title = re.sub(r"[ \t]+#+$", "", m.group(1)).strip()
            return title, "".join(lines[:i] + lines[i + 1:])
    return None, body


def estimate_minutes(body: str) -> int:
    words = code = 0
    for _, line, in_code in _iter_prose_lines(body.splitlines()):
        if in_code:
            code += 1
        else:
            words += len(re.findall(r"\w+", re.sub(r"<[^>]+>", " ", line)))
    return max(1, math.ceil(words / 200 + code / 15))


def _as_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def _humanize(name: str) -> str:
    name = re.sub(r"^\d+[-_. ]*", "", name).replace("-", " ").replace("_", " ").strip()
    return name[:1].upper() + name[1:]


# ---------------------------------------------------------------------------- loading

def find_config(course_dir: Path) -> Path:
    for name in CONFIG_NAMES:
        if (course_dir / name).is_file():
            return course_dir / name
    raise CourseError(f"{course_dir}: no course.yml found")


def is_course_dir(path: Path) -> bool:
    return any((path / name).is_file() for name in CONFIG_NAMES)


def load_course(course_dir: Path, warn: Callable[[str], None] = print) -> Course:
    root = course_dir.resolve()
    cfg_path = find_config(root)
    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CourseError(f"{cfg_path}: invalid YAML: {exc}") from None
    if not isinstance(raw, dict):
        raise CourseError(f"{cfg_path}: expected a mapping at the top level")

    for key in raw:
        if key not in DEFAULTS and key not in ("author",):
            warn(f"{cfg_path.name}: unknown option '{key}' (ignored)")

    config = dict(DEFAULTS)
    config.update(raw)
    if config.get("numbering") not in ("course", "part", "none"):
        raise CourseError(f"{cfg_path.name}: numbering must be course, part or none")
    if config.get("transition") not in ("slide", "fade", "none"):
        raise CourseError(f"{cfg_path.name}: transition must be slide, fade or none")

    authors = _as_list(raw.get("authors")) or _as_list(raw.get("author"))
    labels = resolve_labels(str(config["language"]), config.get("labels") or {})

    course = Course(root=root, config=config, parts=[], labels=labels, updated=None,
                    authors=authors)
    course.parts = _discover_parts(course, warn)
    if not course.chapters:
        raise CourseError(f"{root}: the course has no chapters")

    _finalize(course)
    course.updated = _updated_date(course, cfg_path)
    return course


def _hidden(path: Path, base: Path) -> bool:
    """True for files under (or named) `_something` / `.something`, relative to `base`."""
    try:
        parts = path.resolve().relative_to(base.resolve()).parts
    except ValueError:
        parts = (path.name,)
    return any(p.startswith(("_", ".")) for p in parts)


def _expand(course: Course, patterns: List[str], where: str, seen: set, warn) -> List[Path]:
    """Resolve chapter paths/globs, skipping files already used elsewhere in the course."""
    files: List[Path] = []
    for pattern in patterns:
        full = course.path(pattern)
        if any(ch in pattern for ch in "*?["):
            matches = sorted(Path(p) for p in glob.glob(str(full), recursive=True))
            matches = [m for m in matches if m.is_file() and not _hidden(m, course.root)]
            if not matches:
                raise CourseError(f"{where}: pattern '{pattern}' matched no files")
        elif full.is_file():
            matches = [full]
        else:
            raise CourseError(f"{where}: chapter file not found: {pattern}")
        for m in matches:
            key = m.resolve()
            if key in seen:
                if not any(ch in pattern for ch in "*?["):
                    warn(f"{where}: {pattern} is listed more than once (later entry ignored)")
                continue
            seen.add(key)
            files.append(m)
    return files


def _discover_parts(course: Course, warn) -> List[Part]:
    cfg = course.config
    seen: set = set()
    if cfg.get("parts"):
        parts = []
        for i, entry in enumerate(cfg["parts"], 1):
            if not isinstance(entry, dict):
                raise CourseError(f"course.yml: parts[{i}] must be a mapping with title/chapters")
            files = _expand(course, _as_list(entry.get("chapters")), f"course.yml parts[{i}]",
                            seen, warn)
            parts.append(Part(title=str(entry.get("title") or ""),
                              description=str(entry.get("description") or ""),
                              chapters=[_load_chapter(course, f) for f in files]))
        return parts

    if cfg.get("chapters"):
        files = _expand(course, _as_list(cfg["chapters"]), "course.yml chapters", seen, warn)
        return [Part(chapters=[_load_chapter(course, f) for f in files])]

    base = course.path(str(cfg["chapters_dir"]))
    if not base.is_dir():
        raise CourseError(f"{course.root}: no '{cfg['chapters_dir']}/' folder and no chapters "
                          "listed in course.yml")

    def visible(p: Path) -> bool:
        return not p.name.startswith(("_", "."))

    parts: List[Part] = []
    loose = sorted(p for p in base.glob("*.md") if visible(p))
    if loose:
        parts.append(Part(chapters=[_load_chapter(course, f) for f in loose]))
    for folder in sorted(p for p in base.iterdir() if p.is_dir() and visible(p)):
        meta: Dict[str, Any] = {}
        for name in PART_META_NAMES:
            if (folder / name).is_file():
                meta = yaml.safe_load((folder / name).read_text(encoding="utf-8")) or {}
        files = sorted(p for p in folder.rglob("*.md") if not _hidden(p, folder))
        if not files:
            warn(f"part folder '{folder.name}' has no chapters (skipped)")
            continue
        parts.append(Part(title=str(meta.get("title") or _humanize(folder.name)),
                          description=str(meta.get("description") or ""),
                          chapters=[_load_chapter(course, f) for f in files]))
    return parts


def _load_chapter(course: Course, path: Path) -> Chapter:
    rel = path.resolve().relative_to(course.root).as_posix() \
        if course.root in path.resolve().parents else path.as_posix()
    meta, body = split_front_matter(path.read_text(encoding="utf-8"), rel)
    title = meta.get("title")
    heading, body_wo = extract_title(body)
    if heading is not None:
        body = body_wo
    title = str(title or heading or _humanize(path.stem))
    chapter_id = str(meta.get("id") or slugify(re.sub(r"^\d+[-_. ]*", "", path.stem))
                     or slugify(title))
    try:
        duration = int(meta["duration"]) if meta.get("duration") is not None \
            else estimate_minutes(body)
    except (TypeError, ValueError):
        raise CourseError(f"{rel}: duration must be a whole number of minutes") from None
    return Chapter(path=path.resolve(), rel=rel, id=chapter_id, title=title, body=body,
                   duration=max(0, duration), meta=meta)


def _finalize(course: Course) -> None:
    # Drop drafts and empty groups, then number everything.
    for part in course.parts:
        part.chapters = [c for c in part.chapters if not c.meta.get("draft")]
    course.parts = [p for p in course.parts if p.chapters]

    seen: Dict[str, str] = {}
    numbering = course.config["numbering"]
    part_no = index = 0
    for p_index, part in enumerate(course.parts):
        if part.title:
            part_no += 1
            part.number = part_no
        for c_index, chapter in enumerate(part.chapters, 1):
            if chapter.id in seen:
                raise CourseError(f"{chapter.rel}: chapter id '{chapter.id}' is already used by "
                                  f"{seen[chapter.id]} — set a different `id:` in its front matter")
            seen[chapter.id] = chapter.rel
            chapter.index, chapter.part = index, p_index
            index += 1
            if numbering == "course":
                chapter.number = str(index)
            elif numbering == "part" and part.number:
                chapter.number = f"{part.number}.{c_index}"
            elif numbering == "part":
                chapter.number = str(index)


def _updated_date(course: Course, cfg_path: Path) -> Optional[dt.date]:
    value = course.config.get("updated")
    if value in (None, False, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if str(value).lower() == "auto":
        stamps = [c.path.stat().st_mtime for c in course.chapters] + [cfg_path.stat().st_mtime]
        return dt.date.fromtimestamp(max(stamps))
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        raise CourseError("course.yml: updated must be 'auto' or a date like 2026-10-04") from None
