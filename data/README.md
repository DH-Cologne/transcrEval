# Data

Ten pages of the Viennese *Arbeiter-Zeitung* (`aze`), 1919–1934, each in its own
folder `ANNO_aze<date>-<page>/`. The pages were selected for layout diversity, not
sampled at random; they are an evaluation set, not a representative corpus sample.

Four things live side by side in every folder, and they have **different origins and
different rights**. Please read the two sections below before reusing anything.

```
ANNO_aze19190115-2/
  aze19190115-2.jpg                 page scan            → provided by the ÖNB
  aze19190115-2_ocr_alt.txt         older OCR (2015)     → provided by the ÖNB
  aze19190115-2.xml                 Transkribus ALTO v4  → produced in this project
  aze19190115-2_ocr_neu.txt         text from the ALTO   → produced in this project
  aze19190115-2_ocr_neusort.txt     lines coordinate-sorted → produced in this project
  aze19190115-2_gold_AD.txt         hand transcription   → produced in this project
```

## Material provided by the Austrian National Library

The page scans (`*.jpg`) and the older OCR (`*_ocr_alt.txt`, ABBYY Recognition
Server 4.0, 2015) were **provided by the Österreichische Nationalbibliothek (ÖNB)**
through [ANNO – AustriaN Newspapers Online](https://anno.onb.ac.at/). They are
redistributed here unchanged, for convenience, so that the evaluation can be
reproduced from a single checkout.

Neither the ÖNB nor this project claims copyright in the underlying newspaper. In
its own metadata the ÖNB declares the rights status of these issues as
[**Copyright Not Evaluated (CNE)**](https://rightsstatements.org/vocab/CNE/1.0/) —
the copyright status has not been determined. We make no rights statement of our
own about this material and add no licence to it. Anyone intending to reuse the
scans or the older OCR beyond the reproduction of this evaluation should assess the
rights situation themselves and, in case of doubt, contact the ÖNB.

Each issue can be reached at its source:

| Page | Date | Typeface | Gold by | At ANNO | Metadata (EDM/RDF) |
|---|---|---|---|---|---|
| `aze19190115-2`  | 15 Jan 1919 | Fraktur | AD | [issue](https://anno.onb.ac.at/cgi-content/anno?aid=aze&datum=19190115&seite=2)  | [rdf](http://data.onb.ac.at/ANNO/aze19190115.rdf) |
| `aze19210110-2`  | 10 Jan 1921 | Fraktur | JH | [issue](https://anno.onb.ac.at/cgi-content/anno?aid=aze&datum=19210110&seite=2)  | [rdf](http://data.onb.ac.at/ANNO/aze19210110.rdf) |
| `aze19260523-12` | 23 May 1926 | Fraktur | SD | [issue](https://anno.onb.ac.at/cgi-content/anno?aid=aze&datum=19260523&seite=12) | [rdf](http://data.onb.ac.at/ANNO/aze19260523.rdf) |
| `aze19271213-2`  | 13 Dec 1927 | Fraktur | JH | [issue](https://anno.onb.ac.at/cgi-content/anno?aid=aze&datum=19271213&seite=2)  | [rdf](http://data.onb.ac.at/ANNO/aze19271213.rdf) |
| `aze19280101-1`  | 1 Jan 1928  | Fraktur | AD | [issue](https://anno.onb.ac.at/cgi-content/anno?aid=aze&datum=19280101&seite=1)  | [rdf](http://data.onb.ac.at/ANNO/aze19280101.rdf) |
| `aze19281009-6`  | 9 Oct 1928  | Fraktur | SD | [issue](https://anno.onb.ac.at/cgi-content/anno?aid=aze&datum=19281009&seite=6)  | [rdf](http://data.onb.ac.at/ANNO/aze19281009.rdf) |
| `aze19281111-9`  | 11 Nov 1928 | Fraktur | NR | [issue](https://anno.onb.ac.at/cgi-content/anno?aid=aze&datum=19281111&seite=9)  | [rdf](http://data.onb.ac.at/ANNO/aze19281111.rdf) |
| `aze19291229-13` | 29 Dec 1929 | Fraktur | JH | [issue](https://anno.onb.ac.at/cgi-content/anno?aid=aze&datum=19291229&seite=13) | [rdf](http://data.onb.ac.at/ANNO/aze19291229.rdf) |
| `aze19321217-5`  | 17 Dec 1932 | Fraktur | SD | [issue](https://anno.onb.ac.at/cgi-content/anno?aid=aze&datum=19321217&seite=5)  | [rdf](http://data.onb.ac.at/ANNO/aze19321217.rdf) |
| `aze19341202-5`  | 2 Dec 1934  | **Antiqua** | CS | [issue](https://anno.onb.ac.at/cgi-content/anno?aid=aze&datum=19341202&seite=5)  | [rdf](http://data.onb.ac.at/ANNO/aze19341202.rdf) |

The ANNO link opens the whole issue at the given page. A page image can also be
fetched directly as `https://anno.onb.ac.at/cgi-content/annoshow?call=aze|<date>|<page>|100|0`.

Nine of the ten pages are set in Fraktur; the issue of 2 December 1934 is set in
Antiqua. It is also the page with the highest error rate for both OCR systems — the
scan is visibly degraded as well, so the two possible causes cannot be separated on
a single page.

## Material produced in this project

The Transkribus ALTO files (`*.xml`), the text derived from them (`*_ocr_neu.txt`,
`*_ocr_neusort.txt`) and the hand-made gold standard (`*_gold_<initials>.txt`) were
produced within the project *Viennese Feuilleton and Biopolitics in the Interwar
Period*. This is the first place they are published.

They are released under
[**CC BY 4.0**](https://creativecommons.org/licenses/by/4.0/), insofar as rights
subsist in them. The licence covers the transcription and layout-annotation layer —
our own work. It does not, and cannot, extend to the underlying newspaper text,
whose status is the one described above.

Attribution for reuse:

> Hermes, Jürgen; Dick, Anna-Katharina; Dorfbauer, Sonja; Reiter, Nils; Steindl,
> Christoph (2026): *transcrEval — gold standard and OCR of ten pages of the
> Arbeiter-Zeitung*. Universität zu Köln / Österreichische Nationalbibliothek.
> CC BY 4.0. Scans and 2015 OCR provided by the Österreichische Nationalbibliothek
> via ANNO.

The gold transcriptions follow level 2 of the
[OCR-D ground truth guidelines](https://ocr-d.de/en/gt-guidelines/trans/); the
initials in the filename identify the transcriber. Known candidate errors that
survived proofreading are listed in [`../analysis/gold_candidates.md`](../analysis/gold_candidates.md).

The new OCR was produced with Transkribus (READ COOP); the engine version is
recorded per page in the ALTO `Processing` element, the HTR model is not.
