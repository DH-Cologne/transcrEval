#!/usr/bin/env python3
"""Erzeugt einen scrollbaren Fehler-Review: Gold neben jedem OCR-System.

Abweichungen werden farbig unterlegt:
  - Wortfehler       orange (heller)
  - Zeichenfehler    hellrot (innerhalb des Wortes)
  - verschobene Zeile/Block  hellgelb (Zelle), mit Ereignis-Tag + Verschiebedistanz
  - fehlende Goldzeile / OCR-Zeile ohne Goldentsprechung: eigene Markierung

Die Spalten (ein OCR-System je Spalte) werden aus der Config abgeleitet -- der
Viewer ist damit für beliebig viele Systeme nutzbar. Hervorhebung wird gegen den
NORMALISIERTEN Text berechnet (sonst dominiert die Schreibweise); ein Umschalter
zeigt wahlweise Roh- oder Normtext.

Aufruf:  python code/build_review.py [--config PFAD] [--min-block N]
Ausgabe: <viz>/review.html  (eigenständig, offline im Browser öffenbar)
"""

from __future__ import annotations

import bisect
import html
import json
import sys

from align import align, block_runs, rescue
from config import load_config


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def char_hl(gold: str, ocr: str) -> str:
    """OCR-Seite mit hellrot markierten Zeichenabweichungen ggü. gold."""
    from difflib import SequenceMatcher
    out = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, gold, ocr, autojunk=False).get_opcodes():
        seg = esc(ocr[j1:j2])
        if tag == "equal":
            out.append(seg)
        elif tag in ("replace", "insert"):
            out.append(f'<span class="cerr">{seg}</span>')
        elif tag == "delete":  # im OCR fehlende Goldzeichen
            out.append(f'<span class="omit" title="fehlt: {esc(gold[i1:i2])}">‸</span>')
    return "".join(out)


def word_hl(gold: str, ocr: str) -> str:
    """OCR-Text: abweichende Wörter orange, darin Zeichen hellrot. gold==ocr -> plain."""
    from difflib import SequenceMatcher
    gw, ow = gold.split(), ocr.split()
    parts = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, gw, ow, autojunk=False).get_opcodes():
        if tag == "equal":
            parts.append(esc(" ".join(ow[j1:j2])))
        elif tag == "delete":  # ganze Goldwörter fehlen im OCR
            parts.append(f'<span class="omit" title="fehlt: {esc(" ".join(gw[i1:i2]))}">‸</span>')
        else:  # replace / insert
            inner = char_hl(" ".join(gw[i1:i2]), " ".join(ow[j1:j2]))
            parts.append(f'<span class="werr">{inner}</span>')
    return " ".join(p for p in parts if p)


def build_column(cfg, graw, gnorm, oraw, onorm, min_block):
    """Liefert cells[gi] und spurious[anchor_gi] für eine OCR-Spalte."""
    ops = align(gnorm, onorm, cfg.align)
    pos, rescued = rescue(ops, gnorm, onorm, cfg.align)
    resc_map = dict(rescued)
    resc_o = {oi for _, oi in rescued}
    _, blocks, event_of = block_runs([gi for gi, _ in rescued], pos, min_block)

    def cell(st, tag, graw_s, gnorm_s, oraw_s, onorm_s):
        return {"st": st, "tag": tag,
                "raw": word_hl(graw_s, oraw_s), "norm": word_hl(gnorm_s, onorm_s)}

    cells = {}
    for o in ops:
        if o.kind == "match":
            gi, oi = o.gold[0], o.ocr[0]
            cells[gi] = cell("match", "", graw[gi], gnorm[gi], oraw[oi], onorm[oi])
        elif o.kind == "split":
            gi = o.gold[0]
            cells[gi] = cell("split", "getrennt", graw[gi], gnorm[gi],
                             " ".join(oraw[k] for k in o.ocr), " ".join(onorm[k] for k in o.ocr))
        elif o.kind == "merge":
            g0, g1 = o.gold
            oi = o.ocr[0]
            cells[g0] = cell("merge", "zusammengezogen",
                             graw[g0] + " " + graw[g1], gnorm[g0] + " " + gnorm[g1],
                             oraw[oi], onorm[oi])
            cells[g1] = {"st": "merge2", "tag": "", "raw": "⟵ mit voriger Zeile zusammengezogen",
                         "norm": "⟵ mit voriger Zeile zusammengezogen"}

    # Verschiebedistanz: erwartete OCR-Position aus benachbarten in-Ordnung-Zeilen
    anchors = sorted((gi, pos[gi]) for gi, c in cells.items()
                     if c["st"] in ("match", "split", "merge") and pos[gi] is not None)
    ag = [a[0] for a in anchors]
    ap_ = [a[1] for a in anchors]

    def off_label(gi):
        if pos[gi] is None or not anchors:
            return ""
        r = bisect.bisect_left(ag, gi)
        left = r - 1 if r - 1 >= 0 else None
        right = r if r < len(ag) else None
        if left is not None and right is not None:
            gl, pl, gr, pr = ag[left], ap_[left], ag[right], ap_[right]
            exp = pl + (gi - gl) / (gr - gl) * (pr - pl)
        elif left is not None:
            exp = ap_[left] + (gi - ag[left])
        elif right is not None:
            exp = ap_[right] - (ag[right] - gi)
        else:
            exp = gi
        o = round(pos[gi] - exp)
        return f"{o}↓" if o > 0 else (f"{-o}↑" if o < 0 else "±0")

    for gi, oi in resc_map.items():
        ol = off_label(gi)
        if gi in event_of:
            st, tag = "disloc_block", f"Block ▮{event_of[gi]} · {ol}"
        else:
            st, tag = "disloc_row", f"verschoben {ol}"
        cells[gi] = cell(st, tag, graw[gi], gnorm[gi], oraw[oi], onorm[oi])

    for o in ops:  # fehlende Goldzeilen
        if o.kind == "gap_gold" and o.gold[0] not in cells:
            cells[o.gold[0]] = {"st": "missing", "tag": "im OCR nicht gefunden",
                                "raw": "—", "norm": "—"}

    spurious = {}  # OCR-Zeilen ohne Goldentsprechung, an letzte Goldzeile verankert
    last_gi = -1
    for o in ops:
        if o.kind in ("match", "split", "merge", "gap_gold"):
            last_gi = max(o.gold)
        elif o.kind == "gap_ocr" and o.ocr[0] not in resc_o:
            oi = o.ocr[0]
            spurious.setdefault(last_gi, []).append(
                {"st": "spurious", "tag": "ohne Goldentsprechung",
                 "raw": esc(oraw[oi]), "norm": esc(onorm[oi])})
    return cells, spurious


NA = {"st": "na", "tag": "", "raw": "", "norm": ""}
EMPTY = {"st": "empty", "tag": "", "raw": "", "norm": ""}


def build_doc(cfg, doc, gold_path, min_block, sysnames):
    graw, gnorm, _ = cfg.load_lines(gold_path)
    columns = {}  # name -> (cells, spurious)
    for system in cfg.systems:
        ocr_path = cfg.find_ocr(system, doc)
        if ocr_path is None:
            continue
        oraw, onorm, _ = cfg.load_lines(ocr_path, system.strip_header)
        columns[system.name] = build_column(cfg, graw, gnorm, oraw, onorm, min_block)

    def sysrow(gi):
        out = {}
        for name in sysnames:
            out[name] = columns[name][0].get(gi, NA) if name in columns else NA
        return out

    def spurious_row(name, cell):
        return {"n": None, "g": None,
                "sys": {n: (cell if n == name else EMPTY) for n in sysnames}}

    rows = []
    for name in sysnames:  # spurious ganz am Anfang (Anker -1)
        for anch in (columns.get(name, ({}, {}))[1]).get(-1, []):
            rows.append(spurious_row(name, anch))
    for gi in range(len(graw)):
        rows.append({"n": gi + 1,
                     "g": {"raw": esc(graw[gi]), "norm": esc(gnorm[gi])},
                     "sys": sysrow(gi)})
        for name in sysnames:
            for anch in (columns.get(name, ({}, {}))[1]).get(gi, []):
                rows.append(spurious_row(name, anch))

    return {"doc": doc, "label": cfg.labels.get(doc, doc),
            "present": list(columns.keys()), "rows": rows}


def main():
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

    sysnames = [s.name for s in cfg.systems]
    syscols = [{"k": s.name, "t": s.label} for s in cfg.systems]
    docs = [build_doc(cfg, doc, gold_path, min_block, sysnames)
            for doc, gold_path in cfg.gold_files()]

    cfg.viz_dir.mkdir(exist_ok=True)
    out = cfg.viz_dir / "review.html"
    payload = json.dumps({"project": cfg.project, "min_block": min_block,
                          "systems": syscols, "docs": docs}, ensure_ascii=False)
    out.write_text(TEMPLATE.replace("/*DATA*/", payload), encoding="utf-8")

    n_rows = sum(len(d["rows"]) for d in docs)
    print(f"geschrieben: {out}")
    print(f"{len(docs)} Dokumente, {len(sysnames)} Systeme, min_block={min_block}, {n_rows} Zeilen")
    print("Im Browser öffnen (lokal per Doppelklick / file://).")


TEMPLATE = r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>transcrEval — Fehler-Review</title>
<style>
  :root{
    --bg:#faf8f3; --panel:#fff; --ink:#221f1a; --muted:#6b655b; --line:#e2dccf;
    --gutter:#f0ece3; --head:#efe9dc;
    --c-char:#ff9a9a; --c-word:#ffd9a3; --c-disloc:#fdf3b6; --c-missing:#f3c9c9;
    --c-spur:#e6e2da; --accent:#1367a0;
    --mono:"SFMono-Regular",ui-monospace,Menlo,monospace;
    --serif:"Iowan Old Style",Georgia,"Times New Roman",serif;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  }
  @media (prefers-color-scheme:dark){:root{
    --bg:#16140f; --panel:#1e1b15; --ink:#ece7db; --muted:#9a9184; --line:#332f27;
    --gutter:#211e18; --head:#262219;
    --c-char:#a13b3b; --c-word:#8a5a1e; --c-disloc:#6b5e1c; --c-missing:#5e2a2a;
    --c-spur:#2f2b23; --accent:#4a9fd4;
  }}
  :root[data-theme=dark]{
    --bg:#16140f; --panel:#1e1b15; --ink:#ece7db; --muted:#9a9184; --line:#332f27;
    --gutter:#211e18; --head:#262219;
    --c-char:#a13b3b; --c-word:#8a5a1e; --c-disloc:#6b5e1c; --c-missing:#5e2a2a;
    --c-spur:#2f2b23; --accent:#4a9fd4;
  }
  :root[data-theme=light]{
    --bg:#faf8f3; --panel:#fff; --ink:#221f1a; --muted:#6b655b; --line:#e2dccf;
    --gutter:#f0ece3; --head:#efe9dc;
    --c-char:#ff9a9a; --c-word:#ffd9a3; --c-disloc:#fdf3b6; --c-missing:#f3c9c9;
    --c-spur:#e6e2da; --accent:#1367a0;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%}
  body{background:var(--bg);color:var(--ink);font-family:var(--sans);
    display:flex;flex-direction:column;height:100vh;overflow:hidden}
  header{padding:12px 18px 0;border-bottom:1px solid var(--line);background:var(--panel);flex:none}
  .titlerow{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
  h1{font-family:var(--serif);font-size:19px;font-weight:600;margin:0}
  .sub{color:var(--muted);font-size:12.5px}
  .controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0}
  .docs{display:flex;gap:6px;flex-wrap:wrap}
  button.doc,button.ui{font-family:var(--mono);font-size:12px;border:1px solid var(--line);
    background:var(--panel);color:var(--muted);border-radius:16px;padding:5px 12px;cursor:pointer}
  button.doc.active{background:var(--accent);color:#fff;border-color:var(--accent)}
  button.ui.on{background:var(--accent);color:#fff;border-color:var(--accent)}
  .spacer{flex:1}
  .legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted);padding:2px 0 10px}
  .legend span{display:inline-flex;align-items:center;gap:6px}
  .sw{width:12px;height:12px;border-radius:3px;display:inline-block;border:1px solid rgba(0,0,0,.12)}
  .scroll{overflow:auto;flex:1}
  .grid{display:grid;width:max-content;min-width:100%;
    font-family:var(--serif);font-size:14.5px;line-height:1.5}
  .ghead{position:sticky;top:0;z-index:2;background:var(--head);color:var(--muted);
    font-family:var(--sans);font-size:11px;letter-spacing:.08em;text-transform:uppercase;
    font-weight:600;padding:9px 12px;border-bottom:1px solid var(--line);
    border-left:1px solid var(--line);cursor:pointer;white-space:nowrap}
  .ghead .caret{color:var(--accent);font-weight:700}
  .ghead.guth{position:sticky;left:0;z-index:4;cursor:default}
  .ghead.clp{writing-mode:vertical-rl;text-orientation:mixed;padding:9px 6px;overflow:hidden}
  .cell{padding:5px 12px;border-bottom:1px solid var(--line);border-left:1px solid var(--line);
    white-space:nowrap;min-height:1.5em}
  .cell.clp{overflow:hidden}
  .gut{position:sticky;left:0;z-index:1;padding:5px 6px;text-align:right;color:var(--muted);
    font-family:var(--mono);font-size:11px;background:var(--gutter);
    border-bottom:1px solid var(--line);-webkit-user-select:none;user-select:none}
  .col-gold{color:var(--ink)}
  .werr{background:var(--c-word);border-radius:3px;padding:0 1px;
    -webkit-box-decoration-break:clone;box-decoration-break:clone}
  .cerr{background:var(--c-char);border-radius:2px;
    -webkit-box-decoration-break:clone;box-decoration-break:clone}
  .omit{color:#c0392b;font-weight:700;cursor:help}
  :root[data-theme=dark] .omit{color:#ff8a80}
  @media (prefers-color-scheme:dark){.omit{color:#ff8a80}}
  .st-disloc_row,.st-disloc_block{background:var(--c-disloc)}
  .st-missing{background:var(--c-missing);color:var(--muted);font-style:italic}
  .st-spurious{background:var(--c-spur);font-style:italic}
  .st-merge2,.st-na,.st-empty{color:var(--muted);font-style:italic}
  .st-na{opacity:.5}
  .tag{display:inline-block;font-family:var(--sans);font-size:9.5px;font-weight:700;
    letter-spacing:.04em;text-transform:uppercase;color:var(--muted);
    border:1px solid var(--line);border-radius:4px;padding:0 4px;margin-right:6px;
    vertical-align:1px;background:var(--panel)}
  .toggle-theme{position:fixed;bottom:12px;right:14px;z-index:5;font-family:var(--mono);
    font-size:11px;border:1px solid var(--line);background:var(--panel);color:var(--muted);
    border-radius:16px;padding:5px 11px;cursor:pointer}
  .empty-note{padding:24px;color:var(--muted);font-size:13px}
</style></head>
<body>
<header>
  <div class="titlerow">
    <h1>Fehler-Review</h1>
    <span class="sub" id="sub">Gold gegen OCR · Hervorhebung gegen normalisierten Text</span>
  </div>
  <div class="controls">
    <div class="docs" id="docs"></div>
    <span class="spacer"></span>
    <button class="ui" id="btnMode">Ansicht: normalisiert</button>
    <button class="ui" id="btnOnlyErr">nur Abweichungen</button>
  </div>
  <div class="legend">
    <span><i class="sw" style="background:var(--c-word)"></i>Wortfehler</span>
    <span><i class="sw" style="background:var(--c-char)"></i>Zeichenfehler</span>
    <span><i class="sw" style="background:var(--c-disloc)"></i>Zeile/Block verschoben</span>
    <span><i class="sw" style="background:var(--c-missing)"></i>im OCR fehlt</span>
    <span><i class="sw" style="background:var(--c-spur)"></i>ohne Goldentsprechung</span>
    <span>‸ = ausgelassener Text (Tooltip) · Spaltenkopf klicken = ein-/ausklappen</span>
  </div>
</header>
<div class="scroll"><div class="grid" id="grid"></div></div>
<button class="toggle-theme" id="btnTheme">◐ Theme</button>

<script>
const PAYLOAD = /*DATA*/;
const SYSCOLS = PAYLOAD.systems;                       // [{k,t}] je OCR-System
const COLS = [{k:"gold",t:"Goldstandard"}].concat(SYSCOLS);
let curDoc = 0, mode = "norm", onlyErr = false;
const collapsed = {}; COLS.forEach(c => collapsed[c.k] = false);
const ERRST = new Set(["disloc_row","disloc_block","missing","spurious"]);
const grid = document.getElementById("grid");
const bodyOf = c => (mode==="raw"? c.raw : c.norm) || "";

function template(){
  return "52px " + COLS.map(c => collapsed[c.k] ? "34px" : "max-content").join(" ");
}
function colCell(r, c){
  if(collapsed[c.k]) return `<div class="cell clp col-${c.k}"></div>`;
  if(c.k==="gold") return `<div class="cell col-gold">${r.g? bodyOf(r.g):""}</div>`;
  const cell = r.sys[c.k];
  if(!cell) return `<div class="cell col-${c.k}"></div>`;
  const tag = cell.tag ? `<span class="tag">${cell.tag}</span>` : "";
  return `<div class="cell col-${c.k} st-${cell.st}">${tag}${bodyOf(cell)}</div>`;
}
function rowHasErr(r){
  if(r.g===null) return true;
  for(const c of SYSCOLS){
    const cell = r.sys[c.k];
    if(!cell) continue;
    if(ERRST.has(cell.st)) return true;
    const h = bodyOf(cell);
    if(h.includes("werr")||h.includes("cerr")||h.includes("omit")) return true;
  }
  return false;
}
function headHtml(){
  let h = `<div class="ghead guth">#</div>`;
  for(const c of COLS){
    const cls = collapsed[c.k] ? "ghead clp" : "ghead";
    h += `<div class="${cls}" data-col="${c.k}"><span class="caret">${collapsed[c.k]?"▸":"▾"}</span> ${c.t}</div>`;
  }
  return h;
}
function render(){
  const d = PAYLOAD.docs[curDoc];
  grid.style.gridTemplateColumns = template();
  let html = headHtml(), shown = 0;
  for(const r of d.rows){
    if(onlyErr && !rowHasErr(r)) continue;
    shown++;
    html += `<div class="gut">${r.n??""}</div>` + COLS.map(c => colCell(r, c)).join("");
  }
  grid.innerHTML = html;
  if(shown===0) grid.innerHTML += `<div class="empty-note" style="grid-column:1/-1">Keine Abweichungen in dieser Ansicht.</div>`;
  grid.querySelectorAll(".ghead[data-col]").forEach(el => el.onclick = ()=>{
    collapsed[el.dataset.col] = !collapsed[el.dataset.col]; render();
  });
}
function renderDocs(){
  document.getElementById("docs").innerHTML = PAYLOAD.docs.map((d,i)=>
    `<button class="doc ${i===curDoc?'active':''}" data-i="${i}">${d.label}</button>`).join("");
  document.querySelectorAll("button.doc").forEach(b=>b.onclick=()=>{
    curDoc=+b.dataset.i; renderDocs(); render();
    document.querySelector(".scroll").scrollTop=0; document.querySelector(".scroll").scrollLeft=0;
  });
}
document.getElementById("btnMode").onclick = e=>{
  mode = mode==="norm"?"raw":"norm";
  e.target.textContent = "Ansicht: "+(mode==="norm"?"normalisiert":"roh");
  e.target.classList.toggle("on", mode==="raw");
  render();
};
document.getElementById("btnOnlyErr").onclick = e=>{
  onlyErr=!onlyErr; e.target.classList.toggle("on",onlyErr); render();
};
document.getElementById("btnTheme").onclick = ()=>{
  const root=document.documentElement;
  const cur=root.getAttribute("data-theme")||(matchMedia("(prefers-color-scheme:dark)").matches?"dark":"light");
  root.setAttribute("data-theme", cur==="dark"?"light":"dark");
};
document.getElementById("sub").textContent =
  PAYLOAD.project + " · Hervorhebung gegen normalisierten Text";
renderDocs(); render();
</script>
</body></html>
"""

if __name__ == "__main__":
    main()
