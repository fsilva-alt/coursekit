# My New Course

Course material written in Markdown and rendered with **coursekit** into a single,
self-contained `dist/index.html` (styles, scripts and images included).

## Build

Needs the coursekit repository next to this one (`../coursekit`) and Python 3.9+.

```bash
./build.sh            # build dist/index.html: open it in a browser or publish it anywhere
./build.sh dev        # preview at http://127.0.0.1:8000, rebuilt and reloaded as you save
./build.sh --strict   # fail on warnings (missing images, broken links …)
```

## Layout

```
course.yml               title, authors, colours and other settings
chapters/<part>/*.md     one Markdown file per chapter; one folder per part (_part.yml = title)
assets/                  images (embedded into the page at build time)
styles/custom.css        extra styles for this course
scripts/custom.js        extra behaviour for this course
```

See the Authoring Guide course for every element you can use in a chapter.
