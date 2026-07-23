#!/usr/bin/env python3
"""Zusätzlicher Split-Screen-Viewer: neues OCR (links) neben dem Seitenscan (rechts).

Rechts: das JPG mit den ALTO-TextBlocks als Overlay, nummeriert in Lesereihenfolge;
Blöcke, die (relativ zum Gold) verschoben sind, werden hervorgehoben. Links: das neue
OCR in ALTO-Lesereihenfolge, mit Fehler-Highlighting gegen Gold und Dislokationsfarbe.
Zeile <-> Block sind in beide Richtungen verknüpft (Hover/Klick).

Der bestehende review.html bleibt unberührt. Ausgabe: <viz>/review_split.html
Aufruf:  python code/build_split.py [--config PFAD] [--min-block N]
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET

from align import align, block_runs, rescue
from build_review import esc, word_hl
from config import load_config

NS = "{http://www.loc.gov/standards/alto/ns-v4#}"


def parse_alto(path):
    """(W, H, blocks, lines) — blocks in Lesereihenfolge, lines[i] = (text, block_index)."""
    root = ET.parse(path).getroot()
    page = root.find(f".//{NS}Page")
    W, H = int(page.get("WIDTH")), int(page.get("HEIGHT"))
    blocks, lines = [], []
    for tb in root.iter(NS + "TextBlock"):
        bidx = len(blocks)
        blocks.append({"o": bidx,
                       "x": int(tb.get("HPOS")), "y": int(tb.get("VPOS")),
                       "w": int(tb.get("WIDTH")), "h": int(tb.get("HEIGHT"))})
        for tl in tb.findall(NS + "TextLine"):
            txt = " ".join(s.get("CONTENT") for s in tl.findall(NS + "String")
                           if s.get("CONTENT"))
            if txt.strip():
                lines.append((txt, bidx))
    return W, H, blocks, lines


def build_doc(cfg, doc, folder, gold_path, min_block):
    alto = folder / f"{doc}.xml"
    jpg = folder / f"{doc}.jpg"
    W, H, blocks, alto_lines = parse_alto(alto)

    graw, gnorm, _ = cfg.load_lines(gold_path)
    oraw = [t for t, _ in alto_lines]
    onorm = [cfg.normalize(t) for t in oraw]
    line_block = [b for _, b in alto_lines]

    ops = align(gnorm, onorm, cfg.align)
    pos, rescued = rescue(ops, gnorm, onorm, cfg.align)
    _, _, event_of = block_runs([gi for gi, _ in rescued], pos, min_block)

    # OCR-Zeile -> Goldpartner (für Diff) und -> Ereignis (für Dislokationsfarbe)
    o2g = {}
    for o in ops:
        if o.kind == "match":
            o2g[o.ocr[0]] = o.gold[0]
        elif o.kind == "split":
            o2g[o.ocr[0]] = o2g[o.ocr[1]] = o.gold[0]
        elif o.kind == "merge":
            o2g[o.ocr[0]] = o.gold[0]
    for gi, oi in rescued:
        o2g[oi] = gi

    lines = []
    for oi, (txt, b) in enumerate(alto_lines):
        gi = o2g.get(oi)
        ev = event_of.get(gi, 0) if gi is not None else 0
        if gi is not None:
            html_n = word_hl(gnorm[gi], onorm[oi])
            html_r = word_hl(graw[gi], oraw[oi])
            st = "disloc" if ev else "match"
        else:
            html_n, html_r = esc(onorm[oi]), esc(oraw[oi])
            st = "spurious"
        lines.append({"n": oi + 1, "b": b, "ev": ev, "st": st, "norm": html_n, "raw": html_r})

    # Ereignis je Block = größtes Ereignis seiner Zeilen
    for blk in blocks:
        evs = [ln["ev"] for ln in lines if ln["b"] == blk["o"] and ln["ev"]]
        blk["ev"] = max(evs) if evs else 0

    rel_img = f"../data/{folder.name}/{jpg.name}"
    parts = gold_path.name.split("_gold_")
    initials = parts[1].rsplit(".txt", 1)[0] if len(parts) > 1 else ""
    return {"doc": doc, "label": cfg.labels.get(doc, doc), "gold": initials,
            "img": rel_img, "W": W, "H": H, "blocks": blocks, "lines": lines}


def main():
    args = list(sys.argv[1:])
    cfg_path = None
    if "--config" in args:
        k = args.index("--config")
        cfg_path = args[k + 1]
    cfg = load_config(cfg_path)
    min_block = cfg.align.min_block
    if "--min-block" in args:
        min_block = int(args[args.index("--min-block") + 1])

    docs = [build_doc(cfg, doc, folder, gold_path, min_block)
            for doc, folder, gold_path in cfg.gold_files()]

    cfg.viz_dir.mkdir(exist_ok=True)
    out = cfg.viz_dir / "review_split.html"
    payload = json.dumps({"project": cfg.project, "docs": docs}, ensure_ascii=False)
    out.write_text(TEMPLATE.replace("/*DATA*/", payload), encoding="utf-8")

    nblk = sum(len(d["blocks"]) for d in docs)
    ndis = sum(1 for d in docs for b in d["blocks"] if b["ev"])
    print(f"geschrieben: {out}")
    print(f"{len(docs)} Seiten, {nblk} Blöcke ({ndis} disloziert). Lokal im Browser öffnen.")


TEMPLATE = r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>transcrEval — Split-Review (Text | Scan)</title>
<style>
  :root{
    --bg:#faf8f3; --panel:#fff; --ink:#221f1a; --muted:#6b655b; --line:#e2dccf;
    --c-char:#ff9a9a; --c-word:#ffd9a3; --c-disloc:#fdf3b6; --c-spur:#e6e2da;
    --accent:#1367a0; --box:#8a8577; --boxdis:#e8892b;
    --mono:"SFMono-Regular",ui-monospace,Menlo,monospace;
    --serif:"Iowan Old Style",Georgia,"Times New Roman",serif;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  }
  @media (prefers-color-scheme:dark){:root{
    --bg:#16140f; --panel:#1e1b15; --ink:#ece7db; --muted:#9a9184; --line:#332f27;
    --c-char:#a13b3b; --c-word:#8a5a1e; --c-disloc:#6b5e1c; --c-spur:#2f2b23;
    --accent:#4a9fd4; --box:#6a6456; --boxdis:#e8892b;
  }}
  :root[data-theme=dark]{
    --bg:#16140f; --panel:#1e1b15; --ink:#ece7db; --muted:#9a9184; --line:#332f27;
    --c-char:#a13b3b; --c-word:#8a5a1e; --c-disloc:#6b5e1c; --c-spur:#2f2b23;
    --accent:#4a9fd4; --box:#6a6456; --boxdis:#e8892b;
  }
  :root[data-theme=light]{
    --bg:#faf8f3; --panel:#fff; --ink:#221f1a; --muted:#6b655b; --line:#e2dccf;
    --c-char:#ff9a9a; --c-word:#ffd9a3; --c-disloc:#fdf3b6; --c-spur:#e6e2da;
    --accent:#1367a0; --box:#8a8577; --boxdis:#e8892b;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%}
  body{background:var(--bg);color:var(--ink);font-family:var(--sans);
    display:flex;flex-direction:column;height:100vh;overflow:hidden}
  header{padding:10px 16px;border-bottom:1px solid var(--line);background:var(--panel);flex:none}
  .row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
  h1{font-family:var(--serif);font-size:17px;font-weight:600;margin:0}
  .sub{color:var(--muted);font-size:12px}
  .docs{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px}
  button.doc,button.ui{font-family:var(--mono);font-size:11.5px;border:1px solid var(--line);
    background:var(--panel);color:var(--muted);border-radius:15px;padding:4px 10px;cursor:pointer}
  button.doc.active,button.ui.on{background:var(--accent);color:#fff;border-color:var(--accent)}
  .spacer{flex:1}
  .legend{display:flex;gap:12px;flex-wrap:wrap;font-size:11.5px;color:var(--muted);margin-top:7px}
  .legend span{display:inline-flex;align-items:center;gap:5px}
  .sw{width:11px;height:11px;border-radius:3px;display:inline-block;border:1px solid rgba(0,0,0,.15)}
  main{flex:1;display:flex;min-height:0}
  .left{width:44%;overflow:auto;border-right:2px solid var(--line)}
  .right{flex:1;overflow:auto;background:var(--panel);position:relative}
  .ln{display:grid;grid-template-columns:44px 1fr;gap:8px;padding:3px 10px;
    border-bottom:1px solid var(--line);font-family:var(--serif);font-size:14px;
    line-height:1.45;cursor:pointer;scroll-margin-top:8px}
  .ln:hover{background:color-mix(in srgb,var(--accent) 12%,transparent)}
  .ln.sel{background:color-mix(in srgb,var(--accent) 22%,transparent)}
  .ln .no{color:var(--muted);font-family:var(--mono);font-size:10.5px;text-align:right;
    -webkit-user-select:none;user-select:none}
  .ln.st-disloc{background:var(--c-disloc)}
  .ln.st-spurious{background:var(--c-spur);font-style:italic}
  .bmark{font-family:var(--sans);font-size:9px;font-weight:700;color:var(--muted);
    border:1px solid var(--line);border-radius:3px;padding:0 4px;margin-right:5px;vertical-align:1px}
  .werr{background:var(--c-word);border-radius:3px;padding:0 1px;box-decoration-break:clone;-webkit-box-decoration-break:clone}
  .cerr{background:var(--c-char);border-radius:2px;box-decoration-break:clone;-webkit-box-decoration-break:clone}
  .omit{color:#c0392b;font-weight:700;cursor:help}
  @media (prefers-color-scheme:dark){.omit{color:#ff8a80}}
  .imgwrap{position:relative;width:100%}
  .imgwrap img{display:block;width:100%;height:auto}
  .imgwrap svg{position:absolute;inset:0;width:100%;height:100%}
  .blk{fill:transparent;stroke:var(--box);stroke-width:3;cursor:pointer}
  .blk.dis{fill:color-mix(in srgb,var(--boxdis) 22%,transparent);stroke:var(--boxdis);stroke-width:6}
  .blk.sel{fill:color-mix(in srgb,var(--accent) 28%,transparent);stroke:var(--accent);stroke-width:8}
  .blabel{fill:var(--box);font-family:var(--sans);font-weight:700}
  .blabel.dis{fill:var(--boxdis)}
  .toggle-theme{position:fixed;bottom:10px;right:12px;z-index:5;font-family:var(--mono);
    font-size:11px;border:1px solid var(--line);background:var(--panel);color:var(--muted);
    border-radius:15px;padding:4px 10px;cursor:pointer}
</style></head>
<body>
<header>
  <div class="row">
    <h1>Split-Review</h1><span class="sub" id="sub"></span>
    <span class="spacer"></span>
    <button class="ui" id="btnMode">Ansicht: normalisiert</button>
    <button class="ui" id="btnPath">Lesepfad</button>
  </div>
  <div class="docs" id="docs"></div>
  <div class="legend">
    <span><i class="sw" style="background:var(--c-word)"></i>Wortfehler</span>
    <span><i class="sw" style="background:var(--c-char)"></i>Zeichenfehler</span>
    <span><i class="sw" style="background:var(--c-disloc)"></i>Block verschoben</span>
    <span><i class="sw" style="background:var(--c-spur)"></i>ohne Goldentsprechung</span>
    <span>Block-Nr = ALTO-Lesereihenfolge · Zeile klicken ⇄ Block</span>
  </div>
</header>
<main>
  <div class="left" id="left"></div>
  <div class="right" id="right"></div>
</main>
<button class="toggle-theme" id="btnTheme">◐ Theme</button>

<script>
const PAYLOAD = /*DATA*/;
let curDoc = 0, mode = "norm", showPath = false, sel = null;
const left = document.getElementById("left"), right = document.getElementById("right");
const bodyOf = ln => (mode==="raw"? ln.raw : ln.norm) || "";

function renderLeft(){
  const d = PAYLOAD.docs[curDoc];
  let prevB = -1, h = "";
  for(const ln of d.lines){
    const bm = ln.b!==prevB ? `<span class="bmark">Block ${ln.b+1}</span>` : "";
    prevB = ln.b;
    h += `<div class="ln st-${ln.st}" id="ln-${ln.n}" data-b="${ln.b}">`
      + `<span class="no">${ln.n}</span><span>${bm}${bodyOf(ln)}</span></div>`;
  }
  left.innerHTML = h;
  left.querySelectorAll(".ln").forEach(el => el.onclick = ()=> selectBlock(+el.dataset.b, true));
}
function renderRight(){
  const d = PAYLOAD.docs[curDoc];
  let boxes = "", labels = "", path = "";
  const cx = b => b.x + b.w/2, cy = b => b.y + b.h/2;
  if(showPath){
    const pts = d.blocks.map(b => `${cx(b)},${cy(b)}`).join(" ");
    path = `<polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="3"
      stroke-opacity="0.5" stroke-dasharray="14 10"/>`;
  }
  const fs = Math.round(d.W/45);
  for(const b of d.blocks){
    const dis = b.ev ? " dis" : "";
    boxes += `<rect class="blk${dis}" data-o="${b.o}" x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="4"/>`;
    labels += `<text class="blabel${dis}" data-o="${b.o}" x="${b.x+6}" y="${b.y+fs+4}" `
      + `font-size="${fs}">${b.o+1}${b.ev?" ▮"+b.ev:""}</text>`;
  }
  right.innerHTML = `<div class="imgwrap"><img src="${d.img}" alt="Seite ${d.label}">`
    + `<svg viewBox="0 0 ${d.W} ${d.H}" preserveAspectRatio="xMidYMid meet">${path}${boxes}${labels}</svg></div>`;
  right.querySelectorAll(".blk").forEach(el => el.onclick = ()=> selectBlock(+el.dataset.o, false));
}
function selectBlock(b, fromLeft){
  sel = b;
  document.querySelectorAll(".blk.sel").forEach(e=>e.classList.remove("sel"));
  document.querySelectorAll(".ln.sel").forEach(e=>e.classList.remove("sel"));
  const rect = right.querySelector(`.blk[data-o="${b}"]`);
  if(rect) rect.classList.add("sel");
  const lns = left.querySelectorAll(`.ln[data-b="${b}"]`);
  lns.forEach(e=>e.classList.add("sel"));
  if(fromLeft){ if(rect) rect.scrollIntoView({block:"center",behavior:"smooth"}); }
  else if(lns[0]) lns[0].scrollIntoView({block:"center",behavior:"smooth"});
}
function render(){ renderLeft(); renderRight(); if(sel!==null) selectBlock(sel,false); }
function renderDocs(){
  document.getElementById("docs").innerHTML = PAYLOAD.docs.map((d,i)=>
    `<button class="doc ${i===curDoc?'active':''}" data-i="${i}">${d.label}</button>`).join("");
  document.querySelectorAll("button.doc").forEach(b=>b.onclick=()=>{
    curDoc=+b.dataset.i; sel=null; renderDocs(); render();
    left.scrollTop=0; right.scrollTop=0;
    document.getElementById("sub").textContent = subText();
  });
}
function subText(){
  const d = PAYLOAD.docs[curDoc];
  const dis = d.blocks.filter(b=>b.ev).length;
  return `${d.label} · Gold (${d.gold}) · ${d.blocks.length} Blöcke, ${dis} verschoben`;
}
document.getElementById("btnMode").onclick = e=>{
  mode = mode==="norm"?"raw":"norm";
  e.target.textContent = "Ansicht: "+(mode==="norm"?"normalisiert":"roh");
  e.target.classList.toggle("on", mode==="raw"); renderLeft();
  if(sel!==null){ const l=left.querySelector(`.ln[data-b="${sel}"]`); if(l)l.classList.add("sel"); }
};
document.getElementById("btnPath").onclick = e=>{
  showPath=!showPath; e.target.classList.toggle("on",showPath); renderRight();
  if(sel!==null){ const r=right.querySelector(`.blk[data-o="${sel}"]`); if(r)r.classList.add("sel"); }
};
document.getElementById("btnTheme").onclick = ()=>{
  const root=document.documentElement;
  const cur=root.getAttribute("data-theme")||(matchMedia("(prefers-color-scheme:dark)").matches?"dark":"light");
  root.setAttribute("data-theme", cur==="dark"?"light":"dark");
};
document.getElementById("sub").textContent = subText();
renderDocs(); render();
</script>
</body></html>
"""

if __name__ == "__main__":
    main()
