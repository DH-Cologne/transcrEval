#!/usr/bin/env python3
"""Vorverarbeitung: Zeilentext aus ALTO neu erzeugen, Zeilen koordinatenbasiert sortiert.

Hintergrund: Die Dokumentreihenfolge der TextLine-Elemente folgt nicht zuverlässig
der vertikalen Lage der Zeilen. Dieser Schritt übernimmt die Blockreihenfolge
unverändert aus der Datei und sortiert lediglich die Zeilen INNERHALB jedes
TextBlocks nach VPOS (bei Gleichstand nach HPOS). Es ist also keine eigene
Layoutanalyse, sondern eine Korrektur der Ausgabeordnung anhand der Koordinaten,
die das ALTO selbst mitliefert.

Gemessen an zehn Goldstandard-Seiten senkt das die einzeln fehlplatzierten Zeilen
von 113 auf 9 und verbessert zugleich die CER.

Aufruf:  python code/resort_alto.py [--config PFAD] [--suffix _ocr_neusort.txt]
Ausgabe: je Seitenordner eine zusätzliche Textdatei; die gelieferte Fassung
         bleibt unangetastet, damit beide Varianten vergleichbar bleiben.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

from config import load_config

NS = "{http://www.loc.gov/standards/alto/ns-v4#}"


def resorted_lines(alto_path) -> tuple[list[str], int]:
    """(Zeilen in korrigierter Reihenfolge, Anzahl umsortierter Zeilen)."""
    root = ET.parse(alto_path).getroot()
    out, moved = [], 0
    for tb in root.iter(NS + "TextBlock"):
        lines = []
        for tl in tb.findall(NS + "TextLine"):
            txt = " ".join(s.get("CONTENT") for s in tl.findall(NS + "String")
                           if s.get("CONTENT"))
            if txt.strip():
                lines.append((int(tl.get("VPOS", 0)), int(tl.get("HPOS", 0)), txt))
        ordered = sorted(lines)
        moved += sum(1 for a, b in zip(lines, ordered) if a is not b and a != b)
        out.extend(t for _, _, t in ordered)
    return out, moved


def main() -> None:
    args = list(sys.argv[1:])
    cfg_path = None
    suffix = "_ocr_neusort.txt"
    if "--config" in args:
        k = args.index("--config"); cfg_path = args[k + 1]; del args[k:k + 2]
    if "--suffix" in args:
        k = args.index("--suffix"); suffix = args[k + 1]; del args[k:k + 2]

    cfg = load_config(cfg_path)
    total_moved = total_lines = 0
    print(f"{'Seite':18s} {'Zeilen':>7} {'umsortiert':>11}")
    for doc, folder in cfg.pages():
        alto = folder / f"{doc}.xml"
        if not alto.exists():
            print(f"{doc:18s} — kein ALTO gefunden", file=sys.stderr)
            continue
        lines, moved = resorted_lines(alto)
        (folder / f"{doc}{suffix}").write_text("\n".join(lines) + "\n", encoding="utf-8")
        total_moved += moved
        total_lines += len(lines)
        print(f"{doc:18s} {len(lines):>7} {moved:>11}")
    print(f"\n{total_lines} Zeilen, davon {total_moved} umsortiert "
          f"({total_moved / total_lines:.1%}); geschrieben als *{suffix}")


if __name__ == "__main__":
    main()
