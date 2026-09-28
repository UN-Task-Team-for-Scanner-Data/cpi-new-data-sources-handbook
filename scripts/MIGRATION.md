# Handbook migration: Confluence → Quarto

Status and coordination notes for migrating the **Handbook on utilising new data
sources in the production of consumer price statistics** from the UN Statistics
Confluence wiki (space `GWGSD`) to this Quarto site, hosted on GitHub Pages under
`UN-Task-Team-for-Scanner-Data`.

## Current state (2026-08-03, end of day)

**The full handbook is converted**: all 72 pages from the export's `index.html` tree,
with the sidebar mirroring the wiki hierarchy, cross-page links rewritten to local
targets, and linked attachments (PDF/docx) copied under `files/`. The whole site
passes `scripts/verify_site.py` with zero defects: every page's rendered formula and
image counts match the Confluence source exactly, every internal link and image
resolves, and no page has line-ending corruption. What remains is human review
(reading the pages), org repo access, and deployment — see the issue list below.

Batch tooling:

```
uv run scripts/convert_all.py --plan   # show the page tree, slugs, math/image stats
uv run scripts/convert_all.py --run    # convert everything + rewrite links + sidebar YAML
uv run scripts/verify_site.py          # after quarto render: parity + link check
```

## Deployment

The site is live at
<https://un-task-team-for-scanner-data.github.io/cpi-new-data-sources-handbook/>

`.github/workflows/publish.yml` renders the site and publishes it to the `gh-pages`
branch on every push to `main` (quarto-dev/quarto-actions).

### One-time bootstrap (done 2026-09-10)

The `gh-pages` branch must exist before the workflow or
`quarto publish gh-pages --no-prompt` will run. Quarto creates the branch only when
it can prompt for confirmation, so a non-interactive session must create it first.
The error message is circular. It tells you to run the command you just ran.

```
git checkout --orphan gh-pages
git reset --hard
git commit --allow-empty -m "Initialise gh-pages branch for Quarto publishing"
git push origin gh-pages
git checkout main
quarto publish gh-pages --no-prompt --no-browser
```

Run this from a short local path, for example `C:\qp`. Windows applies a 260
character path limit. Quarto builds a publish worktree under `.quarto/`, and the long
image filenames in this project pass the limit under a deep directory. Also set
`git config core.longpaths true`.

Pushing `gh-pages` enabled GitHub Pages automatically. No Pages setting was needed.
Quarto writes `.nojekyll` to the branch, so Jekyll does not process the site.

`quarto publish gh-pages` writes no `_publish.yml`. That file records a site ID for
the Quarto Pub and Netlify targets. The `gh-pages` target holds its state in the
branch.

### Workflow permissions

Settings → Actions → General → Workflow permissions must be **Read and write
permissions**. The default is read-only. It caps the workflow token, so the action
cannot push to `gh-pages`.

### Subpath

The site serves from a subpath, not a domain root. `site-url` in `_quarto.yml` must
match the published URL exactly, or search and the sitemap point at the wrong host
while every page still renders correctly.

## Pilot scope (how fidelity was established)

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
3. **Content review, per section** — conversion is done; one issue per top-level
   handbook section for a human read-through against the wiki original (layout
   oddities, footnote-ish text, anything the automated parity checks can't judge).
4. **External-image dependency** — one page (Method 4: ML classification) hot-links
   an image from statcan.gc.ca, as the wiki did; decide whether to localize it.
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
- Remote: `https://LAE-ONS-GOV-UK@github.com/UN-Task-Team-for-Scanner-Data/cpi-new-data-sources-handbook.git`
  — the explicit username pins Windows credential selection to the ONS account.
