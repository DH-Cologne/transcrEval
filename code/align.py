#!/usr/bin/env python3
"""Zweistufiges Zeilen-Alignment Gold <-> OCR (generisch, konfigurierbar).

Stufe 1: DP-Alignment in Lesereihenfolge mit Operationen
         1:1-Match, Lücke (Gold/OCR), Split (1 Gold : 2 OCR), Merge (2 Gold : 1 OCR).
Stufe 2: Rettungslauf — übrig gebliebene Zeilen werden positionsunabhängig
         gegeneinander gematcht -> dislozierte Zeilen.

Alle Schwellwerte kommen aus AlignCfg (siehe config.py). Direkt ausgeführt liefert
dieses Modul Kalibrier-Diagnosen (Match-Distanzverteilung) je Gold/OCR-Paar.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

from config import AlignCfg, load_config


def dist(a: str, b: str) -> float:
    return Levenshtein.normalized_distance(a, b)


@dataclass
class Op:
    kind: str            # match | split | merge | gap_gold | gap_ocr
    gold: list[int]
    ocr: list[int]
    d: float | None


def align(gold: list[str], ocr: list[str], cfg: AlignCfg) -> list[Op]:
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
                relax(i + 1, j, cfg.gap, ("gap_gold", 1, 0, None))
            if j < n:
                relax(i, j + 1, cfg.gap, ("gap_ocr", 0, 1, None))
            if i < m and j < n:
                d = dist(gold[i], ocr[j])
                if d < cfg.match_cutoff:
                    relax(i + 1, j + 1, d, ("match", 1, 1, d))
            if i < m and j + 1 < n:  # Goldzeile im OCR in zwei Zeilen getrennt
                d = dist(gold[i], ocr[j] + " " + ocr[j + 1])
                if d < cfg.match_cutoff:
                    relax(i + 1, j + 2, d + cfg.split_penalty, ("split", 1, 2, d))
            if i + 1 < m and j < n:  # zwei Goldzeilen im OCR zusammengezogen
                d = dist(gold[i] + " " + gold[i + 1], ocr[j])
                if d < cfg.match_cutoff:
                    relax(i + 2, j + 1, d + cfg.split_penalty, ("merge", 2, 1, d))

    ops: list[Op] = []
    i, j = m, n
    while i or j:
        kind, di, dj, d = back[i][j]
        ops.append(Op(kind, list(range(i - di, i)), list(range(j - dj, j)), d))
        i, j = i - di, j - dj
    return list(reversed(ops))


def rescue(ops: list[Op], gnorm: list[str], onorm: list[str], cfg: AlignCfg):
    """Stufe 2. Liefert (pos, rescued): OCR-Position je Goldzeile und dislozierte Paare.

    pos[gi] = OCR-Zeilenindex des Partners (aus Match/Split/Merge oder Rettung), sonst None.
    rescued  = Liste (gold_index, ocr_index) der positionsunabhängig geretteten Zeilen.
    """
    pos: list[int | None] = [None] * len(gnorm)
    for o in ops:
        if o.kind in ("match", "split"):
            pos[o.gold[0]] = o.ocr[0]
        elif o.kind == "merge":
            pos[o.gold[0]] = o.ocr[0]
            pos[o.gold[1]] = o.ocr[0]
    ug = [k for o in ops if o.kind == "gap_gold" for k in o.gold]
    uo = [k for o in ops if o.kind == "gap_ocr" for k in o.ocr]
    rescued: list[tuple[int, int]] = []
    if ug and uo:
        cand = sorted(((dist(gnorm[gi], onorm[oi]), gi, oi) for gi in ug for oi in uo),
                      key=lambda t: t[0])
        used_g, used_o = set(), set()
        for d, gi, oi in cand:
            if d >= cfg.rescue_cutoff:
                break
            if gi in used_g or oi in used_o:
                continue
            used_g.add(gi)
            used_o.add(oi)
            rescued.append((gi, oi))
    for gi, oi in rescued:
        pos[gi] = oi
    return pos, rescued


def block_runs(rescued_gold, pos, min_block: int):
    """Gruppiert dislozierte Goldzeilen in gemeinsam verschobene Läufe.

    Ein Lauf = konsekutive Gold-Indizes mit monoton steigender OCR-Position.
    Liefert (runs, blocks, event_of): alle Läufe, die >= min_block langen Läufe
    (Verschiebungs-Ereignisse) und die Zuordnung gold_index -> Ereignisnummer (1-basiert).
    """
    rl = sorted(rescued_gold)
    runs: list[list[int]] = []
    i = 0
    while i < len(rl):
        j = i
        while (j + 1 < len(rl) and rl[j + 1] == rl[j] + 1 and pos[rl[j + 1]] >= pos[rl[j]]):
            j += 1
        runs.append(rl[i:j + 1])
        i = j + 1
    blocks = [r for r in runs if len(r) >= min_block]
    event_of = {gi: e + 1 for e, run in enumerate(blocks) for gi in run}
    return runs, blocks, event_of


def report(doc: str, gold, ocr, cfg: AlignCfg) -> None:
    ops = align(gold, ocr, cfg)
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

    _, rescued = rescue(ops, gold, ocr, cfg)
    print(f"  Stufe 2: {len(rescued)} dislozierte Zeilen gerettet")


def main() -> None:
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else None)
    system = cfg.systems[0]  # Diagnose gegen das erste konfigurierte OCR-System
    for doc, gold_path in cfg.gold_files():
        ocr_path = cfg.find_ocr(system, doc)
        if not ocr_path:
            print(f"{doc}: kein {system.name}-Gegenstück gefunden", file=sys.stderr)
            continue
        _, gnorm, _ = cfg.load_lines(gold_path)
        _, onorm, _ = cfg.load_lines(ocr_path, system.strip_header)
        report(doc, gnorm, onorm, cfg.align)


if __name__ == "__main__":
    main()
