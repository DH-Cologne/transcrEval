# transcrEval

Evaluating OCR of historical newspaper pages. The project compares a **new OCR**
run (produced with [Transkribus](https://www.transkribus.org/)) against an
**older OCR** of the same pages, both measured against a hand-made **gold
standard**. Source material is the Viennese *Arbeiter-Zeitung* (`aze`), 1919–1929.

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
data/
  ALTO XML/      Transkribus ALTO v4 output (coordinates; not used for scoring yet)
  newOCR/        new OCR, one line per recognised text line
  oldOCR/        older OCR of the same pages (leading metadata header is ignored)
  goldstandard/  hand-made reference (blank lines optional; not used for scoring)
code/
  align_prototype.py   two-stage line alignment + calibration diagnostics
  metrics.py           computes all metrics, writes results/metrics_<dir>.csv
  build_review.py      builds viz/review.html, a scrollable error-review viewer
results/         per-page metric tables (CSV)
viz/             metrics_preview.html (chart drafts); review.html (generated, gitignored)
```

File naming: `aze<YYYYMMDD>-<page>[_gold]_<initials>.txt`, where initials mark the
annotator (JH, AD, NR).

## Usage

```bash
python3 -m venv .venv && .venv/bin/pip install rapidfuzz
.venv/bin/python code/metrics.py newOCR                 # score data/newOCR against gold
.venv/bin/python code/metrics.py oldOCR                 # score data/oldOCR against gold
.venv/bin/python code/metrics.py newOCR --min-block 3   # e.g. require 3+ lines per block
```

Results are printed and written to `results/metrics_<dir>.csv`.

For hands-on error analysis, build the side-by-side viewer (Gold | old OCR | new
OCR, deviations colour-coded) and open it locally in a browser:

```bash
.venv/bin/python code/build_review.py           # writes viz/review.html
```

## Status

Work in progress. Currently 4 gold pages exist, 2 of them paired with both OCR
systems; the study targets 10 pages from several volumes. Block localisation is
derived from the alignment and needs no markup in the gold files; blank lines, if
present, are carried through only as an informational `gold_blocks_hint` column.

## License

MIT — © 2026 Institut für Digital Humanities, Universität zu Köln.
