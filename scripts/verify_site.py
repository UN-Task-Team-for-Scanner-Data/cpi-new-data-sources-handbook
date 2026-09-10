# /// script
# requires-python = ">=3.12"
# dependencies = ["beautifulsoup4", "lxml"]
# ///
"""Verify a rendered _site against the Confluence export.

  uv run scripts/verify_site.py [--site <path-to-_site>]

Per page: compares formula and image counts in the rendered HTML against the
source export page body. Also checks every internal link and image src in the
rendered site resolves to a file, and that no .qmd has doubled CR line endings.
Exits 1 on hard failures (missing page, broken internal link/img, page whose
source has math/images but whose render has none).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from convert_all import EXPORT_DIR, REPO_ROOT, assign_slugs, flatten, page_stats, parse_tree

# Letters the .qmd may fall short of its source before it counts as lost prose.
# Conversion normally ADDS letters, because link targets become visible text.
PROSE_TOLERANCE = 100

DROP_SELECTORS = ("div.toc-macro", "ol#breadcrumbs", "div.page-metadata", "style", "script")


def source_prose_letters(node) -> int:
    """Count letters in a source page body, ignoring the page information aside."""
    src = EXPORT_DIR / node.href
    if not src.is_file():
        return 0

    soup = BeautifulSoup(src.read_text(encoding="utf-8", errors="replace"), "lxml")
    content = soup.find("div", id="main-content")
    if content is None:
        return 0

    for selector in DROP_SELECTORS:
        for tag in content.select(selector):
            tag.decompose()
    for aside in content.select("div.cell.aside"):
        heading = aside.find("strong")
        if heading and "page information" in heading.get_text(strip=True).lower():
            aside.decompose()

    return len(re.sub(r"[^a-z]", "", content.get_text(" ", strip=True).lower()))


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default=str(REPO_ROOT / "_site"))
    args = parser.parse_args()
    site = Path(args.site)

    root = parse_tree()
    assign_slugs(root)
    pages = flatten(root)
    hard, soft = [], []

    # 1. per-page content parity
    for node in pages:
        out = site / f"{node.slug}.html"
        if not out.is_file():
            hard.append(f"MISSING RENDER: {node.slug}.html")
            continue
        html = out.read_text(encoding="utf-8")
        r_math = len(re.findall(r'class="math (?:inline|display)"', html))
        r_imgs = len(re.findall(r"<img [^>]*src=\"(?:images/|files/|https?:)", html))
        s_math, s_imgs = page_stats(node)
        if s_math and r_math == 0:
            hard.append(f"NO MATH RENDERED: {node.slug} (source {s_math})")
        elif r_math < s_math:
            soft.append(f"math {r_math}<{s_math}: {node.slug} (literal \\(n\\) refs are benign)")
        if r_imgs != s_imgs:
            (hard if r_imgs < s_imgs else soft).append(
                f"imgs {r_imgs}!={s_imgs}: {node.slug}")

    # 2. internal links + img srcs resolve
    for html_file in sorted(site.glob("*.html")):
        html = html_file.read_text(encoding="utf-8")
        for attr, val in re.findall(r'(href|src)="([^"]+)"', html):
            url = urlparse(val)
            if url.scheme or val.startswith(("#", "mailto:", "data:")):
                continue
            target = (site / unquote(url.path)).resolve() if not url.path.startswith("/") else None
            if target is None or not target.exists():
                hard.append(f"BROKEN {attr}: {val}  (in {html_file.name})")

    # 3. CRLF doubling regression check
    for qmd in sorted(REPO_ROOT.glob("*.qmd")):
        if b"\r\r\n" in qmd.read_bytes():
            hard.append(f"DOUBLED CR: {qmd.name}")

    # 4. prose parity: the .qmd must not be materially shorter than its source.
    # Counting formulas and images cannot detect dropped prose. Pandoc has
    # silently dropped whole paragraphs here, with no warning and no other
    # check failing.
    for node in pages:
        qmd = REPO_ROOT / f"{node.slug}.qmd"
        if not qmd.is_file():
            continue
        src_letters = source_prose_letters(node)
        if not src_letters:
            continue
        body = re.sub(r"^---\n.*?\n---\n", "", qmd.read_text(encoding="utf-8"), flags=re.S)
        out_letters = len(re.sub(r"[^a-z]", "", body.lower()))
        if out_letters < src_letters - PROSE_TOLERANCE:
            hard.append(
                f"PROSE LOST: {node.slug} (source {src_letters}, qmd {out_letters})")

    print(f"pages checked: {len(pages)}")
    for s in soft:
        print("soft:", s)
    for h in hard:
        print("HARD:", h)
    print(f"result: {len(hard)} hard, {len(soft)} soft")
    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
