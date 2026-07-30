# transcrEval

Evaluating OCR of historical newspaper pages. The project compares a **new OCR**
run (produced with [Transkribus](https://www.transkribus.org/)) against an **older
OCR** of the same pages, both measured against a hand-made **gold standard**.
Source material is the Viennese *Arbeiter-Zeitung* (`aze`), 1919–1934.

The pipeline is deliberately project-independent: everything specific to a study
lives in `config.json`, the code in `code/` makes no assumptions about language,
script or source. A different OCR-evaluation project is a new config plus data.

## The problem this solves

Comparing gold standard and OCR as one continuous text — what standard tools do —
conflates two very different things. If a recognition engine outputs lines or
blocks in a different reading order, every displaced line counts as entirely
wrong, and the resulting error rate says more about layout analysis than about
character recognition. On our material the median CER of the new OCR measured
this way is 12.3 %; after separating the two error classes it is 1.6 %.

transcrEval therefore aligns lines by **content, not position** before scoring,
and reports misplacement separately:

| Metric | Meaning |
|---|---|
| **CER** | Character Error Rate (Unicode grapheme clusters) |
| **WER** | Word Error Rate (UAX #29 segmentation, punctuation excluded) |
| **LER** | Line Error Rate — individually misplaced lines |
| **loc_events** | Block relocation events — runs of consecutive lines moved together |

A **block** is defined by the displacement itself: a run of consecutive gold lines
that moved together, in order. A run of at least `min_block` lines (default 2)
counts as one relocation event, so a poem moving as a whole is one error, not one
per stanza. Shorter runs and isolated single-line shifts stay in the LER.

CER and WER follow the definitions used by
[dinglehopper](https://github.com/qurator-spk/dinglehopper) (OCR-D) and were
cross-checked against it: on a page without reading-order deviations the values
agree to 0.06 pp, the remainder being dinglehopper counting line breaks as
reference characters.

## Repository layout

```
config.json      project configuration — all project-specific settings live here
data/
  README.md                  provenance and rights of the data — read before reusing
  ANNO_aze<date>-<page>/     one folder per newspaper page, containing:
    <doc>_ocr_alt.txt          older OCR, cut from the issue (metadata header stripped)
    <doc>_ocr_neu.txt          new OCR, extracted from the page's ALTO in document order
    <doc>_ocr_neusort.txt      same, but lines re-sorted by coordinates (see below)
    <doc>.xml                  the page's Transkribus ALTO v4
    <doc>.jpg                  the page scan
    <doc>_gold_<initials>.txt  hand-made reference
code/
  config.py            loads config.json; normalization, tokenization, file discovery
  align.py             two-stage line alignment, rescue, block-run detection
  metrics.py           all metrics for all pages → results/metrics.csv
  resort_alto.py       preprocessing: rebuild OCR text with coordinate-sorted lines
  build_review.py      → viz/review.html, scrollable error review
  build_split.py       → viz/review_split.html, text next to the page scan
  error_analysis.py    character-level error typology → results/errors.csv
  gold_audit.py        candidate errors *in the gold standard* (never edits)
  export_line_anomalies.py  misplaced lines with ALTO line IDs → results/
analysis/          R evaluation: boxplots and statistics (see analysis/README.md)
results/           metric tables and diagnostic exports (CSV)
viz/               generated HTML viewers
```

`<doc>` is the document key, e.g. `aze19291229-13`.

## Usage

```bash
python3 -m venv .venv && .venv/bin/pip install rapidfuzz uniseg
```

Regenerate the coordinate-sorted OCR text (only needed when the ALTO files change):

```bash
.venv/bin/python code/resort_alto.py
```

Score every gold page against every configured OCR system:

```bash
.venv/bin/python code/metrics.py                 # → results/metrics.csv
.venv/bin/python code/metrics.py --min-block 3   # require 3+ lines per relocated block
.venv/bin/python code/metrics.py --config other.json
```

One run writes a single `results/metrics.csv` in wide format: one row per document,
with each metric's per-system columns (`cer_norm_alt`, `cer_norm_neu`, …) side by
side. Pages without a gold file are skipped.

Build the viewers and the diagnostic exports:

```bash
.venv/bin/python code/build_review.py         # gold + all systems, line-synchronous
.venv/bin/python code/build_split.py          # new OCR next to the scan, ALTO blocks overlaid
.venv/bin/python code/error_analysis.py       # error typology
.venv/bin/python code/gold_audit.py --md analysis/gold_candidates.md
.venv/bin/python code/export_line_anomalies.py --system neu
Rscript analysis/analyze.R                    # boxplots + statistics (needs ggplot2)
```

The viewers are self-contained HTML; `review_split.html` references the page JPGs
by relative path, so keep it in `viz/` alongside `data/`.

## Line re-sorting (preprocessing)

The order of `TextLine` elements within a `TextBlock` does not reliably follow
their vertical position on the page. `resort_alto.py` rebuilds the OCR text with
the block order unchanged and the lines within each block sorted by `VPOS` — no
layout analysis of our own, just a correction against the coordinates the ALTO
already carries. Across ten pages this affects 9.5 % of all lines and reduces
individually misplaced lines from 113 to 9.

Because it changes only the order and not a single character, the result is
carried as a separate system (`neusort`) rather than replacing the delivered text,
so both can be compared. Block order is untouched and still requires the alignment.

## Configuration (`config.json`)

JSON, so R (`jsonlite`) can read it too; the `_about` field replaces comments.
Paths are relative to the config file. Data is organized as one folder per page.

| Key | Purpose |
|---|---|
| `data_dir`, `results_dir`, `viz_dir` | folders |
| `page_glob` | glob for the per-page folders under `data_dir` |
| `doc_key` | regex whose group 1 is the document key, taken from the folder name |
| `gold.file` | filename pattern of the gold file inside a page folder (`{doc}` substituted) |
| `systems[]` | one per OCR system: `name` (→ CSV suffix), `label`, `file` pattern, optional `source` (provenance shown in viewers) and `strip_header` regex |
| `normalize` | `unicode` form, `collapse_whitespace`, and a `replace` table applied before alignment |
| `word_tokenizer` | WER convention: `punct_ignore` (default, matches dinglehopper), `punct_separate`, `whitespace` |
| `display_tokenizer` | tokenization for *highlighting* (default `punct_separate`), deliberately separate so punctuation errors stay visible although they do not count towards the WER |
| `align` | `gap`, `split_penalty`, `match_cutoff`, `rescue_cutoff`, `min_block` |
| `labels` | optional map document key → human-readable label |

Add or remove `systems` freely — metrics, viewers and the R analysis adapt to any
number of them.

## Transcription conventions

The gold standard follows level 2 of the
[OCR-D ground truth guidelines](https://ocr-d.de/de/gt-guidelines/trans/): historical
spellings such as long ſ are preserved, consonantal ligatures are resolved. The
normalization applied before scoring corresponds to level 1 (ſ → s, ligatures split,
hyphenation marks unified to the hyphen-minus) and additionally folds the soft
hyphen used by the older OCR. All rates are reported normalized; raw values are
available in the CSV as `cer_raw` / `wer_raw`.

## Provenance

Old OCR: ABBYY Recognition Server 4.0 (2015) — the text files carry no software
metadata; the bracket header is only an export timestamp. New OCR: Transkribus /
READ COOP, engine `TrHtr` — recorded per page in each ALTO's `Processing` block,
but the exact HTR model is not stored there. The engine version is not uniform:
8 pages `2.44.0`, 2 pages `2.48.0`. The split viewer shows engine and date per page.

## Status

Ten gold pages, all paired with both OCR systems. Results feed a poster submission
for DHd 2027; applying the same procedure to the *Neue Freie Presse* is in
preparation.

## Data, provenance and rights

The repository ships the ten evaluated pages so the results can be reproduced from
a single checkout. The files in `data/` do not share one origin, and therefore not
one set of terms — [`data/README.md`](data/README.md) documents this per file type.
In short:

| What | Origin | Terms |
|---|---|---|
| `code/`, `analysis/`, `viz/`, `config.json` | this project | MIT |
| gold standard, Transkribus ALTO and the text derived from it | this project | CC BY 4.0 |
| page scans (`*.jpg`), older OCR (`*_ocr_alt.txt`) | provided by the ÖNB via [ANNO](https://anno.onb.ac.at/) | no rights claimed here; the ÖNB records the status as [Copyright Not Evaluated](https://rightsstatements.org/vocab/CNE/1.0/) |

The gold standard and the new OCR are published here for the first time and have no
other citable location. The ÖNB material is redistributed for convenience only;
`data/README.md` links every page to its source at ANNO.

## Citation

> Hermes, Jürgen; Dick, Anna-Katharina; Dorfbauer, Sonja; Reiter, Nils; Steindl,
> Christoph (2026): *transcrEval: Line-Aware OCR Evaluation for Historical
> Newspapers*. Universität zu Köln. https://github.com/DH-Cologne/transcrEval

Machine-readable metadata is in [`CITATION.cff`](CITATION.cff).

## License

The **code** — everything outside `data/` — is MIT, © 2026 Institut für Digital
Humanities, Universität zu Köln; see [`LICENSE`](LICENSE). The MIT licence does not
extend to `data/`, which is covered by the terms in the table above.
