#!/usr/bin/env python3
"""Metriken auf Basis des zweistufigen Zeilen-Alignments (siehe align_prototype).

CER  = Zeichen-Editierdistanz / Goldzeichen   (kontrastiv: roh und normalisiert)
WER  = Wort-Editierdistanz   / Goldwörter     (kontrastiv: roh und normalisiert)
RLER = individuell verrutschte Goldzeilen / Goldzeilen (Rate)
BLER = Verschiebungs-Ereignisse je Seite (loc_events, absolute Zahl, KEINE Rate)

Dislozierte Zeilen zählen in CER/WER nur mit ihren Inhaltsfehlern, nicht als
Totalausfall. Goldzeilen ohne Partner zählen als komplett ausgelassen,
OCR-Zeilen ohne Partner als komplett eingefügt.

Lokalisierung ist VERSCHIEBUNGSBASIERT und unabhängig von Leerzeilen:
- Ein Block ist ein maximaler Lauf konsekutiver Goldzeilen, die gemeinsam und in
  gleicher Reihenfolge ins OCR gewandert sind (benachbarte Gold-Indizes, monoton
  steigende OCR-Position). Läufe ab MIN_BLOCK_LINES Zeilen sind je EIN
  Verschiebungs-Ereignis (loc_event) -> ein Gedicht, das geschlossen umzieht,
  ist ein Fehler, nicht N.
- Kürzere Läufe / einzeln verrutschte Zeilen bleiben RLER.

Die Leerzeilen-Blöcke im Gold werden nur noch als Zusatzinfo (gold_blocks_hint)
mitgeführt, nicht mehr zur Metrik-Berechnung genutzt.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from rapidfuzz.distance import Levenshtein

from align_prototype import RESCUE_CUTOFF, align, dist, is_content, normalize

DATA = Path(__file__).resolve().parent.parent / "data"
RESULTS = Path(__file__).resolve().parent.parent / "results"

# Mindestlänge (Zeilen) eines gemeinsam verschobenen Laufs, damit er als
# Blockverschiebung (loc_event) zählt statt als einzelne Zeilenfehler (RLER).
# Konfigurierbar per CLI: python code/metrics.py <ocrdir> --min-block N
MIN_BLOCK_LINES = 2


def load(path: Path) -> tuple[list[str], list[str], list[int]]:
    """Nicht-leere Zeilen als (roh, normalisiert, block_id), Reihenfolge erhalten.

    block_id inkrementiert an jeder echten Leerzeile (Blockgrenze im Gold).
    OCR-Dateien haben keine Leerzeilen -> alle Zeilen in Block 0.
    """
    raw: list[str] = []
    blocks: list[int] = []
    blk = 0
    prev_blank = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if is_content(line):
            if prev_blank and raw:
                blk += 1
            raw.append(line)
            blocks.append(blk)
            prev_blank = False
        elif not line.strip():
            prev_blank = True
        # Metadaten-Header (nur altes OCR) sind weder Inhalt noch Blockgrenze
    return raw, [normalize(l) for l in raw], blocks


def evaluate(gold_path: Path, ocr_path: Path, min_block: int = MIN_BLOCK_LINES) -> dict:
    graw, gnorm, gblocks = load(gold_path)
    oraw, onorm, _ = load(ocr_path)
    ops = align(gnorm, onorm)

    # (gold_indices, ocr_indices) aller inhaltlich gematchten Paare
    pairs = [(o.gold, o.ocr) for o in ops if o.kind in ("match", "split", "merge")]
    unmatched_g = [k for o in ops if o.kind == "gap_gold" for k in o.gold]
    unmatched_o = [k for o in ops if o.kind == "gap_ocr" for k in o.ocr]

    # Stufe 2: dislozierte Zeilen unter den Lücken suchen
    rescued: list[tuple[int, int]] = []
    if unmatched_g and unmatched_o:
        cand = sorted(
            ((dist(gnorm[gi], onorm[oi]), gi, oi)
             for gi in unmatched_g for oi in unmatched_o),
            key=lambda t: t[0],
        )
        used_g, used_o = set(), set()
        for d, gi, oi in cand:
            if d >= RESCUE_CUTOFF:
                break
            if gi in used_g or oi in used_o:
                continue
            used_g.add(gi)
            used_o.add(oi)
            rescued.append((gi, oi))
    unmatched_g = [k for k in unmatched_g if k not in {g for g, _ in rescued}]
    unmatched_o = [k for k in unmatched_o if k not in {o for _, o in rescued}]

    all_pairs = pairs + [([g], [o]) for g, o in rescued]

    def error_rates(glines: list[str], olines: list[str]) -> tuple[float, float]:
        cer_num = cer_den = wer_num = wer_den = 0
        for gidx, oidx in all_pairs:
            g = " ".join(glines[k] for k in gidx)
            o = " ".join(olines[k] for k in oidx)
            cer_num += Levenshtein.distance(g, o)
            cer_den += len(g)
            wer_num += Levenshtein.distance(g.split(), o.split())
            wer_den += len(g.split())
        for k in unmatched_g:  # ausgelassen: alles falsch
            cer_num += len(glines[k])
            cer_den += len(glines[k])
            wer_num += len(glines[k].split())
            wer_den += len(glines[k].split())
        for k in unmatched_o:  # eingefügt: Einfügefehler, kein Goldanteil
            cer_num += len(olines[k])
            wer_num += len(olines[k].split())
        return cer_num / cer_den, wer_num / wer_den

    cer_raw, wer_raw = error_rates(graw, oraw)
    cer_norm, wer_norm = error_rates(gnorm, onorm)

    # --- Lokalisierung: OCR-Position je Goldzeile bestimmen ---------------
    pos: list[int | None] = [None] * len(gnorm)
    for o in ops:
        if o.kind in ("match", "split"):
            pos[o.gold[0]] = o.ocr[0]
        elif o.kind == "merge":
            pos[o.gold[0]] = o.ocr[0]
            pos[o.gold[1]] = o.ocr[0]
    for gi, oi in rescued:
        pos[gi] = oi
    rescued_lines = sorted(gi for gi, _ in rescued)  # dislozierte Goldzeilen, aufsteigend

    # --- Verschiebungsbasierte Blöcke ------------------------------------
    # Ein "Block" ist ein maximaler Lauf KONSEKUTIVER Goldzeilen, die gemeinsam
    # umgezogen sind: benachbarte Gold-Indizes UND monoton steigende OCR-Position
    # (Reihenfolge erhalten). Unabhängig von Leerzeilen. Läufe ab min_block Zeilen
    # sind ein Verschiebungs-Ereignis (loc_event); kürzere Läufe / Einzelzeilen
    # bleiben individuelle Zeilenverschiebungen (RLER).
    runs: list[list[int]] = []
    i = 0
    while i < len(rescued_lines):
        j = i
        while (j + 1 < len(rescued_lines)
               and rescued_lines[j + 1] == rescued_lines[j] + 1
               and pos[rescued_lines[j + 1]] >= pos[rescued_lines[j]]):
            j += 1
        runs.append(rescued_lines[i:j + 1])
        i = j + 1
    block_runs = [r for r in runs if len(r) >= min_block]
    loc_events = len(block_runs)
    block_lines = {gi for r in block_runs for gi in r}
    indiv_disloc = [gi for gi in rescued_lines if gi not in block_lines]

    return {
        "doc": gold_path.name.split("_")[0],
        "gold_lines": len(graw),
        "ocr_lines": len(oraw),
        "min_block": min_block,
        "matched": sum(1 for o in ops if o.kind == "match"),
        "split": sum(1 for o in ops if o.kind == "split"),
        "merge": sum(1 for o in ops if o.kind == "merge"),
        "cer_raw": round(cer_raw, 4),
        "cer_norm": round(cer_norm, 4),
        "wer_raw": round(wer_raw, 4),
        "wer_norm": round(wer_norm, 4),
        "rler": round(len(indiv_disloc) / len(graw), 4),
        "loc_events": loc_events,
        "lines_disloc_total": len(rescued_lines),
        "lines_disloc_indiv": len(indiv_disloc),
        "lines_disloc_block": len(block_lines),
        "largest_block": max((len(r) for r in block_runs), default=0),
        "gold_blocks_hint": len(set(gblocks)),  # Leerzeilen-Blöcke, nur Zusatzinfo
        "gold_missed": len(unmatched_g),
        "ocr_spurious": len(unmatched_o),
    }


def main() -> None:
    args = [a for a in sys.argv[1:]]
    min_block = MIN_BLOCK_LINES
    if "--min-block" in args:
        k = args.index("--min-block")
        min_block = int(args[k + 1])
        del args[k:k + 2]
    ocr_dir = DATA / (args[0] if args else "newOCR")
    rows = []
    for gold_path in sorted((DATA / "goldstandard").glob("*.txt")):
        doc = gold_path.name.split("_")[0]
        candidates = sorted(ocr_dir.glob(f"{doc}_*.txt")) or sorted(ocr_dir.glob(f"{doc}*.txt"))
        if not candidates:
            print(f"{doc}: keine Datei in {ocr_dir.name}/ gefunden", file=sys.stderr)
            continue
        rows.append(evaluate(gold_path, candidates[0], min_block=min_block))

    if not rows:
        sys.exit("keine auswertbaren Paare gefunden")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"metrics_{ocr_dir.name}.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    cols = ["doc", "cer_norm", "wer_norm", "rler", "loc_events",
            "lines_disloc_block", "lines_disloc_indiv", "largest_block"]
    widths = [max(len(c), 10) for c in cols]
    print(f"min_block = {min_block} Zeilen\n")
    print("  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        print("  ".join(str(r[c]).ljust(w) for c, w in zip(cols, widths)))
    print(f"\nCSV: {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")


if __name__ == "__main__":
    main()
