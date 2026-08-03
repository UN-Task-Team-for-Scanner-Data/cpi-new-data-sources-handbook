# Handbook migration: Confluence → Quarto

Status and coordination notes for migrating the **Handbook on utilising new data
sources in the production of consumer price statistics** from the UN Statistics
Confluence wiki (space `GWGSD`) to this Quarto site, hosted on GitHub Pages under
`UN-Task-Team-for-Scanner-Data`.

## Pilot scope (current state)

As agreed by email (Jul–Aug 2026): convert **one or two example pages** that are
heavy in both **LaTeX and images**, verify they render faithfully, then scale to
the full set (~73 pages). Pilot pages, chosen after scanning the whole export
(7 pages contain LaTeX; these two also carry the most images):

| Page | Source file | Why |
|---|---|---|
| Extension methods | `Extension-methods_240910490.html` | 12 images + splicing/extension formulas |
| How to evaluate classification methods | `How-to-evaluate-classification-methods_337281196.html` | 7 images + accuracy/precision/recall formulas |

Useful facts about the Confluence export discovered during scanning:

- Formulas are exported as **literal LaTeX text** (`\( ... \)` / `\[ ... \]` inside
  `<span>`s) — not images — so math survives conversion losslessly.
- Images live at `attachments/<pageid>/<attachmentid>.<ext>` and are referenced from
  `span.confluence-embedded-file-wrapper` containers.
- Page hierarchy is recoverable from the export's `index.html` nested lists and each
  page's breadcrumb trail.
- Confluence chrome to strip per page: `div.toc-macro`, breadcrumbs, page metadata,
  `span.inline-comment-marker` (unresolved review comments!), `columnLayout`/`cell`
  layout wrappers.

## How to convert a page

```
uv run scripts/convert_page.py <path-to-export-page.html> <slug>
```

Writes `<slug>.qmd` at the repo root and copies referenced images to
`images/<slug>/`. Then add the page to the `sidebar` in `_quarto.yml`.

## Local preview

```
.\scripts\serve.ps1           # live-reload dev server (quarto preview)
.\scripts\serve.ps1 -Static   # render + serve _site/ exactly as GitHub Pages would
```

## Conversion pitfalls found during the pilot (already handled in `convert_page.py`)

- **CRLF doubling**: pandoc emits CRLF on Windows; writing its stdout in text mode
  doubles the CR (`\r\r\n`), which makes Quarto silently drop whole blocks of a page
  (images, sections) with no warning. The converter normalizes newlines and writes LF.
- **Confluence anchor IDs**: heading ids like `{#...method(WISP)}` contain characters
  invalid in CSS selectors; the converter strips them to `[A-Za-z0-9_-]`.
- **Layout wrappers**: all residual `<div>`/`<span>` wrappers are unwrapped so pandoc
  emits plain markdown; Confluence layout markup carries no meaning in Quarto.
- **Verify with clean state**: always delete `.quarto/` before a build you intend to
  judge (serve.ps1 does this automatically). If the repo lives in a Google-Drive-synced
  folder, be aware Drive can serve stale file content to build tools; when output looks
  impossible, re-render from a fresh local copy.

## Styling

Matches the UNTT reproducibility-project site: Bootstrap themes `flatly` (light) /
`cyborg` (dark), navbar layout and footer conventions copied from its `_quarto.yml`.
Their `styles.css` is currently an empty placeholder; ours mirrors that. Colour/logo
polish against Helen's `UNTT slide template.potx` is a later step.

## Proposed GitHub issues (to file once the org repo exists)

1. **Pilot sign-off** — review the two pilot pages side-by-side against Confluence;
   agree conversion fidelity is acceptable.
2. **Site chrome** — logo/favicon, footer, announcement banner, repo-url/repo-actions
   once the repo URL is known; styling pass vs the UNTT slide template.
3. **Bulk conversion, per section** — one issue per top-level handbook section
   (Initial considerations; Data selection & acquisition; Web scraping; Scanner data;
   Preparation of data; Classification; Data filtering; Index methods; Aggregation; …),
   using `scripts/convert_page.py`; nav order from export `index.html`.
4. **Internal link rewriting** — converted pages still contain relative links to
   Confluence export filenames (`Page-Name_<id>.html`); rewrite to `.qmd` slugs once
   the full page set exists (extend `convert_page.py` with a filename→slug map).
5. **References → BibTeX** — collect citations from handbook pages into
   `references.bib`; switch pages to Quarto citation syntax.
6. **Unresolved Confluence comments** — the export carries inline review-comment
   markers; decide whether any embedded review feedback needs carrying over before
   deletion.
7. **Deployment** — GitHub Actions workflow (`quarto-dev/quarto-actions`): render on
   push to `main`, publish to GitHub Pages.
8. **Zenodo/DOI** — archive releases to Zenodo for a citable DOI (as on the
   reproducibility project site).

## Constraints

- Commits to this repo are authored solely by Lewis (`LAE-ONS-GOV-UK`).
- Target remote (once created): `https://LAE-ONS-GOV-UK@github.com/UN-Task-Team-for-Scanner-Data/<repo>.git`
  — the explicit username pins Windows credential selection to the ONS account.
