# Goldstandard — Fehlerkandidaten zum Durchgehen

Automatisch erzeugt mit `code/gold_audit.py` (Arbeiter-Zeitung OCR-Evaluation).

Methode: Stellen, an denen **Altes OCR und Neues OCR (Transkribus) und Neues OCR, Zeilen nachsortiert dasselbe Wort lesen, das Gold aber
ein anderes** hat. Zwei unabhängige Engines als Konsens → das Gold ist der
Ausreißer. Vergleich auf normalisiertem Text; Ligaturen, typografische
Anführungszeichen und reine Satzzeichen sind weggefaltet.

**Kandidaten, keine Gewissheiten** — bitte am Scan prüfen. Achtung: Irren beide
OCR gleich (z. B. langes ſ als „f“), ist das Gold richtig und der Treffer ein
Fehlalarm. Zeilennummer = Spalte „#“ im Review-Viewer.

Stand: 4 Kandidaten auf 3 Seiten.

| ☐ | Seite | Zeile | Gold | OCR-Konsens | Kontext |
|---|---|---|---|---|---|
| ☐ | aze19190115-2 | 99 | `besonderen` | `besonderrn` | Kinder in einem Entwicklungsalter, wo ſich die beſonderen |
| ☐ | aze19190115-2 | 299 | `Günther-Schoeller` | `Günther-Schveller` | fonds Günther⸗Schoeller Geld genommen hat, zerſtreut |
| ☐ | aze19271213-2 | 266 | `seine` | `feine` | Abfertigung und erſt wenn ſeine Arbeitsfähigkeit zu |
| ☐ | aze19280101-1 | 317 | `Kleinrentnerantrag` | `Kleinrentuerantrag` | unſeren Kleinrentnerantrag |

---

Erzeugen mit: `python code/gold_audit.py --md analysis/gold_candidates.md`
