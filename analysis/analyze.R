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
sys_labels <- c(alt = "altes OCR", neu = "neues OCR",
                neusort = "neues OCR, nachsortiert")
long$system_lab <- ifelse(long$system %in% names(sys_labels),
                          sys_labels[long$system], long$system)
# Reihenfolge wie in Tab. 1: alt, neu, nachsortiert
long$system_lab <- factor(long$system_lab, levels = unname(sys_labels))
sys_fill <- c("altes OCR" = "#c2751a", "neues OCR" = "#1367a0",
              "neues OCR, nachsortiert" = "#1f8a5b")

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

# ---- Statistische Kennwerte (posterfähig) ---------------------------------
# Gepaarter Wilcoxon-Vorzeichen-Rang-Test: bei n=10 und schiefen Verteilungen
# angemessener als ein t-Test. Jede Seite liefert ein Paar (alt vs. neu).
wide <- read.csv(csv, check.names = FALSE, stringsAsFactors = FALSE)
ref_sys <- "alt"; new_sys <- "neu"     # Vergleichsrichtung: alt -> neu
test_metrics <- c(cer_norm = "CER (normalisiert)", wer_norm = "WER (normalisiert)",
                  cer_raw  = "CER (roh)",          wer_raw  = "WER (roh)")

stats <- do.call(rbind, lapply(names(test_metrics), function(m) {
  a <- wide[[paste0(m, "_", ref_sys)]]
  b <- wide[[paste0(m, "_", new_sys)]]
  if (is.null(a) || is.null(b)) return(NULL)
  ok <- !is.na(a) & !is.na(b); a <- a[ok]; b <- b[ok]
  w <- suppressWarnings(wilcox.test(a, b, paired = TRUE))
  red <- 1 - b / a                     # relative Fehlerreduktion je Seite
  data.frame(
    metrik        = test_metrics[[m]],
    n             = length(a),
    median_alt    = median(a),
    median_neu    = median(b),
    faktor        = median(a) / median(b),
    reduktion_med = median(red),
    reduktion_min = min(red),
    reduktion_max = max(red),
    spanne_alt    = sprintf("%.1f–%.1f%%", min(a) * 100, max(a) * 100),
    spanne_neu    = sprintf("%.1f–%.1f%%", min(b) * 100, max(b) * 100),
    V             = unname(w$statistic),
    p             = w$p.value,
    stringsAsFactors = FALSE
  )
}))

write.csv(stats, file.path(script_dir, "stats.csv"), row.names = FALSE)

cat("\n\n=== Kennwerte für Abstract/Poster ===\n")
for (i in seq_len(nrow(stats))) {
  s <- stats[i, ]
  cat(sprintf(
    "%s: Median %.2f%% (alt) vs. %.2f%% (neu), Faktor %.1f; Reduktion Median %.1f%% (%.1f–%.1f%%); Wilcoxon V=%g, p=%.4f, n=%d\n",
    s$metrik, s$median_alt * 100, s$median_neu * 100, s$faktor,
    s$reduktion_med * 100, s$reduktion_min * 100, s$reduktion_max * 100,
    s$V, s$p, s$n))
}

# Deskriptiv: Lokalisierung. Bewusst KEIN Test -- zu viele Nullen (Seiten ohne
# jede Blockverschiebung), das trägt bei n=10 keinen Signifikanztest.
loc <- data.frame(
  system = c(ref_sys, new_sys),
  loc_events_summe = c(sum(wide[[paste0("loc_events_", ref_sys)]], na.rm = TRUE),
                       sum(wide[[paste0("loc_events_", new_sys)]], na.rm = TRUE)),
  seiten_ohne = c(sum(wide[[paste0("loc_events_", ref_sys)]] == 0, na.rm = TRUE),
                  sum(wide[[paste0("loc_events_", new_sys)]] == 0, na.rm = TRUE)),
  anteil_versch_zeilen_med = c(
    median(wide[[paste0("lines_disloc_block_", ref_sys)]] / wide$gold_lines, na.rm = TRUE),
    median(wide[[paste0("lines_disloc_block_", new_sys)]] / wide$gold_lines, na.rm = TRUE))
)
write.csv(loc, file.path(script_dir, "stats_localisation.csv"), row.names = FALSE)
cat("\nLokalisierung (deskriptiv, kein Test):\n")
print(loc, row.names = FALSE)

cat("\nFiguren geschrieben nach:", fig_dir, "\n")
cat("Long-Tabelle:", file.path(script_dir, "metrics_long.csv"), "\n")
cat("Kennwerte:   ", file.path(script_dir, "stats.csv"), "/ stats_localisation.csv\n")

# ---- Figur 4: vier Boxplots nebeneinander (CER-Paar | WER-Paar) -----------
# Layout nach Vorgabe: CER alt/neu, Abstand, WER alt/neu. Zwei Varianten, weil
# CER (max 24 %) und WER (max 92 %) sehr unterschiedliche Wertebereiche haben.
# Berichtet exakt die Werte der Zeilen "mit Zeilen-Alignment" aus Tab. 1:
# drei Systeme je Metrik, CER-Gruppe und WER-Gruppe durch eine Lücke getrennt.
f4 <- long[long$metric %in% c("cer_norm", "wer_norm"), ]
f4$grp <- ifelse(f4$metric == "cer_norm", "CER (normalisiert)", "WER (normalisiert)")
f4$key <- paste(f4$metric, f4$system)
sys_short <- c(alt = "altes\nOCR", neu = "neues\nOCR",
               neusort = "neues OCR\nnachsortiert")

# systems: welche Systeme nebeneinander stehen; free_scales: getrennte y-Achsen
box_group <- function(systems, free_scales) {
  df <- f4[f4$system %in% systems, ]
  n <- length(systems)
  slot <- setNames(seq_len(n), systems)
  gap <- n + 0.8                       # Abstand zwischen CER- und WER-Gruppe
  df$xpos <- slot[df$system] + ifelse(df$metric == "cer_norm", 0, gap)
  brk <- c(seq_len(n), seq_len(n) + gap)
  lab <- rep(unname(sys_short[systems]), 2)
  mid <- c(mean(seq_len(n)), mean(seq_len(n)) + gap)
  p <- ggplot(df, aes(x = xpos, y = value, group = key, fill = system_lab)) +
    geom_boxplot(width = 0.75, alpha = 0.65, outlier.shape = NA) +
    geom_jitter(width = 0.14, height = 0, size = 1.7, alpha = 0.75) +
    scale_fill_manual(values = sys_fill) +
    scale_y_continuous(labels = pct, expand = expansion(mult = c(0.02, 0.10))) +
    labs(x = NULL, y = "Fehlerrate", fill = NULL) + base_theme
  if (free_scales) {
    p + facet_wrap(~grp, scales = "free", strip.position = "bottom") +
      scale_x_continuous(breaks = brk, labels = lab) +
      theme(strip.placement = "outside", panel.spacing = unit(1.4, "lines"))
  } else {
    p + scale_x_continuous(breaks = brk, labels = lab,
      sec.axis = sec_axis(~., breaks = mid,
                          labels = c("CER (normalisiert)", "WER (normalisiert)")))
  }
}

drei <- c("alt", "neu", "neusort")
zwei <- c("alt", "neu")
save_fig(box_group(drei, FALSE), "04a_drei_systeme_gemeinsame_achse", w = 7.5, h = 5)
save_fig(box_group(drei, TRUE),  "04b_drei_systeme_getrennte_achsen", w = 7.5, h = 5)
save_fig(box_group(zwei, FALSE), "04c_alt_neu_gemeinsame_achse",      w = 6.5, h = 5)
save_fig(box_group(zwei, TRUE),  "04d_alt_neu_getrennte_achsen",      w = 6.5, h = 5)
cat("\nFigur 4 in vier Varianten geschrieben (drei bzw. zwei Systeme).\n")
