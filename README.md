# transcrEval

Evaluating OCR of historical newspaper pages. The project compares a **new OCR**
run (produced with [Transkribus](https://www.transkribus.org/)) against an
**older OCR** of the same pages, both measured against a hand-made **gold
standard**. Source material is the Viennese *Arbeiter-Zeitung* (`aze`), 1919–1932.

## What it measures

Each OCR text is scored per page against the gold standard on four metrics:

| Metric | Meaning |
|---|---|
| **CER** | Character Error Rate — reported both raw and normalized |
| **WER** | Word Error Rate — reported both raw and normalized |
| **RLER** | Row Localisation Error Rate — individually misplaced lines |
| **loc_events** | Block relocation events — runs of consecutive lines moved together |

The key idea: Transkribus sometimes swaps the reading order of lines or whole
blocks. A two-stage line alignment matches lines by **content, not position**, so
a reordered line is not counted as all-characters-wrong. Its displacement is
reported separately as a localisation error instead. A **block** is defined by the
displacement itself — a run of consecutive gold lines that moved together, in
order — independent of any layout markup. A run of at least `MIN_BLOCK_LINES`
(default 2, configurable via `--min-block`) counts as **one** relocation event, so
a poem that moves as a whole is one error, not one per stanza. Shorter runs and
isolated single-line shifts stay in the RLER.

Normalization (long ſ → s, ligatures, hyphen variants ⸗/¬/=) is applied before
alignment; CER/WER are then reported both raw and normalized, so the contrast
between transcription conventions and genuine recognition errors stays visible.

## Repository layout

```
config.json      project configuration — all project-specific settings live here
data/
  ALTO XML/      Transkribus ALTO v4 output (coordinates; not used for scoring yet)
  newOCR/        new OCR, one line per recognised text line
  oldOCR/        older OCR of the same pages (leading metadata header is stripped)
  goldstandard/  hand-made reference (blank lines optional; not used for scoring)
code/
  config.py        loads config.json (paths, systems, normalization, thresholds)
  align.py         two-stage line alignment, rescue, block-run detection + diagnostics
  metrics.py       computes all metrics for all pages, writes <results>/metrics.csv
  build_review.py  builds <viz>/review.html, a scrollable error-review viewer
results/         metric table (CSV)
viz/             metrics_preview.html (chart drafts); review.html (generated, gitignored)
```

The `code/` modules are generic; everything specific to this study is in
`config.json`. A different OCR-evaluation project = a new `config.json` (+ data),
selected with `--config <path>`.

## Configuration (`config.json`)

JSON (so R via `jsonlite` can read it too; the `_about` field replaces comments).
Paths are relative to the config file. Key sections:

| Key | Purpose |
|---|---|
| `data_dir`, `results_dir`, `viz_dir` | folders (relative to config) |
| `gold.dir`, `gold.glob`, `gold.doc_key` | gold folder, file glob, and a regex whose group 1 is the document key |
| `systems[]` | one entry per OCR system: `name` (→ CSV suffix), `label` (viewer header), `dir`, `glob` (`{doc}` is substituted), optional `strip_header` regex for lines to drop |
| `normalize` | `unicode` form, `collapse_whitespace`, and a `replace` table of character substitutions applied before alignment |
| `align` | `gap`, `split_penalty`, `match_cutoff`, `rescue_cutoff`, `min_block` |
| `labels` | optional map document key → human-readable label |

Add or remove `systems` freely — metrics and viewer adapt to any number of them.

## Usage

```bash
python3 -m venv .venv && .venv/bin/pip install rapidfuzz
.venv/bin/python code/metrics.py                       # score every gold page vs. all OCR systems
.venv/bin/python code/metrics.py --min-block 3         # require 3+ lines per relocated block
.venv/bin/python code/metrics.py --config other.json   # run a different project
```

One run evaluates each gold page against every configured OCR system and writes a
single `results/metrics.csv` in wide format: one row per document, with each
metric's per-system columns (e.g. `cer_norm_alt`, `cer_norm_neu`) side by side.

For hands-on error analysis, build the side-by-side viewer (Gold plus one column
per OCR system, deviations colour-coded, columns collapsible) and open it locally:

```bash
.venv/bin/python code/build_review.py           # writes viz/review.html
```

## Status

Work in progress. Currently 6 gold pages exist, all paired with both OCR systems;
the study targets 10 pages from several volumes. Block localisation is derived from
the alignment and needs no markup in the gold files; blank lines, if present, are
carried through only as an informational `gold_blocks_hint` column.

## License

MIT — © 2026 Institut für Digital Humanities, Universität zu Köln.
