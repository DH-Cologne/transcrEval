#!/usr/bin/env python3
"""Exportiert einzeln verschobene Zeilen mit ALTO-Koordinaten -- Material für Bugreports.

Betrachtet werden Goldzeilen, die das positionsunabhängige Alignment (Stufe 2) an
anderer Stelle wiederfindet und die NICHT Teil eines gemeinsam verlagerten Blocks
sind. Jede solche Zeile wird klassifiziert:

  invertiert_im_block  Die Zeile steht in der ALTO-Dokumentordnung NACH ihrer
                       Vorgängerzeile, liegt auf der Seite aber HÖHER -- und beide
                       gehören zum selben TextBlock. Mechanisch erklärbarer Fall;
                       betrifft auffällig oft eingerückte Absatzanfänge.
  weitwurf             Verschiebung um mehr als fünf Positionen; hängt meist mit
                       seitenweit instabiler Lesereihenfolge zusammen.
  ungeklaert           Verschiebung um 1-5 Positionen ohne erkennbares Muster.

Ausgabe: <results>/line_order_anomalies.csv (eine Zeile je Fall, mit Zeilen-IDs,
Bounding Box und Nachbarzeile zum direkten Nachschlagen im ALTO).

Aufruf:  python code/export_line_anomalies.py [--config PFAD] [--system NAME]
"""

from __future__ import annotations

import csv
import sys
import xml.etree.ElementTree as ET

from align import align, block_runs, rescue
from config import load_config

NS = "{http://www.loc.gov/standards/alto/ns-v4#}"
INDENT_PX = 40      # ab dieser Rechtsversetzung gilt eine Zeile als eingerückt
FAR_MOVE = 5        # ab dieser Distanz gilt eine Verschiebung als "Weitwurf"


def alto_lines(path):
    """Textzeilen in Dokumentordnung mit ID, Box und zugehörigem TextBlock."""
    out = []
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return out
    for tb in root.iter(NS + "TextBlock"):
        for tl in tb.findall(NS + "TextLine"):
            content = [s.get("CONTENT") for s in tl.findall(NS + "String")]
            if not any(content):
                continue
            out.append({
                "line_id": tl.get("ID", ""), "block_id": tb.get("ID", ""),
                "hpos": int(tl.get("HPOS", 0)), "vpos": int(tl.get("VPOS", 0)),
                "width": int(tl.get("WIDTH", 0)), "height": int(tl.get("HEIGHT", 0)),
                "baseline": (tl.get("BASELINE") or "").split(" ")[0],
            })
    return out


def main():
    args = list(sys.argv[1:])
    cfg_path = None
    sysname = "neu"
    if "--config" in args:
        k = args.index("--config"); cfg_path = args[k + 1]; del args[k:k + 2]
    if "--system" in args:
        k = args.index("--system"); sysname = args[k + 1]; del args[k:k + 2]

    cfg = load_config(cfg_path)
    system = cfg.system(sysname)
    rows = []

    for doc, folder, gold_path in cfg.gold_files():
        ocr_path = cfg.find_ocr(system, folder, doc)
        if ocr_path is None:
            continue
        graw, gnorm, _ = cfg.load_lines(gold_path)
        oraw, onorm, _ = cfg.load_lines(ocr_path, system.strip_header)
        ops = align(gnorm, onorm, cfg.align)
        pos, rescued = rescue(ops, gnorm, onorm, cfg.align)
        _, blocks, _ = block_runs([g for g, _ in rescued], pos, cfg.align.min_block)
        in_block = {g for r in blocks for g in r}
        L = alto_lines(folder / f"{doc}.xml")

        for gi, oi in sorted(rescued):
            if gi in in_block:
                continue
            dist = oi - gi
            cur = L[oi] if oi < len(L) else None
            prev = L[oi - 1] if 0 < oi <= len(L) else None

            muster = "ungeklaert"
            indent = ""
            if cur and prev and cur["block_id"] == prev["block_id"] \
                    and cur["vpos"] < prev["vpos"]:
                muster = "invertiert_im_block"
                indent = cur["hpos"] - prev["hpos"]
            elif abs(dist) > FAR_MOVE:
                muster = "weitwurf"

            rows.append({
                "seite": doc,
                "label": cfg.labels.get(doc, doc),
                "muster": muster,
                "gold_zeile": gi + 1,
                "ocr_index": oi,
                "distanz": dist,
                "line_id": cur["line_id"] if cur else "",
                "block_id": cur["block_id"] if cur else "",
                "hpos": cur["hpos"] if cur else "",
                "vpos": cur["vpos"] if cur else "",
                "width": cur["width"] if cur else "",
                "height": cur["height"] if cur else "",
                "baseline_start": cur["baseline"] if cur else "",
                "einzug_px": indent,
                "eingerueckt": (1 if isinstance(indent, int) and indent > INDENT_PX else
                                0 if isinstance(indent, int) else ""),
                "vorher_line_id": prev["line_id"] if prev else "",
                "vorher_vpos": prev["vpos"] if prev else "",
                "vorher_hpos": prev["hpos"] if prev else "",
                "text_gold": graw[gi],
                "text_vorherige_ocr_zeile": oraw[oi - 1] if 0 < oi < len(oraw) else "",
            })

    if not rows:
        sys.exit("keine Einzelverschiebungen gefunden")

    order = {"invertiert_im_block": 0, "weitwurf": 1, "ungeklaert": 2}
    rows.sort(key=lambda r: (order[r["muster"]], r["seite"], r["gold_zeile"]))

    cfg.results_dir.mkdir(exist_ok=True)
    out = cfg.results_dir / f"line_order_anomalies_{sysname}.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    c = Counter(r["muster"] for r in rows)
    print(f"System »{sysname}«: {len(rows)} einzeln verschobene Zeilen")
    for k in ("invertiert_im_block", "weitwurf", "ungeklaert"):
        print(f"   {k:22s} {c.get(k,0):4d}")
    ind = sum(1 for r in rows if r["muster"] == "invertiert_im_block" and r["eingerueckt"] == 1)
    if c.get("invertiert_im_block"):
        print(f"   davon eingerueckt (>{INDENT_PX}px): {ind}")
    print(f"\nCSV: {out}")


if __name__ == "__main__":
    main()
