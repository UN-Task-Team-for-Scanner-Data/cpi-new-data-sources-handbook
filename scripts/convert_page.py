# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "beautifulsoup4",
#     "lxml",
# ]
# ///
"""Convert one Confluence HTML space-export page into a Quarto .qmd file.

Usage (from the repo root):
    uv run scripts/convert_page.py <export_html_path> <slug>

Writes <repo>/<slug>.qmd and copies referenced attachment images to
<repo>/images/<slug>/.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parent.parent

REMOVE_SELECTORS = (
    "div.toc-macro",
    "ol#breadcrumbs",
    "div.page-metadata",
    "div.footer",
    "#footer",
    "style",
    "script",
)

UNWRAP_SELECTORS = (
    "span.inline-comment-marker",
    "span.confluence-embedded-file-wrapper",
    "a.confluence-embedded-image",
)

LAYOUT_UNWRAP_SELECTORS = (
    "div.contentLayout2",
    "div.columnLayout",
    "div.cell",
    "div.innerCell",
)

IMG_KEEP_ATTRS = {"src", "alt"}


def _fix_console_encoding() -> None:
    """Avoid UnicodeEncodeError on Windows consoles using legacy code pages."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a Confluence export HTML page to a Quarto .qmd file."
    )
    parser.add_argument("export_html_path", type=Path, help="Path to the exported Confluence HTML page.")
    parser.add_argument("slug", help="Output slug: produces <slug>.qmd and images/<slug>/.")
    parser.add_argument(
        "--debug-html",
        action="store_true",
        help="Also write the cleaned intermediate HTML to scripts/_debug/<slug>.cleaned.html.",
    )
    # NOTE: no --regex-math flag. Math delimiters (\(...\) \[...\]) are left as
    # literal text; conversion to $...$ is handled by pandoc's
    # tex_math_single_backslash reader extension in run_pandoc(), not by regex.
    return parser.parse_args()


def extract_title(soup: BeautifulSoup) -> str:
    """Prefer the element with id="title-text" (tag varies: h1 or nested span);
    fall back to <title>. Both are observed, in this export, to repeat the
    "<space name> : <page name>" pattern, so the " : " split/last-part cleanup
    is applied to whichever source is used.
    """
    node = soup.find(id="title-text")
    if node is not None:
        text = node.get_text(" ", strip=True)
    else:
        title_tag = soup.find("title")
        text = title_tag.get_text(strip=True) if title_tag else ""
    text = " ".join(text.split())
    if " : " in text:
        text = text.split(" : ")[-1].strip()
    return text


def clean_content(content) -> None:
    """Mutate the main-content tag in place per the cleanup steps."""
    # a. remove entirely
    for selector in REMOVE_SELECTORS:
        for tag in content.select(selector):
            tag.decompose()

    # b. unwrap (keep children, drop wrapper)
    for selector in UNWRAP_SELECTORS:
        for tag in content.select(selector):
            tag.unwrap()

    # c. flatten layout wrappers
    for selector in LAYOUT_UNWRAP_SELECTORS:
        for tag in content.select(selector):
            tag.unwrap()

    # d. remove orphaned "Contents:" paragraphs (preceded the removed toc-macro)
    for p in content.find_all("p"):
        if p.get_text(strip=True) in ("Contents:", "Contents"):
            p.decompose()

    # e. strip img attributes except src/alt
    for img in content.find_all("img"):
        img.attrs = {k: v for k, v in img.attrs.items() if k in IMG_KEEP_ATTRS}

    # f. unwrap remaining div/span wrappers (loop: unwrapping can expose new
    # nested div/span elements)
    while True:
        wrappers = content.find_all(["div", "span"])
        if not wrappers:
            break
        for w in wrappers:
            w.unwrap()

    # g. strip a tag attributes except href
    for a in content.find_all("a"):
        a.attrs = {k: v for k, v in a.attrs.items() if k == "href"}

    # h. sanitize id attributes: Confluence anchors contain characters that are
    # invalid in CSS selectors (parentheses, dots, ...) and make Quarto's HTML
    # post-processing silently drop content
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    for tag in content.find_all(id=True):
        tag["id"] = "".join(ch for ch in tag["id"] if ch in allowed)


def process_images(content, html_path: Path, slug: str) -> None:
    """Copy attachments/* images next to the qmd and rewrite their src."""
    src_dir = html_path.parent
    dest_dir = REPO_ROOT / "images" / slug
    for img in content.find_all("img"):
        src = img.get("src", "")
        if not src.startswith("attachments/"):
            continue
        filename = PurePosixPath(src).name
        source_file = (src_dir / src).resolve()
        if not source_file.is_file():
            print(f"WARNING: image file missing on disk, leaving tag as-is: {source_file}", file=sys.stderr)
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, dest_dir / filename)
        img["src"] = f"images/{slug}/{filename}"


def find_quarto() -> str | None:
    exe = shutil.which("quarto")
    if exe:
        return exe
    for candidate in (
        Path("C:/Program Files/Quarto/bin/quarto.exe"),
        Path(os.path.expandvars("%LOCALAPPDATA%/Programs/Quarto/bin/quarto.exe")),
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def process_attachment_links(content, html_path: Path, slug: str) -> None:
    """Copy non-image attachments (pdf, docx, ...) linked from the page and
    rewrite their hrefs, mirroring process_images."""
    src_dir = html_path.parent
    dest_dir = REPO_ROOT / "files" / slug
    for a in content.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("attachments/"):
            continue
        filename = PurePosixPath(href).name
        source_file = (src_dir / href).resolve()
        if not source_file.is_file():
            print(f"WARNING: linked attachment missing on disk, leaving href as-is: {source_file}", file=sys.stderr)
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, dest_dir / filename)
        a["href"] = f"files/{slug}/{filename}"


def run_pandoc(html_fragment: str) -> str:
    quarto_exe = find_quarto()
    if not quarto_exe:
        print(
            "ERROR: quarto not found on PATH or at the common install locations "
            "(C:/Program Files/Quarto/bin/quarto.exe, "
            "%LOCALAPPDATA%/Programs/Quarto/bin/quarto.exe).",
            file=sys.stderr,
        )
        sys.exit(2)

    cmd = [
        quarto_exe,
        "pandoc",
        "-f",
        "html+tex_math_single_backslash",
        "-t",
        "markdown+tex_math_dollars-simple_tables-multiline_tables",
        "--wrap=none",
    ]
    result = subprocess.run(cmd, input=html_fragment.encode("utf-8"), capture_output=True)
    if result.returncode != 0:
        print(result.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
        sys.exit(result.returncode)
    # pandoc emits CRLF on Windows; normalize so text-mode writes can't double
    # the CR (\r\r\n breaks Quarto's parser and silently drops blocks)
    return result.stdout.decode("utf-8").replace("\r\n", "\n")


def build_qmd(title: str, markdown: str) -> str:
    escaped_title = title.replace('"', '\\"')
    body = markdown.strip("\n")
    return f'---\ntitle: "{escaped_title}"\n---\n\n{body}\n'


def main() -> None:
    _fix_console_encoding()
    args = parse_args()
    slug: str = args.slug

    html_path = Path(args.export_html_path).resolve()
    if not html_path.is_file():
        print(f"ERROR: source HTML not found: {html_path}", file=sys.stderr)
        sys.exit(1)

    html_text = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html_text, "lxml")

    title = extract_title(soup)

    content = soup.find("div", id="main-content")
    if content is None:
        print(f'ERROR: no <div id="main-content"> found in {html_path}', file=sys.stderr)
        sys.exit(1)

    clean_content(content)
    process_images(content, html_path, slug)
    process_attachment_links(content, html_path, slug)

    cleaned_html = content.decode_contents()

    if args.debug_html:
        debug_dir = REPO_ROOT / "scripts" / "_debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = debug_dir / f"{slug}.cleaned.html"
        debug_path.write_text(cleaned_html, encoding="utf-8")
        print(f"Wrote debug HTML: {debug_path}")

    markdown = run_pandoc(cleaned_html)

    qmd_text = build_qmd(title, markdown)
    qmd_path = REPO_ROOT / f"{slug}.qmd"
    qmd_path.write_text(qmd_text, encoding="utf-8", newline="\n")
    print(f"Wrote {qmd_path}")


if __name__ == "__main__":
    main()
