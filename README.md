# coursekit

The rendering tool for step-by-step courses. Write a course as a folder of Markdown files;
coursekit turns it into a **single self-contained `index.html`**:

- chapters on the left, one chapter at a time on the right
- Back/Next with slide transitions, progress and time remaining
- light/dark mode
- everything (styles, scripts, images — even remote ones) embedded in the file

## How it's organised

coursekit lives in its own repository. Every course is a separate repository **next to it**
in the same working folder, and uses it by reference through its `build.sh`:

```
work/
├── coursekit/          ← this repository: the tool, the theme and the course template
├── python-basics/      ← example course (its own repository)
├── authoring-guide/    ← the documentation, written as a course (its own repository)
└── my-new-course/      ← every new course: its own folder and repository
    ├── build.sh        ← calls ../coursekit
    ├── course.yml
    ├── chapters/01-intro/_part.yml, 01-welcome.md, …
    ├── assets/  styles/custom.css  scripts/custom.js
    └── dist/index.html ← the result
```

Courses don't copy anything from coursekit. A change to the tool, theme or layout reaches
every course on its next build: `git pull` in `coursekit/`, then rebuild.

## Getting started

Requirements: Python 3.9+ and a POSIX shell (Linux, macOS, WSL or Git Bash). No Node.js.

```bash
cd work
git clone <coursekit repo> coursekit
git clone <a course repo> python-basics

cd python-basics
./build.sh            # → dist/index.html. The first run sets up coursekit/.venv by itself.
./build.sh dev        # preview at http://127.0.0.1:8000, rebuilt and reloaded as you save
./build.sh --strict   # fail on warnings (missing images, broken links …), e.g. in CI
```

The launcher `coursekit/bin/coursekit` creates the tool's virtual environment on first use and
refreshes it whenever `requirements.txt` changes. Set `COURSEKIT=/path/to/coursekit` if a
course can't find the tool next to it.

### A new course

From the working folder:

```bash
coursekit/bin/coursekit new intro-to-linux --title "Introduction to Linux"
cd intro-to-linux && ./build.sh dev
```

This copies `templates/starter/` into `./intro-to-linux/`, sets the title, and points its
`build.sh` at this checkout. It also runs `git init`; pass `--no-git` to skip that. To start
from an existing course instead, use `--template ../python-basics`.

## Writing chapters

A chapter is a Markdown file with optional front matter. The first `# heading` is the title:

```markdown
---
duration: 10        # minutes (feeds "time remaining"; estimated from the text if omitted)
---

# Variables and data types

Text, **Markdown**, and any <abbr title="unrestricted">raw HTML</abbr>.
```

Parts are the sub-folders of `chapters/`, each with an optional `_part.yml`
(`title:`, `description:`), sorted by name. Alternatively, list them in `course.yml` under
`parts:` (glob patterns allowed), or use a flat `chapters:` list for a course without parts.

### Elements

| Element | Syntax |
| --- | --- |
| Callouts | `:::note`, `info`, `tip`, `success`, `important`, `warning`, `caution`, `danger` (+ optional title) or GitHub style `> [!TIP]` |
| Exercise box | `:::exercise [title]` |
| Collapsibles | `:::details Summary`, `:::hint`, `:::solution` |
| Tabs (synced by label, remembered) | `::::tabs` containing `:::tab Windows` … |
| Columns / cards | `::::columns` containing `:::column`; `:::card [title]` |
| Numbered procedure | `:::steps` around an ordered list |
| Quiz | `:::quiz Question?` + `- [x] right` / `- [ ] wrong` (several `[x]` = multiple choice); text after the list = explanation |
| Checklist (remembered) | `- [ ] item` |
| Code | ```` ```python title="app.py" hl_lines="2 4-6" linenums ```` — `console` / `pycon` transcripts copy only the commands |
| Images | `![alt](assets/x.png "Caption")` (title → figure) · `{width=400}` · local or `https://` — all embedded |
| Attributes | `{.class #id key=value}` after links/images/inline code, or on the line before a block |
| Extras | `<kbd>`, `<mark>`, `<span class="badge">`, `[Link](url){.button}`, footnotes, definition lists, tables |

Nest containers by giving the outer one more colons (`::::tabs` around `:::tab`). Link to other
chapters with `#chapter-id` or the file name (`[next](02-setup.md#section)`). The Authoring
Guide course documents every element and option in detail.

## Customising

- **`course.yml`**: title, authors, accent colour, logo, numbering, transitions,
  highlighting, language (`en`, `pt`, `es`) and any interface string (`labels:`).
  `templates/starter/course.yml` documents every option.
- **Per-course styles**: files in `styles:` are inlined after the base theme. They can
  redefine tokens (`--accent`, `--font-sans`, `--content-w`, …) or add classes, and
  `replace_base_styles: true` drops the base theme entirely. `url()` assets are embedded.
- **Per-course scripts**: files in `scripts:` run after the runtime and can use
  `window.coursekit` (`onChapter`, `go`, `next`, `prev`, `toast`) and the
  `coursekit:chapterchange` / `coursekit:finish` events.
- **Layout**: copy `coursekit/theme/layout.html` into a course and set `layout:`;
  `head:` adds raw HTML to `<head>`.
- **For every course at once**: edit the theme here, in `coursekit/theme/`
  (`base.css`, `app.js`, `layout.html`).

## Publishing

`./build.sh` writes one standalone file, `dist/index.html`. Put it on any static host or in an
LMS, share it on a drive, or open it straight from disk. `dist/` and `.cache/` are git-ignored
by default. Remove `dist/` from a course's `.gitignore` if you publish straight from its
repository, for example with Pages.

## This repository

```
bin/coursekit         launcher (manages .venv, then runs the CLI: build | dev | new)
coursekit/            the builder (Python) and theme/ (layout.html, base.css, app.js)
templates/starter/    copied by `coursekit new` (includes build.sh, .gitignore, README.md)
requirements.txt      4 small dependencies
```
