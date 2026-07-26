# transcrEval

Evaluating OCR of historical newspaper pages. The project compares a **new OCR**
run (produced with [Transkribus](https://www.transkribus.org/)) against an
**older OCR** of the same pages, both measured against a hand-made **gold
standard**. Source material is the Viennese *Arbeiter-Zeitung* (`aze`), 1919–1932.

**OCR provenance.** Old OCR: ABBYY Recognition Server 4.0 (2015) — the text files
carry no software metadata; the bracket header is only an export timestamp. New
OCR: Transkribus / READ COOP, engine `TrHtr` — recorded per page in each ALTO's
`Processing` block, but the exact HTR model is **not** stored there. The engine
version is not uniform: 8 pages `2.44.0`, 2 pages (17.12.1932, 02.12.1934) `2.48.0`.
The split viewer shows the precise engine + date for each page.

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
  ANNO_aze<date>-<page>/   one folder per newspaper page, containing:
    <doc>_ocr_alt.txt        older OCR, one page cut from the issue (metadata header stripped)
    <doc>_ocr_neu.txt        new OCR, extracted from the page's ALTO
    <doc>.xml                the page's Transkribus ALTO v4
    <doc>.jpg                the page scan
    <doc>_gold_<initials>.txt  hand-made reference (present for annotated pages)
code/
  config.py        loads config.json (paths, page/systems discovery, normalization, thresholds)
  align.py         two-stage line alignment, rescue, block-run detection + diagnostics
  metrics.py       computes all metrics for all pages, writes <results>/metrics.csv
  build_review.py  builds <viz>/review.html, a scrollable error-review viewer
  build_split.py   builds <viz>/review_split.html, text next to the page scan (ALTO blocks)
  gold_audit.py    lists candidate errors *in the gold standard* (never edits)
  error_analysis.py  character-level error typology → <results>/errors.csv
results/         metric table (CSV)
viz/             metrics_preview.html (chart drafts); review*.html (generated, committed)
```

`<doc>` is the document key, e.g. `aze19291229-13`. The `code/` modules are generic;
everything specific to this study is in `config.json`. A different OCR-evaluation
project = a new `config.json` (+ data), selected with `--config <path>`.

## Configuration (`config.json`)

JSON (so R via `jsonlite` can read it too; the `_about` field replaces comments).
Paths are relative to the config file. Data is organized as one folder per page.

| Key | Purpose |
|---|---|
| `data_dir`, `results_dir`, `viz_dir` | folders (relative to config) |
| `page_glob` | glob for the per-page folders under `data_dir` (e.g. `ANNO_aze*`) |
| `doc_key` | regex whose group 1 is the document key, taken from the folder name |
| `gold.file` | filename pattern of the gold file inside a page folder (`{doc}` substituted) |
| `systems[]` | one per OCR system: `name` (→ CSV suffix), `label` (viewer header), `file` (filename pattern, `{doc}`/`{name}` substituted), optional `source` (provenance shown in viewers) and `strip_header` regex |
| `normalize` | `unicode` form, `collapse_whitespace`, and a `replace` table of character substitutions applied before alignment |
| `word_tokenizer` | how the WER counts words: `punct_separate` (default, punctuation is its own token — OCR-D practice), `whitespace` (punctuation glued to the word, strictest), `punct_ignore` (punctuation excluded — ISRI practice). The viewers highlight with the same tokenization, so a stray comma marks only the comma. |
| `align` | `gap`, `split_penalty`, `match_cutoff`, `rescue_cutoff`, `min_block` |
| `labels` | optional map document key → human-readable label |

Pages without a gold file are skipped. Add or remove `systems` freely — metrics and
viewer adapt to any number of them.

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

A second, split-screen viewer shows the new OCR next to the page scan, with the
ALTO text blocks overlaid, numbered in reading order and highlighting relocated
blocks (text line ⇄ image block are linked both ways):

```bash
.venv/bin/python code/build_split.py            # writes viz/review_split.html
```

`review_split.html` references the page JPGs by relative path, so keep it in `viz/`
alongside `data/`.

To characterise *what kind* of errors a system makes (operation, character class,
position in line / word / page, confusion pairs), run the error typology. It writes
one row per character error to `results/errors.csv` for further analysis in R:

```bash
.venv/bin/python code/error_analysis.py               # all systems
.venv/bin/python code/error_analysis.py --system neu  # one system only
```

To sanity-check the gold standard itself, `gold_audit.py` reports places where all
OCR systems agree on a word but the gold differs — a strong hint that the gold is
the outlier. It only reports, never edits:

```bash
.venv/bin/python code/gold_audit.py                            # to the console
.venv/bin/python code/gold_audit.py --md analysis/gold_candidates.md
```

Caveat: where both engines make the *same* mistake (classically reading long ſ as
"f"), the gold is right and the hit is a false alarm.

For the statistical evaluation, an R scaffold in `analysis/` reads `metrics.csv`
and produces comparative boxplots (old vs. new OCR); see `analysis/README.md`:

```bash
Rscript analysis/analyze.R       # needs ggplot2 (+ scales)
```

## Status

Work in progress. Currently 6 gold pages exist, all paired with both OCR systems;
the study targets 10 pages from several volumes. Block localisation is derived from
the alignment and needs no markup in the gold files; blank lines, if present, are
carried through only as an informational `gold_blocks_hint` column.

## License

MIT — © 2026 Institut für Digital Humanities, Universität zu Köln.
