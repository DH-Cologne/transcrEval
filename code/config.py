#!/usr/bin/env python3
"""Projektkonfiguration für transcrEval.

Lädt eine JSON-Config (Default: config.json im Projektwurzelverzeichnis) und stellt
alle projektspezifischen Einstellungen bereit: Pfade, OCR-Systeme, Normalisierung,
Alignment-Schwellwerte, Labels. Der übrige Code ist dadurch generisch und für
weitere OCR-Auswertungsprojekte nutzbar -- ein neues Projekt = neue config.json.

JSON wurde gewählt, weil R (jsonlite) es nativ liest; Kommentare ersetzt das
Feld "_about" und die Schema-Doku im README.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.json"


@dataclass
class NormalizeCfg:
    unicode: str | None = "NFC"
    collapse_whitespace: bool = True
    replace: dict[str, str] = field(default_factory=dict)


@dataclass
class AlignCfg:
    gap: float = 0.35
    split_penalty: float = 0.10
    match_cutoff: float = 0.60
    rescue_cutoff: float = 0.50
    min_block: int = 2


@dataclass
class SystemCfg:
    name: str                       # Kurzname -> CSV-Suffix
    dir: Path
    label: str = ""                 # Anzeigename im Review (Default: name)
    glob: str = "{doc}*.txt"
    strip_header: re.Pattern | None = None  # Zeilen, die als Header verworfen werden

    def __post_init__(self):
        if not self.label:
            self.label = self.name


@dataclass
class Config:
    root: Path
    project: str
    data_dir: Path
    results_dir: Path
    viz_dir: Path
    gold_dir: Path
    gold_glob: str
    doc_key: re.Pattern
    systems: list[SystemCfg]
    norm: NormalizeCfg
    align: AlignCfg
    labels: dict[str, str]

    # --- Normalisierung ------------------------------------------------
    def normalize(self, line: str) -> str:
        if self.norm.unicode:
            line = unicodedata.normalize(self.norm.unicode, line)
        for src, dst in self.norm.replace.items():
            line = line.replace(src, dst)
        if self.norm.collapse_whitespace:
            line = " ".join(line.split())
        return line

    def is_content(self, line: str, header: re.Pattern | None) -> bool:
        return bool(line.strip()) and not (header and header.match(line))

    def load_lines(self, path: Path, header: re.Pattern | None = None):
        """(raw, normalisiert, block_id) je Inhaltszeile; block_id zählt an Leerzeilen."""
        raw: list[str] = []
        blocks: list[int] = []
        blk, prev_blank = 0, False
        for line in path.read_text(encoding="utf-8").splitlines():
            if self.is_content(line, header):
                if prev_blank and raw:
                    blk += 1
                raw.append(line)
                blocks.append(blk)
                prev_blank = False
            elif not line.strip():
                prev_blank = True
        return raw, [self.normalize(l) for l in raw], blocks

    # --- Dateierkennung ------------------------------------------------
    def doc_of(self, filename: str) -> str | None:
        m = self.doc_key.search(filename)
        return m.group(1) if m else None

    def gold_files(self) -> list[tuple[str, Path]]:
        out = []
        for p in sorted(self.gold_dir.glob(self.gold_glob)):
            doc = self.doc_of(p.name)
            if doc:
                out.append((doc, p))
        return out

    def system(self, name: str) -> SystemCfg:
        return next(s for s in self.systems if s.name == name)

    def find_ocr(self, system: SystemCfg, doc: str) -> Path | None:
        cand = sorted(system.dir.glob(system.glob.format(doc=doc)))
        return cand[0] if cand else None


def load_config(path: str | Path | None = None) -> Config:
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    if not cfg_path.exists():
        raise SystemExit(f"Config nicht gefunden: {cfg_path}")
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    root = cfg_path.resolve().parent

    def rel(key, default):
        return root / data.get(key, default)

    data_dir = rel("data_dir", "data")
    gold = data.get("gold", {})
    norm = data.get("normalize", {})
    aln = data.get("align", {})

    systems = []
    for s in data.get("systems", []):
        systems.append(SystemCfg(
            name=s["name"],
            dir=data_dir / s["dir"],
            label=s.get("label", ""),
            glob=s.get("glob", "{doc}*.txt"),
            strip_header=re.compile(s["strip_header"]) if s.get("strip_header") else None,
        ))

    return Config(
        root=root,
        project=data.get("project", cfg_path.stem),
        data_dir=data_dir,
        results_dir=rel("results_dir", "results"),
        viz_dir=rel("viz_dir", "viz"),
        gold_dir=data_dir / gold.get("dir", "goldstandard"),
        gold_glob=gold.get("glob", "*.txt"),
        doc_key=re.compile(gold.get("doc_key", r"^([^_.]+)")),
        systems=systems,
        norm=NormalizeCfg(
            unicode=norm.get("unicode", "NFC"),
            collapse_whitespace=norm.get("collapse_whitespace", True),
            replace=norm.get("replace", {}),
        ),
        align=AlignCfg(
            gap=aln.get("gap", 0.35),
            split_penalty=aln.get("split_penalty", 0.10),
            match_cutoff=aln.get("match_cutoff", 0.60),
            rescue_cutoff=aln.get("rescue_cutoff", 0.50),
            min_block=aln.get("min_block", 2),
        ),
        labels=data.get("labels", {}),
    )
