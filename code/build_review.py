#!/usr/bin/env python3
"""Erzeugt einen scrollbaren Fehler-Review: Gold | altes OCR | neues OCR nebeneinander.

Abweichungen werden farbig unterlegt:
  - Wortfehler       orange (heller)
  - Zeichenfehler    hellrot (innerhalb des Wortes)
  - verschobene Zeile/Block  hellgelb (Zelle), mit Ereignis-Tag
  - fehlende Goldzeile / OCR-Zeile ohne Goldentsprechung: eigene Markierung

Hervorhebung wird gegen den NORMALISIERTEN Text berechnet (sonst dominiert ſ/s);
ein Umschalter im Viewer zeigt wahlweise Roh- oder Normtext. Das Layout ist auf
eine spätere vierte Spalte (PDF) vorbereitet.

Aufruf:  python code/build_review.py [--min-block N]
Ausgabe: viz/review.html  (eigenständig, offline im Browser öffenbar)
"""

from __future__ import annotations

import bisect
import html
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

from align_prototype import RESCUE_CUTOFF, align, dist
from metrics import MIN_BLOCK_LINES, load

DATA = Path(__file__).resolve().parent.parent / "data"
VIZ = Path(__file__).resolve().parent.parent / "viz"

DOC_LABELS = {
    "aze19190115-2": "15.01.1919 · S. 2",
    "aze19210110-2": "10.01.1921 · S. 2",
    "aze19260523-12": "23.05.1926 · S. 12",
    "aze19280101-1": "01.01.1928 · S. 1",
    "aze19281009-6": "09.10.1928 · S. 6",
    "aze19281111-9": "11.11.1928 · S. 9",
    "aze19291229-13": "29.12.1929 · S. 13",
    "aze19321217-5": "17.12.1932 · S. 5",
}


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def char_hl(gold: str, ocr: str) -> str:
    """OCR-Seite mit hellrot markierten Zeichenabweichungen ggü. gold."""
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


def align_pair(gnorm, onorm, min_block):
    """Alignment + Positionsbestimmung + Verschiebungs-Läufe (wie metrics.py)."""
    ops = align(gnorm, onorm)
    pos = [None] * len(gnorm)
    for o in ops:
        if o.kind in ("match", "split"):
            pos[o.gold[0]] = o.ocr[0]
        elif o.kind == "merge":
            pos[o.gold[0]] = o.ocr[0]
            pos[o.gold[1]] = o.ocr[0]
    ug = [k for o in ops if o.kind == "gap_gold" for k in o.gold]
    uo = [k for o in ops if o.kind == "gap_ocr" for k in o.ocr]
    rescued = []
    if ug and uo:
        cand = sorted(((dist(gnorm[gi], onorm[oi]), gi, oi) for gi in ug for oi in uo),
                      key=lambda t: t[0])
        usg, uso = set(), set()
        for d, gi, oi in cand:
            if d >= RESCUE_CUTOFF:
                break
            if gi in usg or oi in uso:
                continue
            usg.add(gi)
            uso.add(oi)
            rescued.append((gi, oi))
    for gi, oi in rescued:
        pos[gi] = oi
    resc_g = {gi for gi, _ in rescued}
    resc_o = {oi for _, oi in rescued}
    resc_map = dict(rescued)
    # Verschiebungs-Läufe -> Ereignis-Index je Goldzeile
    rl = sorted(resc_g)
    event_of = {}
    ev = 0
    i = 0
    while i < len(rl):
        j = i
        while (j + 1 < len(rl) and rl[j + 1] == rl[j] + 1 and pos[rl[j + 1]] >= pos[rl[j]]):
            j += 1
        if j - i + 1 >= min_block:
            ev += 1
            for k in range(i, j + 1):
                event_of[rl[k]] = ev
        i = j + 1
    return ops, resc_g, resc_o, resc_map, event_of, pos


def build_column(graw, gnorm, oraw, onorm, min_block):
    """Liefert cells[gi] und spurious[anchor_gi] für eine OCR-Spalte."""
    ops, resc_g, resc_o, resc_map, event_of, pos = align_pair(gnorm, onorm, min_block)

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
            cells[gi] = cell("split", "getrennt",
                             graw[gi], gnorm[gi],
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
    # interpolieren; Offset = tatsächliche minus erwartete Position (in Zeilen).
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

    # dislozierte Zeilen (waren gap_gold) überschreiben / ergänzen
    for gi, oi in resc_map.items():
        ol = off_label(gi)
        if gi in event_of:
            st, tag = "disloc_block", f"Block ▮{event_of[gi]} · {ol}"
        else:
            st, tag = "disloc_row", f"verschoben {ol}"
        cells[gi] = cell(st, tag, graw[gi], gnorm[gi], oraw[oi], onorm[oi])
    # fehlende Goldzeilen (gap_gold, nicht gerettet)
    for o in ops:
        if o.kind == "gap_gold":
            gi = o.gold[0]
            if gi not in cells:
                cells[gi] = {"st": "missing", "tag": "im OCR nicht gefunden",
                             "raw": "—", "norm": "—"}
    # OCR-Zeilen ohne Goldentsprechung (spurious), an letzte Goldzeile verankert
    spurious = {}
    last_gi = -1
    for o in ops:
        if o.kind in ("match", "split", "merge", "gap_gold"):
            last_gi = max(o.gold)
        elif o.kind == "gap_ocr":
            oi = o.ocr[0]
            if oi in resc_o:
                continue
            spurious.setdefault(last_gi, []).append(
                {"st": "spurious", "tag": "ohne Goldentsprechung",
                 "raw": esc(oraw[oi]), "norm": esc(onorm[oi])})
    return cells, spurious


def build_doc(doc, gold_path, min_block):
    graw, gnorm, _ = load(gold_path)
    new_c = old_c = None
    new_s = old_s = {}
    npath = sorted((DATA / "newOCR").glob(f"{doc}_*.txt")) or sorted((DATA / "newOCR").glob(f"{doc}*.txt"))
    opath = sorted((DATA / "oldOCR").glob(f"{doc}_*.txt")) or sorted((DATA / "oldOCR").glob(f"{doc}*.txt"))
    if npath:
        nraw, nnorm, _ = load(npath[0])
        new_c, new_s = build_column(graw, gnorm, nraw, nnorm, min_block)
    if opath:
        oraw2, onorm2, _ = load(opath[0])
        old_c, old_s = build_column(graw, gnorm, oraw2, onorm2, min_block)

    def occ(cells, gi):
        if cells is None:
            return {"st": "na", "tag": "", "raw": "", "norm": ""}
        return cells.get(gi, {"st": "na", "tag": "", "raw": "", "norm": ""})

    def empty():
        return {"st": "empty", "tag": "", "raw": "", "norm": ""}

    rows = []
    for anch in old_s.get(-1, []):  # spurious ganz am Anfang
        rows.append({"n": None, "g": None, "new": empty(), "old": anch})
    for anch in new_s.get(-1, []):
        rows.append({"n": None, "g": None, "new": anch, "old": empty()})
    for gi in range(len(graw)):
        rows.append({"n": gi + 1,
                     "g": {"raw": esc(graw[gi]), "norm": esc(gnorm[gi])},
                     "new": occ(new_c, gi), "old": occ(old_c, gi)})
        for anch in new_s.get(gi, []):
            rows.append({"n": None, "g": None, "new": anch, "old": empty()})
        for anch in old_s.get(gi, []):
            rows.append({"n": None, "g": None, "new": empty(), "old": anch})

    return {"doc": doc, "label": DOC_LABELS.get(doc, doc),
            "hasOld": old_c is not None, "hasNew": new_c is not None, "rows": rows}


def main():
    args = sys.argv[1:]
    min_block = MIN_BLOCK_LINES
    if "--min-block" in args:
        k = args.index("--min-block")
        min_block = int(args[k + 1])
    docs = []
    for gold_path in sorted((DATA / "goldstandard").glob("*.txt")):
        doc = gold_path.name.split("_")[0]
        docs.append(build_doc(doc, gold_path, min_block))

    VIZ.mkdir(exist_ok=True)
    out = VIZ / "review.html"
    payload = json.dumps({"min_block": min_block, "docs": docs}, ensure_ascii=False)
    out.write_text(TEMPLATE.replace("/*DATA*/", payload), encoding="utf-8")

    n_err = sum(1 for d in docs for r in d["rows"]
                if r["new"]["st"] not in ("match", "na", "empty")
                or r["old"]["st"] not in ("match", "na", "empty"))
    print(f"geschrieben: {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")
    print(f"{len(docs)} Dokumente, min_block={min_block}, "
          f"{sum(len(d['rows']) for d in docs)} Zeilen, ~{n_err} mit Auffälligkeit")
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
  :root[data-theme=dark] .omit,@media (prefers-color-scheme:dark){.omit{color:#ff8a80}}
  .st-disloc_row,.st-disloc_block{background:var(--c-disloc)}
  .st-missing{background:var(--c-missing);color:var(--muted);font-style:italic}
  .st-spurious{background:var(--c-spur);font-style:italic}
  .st-merge2,.st-na,.st-empty{color:var(--muted);font-style:italic}
  .st-na{opacity:.5}
  .tag{display:inline-block;font-family:var(--sans);font-size:9.5px;font-weight:700;
    letter-spacing:.04em;text-transform:uppercase;color:var(--muted);
    border:1px solid var(--line);border-radius:4px;padding:0 4px;margin-right:6px;
    vertical-align:1px;background:var(--panel)}
  .hidden{display:none}
  .toggle-theme{position:fixed;bottom:12px;right:14px;z-index:5;font-family:var(--mono);
    font-size:11px;border:1px solid var(--line);background:var(--panel);color:var(--muted);
    border-radius:16px;padding:5px 11px;cursor:pointer}
  .empty-note{padding:24px;color:var(--muted);font-size:13px}
</style></head>
<body>
<header>
  <div class="titlerow">
    <h1>Fehler-Review</h1>
    <span class="sub">Gold gegen OCR · Hervorhebung gegen normalisierten Text</span>
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
    <span>‸ = ausgelassener Text (Tooltip)</span>
  </div>
</header>
<div class="scroll"><div class="grid" id="grid"></div></div>
<button class="toggle-theme" id="btnTheme">◐ Theme</button>

<script>
const PAYLOAD = /*DATA*/;
let curDoc = 0, mode = "norm", onlyErr = false;
const collapsed = {gold:false, old:false, new:false};
const COLS = [{k:"gold",t:"Goldstandard"},{k:"old",t:"Altes OCR"},{k:"new",t:"Neues OCR"}];
const ERRST = new Set(["disloc_row","disloc_block","missing","spurious"]);
const grid = document.getElementById("grid");

const bodyOf = c => (mode==="raw"? c.raw : c.norm) || "";
function template(){
  return "52px " + COLS.map(c => collapsed[c.k] ? "34px" : "max-content").join(" ");
}
function ocrCell(c, k){
  if(collapsed[k]) return `<div class="cell clp col-${k}"></div>`;
  if(!c) return `<div class="cell col-${k}"></div>`;
  const tag = c.tag ? `<span class="tag">${c.tag}</span>` : "";
  return `<div class="cell col-${k} st-${c.st}">${tag}${bodyOf(c)}</div>`;
}
function goldCell(r){
  if(collapsed.gold) return `<div class="cell clp col-gold"></div>`;
  return `<div class="cell col-gold">${r.g? bodyOf(r.g):""}</div>`;
}
function rowHasErr(r){
  if(r.g===null) return true; // spurious-Zeile
  if(ERRST.has(r.new.st)||ERRST.has(r.old.st)) return true;
  const h = bodyOf(r.new)+bodyOf(r.old);
  return h.includes("werr")||h.includes("cerr")||h.includes("omit");
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
  let html = headHtml(), shown=0;
  for(const r of d.rows){
    if(onlyErr && !rowHasErr(r)) continue;
    shown++;
    html += `<div class="gut">${r.n??""}</div>` + goldCell(r)
      + ocrCell(r.old,"old") + ocrCell(r.new,"new");
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
renderDocs(); render();
</script>
</body></html>
"""

if __name__ == "__main__":
    main()
