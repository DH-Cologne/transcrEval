#!/usr/bin/env python3
"""Prototyp: geordnetes Zeilen-Alignment Gold <-> OCR per dynamischer Programmierung.

Stufe 1: DP-Alignment in Lesereihenfolge mit Operationen
         1:1-Match, Lücke (Gold/OCR), Split (1 Gold : 2 OCR), Merge (2 Gold : 1 OCR).
Stufe 2: Rettungslauf — übrig gebliebene Zeilen werden positionsunabhängig
         gegeneinander gematcht -> Kandidaten für dislozierte Zeilen (RLER).

Nur Diagnose-Output zur Kalibrierung der Schwellwerte, noch keine Metriken.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz.distance import Levenshtein

DATA = Path(__file__).resolve().parent.parent / "data"

GAP = 0.35
SPLIT_PENALTY = 0.10   # leichter Aufschlag, damit 1:1 bei Gleichstand gewinnt
MATCH_CUTOFF = 0.60    # Stufe 1: Matches oberhalb werden verweigert -> Lücken
RESCUE_CUTOFF = 0.50   # Stufe 2: max. normalisierte LD für dislozierte Paare


def normalize(line: str) -> str:
    line = unicodedata.normalize("NFC", line)
    line = line.replace("ſ", "s").replace("ﬅ", "st")
    for hyphen in "⸗¬=":
        line = line.replace(hyphen, "-")
    return " ".join(line.split())


# Metadaten-Header des alten OCR, z.B. "[ 2023-06-29 10:37:53.640 - 19210110 - Seite 2 ]"
_METADATA = re.compile(r"^\[\s*\d{4}-\d{2}-\d{2}\s.*\]\s*$")


def is_content(line: str) -> bool:
    return bool(line.strip()) and not _METADATA.match(line)


def load_lines(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8").splitlines()
    return [normalize(l) for l in raw if is_content(l)]


def dist(a: str, b: str) -> float:
    return Levenshtein.normalized_distance(a, b)


@dataclass
class Op:
    kind: str            # match | split | merge | gap_gold | gap_ocr
    gold: list[int]
    ocr: list[int]
    d: float | None


def align(gold: list[str], ocr: list[str]) -> list[Op]:
    m, n = len(gold), len(ocr)
    INF = float("inf")
    dp = [[INF] * (n + 1) for _ in range(m + 1)]
    back: list[list[tuple | None]] = [[None] * (n + 1) for _ in range(m + 1)]
    dp[0][0] = 0.0

    for i in range(m + 1):
        for j in range(n + 1):
            cur = dp[i][j]
            if cur == INF:
                continue

            def relax(ni: int, nj: int, cost: float, op: tuple):
                if cur + cost < dp[ni][nj]:
                    dp[ni][nj] = cur + cost
                    back[ni][nj] = op

            if i < m:
                relax(i + 1, j, GAP, ("gap_gold", 1, 0, None))
            if j < n:
                relax(i, j + 1, GAP, ("gap_ocr", 0, 1, None))
            if i < m and j < n:
                d = dist(gold[i], ocr[j])
                if d < MATCH_CUTOFF:
                    relax(i + 1, j + 1, d, ("match", 1, 1, d))
            if i < m and j + 1 < n:  # Goldzeile im OCR in zwei Zeilen getrennt
                d = dist(gold[i], ocr[j] + " " + ocr[j + 1])
                if d < MATCH_CUTOFF:
                    relax(i + 1, j + 2, d + SPLIT_PENALTY, ("split", 1, 2, d))
            if i + 1 < m and j < n:  # zwei Goldzeilen im OCR zusammengezogen
                d = dist(gold[i] + " " + gold[i + 1], ocr[j])
                if d < MATCH_CUTOFF:
                    relax(i + 2, j + 1, d + SPLIT_PENALTY, ("merge", 2, 1, d))

    ops: list[Op] = []
    i, j = m, n
    while i or j:
        kind, di, dj, d = back[i][j]
        ops.append(Op(kind, list(range(i - di, i)), list(range(j - dj, j)), d))
        i, j = i - di, j - dj
    return list(reversed(ops))


def report(doc: str, gold_path: Path, ocr_path: Path) -> None:
    gold, ocr = load_lines(gold_path), load_lines(ocr_path)
    ops = align(gold, ocr)

    matches = [o for o in ops if o.kind in ("match", "split", "merge")]
    gap_gold = [o for o in ops if o.kind == "gap_gold"]
    gap_ocr = [o for o in ops if o.kind == "gap_ocr"]

    print(f"\n{'=' * 78}\n{doc}:  Gold {len(gold)} Zeilen | OCR {len(ocr)} Zeilen")
    n_split = sum(1 for o in matches if o.kind == "split")
    n_merge = sum(1 for o in matches if o.kind == "merge")
    print(f"  Stufe 1: {len(matches) - n_split - n_merge} x 1:1, {n_split} x Split, "
          f"{n_merge} x Merge, {len(gap_gold)} Gold-Lücken, {len(gap_ocr)} OCR-Lücken")

    buckets = [0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.01]
    hist = [0] * (len(buckets) - 1)
    for o in matches:
        for k in range(len(buckets) - 1):
            if buckets[k] <= o.d < buckets[k + 1]:
                hist[k] += 1
                break
    print("  Verteilung der Match-Distanzen (normalisierte LD):")
    for k in range(len(buckets) - 1):
        label = f"{buckets[k]:.2f}-{min(buckets[k + 1], 1.0):.2f}"
        print(f"    {label}: {'#' * hist[k]} {hist[k]}")

    worst = sorted(matches, key=lambda o: -o.d)[:5]
    print("  Schlechteste akzeptierte Matches:")
    for o in worst:
        g = " / ".join(gold[k] for k in o.gold)
        c = " / ".join(ocr[k] for k in o.ocr)
        print(f"    d={o.d:.2f} [{o.kind}] G{o.gold}: {g[:70]}")
        print(f"             {'':>9}O{o.ocr}: {c[:70]}")

    # Stufe 2: Rettungslauf für Lücken -> dislozierte Zeilen
    ug = [k for o in gap_gold for k in o.gold]
    uo = [k for o in gap_ocr for k in o.ocr]
    rescued = []
    if ug and uo:
        cand = sorted(
            ((dist(gold[gi], ocr[oi]), gi, oi) for gi in ug for oi in uo),
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
            rescued.append((d, gi, oi))

    print(f"  Stufe 2: {len(rescued)} dislozierte Zeilen gerettet, "
          f"{len(ug) - len(rescued)} Goldzeilen ohne Partner (ausgelassen), "
          f"{len(uo) - len(rescued)} OCR-Zeilen ohne Partner (halluziniert/anders)")
    for d, gi, oi in rescued[:8]:
        print(f"    d={d:.2f}  Gold[{gi}] -> OCR[{oi}]: {gold[gi][:60]}")
    for gi in sorted(set(ug) - {g for _, g, _ in rescued})[:5]:
        print(f"    ohne Partner Gold[{gi}]: {gold[gi][:60]}")
    for oi in sorted(set(uo) - {o for _, _, o in rescued})[:5]:
        print(f"    ohne Partner OCR[{oi}]: {ocr[oi][:60]}")


def main() -> None:
    gold_dir, ocr_dir = DATA / "goldstandard", DATA / "newOCR"
    for gold_path in sorted(gold_dir.glob("*.txt")):
        doc = gold_path.name.split("_")[0]
        ocr_matches = sorted(ocr_dir.glob(f"{doc}_*.txt"))
        if not ocr_matches:
            print(f"{doc}: kein newOCR-Gegenstück gefunden", file=sys.stderr)
            continue
        report(doc, gold_path, ocr_matches[0])


if __name__ == "__main__":
    main()
