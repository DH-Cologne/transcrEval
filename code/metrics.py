#!/usr/bin/env python3
"""Metriken auf Basis des zweistufigen Zeilen-Alignments (siehe align.py).

CER  = Zeichen-Editierdistanz / Goldzeichen   (kontrastiv: roh und normalisiert)
WER  = Wort-Editierdistanz   / Goldwörter     (kontrastiv: roh und normalisiert)
RLER = individuell verrutschte Goldzeilen / Goldzeilen (Rate)
BLER = Verschiebungs-Ereignisse je Seite (loc_events, absolute Zahl, KEINE Rate)

Dislozierte Zeilen zählen in CER/WER nur mit ihren Inhaltsfehlern, nicht als
Totalausfall. Goldzeilen ohne Partner zählen als komplett ausgelassen,
OCR-Zeilen ohne Partner als komplett eingefügt.

Lokalisierung ist VERSCHIEBUNGSBASIERT (unabhängig von Leerzeilen): ein Block ist
ein maximaler Lauf konsekutiver Goldzeilen, die gemeinsam+in Reihenfolge ins OCR
gewandert sind. Läufe ab min_block Zeilen sind je EIN Verschiebungs-Ereignis
(loc_event); kürzere Läufe / Einzelzeilen bleiben RLER.

Aufruf:  python code/metrics.py [--config PFAD] [--min-block N]
Wertet jede Goldseite gegen alle konfigurierten OCR-Systeme aus und schreibt eine
<results>/metrics.csv im Wide-Format: EINE Zeile pro Dokument, je Metrik die
Spalten <metrik>_<system> nebeneinander (Systemnamen aus der Config).
"""

from __future__ import annotations

import csv
import sys

from rapidfuzz.distance import Levenshtein

from align import align, block_runs, rescue
from config import Config, SystemCfg, load_config


def evaluate(cfg: Config, gold_path, ocr_path, system: SystemCfg, min_block: int) -> dict:
    graw, gnorm, gblocks = cfg.load_lines(gold_path)
    oraw, onorm, _ = cfg.load_lines(ocr_path, system.strip_header)
    ops = align(gnorm, onorm, cfg.align)

    pairs = [(o.gold, o.ocr) for o in ops if o.kind in ("match", "split", "merge")]
    pos, rescued = rescue(ops, gnorm, onorm, cfg.align)
    rescued_g = {gi for gi, _ in rescued}
    rescued_o = {oi for _, oi in rescued}
    unmatched_g = [k for o in ops if o.kind == "gap_gold" for k in o.gold if k not in rescued_g]
    unmatched_o = [k for o in ops if o.kind == "gap_ocr" for k in o.ocr if k not in rescued_o]

    all_pairs = pairs + [([g], [o]) for g, o in rescued]

    def error_rates(glines, olines):
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

    # Lokalisierung: verschiebungsbasierte Blöcke
    rescued_lines = sorted(rescued_g)
    _, blocks, _ = block_runs(rescued_lines, pos, min_block)
    block_lines = {gi for r in blocks for gi in r}
    indiv_disloc = [gi for gi in rescued_lines if gi not in block_lines]

    return {
        "doc": cfg.doc_of(gold_path.name),
        "gold_lines": len(graw),
        "ocr_lines": len(oraw),
        "cer_raw": round(cer_raw, 4),
        "cer_norm": round(cer_norm, 4),
        "wer_raw": round(wer_raw, 4),
        "wer_norm": round(wer_norm, 4),
        "rler": round(len(indiv_disloc) / len(graw), 4),
        "loc_events": len(blocks),
        "lines_disloc_total": len(rescued_lines),
        "lines_disloc_indiv": len(indiv_disloc),
        "lines_disloc_block": len(block_lines),
        "largest_block": max((len(r) for r in blocks), default=0),
        "gold_blocks_hint": len(set(gblocks)),  # Leerzeilen-Blöcke, nur Zusatzinfo
        "gold_missed": len(unmatched_g),
        "ocr_spurious": len(unmatched_o),
    }


# Metriken, die im Wide-Format je System nebeneinander erscheinen
WIDE_METRICS = ["cer_raw", "cer_norm", "wer_raw", "wer_norm", "rler", "loc_events",
                "lines_disloc_block", "lines_disloc_indiv", "largest_block",
                "gold_missed", "ocr_spurious"]


def main() -> None:
    args = list(sys.argv[1:])
    cfg_path = None
    if "--config" in args:
        k = args.index("--config")
        cfg_path = args[k + 1]
        del args[k:k + 2]
    cfg = load_config(cfg_path)
    min_block = cfg.align.min_block
    if "--min-block" in args:
        k = args.index("--min-block")
        min_block = int(args[k + 1])
        del args[k:k + 2]

    per_doc: dict[str, dict] = {}
    order: list[str] = []
    for doc, folder, gold_path in cfg.gold_files():
        for system in cfg.systems:
            ocr_path = cfg.find_ocr(system, folder, doc)
            if ocr_path is None:
                continue
            per_doc.setdefault(doc, {})[system.name] = evaluate(
                cfg, gold_path, ocr_path, system, min_block)
            if doc not in order:
                order.append(doc)

    if not order:
        sys.exit("keine auswertbaren Paare gefunden")

    sysnames = [s.name for s in cfg.systems]
    rows = []
    for doc in order:
        systems = per_doc[doc]
        any_res = next(iter(systems.values()))
        row = {"doc": doc, "gold_lines": any_res["gold_lines"], "min_block": min_block}
        for metric in WIDE_METRICS:
            for name in sysnames:
                row[f"{metric}_{name}"] = systems[name][metric] if name in systems else ""
        rows.append(row)

    cfg.results_dir.mkdir(exist_ok=True)
    out = cfg.results_dir / "metrics.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    cols = ["doc"] + [f"cer_norm_{n}" for n in sysnames] \
        + [f"wer_norm_{n}" for n in sysnames] + [f"loc_events_{n}" for n in sysnames]
    widths = [max(len(c), 8) for c in cols]
    print(f"{cfg.project} · min_block={min_block} · {len(rows)} Dokumente\n")
    print("  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        print("  ".join(str(r[c]).ljust(w) for c, w in zip(cols, widths)))
    print(f"\nCSV: {out}")


if __name__ == "__main__":
    main()
