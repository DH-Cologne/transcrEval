# analysis/

R-Auswertung der OCR-Metriken. Liest `../results/metrics.csv` (von
`code/metrics.py` erzeugt) und baut vergleichende Boxplots (altes vs. neues OCR).

## Ausführen

```bash
Rscript analysis/analyze.R      # vom Projektwurzelverzeichnis
```

Benötigt nur **ggplot2** (und optional **scales** für Prozentachsen):

```r
install.packages(c("ggplot2", "scales"))
```

## Ausgabe

- `figures/01_cer_wer_norm.{png,pdf}` — CER & WER (normalisiert), alt vs. neu
- `figures/02_normalisierung.{png,pdf}` — Effekt der Normalisierung (roh vs. norm.)
- `figures/03a_rler.{png,pdf}` — Zeilenverschiebung (RLER)
- `figures/03b_loc_events.{png,pdf}` — Blockverschiebungen je Seite
- `metrics_long.csv` — die Metriken im Long-Format (doc, metric, system, value),
  bequem für eigene weitere Auswertungen

PDF ist vektoriell und damit direkt für das DHd-Poster verwendbar.

## Erweitern

`metrics_long.csv` bzw. das `long`-Objekt im Skript ist der Ausgangspunkt für
weitere Analysen (Signifikanztests, Korrelation Textmenge ↔ Fehler, Aggregate je
Jahrgang usw.). Neue Metriken aus der CSV werden automatisch mit umgeformt.
