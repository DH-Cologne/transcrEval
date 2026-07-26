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
    file: str = "{doc}_ocr_{name}.txt"  # Dateimuster im Seitenordner; {doc} wird ersetzt
    label: str = ""                 # Anzeigename im Review (Default: name)
    source: str = ""                # Provenienz (OCR-Engine/Modell/Jahr), frei
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
    page_glob: str          # Glob für die Seitenordner unter data_dir
    doc_key: re.Pattern     # Regex, Gruppe 1 = Dokumentschlüssel (aus Ordnername)
    gold_file: str          # Dateimuster des Goldstandards im Seitenordner
    systems: list[SystemCfg]
    norm: NormalizeCfg
    align: AlignCfg
    labels: dict[str, str]
    word_tokenizer: str = "punct_separate"   # siehe tokenize()

    # --- Normalisierung ------------------------------------------------
    def normalize(self, line: str) -> str:
        if self.norm.unicode:
            line = unicodedata.normalize(self.norm.unicode, line)
        for src, dst in self.norm.replace.items():
            line = line.replace(src, dst)
        if self.norm.collapse_whitespace:
            line = " ".join(line.split())
        return line

    _TOKEN_PATTERNS = {
        "whitespace": r"\S+",       # Interpunktion klebt am Wort (strengste Variante)
        "punct_ignore": r"\w+",     # Satzzeichen bleiben unberücksichtigt (ISRI-Praxis)
        "punct_separate": r"\w+|[^\w\s]",   # Satzzeichen als eigene Token (OCR-D-Praxis)
    }

    def token_pattern(self) -> str:
        return self._TOKEN_PATTERNS.get(self.word_tokenizer,
                                        self._TOKEN_PATTERNS["punct_separate"])

    def tokenize(self, line: str) -> list[str]:
        """Wörter für die WER; Konvention konfigurierbar über word_tokenizer."""
        return re.findall(self.token_pattern(), line, re.UNICODE)

    def tokenize_spans(self, line: str) -> list[tuple[str, int, int]]:
        """Wie tokenize(), zusätzlich mit (Token, Start, Ende).

        Erlaubt es der Visualisierung, exakt dieselbe Tokenisierung wie die Metrik
        zu verwenden und trotzdem die Originalschreibung inkl. Abstände zu zeigen.
        """
        return [(m.group(0), m.start(), m.end())
                for m in re.finditer(self.token_pattern(), line, re.UNICODE)]

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

    # --- Dateierkennung (ein Ordner je Seite) --------------------------
    def doc_of(self, name: str) -> str | None:
        m = self.doc_key.search(name)
        return m.group(1) if m else None

    def pages(self) -> list[tuple[str, Path]]:
        """(doc, Seitenordner) für alle Ordner, die zum page_glob passen."""
        out = []
        for folder in sorted(self.data_dir.glob(self.page_glob)):
            if not folder.is_dir():
                continue
            doc = self.doc_of(folder.name)
            if doc:
                out.append((doc, folder))
        return out

    def gold_of(self, folder: Path, doc: str) -> Path | None:
        cand = sorted(folder.glob(self.gold_file.format(doc=doc)))
        return cand[0] if cand else None

    def gold_files(self) -> list[tuple[str, Path, Path]]:
        """(doc, Seitenordner, Gold-Pfad) für Seiten MIT Goldstandard."""
        out = []
        for doc, folder in self.pages():
            gold = self.gold_of(folder, doc)
            if gold:
                out.append((doc, folder, gold))
        return out

    def system(self, name: str) -> SystemCfg:
        return next(s for s in self.systems if s.name == name)

    def find_ocr(self, system: SystemCfg, folder: Path, doc: str) -> Path | None:
        cand = sorted(folder.glob(system.file.format(doc=doc, name=system.name)))
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
            file=s.get("file", "{doc}_ocr_{name}.txt"),
            label=s.get("label", ""),
            source=s.get("source", ""),
            strip_header=re.compile(s["strip_header"]) if s.get("strip_header") else None,
        ))

    return Config(
        root=root,
        project=data.get("project", cfg_path.stem),
        data_dir=data_dir,
        results_dir=rel("results_dir", "results"),
        viz_dir=rel("viz_dir", "viz"),
        page_glob=data.get("page_glob", "*"),
        doc_key=re.compile(data.get("doc_key", r"(.+)")),
        gold_file=gold.get("file", "{doc}_gold_*.txt"),
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
        word_tokenizer=data.get("word_tokenizer", "punct_separate"),
    )
