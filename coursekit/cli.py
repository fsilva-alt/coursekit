"""Command line: `coursekit build | dev | new`.

Normally run through `bin/coursekit` (which manages the virtual environment) or through a
course's own `build.sh`, which calls `../coursekit/bin/coursekit`.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .build import BuildResult, build_course
from .config import CourseError, is_course_dir, slugify

PACKAGE_DIR = Path(__file__).resolve().parent
TOOL_DIR = PACKAGE_DIR.parent
TEMPLATES_DIR = TOOL_DIR / "templates"


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _size(path: Path) -> str:
    n = path.stat().st_size
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def _course_dirs(paths: List[Path]) -> List[Path]:
    dirs = [p.resolve() for p in (paths or [Path(".")])]
    missing = [str(p) for p in dirs if not is_course_dir(p)]
    if missing:
        raise CourseError("not a course folder (no course.yml): " + ", ".join(missing))
    return dirs


def _output_for(course_dir: Path, out: Optional[Path], many: bool) -> Path:
    """Default <course>/dist/index.html; --out DIR → DIR/index.html (DIR/<course>/… for several)."""
    if out is None:
        return course_dir / "dist" / "index.html"
    out = out.resolve()
    if out.suffix.lower() in (".html", ".htm"):
        return out
    return out / course_dir.name / "index.html" if many else out / "index.html"


def build_one(course_dir: Path, output: Path, dev: bool = False) -> Optional[BuildResult]:
    print(f"* {course_dir.name}")
    try:
        result = build_course(course_dir, output, cache_dir=course_dir / ".cache", dev=dev)
    except (CourseError, FileNotFoundError) as exc:
        print(f"  error: {exc}")
        return None
    print(f"  -> {_rel(result.output)}  ({_size(result.output)}, "
          f"{len(result.course.chapters)} chapters, {result.seconds:.2f}s)")
    return result


def cmd_build(args) -> int:
    try:
        dirs = _course_dirs(args.courses)
    except CourseError as exc:
        print(f"error: {exc}")
        return 1
    many = len(dirs) > 1
    if many and args.out and args.out.suffix.lower() in (".html", ".htm"):
        print("error: --out must be a folder when building several courses")
        return 1
    results = [build_one(d, _output_for(d, args.out, many)) for d in dirs]
    built = [r for r in results if r is not None]
    warnings = sum(len(r.warnings) for r in built)
    if warnings:
        print(f"\n{warnings} warning(s).")
    return 1 if len(built) < len(results) or (args.strict and warnings) else 0


def cmd_dev(args) -> int:
    from .devserver import serve

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)   # show rebuild output immediately
    try:
        course_dir = _course_dirs([args.course] if args.course else [])[0]
    except CourseError as exc:
        print(f"error: {exc}")
        return 1
    out_dir = course_dir / ".cache" / "dev"
    output = out_dir / "index.html"
    build_one(course_dir, output, dev=True)          # on errors, keep serving: fix and save
    serve(out_dir, course_dir, [PACKAGE_DIR / "theme"],
          lambda: build_one(course_dir, output, dev=True), args.host, args.port, args.open)
    return 0


def cmd_new(args) -> int:
    slug = slugify(args.name)
    if not slug:
        print("error: please give the course a name, e.g. `coursekit new intro-to-linux`")
        return 1
    template = (args.template or TEMPLATES_DIR / "starter").resolve()
    if not is_course_dir(template):
        print(f"error: template not found: {template}")
        return 1
    dest = (args.dir / slug).resolve()
    if dest.exists():
        print(f"error: {_rel(dest)} already exists")
        return 1

    title = args.title or slug.replace("-", " ").title()
    shutil.copytree(template, dest, ignore=shutil.ignore_patterns(
        ".git", ".cache", "dist", "__pycache__", ".DS_Store"))

    cfg = dest / "course.yml"
    quoted = '"' + title.replace("\\", "\\\\").replace('"', '\\"') + '"'
    cfg.write_text(re.sub(r"(?m)^title:.*$", lambda _: f"title: {quoted}",
                          cfg.read_text(encoding="utf-8"), count=1), encoding="utf-8")

    readme = dest / "README.md"
    if readme.is_file():
        readme.write_text(re.sub(r"(?m)\A# .*$", lambda _: f"# {title}",
                                 readme.read_text(encoding="utf-8"), count=1), encoding="utf-8")

    # Point build.sh at this copy of coursekit, wherever the new course was created.
    script = dest / "build.sh"
    if script.is_file():
        tool = os.path.relpath(TOOL_DIR, dest).replace(os.sep, "/")
        text = re.sub(r'(COURSEKIT="\$\{COURSEKIT:-)[^}]*(\}")', lambda m: m.group(1) + tool + m.group(2),
                      script.read_text(encoding="utf-8"))
        script.write_text(text, encoding="utf-8")
        script.chmod(0o755)

    git = ""
    if not args.no_git and shutil.which("git"):
        if subprocess.run(["git", "init", "-q"], cwd=dest).returncode == 0:
            git = " (new git repository)"
    print(f"Created {_rel(dest)}/{git} from the '{template.name}' template.\n")
    print("Next steps:")
    print(f"  cd {_rel(dest)}")
    print("  ./build.sh dev     # preview with live reload while you write")
    print("  ./build.sh         # build dist/index.html")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="coursekit",
        description="Build step-by-step courses from Markdown into single, self-contained HTML files.")
    parser.add_argument("--version", action="version", version=f"coursekit {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="command")
    sub.required = True

    b = sub.add_parser("build", help="build a course into <course>/dist/index.html")
    b.add_argument("courses", nargs="*", type=Path, help="course folder(s) (default: the current folder)")
    b.add_argument("--out", type=Path,
                   help="output folder (or .html file) instead of <course>/dist/")
    b.add_argument("--strict", action="store_true", help="exit with an error if there are warnings")
    b.set_defaults(func=cmd_build)

    d = sub.add_parser("dev", help="preview a course with automatic rebuild and live reload")
    d.add_argument("course", nargs="?", type=Path, help="course folder (default: the current folder)")
    d.add_argument("--host", default="127.0.0.1")
    d.add_argument("--port", type=int, default=8000)
    d.add_argument("--open", action="store_true", help="open the browser")
    d.set_defaults(func=cmd_dev)

    n = sub.add_parser("new", help="create a new course folder from a template")
    n.add_argument("name", help="folder name, e.g. intro-to-linux")
    n.add_argument("--title", help='course title, e.g. "Introduction to Linux"')
    n.add_argument("--dir", type=Path, default=Path("."),
                   help="where to create it (default: the current folder)")
    n.add_argument("--template", type=Path,
                   help="course folder to copy (default: coursekit/templates/starter)")
    n.add_argument("--no-git", action="store_true", help="don't run `git init` in the new folder")
    n.set_defaults(func=cmd_new)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
