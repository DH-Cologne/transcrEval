#!/usr/bin/env Rscript
# transcrEval — Auswertungsgerüst
# Liest results/metrics.csv (Wide-Format), formt es nach Long um und erzeugt
# vergleichende Boxplots (altes vs. neues OCR) für CER, WER, RLER und loc_events.
# Bewusst schlank: nur ggplot2 (+ scales) nötig, Reshaping in Base-R.
#
# Aufruf:  Rscript analysis/analyze.R
# Ausgabe: analysis/figures/*.png|pdf  und  analysis/metrics_long.csv

suppressWarnings(suppressMessages({
  ok <- requireNamespace("ggplot2", quietly = TRUE)
}))
if (!ok) stop("Paket 'ggplot2' fehlt. Installieren mit: install.packages('ggplot2')")
library(ggplot2)
has_scales <- requireNamespace("scales", quietly = TRUE)

# ---- Pfade robust bestimmen (egal von wo aufgerufen) ----------------------
args <- commandArgs(FALSE)
file_arg <- sub("^--file=", "", args[grep("^--file=", args)])
script_dir <- if (length(file_arg)) dirname(normalizePath(file_arg)) else getwd()
root <- dirname(script_dir)
csv <- file.path(root, "results", "metrics.csv")
if (!file.exists(csv)) stop("Nicht gefunden: ", csv, " — zuerst code/metrics.py laufen lassen.")
fig_dir <- file.path(script_dir, "figures")
dir.create(fig_dir, showWarnings = FALSE)

# ---- Einlesen und nach Long umformen --------------------------------------
d <- read.csv(csv, check.names = FALSE, stringsAsFactors = FALSE)

# Systemnamen aus den Spaltensuffixen ableiten (z.B. cer_norm_alt -> alt)
metric_cols <- grep("_(.+)$", names(d), value = TRUE)
metric_cols <- metric_cols[!names(d)[match(metric_cols, names(d))] %in% c("doc", "gold_lines", "min_block")]
systems <- unique(sub("^.*_", "", metric_cols))          # z.B. c("alt","neu")
systems <- systems[systems != ""]
suffix <- paste0("_(", paste(systems, collapse = "|"), ")$")
metric_cols <- grep(suffix, names(d), value = TRUE)

long <- do.call(rbind, lapply(metric_cols, function(col) {
  data.frame(
    doc    = d$doc,
    metric = sub(suffix, "", col),
    system = sub(paste0("^.*", suffix), "\\1", col),
    value  = suppressWarnings(as.numeric(d[[col]])),
    stringsAsFactors = FALSE
  )
}))
long <- long[!is.na(long$value), ]

# lesbare System-Labels + feste Farben
sys_labels <- c(alt = "altes OCR", neu = "neues OCR (Transkribus)")
long$system_lab <- ifelse(long$system %in% names(sys_labels),
                          sys_labels[long$system], long$system)
sys_fill <- c("altes OCR" = "#c2751a", "neues OCR (Transkribus)" = "#1367a0")

write.csv(long, file.path(script_dir, "metrics_long.csv"), row.names = FALSE)

# ---- kleine Zusammenfassung in die Konsole --------------------------------
summ <- aggregate(value ~ metric + system, long,
                  function(x) c(median = median(x), mean = mean(x),
                                min = min(x), max = max(x)))
summ <- do.call(data.frame, summ)
cat("\nZusammenfassung (Median/Mean/Min/Max je Metrik & System):\n")
print(summ, row.names = FALSE)

# ---- Plot-Helfer ----------------------------------------------------------
pct <- if (has_scales) scales::label_percent(accuracy = 0.1) else waiver()
base_theme <- theme_minimal(base_size = 12) +
  theme(legend.position = "top", legend.title = element_blank(),
        strip.text = element_text(face = "bold"),
        plot.title = element_text(face = "bold"))

box <- function(df, title, ylab, as_pct = FALSE, facet = TRUE) {
  p <- ggplot(df, aes(system_lab, value, fill = system_lab)) +
    geom_boxplot(width = 0.55, alpha = 0.6, outlier.shape = NA) +
    geom_jitter(width = 0.12, height = 0, size = 1.8, alpha = 0.7) +
    scale_fill_manual(values = sys_fill) +
    labs(title = title, x = NULL, y = ylab) + base_theme
  if (as_pct) p <- p + scale_y_continuous(labels = pct)
  if (facet) p <- p + facet_wrap(~metric_lab, scales = "free_y")
  p
}

save_fig <- function(p, name, w = 8, h = 5) {
  ggsave(file.path(fig_dir, paste0(name, ".png")), p, width = w, height = h, dpi = 150)
  ggsave(file.path(fig_dir, paste0(name, ".pdf")), p, width = w, height = h)  # vektoriell fürs Poster
}

metric_names <- c(cer_norm = "CER (normalisiert)", wer_norm = "WER (normalisiert)",
                  cer_raw = "CER (roh)", wer_raw = "WER (roh)",
                  rler = "RLER (Zeilenverschiebung)")
lab_of <- function(m) ifelse(m %in% names(metric_names), metric_names[m], m)

# ---- Figur 1: normalisierte Fehlerraten (Kernvergleich) -------------------
f1 <- long[long$metric %in% c("cer_norm", "wer_norm"), ]
f1$metric_lab <- lab_of(f1$metric)
save_fig(box(f1, "Zeichen- und Wortfehlerrate: altes vs. neues OCR",
             "Fehlerrate", as_pct = TRUE), "01_cer_wer_norm")

# ---- Figur 2: Normalisierungseffekt (roh vs. normalisiert) ----------------
f2 <- long[long$metric %in% c("cer_raw", "cer_norm", "wer_raw", "wer_norm"), ]
f2$metric_lab <- lab_of(f2$metric)
f2$metric_lab <- factor(f2$metric_lab, levels = c("CER (roh)", "CER (normalisiert)",
                                                  "WER (roh)", "WER (normalisiert)"))
save_fig(box(f2, "Effekt der Normalisierung (roh vs. normalisiert)",
             "Fehlerrate", as_pct = TRUE), "02_normalisierung", w = 9, h = 5.5)

# ---- Figur 3: Lokalisierung (RLER-Rate + loc_events-Zahl) -----------------
f3a <- long[long$metric == "rler", ]
f3a$metric_lab <- "RLER (Zeilenverschiebung)"
save_fig(box(f3a, "Zeilen-Lokalisierungsfehler (RLER)", "Rate",
             as_pct = TRUE, facet = FALSE), "03a_rler")

f3b <- long[long$metric == "loc_events", ]
save_fig(box(f3b, "Blockverschiebungen je Seite (loc_events)",
             "Ereignisse je Seite", as_pct = FALSE, facet = FALSE), "03b_loc_events")

cat("\nFiguren geschrieben nach:", fig_dir, "\n")
cat("Long-Tabelle:", file.path(script_dir, "metrics_long.csv"), "\n")
