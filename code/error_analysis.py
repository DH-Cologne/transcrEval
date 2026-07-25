#!/usr/bin/env python3
"""Fehlertypologie auf Zeichenebene: Was für Fehler macht welches OCR, und wo?

Für jedes alignierte Zeilenpaar werden die Zeichen-Editieroperationen bestimmt und
mit Merkmalen versehen:
  - Operation:        Ersetzung / Auslassung (im OCR fehlt) / Einfügung (OCR erfindet)
  - Zeichenklasse:    Kleinbuchstabe, Großbuchstabe, Umlaut/ß, Ziffer, Interpunktion,
                      Leerzeichen, Trennstrich, Sonstiges
  - Stellung i.d.Zeile: relative Position (Dezil) + Flags Zeilenanfang/-ende
  - Stellung im Wort: wortinitial / wortfinal / wortintern
  - Stellung a.d.Seite: relative Zeilennummer (Dezil), Seitendrittel
  - bei ALTO-Systemen zusätzlich die vertikale/horizontale Lage der Zeile im Scan

Ausgabe: <results>/errors.csv (eine Zeile je Fehler, für eigene Auswertung in R)
         plus eine Zusammenfassung in der Konsole.

Aufruf:  python code/error_analysis.py [--config PFAD] [--system NAME] [--top N]
"""

from __future__ import annotations

import csv
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from difflib import SequenceMatcher

from align import align, rescue
from config import load_config

NS = "{http://www.loc.gov/standards/alto/ns-v4#}"
PUNCT = set(".,;:!?()[]«»„“”\"'…")
HYPHEN = set("-–—⸗¬")


def char_class(ch: str) -> str:
    if ch == " ":
        return "Leerzeichen"
    if ch in HYPHEN:
        return "Trennstrich"
    if ch in PUNCT:
        return "Interpunktion"
    if ch.isdigit():
        return "Ziffer"
    if ch.isalpha():
        if ch in "äöüÄÖÜßſ":
            return "Umlaut/ß"
        return "Großbuchstabe" if ch.isupper() else "Kleinbuchstabe"
    return "Sonstiges"


def word_position(line: str, idx: int) -> str:
    """wortinitial / wortfinal / wortintern / (Leerzeichen selbst)."""
    if idx >= len(line) or line[idx] == " ":
        return "Wortgrenze"
    before_space = idx == 0 or line[idx - 1] == " "
    after_space = idx == len(line) - 1 or line[idx + 1] == " "
    if before_space and after_space:
        return "Einzelzeichen"
    if before_space:
        return "wortinitial"
    if after_space:
        return "wortfinal"
    return "wortintern"


def alto_line_boxes(path):
    """TextLine-Boxen in Dokumentreihenfolge: (VPOS, HPOS, Seitenhöhe, Seitenbreite)."""
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return [], 0, 0
    page = root.find(f".//{NS}Page")
    if page is None:
        return [], 0, 0
    H, W = int(page.get("HEIGHT", 0)), int(page.get("WIDTH", 0))
    boxes = []
    for tl in root.iter(NS + "TextLine"):
        has_text = any(s.get("CONTENT") for s in tl.findall(NS + "String"))
        if has_text:
            boxes.append((int(tl.get("VPOS", 0)), int(tl.get("HPOS", 0))))
    return boxes, H, W


def gold_partner(ops, ocr_lines, rescued):
    """Goldzeilen-Index -> (OCR-Text, OCR-Zeilenindex oder None bei Mehrfachbezug)."""
    m = {}
    for o in ops:
        if o.kind == "match":
            m[o.gold[0]] = (ocr_lines[o.ocr[0]], o.ocr[0])
        elif o.kind == "split":
            m[o.gold[0]] = (" ".join(ocr_lines[k] for k in o.ocr), o.ocr[0])
        elif o.kind == "merge":
            joined = ocr_lines[o.ocr[0]]
            m[o.gold[0]] = (joined, o.ocr[0])
            m[o.gold[1]] = (joined, o.ocr[0])
    for gi, oi in rescued:
        m[gi] = (ocr_lines[oi], oi)
    return m


def analyse(cfg, only_system=None):
    rows = []
    opportunities = Counter()   # Zeichen-Gelegenheiten je System (für Raten)
    for doc, folder, gold_path in cfg.gold_files():
        graw, gnorm, _ = cfg.load_lines(gold_path)
        n_lines = len(gnorm)
        for system in cfg.systems:
            if only_system and system.name != only_system:
                continue
            ocr_path = cfg.find_ocr(system, folder, doc)
            if ocr_path is None:
                continue
            _, onorm, _ = cfg.load_lines(ocr_path, system.strip_header)
            ops = align(gnorm, onorm, cfg.align)
            _, rescued = rescue(ops, gnorm, onorm, cfg.align)
            partners = gold_partner(ops, onorm, rescued)

            boxes, page_h, page_w = alto_line_boxes(folder / f"{doc}.xml")

            for gi, gline in enumerate(gnorm):
                if gi not in partners:
                    continue
                oline, oidx = partners[gi]
                opportunities[system.name] += len(gline)
                line_rel = gi / max(n_lines - 1, 1)
                page_third = ("oben" if line_rel < 1 / 3 else
                              "mitte" if line_rel < 2 / 3 else "unten")
                # vertikale/horizontale Lage aus ALTO (nur wenn Zeilen 1:1 passen)
                vrel = hrel = ""
                if boxes and oidx is not None and oidx < len(boxes) and page_h:
                    vrel = round(boxes[oidx][0] / page_h, 3)
                    hrel = round(boxes[oidx][1] / page_w, 3) if page_w else ""

                sm = SequenceMatcher(None, gline, oline, autojunk=False)
                for tag, i1, i2, j1, j2 in sm.get_opcodes():
                    if tag == "equal":
                        continue
                    if tag == "replace":
                        pairs = [(i1 + k, gline[i1 + k],
                                  oline[j1 + k] if j1 + k < j2 else "")
                                 for k in range(i2 - i1)]
                        op_name = "Ersetzung"
                    elif tag == "delete":
                        pairs = [(i1 + k, gline[i1 + k], "") for k in range(i2 - i1)]
                        op_name = "Auslassung"
                    else:  # insert
                        pairs = [(i1, "", oline[j1 + k]) for k in range(j2 - j1)]
                        op_name = "Einfügung"

                    for idx, gch, och in pairs:
                        pos_rel = idx / max(len(gline) - 1, 1)
                        ref = gch if gch else och
                        rows.append({
                            "doc": doc, "system": system.name, "line": gi + 1,
                            "op": op_name,
                            "gold_char": gch, "ocr_char": och,
                            "klasse": char_class(ref),
                            "char_idx": idx, "line_len": len(gline),
                            "pos_rel": round(pos_rel, 3),
                            "pos_dezil": min(int(pos_rel * 10) + 1, 10),
                            "zeilenanfang": int(idx <= 1),
                            "zeilenende": int(idx >= len(gline) - 2),
                            "wortpos": word_position(gline, idx) if gch else "Einfügung",
                            "zeile_rel": round(line_rel, 3),
                            "seitendrittel": page_third,
                            "alto_vrel": vrel, "alto_hrel": hrel,
                        })
    return rows, opportunities


def summarise(rows, opportunities, top_n=12):
    systems = sorted({r["system"] for r in rows})
    for s in systems:
        sub = [r for r in rows if r["system"] == s]
        total = len(sub)
        opp = opportunities[s]
        print(f"\n{'=' * 74}\nSystem »{s}«: {total} Zeichenfehler auf {opp} Goldzeichen "
              f"({total / opp * 100:.2f} %)")

        print("\n  Operation:")
        for k, v in Counter(r["op"] for r in sub).most_common():
            print(f"    {k:12s} {v:6d}  {v / total * 100:5.1f} %")

        print("\n  Zeichenklasse (des betroffenen Zeichens):")
        for k, v in Counter(r["klasse"] for r in sub).most_common():
            print(f"    {k:16s} {v:6d}  {v / total * 100:5.1f} %")

        print("\n  Stellung im Wort:")
        for k, v in Counter(r["wortpos"] for r in sub).most_common():
            print(f"    {k:16s} {v:6d}  {v / total * 100:5.1f} %")

        print("\n  Stellung in der Zeile (Dezil, 1=Anfang … 10=Ende):")
        dez = Counter(r["pos_dezil"] for r in sub)
        mx = max(dez.values()) if dez else 1
        for d in range(1, 11):
            v = dez.get(d, 0)
            bar = "█" * round(v / mx * 34)
            print(f"    {d:2d}  {v:5d}  {v / total * 100:5.1f} % {bar}")
        ende = sum(1 for r in sub if r["zeilenende"])
        anfang = sum(1 for r in sub if r["zeilenanfang"])
        print(f"    -> letzte 2 Zeichen: {ende} ({ende / total * 100:.1f} %), "
              f"erste 2: {anfang} ({anfang / total * 100:.1f} %)")

        print("\n  Seitendrittel:")
        for k, v in Counter(r["seitendrittel"] for r in sub).most_common():
            print(f"    {k:8s} {v:6d}  {v / total * 100:5.1f} %")

        print(f"\n  Häufigste Verwechslungen (Gold → OCR), Top {top_n}:")
        conf = Counter((r["gold_char"], r["ocr_char"]) for r in sub
                       if r["op"] == "Ersetzung")
        for (g, o), v in conf.most_common(top_n):
            print(f"    »{g}« → »{o}«   {v}")

        print(f"\n  Häufigste Auslassungen (im OCR verschluckt), Top {top_n}:")
        om = Counter(r["gold_char"] for r in sub if r["op"] == "Auslassung")
        for g, v in om.most_common(top_n):
            name = unicodedata.name(g, "?") if g.strip() else "SPACE"
            print(f"    »{g}« ({name.lower()})  {v}")


def main():
    args = list(sys.argv[1:])
    cfg_path = only_system = None
    top_n = 12
    if "--config" in args:
        k = args.index("--config"); cfg_path = args[k + 1]; del args[k:k + 2]
    if "--system" in args:
        k = args.index("--system"); only_system = args[k + 1]; del args[k:k + 2]
    if "--top" in args:
        k = args.index("--top"); top_n = int(args[k + 1]); del args[k:k + 2]

    cfg = load_config(cfg_path)
    rows, opportunities = analyse(cfg, only_system)
    if not rows:
        sys.exit("keine Fehler gefunden (stimmen Config und Daten?)")

    cfg.results_dir.mkdir(exist_ok=True)
    out = cfg.results_dir / "errors.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    summarise(rows, opportunities, top_n)
    print(f"\n\nEinzelfehler (für eigene Auswertung): {out}")


if __name__ == "__main__":
    main()
