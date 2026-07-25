#!/usr/bin/env python3
"""Gold-Audit: findet Kandidaten für Fehler IM GOLDSTANDARD (nur listen, nie ändern).

Idee: Wo zwei unabhängige OCR-Systeme (z.B. ABBYY 2015 und Transkribus 2026)
dasselbe Wort lesen, das Gold aber ein anderes hat, ist die Goldstelle der
Ausreißer -- ein Kandidat für einen Transkriptionsfehler.

Grenzen der Methode (wichtig fürs Interpretieren):
- Findet nur Fehler, bei denen BEIDE OCR zufällig richtig UND einig waren.
- Irren beide gleich (klassisch: langes ſ als "f" gelesen), ist das Gold richtig
  und der Treffer ein Fehlalarm -> Gruppe C im Bericht.
- Braucht >= 2 OCR-Systeme in der Config.

Vergleich läuft auf normalisiertem Text; zusätzlich werden Ligaturen, typografische
Anführungszeichen und reine Satzzeichen-Unterschiede weggefaltet ("bereinigt"),
weil das Transkriptionskonventionen sind, keine Fehler.

Aufruf:
  python code/gold_audit.py                     # bereinigte Kandidaten in die Konsole
  python code/gold_audit.py --all               # auch die weggefalteten Treffer zeigen
  python code/gold_audit.py --md analysis/gold_candidates.md   # Checkliste schreiben
  python code/gold_audit.py --config other.json
"""

from __future__ import annotations

import sys
from difflib import SequenceMatcher
from pathlib import Path

from align import align, rescue
from config import load_config

MIN_WORD = 3          # kürzere Wörter erzeugen zu viel Rauschen
LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
             "ﬅ": "st", "ﬆ": "st"}
QUOTES = "„“”«»‚‘’"
STRIP = ".,;:!?\"'-–—…()[]"


def fold(word: str) -> str:
    """Konventionen wegfalten: Ligaturen, Quotes, Randsatzzeichen, Groß/Klein."""
    for src, dst in LIGATURES.items():
        word = word.replace(src, dst)
    for q in QUOTES:
        word = word.replace(q, '"')
    return word.strip(STRIP).lower()


def gold_partner(ops, ocr_lines, rescued):
    """Goldzeilen-Index -> zugeordneter OCR-Text (Match/Split/Merge/Rettung)."""
    m = {}
    for o in ops:
        if o.kind == "match":
            m[o.gold[0]] = ocr_lines[o.ocr[0]]
        elif o.kind == "split":
            m[o.gold[0]] = " ".join(ocr_lines[k] for k in o.ocr)
        elif o.kind == "merge":
            joined = ocr_lines[o.ocr[0]]
            m[o.gold[0]] = m[o.gold[1]] = joined
    for gi, oi in rescued:
        m[gi] = ocr_lines[oi]
    return m


def word_partners(gold_words: list[str], ocr_words: list[str]) -> list[str | None]:
    """Je Goldwort das gegenüberstehende OCR-Wort (bzw. der ersetzende Block)."""
    out: list[str | None] = [None] * len(gold_words)
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, gold_words, ocr_words,
                                               autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                out[k] = gold_words[k]
        elif tag == "replace":
            block = " ".join(ocr_words[j1:j2])
            for k in range(i1, i2):
                out[k] = block
    return out


def collect(cfg) -> list[dict]:
    """Alle Konsens-Treffer über alle Seiten sammeln."""
    if len(cfg.systems) < 2:
        sys.exit("Gold-Audit braucht mindestens zwei OCR-Systeme in der Config.")

    found = []
    for doc, folder, gold_path in cfg.gold_files():
        graw, gnorm, _ = cfg.load_lines(gold_path)

        # je System: Goldzeile -> OCR-Text
        per_system = {}
        for system in cfg.systems:
            ocr_path = cfg.find_ocr(system, folder, doc)
            if ocr_path is None:
                continue
            _, onorm, _ = cfg.load_lines(ocr_path, system.strip_header)
            ops = align(gnorm, onorm, cfg.align)
            _, rescued = rescue(ops, gnorm, onorm, cfg.align)
            per_system[system.name] = gold_partner(ops, onorm, rescued)
        if len(per_system) < 2:
            continue

        names = list(per_system)
        for gi, gline in enumerate(gnorm):
            partners = [per_system[n].get(gi) for n in names]
            if any(p is None for p in partners):
                continue
            gwords = gline.split()
            aligned = [word_partners(gwords, p.split()) for p in partners]
            for k, gword in enumerate(gwords):
                cands = [a[k] for a in aligned]
                if any(c is None for c in cands):
                    continue
                if len(set(cands)) != 1:      # kein Konsens zwischen den Systemen
                    continue
                consensus = cands[0]
                if consensus == gword:
                    continue
                if len(consensus) < MIN_WORD or len(gword) < MIN_WORD:
                    continue
                found.append({
                    "doc": doc, "line": gi + 1, "gold": gword,
                    "consensus": consensus, "context": graw[gi],
                    "clean": fold(gword) != fold(consensus),
                })
    return found


def print_report(rows: list[dict], show_all: bool) -> None:
    clean = [r for r in rows if r["clean"]]
    folded = [r for r in rows if not r["clean"]]
    print(f"{len(rows)} Konsens-Treffer gesamt · {len(clean)} nach Bereinigung "
          f"(Ligaturen/Quotes/Satzzeichen weggefaltet)\n")
    cur = None
    for r in clean:
        if r["doc"] != cur:
            print(f"\n=== {r['doc']} ===")
            cur = r["doc"]
        print(f"  Z{r['line']:>4}  Gold »{r['gold']}«  ↔  OCR-Konsens »{r['consensus']}«")
        print(f"         {r['context'][:78]}")
    if show_all and folded:
        print(f"\n\n--- weggefaltet ({len(folded)}: nur Konventionen, keine Fehler) ---")
        for r in folded:
            print(f"  {r['doc']} Z{r['line']:>4}  »{r['gold']}« ↔ »{r['consensus']}«")


def write_md(rows: list[dict], path: Path, cfg) -> None:
    clean = [r for r in rows if r["clean"]]
    sysnames = " und ".join(s.label or s.name for s in cfg.systems)
    lines = [
        "# Goldstandard — Fehlerkandidaten zum Durchgehen",
        "",
        f"Automatisch erzeugt mit `code/gold_audit.py` ({cfg.project}).",
        "",
        f"Methode: Stellen, an denen **{sysnames} dasselbe Wort lesen, das Gold aber",
        "ein anderes** hat. Zwei unabhängige Engines als Konsens → das Gold ist der",
        "Ausreißer. Vergleich auf normalisiertem Text; Ligaturen, typografische",
        "Anführungszeichen und reine Satzzeichen sind weggefaltet.",
        "",
        "**Kandidaten, keine Gewissheiten** — bitte am Scan prüfen. Achtung: Irren beide",
        "OCR gleich (z. B. langes ſ als „f“), ist das Gold richtig und der Treffer ein",
        "Fehlalarm. Zeilennummer = Spalte „#“ im Review-Viewer.",
        "",
        f"Stand: {len(clean)} Kandidaten auf {len(set(r['doc'] for r in clean))} Seiten.",
        "",
        "| ☐ | Seite | Zeile | Gold | OCR-Konsens | Kontext |",
        "|---|---|---|---|---|---|",
    ]
    for r in clean:
        ctx = r["context"][:70].replace("|", "\\|")
        lines.append(f"| ☐ | {r['doc']} | {r['line']} | `{r['gold']}` | "
                     f"`{r['consensus']}` | {ctx} |")
    lines += ["", "---", "",
              "Erzeugen mit: `python code/gold_audit.py --md analysis/gold_candidates.md`"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nCheckliste geschrieben: {path}")


def main() -> None:
    args = list(sys.argv[1:])
    cfg_path = None
    md_path = None
    if "--config" in args:
        k = args.index("--config")
        cfg_path = args[k + 1]
        del args[k:k + 2]
    if "--md" in args:
        k = args.index("--md")
        md_path = Path(args[k + 1])
        del args[k:k + 2]
    show_all = "--all" in args

    cfg = load_config(cfg_path)
    rows = collect(cfg)
    print_report(rows, show_all)
    if md_path:
        write_md(rows, md_path, cfg)


if __name__ == "__main__":
    main()
