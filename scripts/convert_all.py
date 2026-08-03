# /// script
# requires-python = ">=3.12"
# dependencies = ["beautifulsoup4", "lxml"]
# ///
"""Batch-convert the whole Confluence export to Quarto pages.

  uv run scripts/convert_all.py --plan   # show the page tree, slugs and content stats; no writes
  uv run scripts/convert_all.py --run    # convert every page, rewrite internal links,
                                         # write scripts/_generated_sidebar.yml

Reads the export's index.html "Available Pages" tree for hierarchy and order,
drives scripts/convert_page.py per page, then post-processes all *.qmd files so
links between handbook pages point at the local .qmd targets.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parent.parent
# The Confluence export is not committed; default assumes it sits next to the
# repo, override with HANDBOOK_EXPORT_DIR when running from a copied tree.
EXPORT_DIR = Path(
    os.environ.get(
        "HANDBOOK_EXPORT_DIR",
        REPO_ROOT.parent
        / "project_init_docs"
        / "Confluence-space-export-171411-2.html"
        / "GWGSD",
    )
)
ROOT_PAGE_PREFIX = "Handbook-on-utilising-new-data-sources"
SLUG_OVERRIDES = {ROOT_PAGE_PREFIX: "introduction"}
ID_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def _fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class Node:
    href: str
    title: str
    depth: int
    slug: str = ""
    children: list["Node"] = field(default_factory=list)


def parse_tree() -> Node:
    soup = BeautifulSoup((EXPORT_DIR / "index.html").read_text(encoding="utf-8"), "lxml")
    root_a = next(
        a for a in soup.find_all("a", href=True) if a["href"].startswith(ROOT_PAGE_PREFIX)
    )
    root_li = root_a.find_parent("li")

    def walk(li, depth: int) -> Node:
        a = li.find("a", href=True)
        node = Node(href=a["href"], title=a.get_text(" ", strip=True), depth=depth)
        for sub_ul in li.find_all("ul", recursive=False):
            for sub_li in sub_ul.find_all("li", recursive=False):
                node.children.append(walk(sub_li, depth + 1))
        return node

    return walk(root_li, 0)


def flatten(node: Node) -> list[Node]:
    out = [node]
    for child in node.children:
        out.extend(flatten(child))
    return out


def slug_for(node: Node, taken: set[str]) -> str:
    stem = re.sub(r"_\d+\.html$", "", node.href)
    for prefix, override in SLUG_OVERRIDES.items():
        if node.href.startswith(prefix):
            stem = override
    if not stem or stem.isdigit() or stem.endswith(".html"):
        stem = node.title
    slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", stem.lower())).strip("-")
    base, n = slug, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    taken.add(slug)
    return slug


def assign_slugs(root: Node) -> dict[str, str]:
    taken: set[str] = set()
    mapping: dict[str, str] = {}
    for node in flatten(root):
        node.slug = slug_for(node, taken)
        mapping[node.href] = node.slug
    return mapping


def page_stats(node: Node) -> tuple[int, int]:
    raw = (EXPORT_DIR / node.href).read_bytes()
    main = raw.find(b'id="main-content"')
    end = raw.find(b"Attachments:")
    body = raw[main : end if end > main else len(raw)]
    return len(re.findall(rb"\\\(|\\\[", body)), len(re.findall(rb"<img ", body))


def sidebar_yaml(root: Node) -> str:
    lines = ["      - index.qmd", f"      - {root.slug}.qmd", '      - "---"']

    def emit(node: Node, indent: str) -> None:
        if node.children:
            lines.append(f'{indent}- section: "{node.title}"')
            lines.append(f"{indent}  href: {node.slug}.qmd")
            lines.append(f"{indent}  contents:")
            for child in node.children:
                emit(child, indent + "    ")
        else:
            lines.append(f"{indent}- {node.slug}.qmd")

    for top in root.children:
        emit(top, "      ")
    return "\n".join(lines) + "\n"


def rewrite_links(mapping: dict[str, str]) -> None:
    href_re = re.compile(r"([(\"'])([A-Za-z0-9._%-]+\.html)(#[^)\"']*)?([)\"'])")

    def fix(match: re.Match) -> str:
        open_c, fname, frag, close_c = match.groups()
        slug = mapping.get(fname)
        if slug is None:
            unknown.add(fname)
            return match.group(0)
        new_frag = ""
        if frag:
            cleaned = "".join(ch for ch in frag[1:] if ch in ID_ALLOWED)
            new_frag = f"#{cleaned}" if cleaned else ""
        return f"{open_c}{slug}.qmd{new_frag}{close_c}"

    unknown: set[str] = set()
    for qmd in sorted(REPO_ROOT.glob("*.qmd")):
        text = qmd.read_text(encoding="utf-8")
        new_text = href_re.sub(fix, text)
        if new_text != text:
            qmd.write_text(new_text, encoding="utf-8", newline="\n")
    if unknown:
        print(f"NOTE: {len(unknown)} linked .html files not in the page tree "
              f"(left untouched): {sorted(unknown)[:10]}{' ...' if len(unknown) > 10 else ''}")


def main() -> None:
    _fix_console_encoding()
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()

    root = parse_tree()
    mapping = assign_slugs(root)
    pages = flatten(root)
    print(f"{len(pages)} pages in tree")

    if args.plan:
        for node in pages:
            math, imgs = page_stats(node)
            marks = (f" math={math}" if math else "") + (f" imgs={imgs}" if imgs else "")
            print(f"{'  ' * node.depth}{node.title}  ->  {node.slug}{marks}")
        return

    failures: list[str] = []
    for i, node in enumerate(pages, 1):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "convert_page.py"),
             str(EXPORT_DIR / node.href), node.slug],
            capture_output=True, text=True,
        )
        status = "ok" if result.returncode == 0 else f"FAIL rc={result.returncode}"
        print(f"[{i}/{len(pages)}] {node.slug}: {status}")
        if result.returncode != 0:
            failures.append(node.slug)
            print(result.stderr.strip()[-500:])
        elif result.stderr.strip():
            print("   " + result.stderr.strip().replace("\n", "\n   ")[:400])

    rewrite_links(mapping)
    out = REPO_ROOT / "scripts" / "_generated_sidebar.yml"
    out.write_text(sidebar_yaml(root), encoding="utf-8", newline="\n")
    print(f"Sidebar YAML written to {out}")
    if failures:
        print(f"FAILURES: {failures}")
        sys.exit(1)


if __name__ == "__main__":
    main()
