"""Embed images (local and remote) and CSS `url()` assets as data: URIs.

* `<img src>` in rendered chapters — from Markdown or raw HTML — is embedded. Relative paths
  are looked up next to the chapter file first, then from the course root; `/x.png` means
  `<course>/x.png`.
* Remote images (http/https) are downloaded once and cached in `.cache/images/`.
* Add `data-embed="false"` to an <img> (or `{data-embed=false}` after a Markdown image)
  to leave it untouched.
* `url(...)` references in custom stylesheets (fonts, backgrounds) are embedded relative to
  the stylesheet.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import mimetypes
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

MIME_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".webp": "image/webp", ".svg": "image/svg+xml", ".avif": "image/avif",
    ".ico": "image/x-icon", ".bmp": "image/bmp", ".woff2": "font/woff2", ".woff": "font/woff",
    ".ttf": "font/ttf", ".otf": "font/otf", ".mp3": "audio/mpeg", ".mp4": "video/mp4",
    ".webm": "video/webm", ".json": "application/json", ".css": "text/css",
}
LARGE_FILE = 2 * 1024 * 1024
USER_AGENT = "coursekit/1.0 (static course builder; +https://example.invalid/coursekit)"

_IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
_SRC_ATTR = re.compile(r"""(\ssrc\s*=\s*)(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""", re.I)
_NO_EMBED = re.compile(r"""\sdata-embed\s*=\s*["']?false""", re.I)
_CSS_URL = re.compile(r"""url\(\s*(["']?)([^"')]+?)\1\s*\)""", re.I)


def sniff_mime(data: bytes) -> Optional[str]:
    head = data[:2048].lstrip()
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:12] in (b"ftypavif", b"ftypavis"):
        return "image/avif"
    if data.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    if head.startswith(b"<svg") or (head.startswith((b"<?xml", b"<!--", b"<!DOCTYPE"))
                                    and b"<svg" in data[:8192]):
        return "image/svg+xml"
    return None


def data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def is_remote(src: str) -> bool:
    return bool(re.match(r"^(https?:)?//", src, re.I))


class AssetEmbedder:
    def __init__(self, cache_dir: Path, *, embed_local: bool = True, embed_remote: bool = True,
                 warn: Callable[[str], None] = print):
        self.cache_dir = cache_dir
        self.embed_local = embed_local
        self.embed_remote = embed_remote
        self.warn = warn
        self._remote: Dict[str, Optional[Tuple[bytes, str]]] = {}
        self.stats = {"local": 0, "remote": 0, "bytes": 0}

    # ------------------------------------------------------------------ files
    def file_data_uri(self, path: Path, where: str = "") -> Optional[str]:
        try:
            data = path.read_bytes()
        except OSError:
            self.warn(f"{where}image not found: {path}")
            return None
        mime = MIME_TYPES.get(path.suffix.lower()) or sniff_mime(data) \
            or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if len(data) > LARGE_FILE:
            self.warn(f"{where}{path.name} is {len(data) / 1e6:.1f} MB — consider compressing it")
        self.stats["local"] += 1
        self.stats["bytes"] += len(data)
        return data_uri(data, mime)

    def resolve_local(self, src: str, search_dirs: Iterable[Path], root: Path) -> Optional[Path]:
        path = unquote(urlsplit(src).path)
        if not path:
            return None
        if path.startswith("/"):
            candidate = root / path.lstrip("/")
            return candidate if candidate.is_file() else None
        for base in search_dirs:
            candidate = (base / path).resolve()
            if candidate.is_file():
                return candidate
        return None

    # ------------------------------------------------------------------ remote
    def _cache_paths(self, url: str) -> Tuple[Path, Path]:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        return self.cache_dir / f"{key}.bin", self.cache_dir / f"{key}.json"

    def fetch(self, url: str) -> Optional[Tuple[bytes, str]]:
        if url in self._remote:
            return self._remote[url]
        blob_path, meta_path = self._cache_paths(url)
        result: Optional[Tuple[bytes, str]] = None
        if blob_path.is_file() and meta_path.is_file():
            try:
                result = (blob_path.read_bytes(), json.loads(meta_path.read_text())["mime"])
            except (OSError, ValueError, KeyError):
                result = None
        if result is None:
            result = self._download(url)
            if result is not None:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                blob_path.write_bytes(result[0])
                meta_path.write_text(json.dumps({"url": url, "mime": result[1]}))
        self._remote[url] = result
        return result

    def _download(self, url: str) -> Optional[Tuple[bytes, str]]:
        full = "https:" + url if url.startswith("//") else url
        request = urllib.request.Request(full, headers={"User-Agent": USER_AGENT,
                                                        "Accept": "image/*,*/*;q=0.8"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
                header = response.headers.get_content_type()
        except Exception as exc:  # network errors, HTTP errors, timeouts
            self.warn(f"could not download {url} ({exc}); keeping the external link")
            return None
        mime = header if header.startswith("image/") else sniff_mime(data)
        if not mime:
            self.warn(f"{url} did not return an image ({header}); keeping the external link")
            return None
        if mime == "image/svg+xml" or sniff_mime(data) == "image/svg+xml":
            mime = "image/svg+xml"
        return data, mime

    # ------------------------------------------------------------------ HTML
    def embed_html(self, markup: str, search_dirs: List[Path], root: Path, where: str = "") -> str:
        tags = [(m, _SRC_ATTR.search(m.group(0))) for m in _IMG_TAG.finditer(markup)]
        remote = {html.unescape(s) for _, sm in tags if sm
                  for s in [next(g for g in sm.group(2, 3, 4) if g is not None)]
                  if is_remote(html.unescape(s))}
        if remote and self.embed_remote:
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(self.fetch, sorted(remote)))

        def replace_tag(m: re.Match) -> str:
            tag = m.group(0)
            if _NO_EMBED.search(tag):
                return tag
            sm = _SRC_ATTR.search(tag)
            if not sm:
                return tag
            src = html.unescape(next(g for g in sm.group(2, 3, 4) if g is not None)).strip()
            new = self._embed_src(src, search_dirs, root, where)
            if not new:
                return tag
            return tag[:sm.start()] + f'{sm.group(1)}"{new}"' + tag[sm.end():]

        return _IMG_TAG.sub(replace_tag, markup)

    def _embed_src(self, src: str, search_dirs: List[Path], root: Path, where: str) -> Optional[str]:
        if not src or src.startswith(("data:", "blob:", "#")):
            return None
        if is_remote(src):
            if not self.embed_remote:
                return None
            fetched = self.fetch(src)
            if not fetched:
                return None
            self.stats["remote"] += 1
            self.stats["bytes"] += len(fetched[0])
            return data_uri(*fetched)
        if re.match(r"^[a-z][a-z0-9+.-]*:", src, re.I) or not self.embed_local:
            return None
        path = self.resolve_local(src, search_dirs, root)
        if path is None:
            self.warn(f"{where}image not found: {src}")
            return None
        return self.file_data_uri(path, where)

    # ------------------------------------------------------------------ CSS
    def embed_css(self, css: str, css_path: Path) -> str:
        def replace(m: re.Match) -> str:
            ref = m.group(2).strip()
            if ref.startswith(("data:", "#")) or is_remote(ref) or ":" in ref.split("/")[0]:
                return m.group(0)
            path = (css_path.parent / unquote(urlsplit(ref).path)).resolve()
            uri = self.file_data_uri(path, f"{css_path.name}: ") if path.is_file() else None
            if uri is None:
                self.warn(f"{css_path.name}: asset not found: {ref}")
                return m.group(0)
            return f'url("{uri}")'
        return _CSS_URL.sub(replace, css)
