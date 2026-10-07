# Journal figure specifications

[← README](../README.md) · [the layout file](layout.md) · [the layout file](layout.md)

## Scope

This file collects the figure requirements of the journals we target, with sources and how each value
was checked.
The bundled presets in `src/plotplate/presets/journals/` encode these values.
Guidelines change: check the source page again before a submission.

Retrieved on 2026-09-14.

## How the values were checked

| status | meaning |
| --- | --- |
| direct | read from the official page |
| archived | read from an Internet Archive copy of the official page (the journal site blocks automated access) |
| secondary | not found in journal text; taken from search-engine excerpts, confirm before use |

## Summary

Widths and heights are millimetres at final print size.

| journal (preset) | column widths | max height | text size | font | panel labels | min line | final files | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Nature (`nature`) | 89, 183 | 170 | 5-7 pt | Arial or Helvetica | 8 pt bold lowercase | not stated | vector PDF/EPS/AI, editable text | direct |
| Science (`science`) | 57, 121, 184 | not stated | about 7 pt, min 5 pt | Helvetica preferred | 10 pt bold capitals | 0.5 pt | PDF/EPS/AI, TIFF 300 dpi | archived |
| Cell Press (`cell`) | 85, 114, 174 (55 for 3-column formats) | 200 (recommended) | 6-8 pt | Arial only | capital letters | 0.5 pt (0.5-1.5 pt range) | TIFF or PDF, one file per figure | archived |
| NAR (`nar`) | 84, 178 | 230 | min 5 pt | plain sans-serif | not found | not found | not found | secondary |
| Genome Biology / BMC (`genome-biology`) | 85, 170 | 225 incl. legend | legible (not stated) | not stated | not stated | 0.25 pt | PDF preferred for vector, one composite file | archived |
| Genome Research (`genome-research`) | not stated (figures resized) | not stated | 8-10 pt, spread ≤ 2 pt | Helvetica or Arial | 12 pt bold capitals | 0.25 pt | TIFF/EPS/PDF/JPEG/AI | archived |
| PLOS Genetics, PLOS Comp Biol (`plos`) | 66.8-190.5, text column ≤ 132 | 222.3 | 8-12 pt | Arial, Times or Symbol | (A) or (a) | not stated | TIFF (LZW) or EPS only, one file per figure | direct |

"PLOS Genomics" does not exist as a journal; PLOS Genetics and PLOS Computational Biology share
identical specifications, and other PLOS journals likely do too.

## What this means for the package

- **One file per figure at production.**
  Cell, BMC, PLOS and Science want every panel of a figure in a single file.
  The LaTeX snippet serves the manuscript; `plotplate export layout.yaml -o Fig1.pdf` (or `.tif`)
  writes the production file with the same placement and the panel letters in the figure font.
- **Formats differ.**
  Nature refuses TIFF/PNG and wants editable vector files; PLOS accepts only TIFF or EPS and refuses
  LaTeX-generated EPS.
  `plotplate export` warns when the extension is not in the preset's `deliverable.formats`.
- **Minimum text sizes range from 5 pt (Nature, Science, NAR) to 8 pt (Genome Research, PLOS).**
  A layout built for Nature at 5-7 pt does not pass PLOS or Genome Research without enlarging text or
  boxes.
  Switching `journal:` in a layout reruns every check against the new limits.
- **Genome Research limits the spread of font sizes to 2 pt within a figure.**
  The `font-size-spread` check reports it when `font.max_spread` is set (the preset sets it).
- **Line widths.**
  Science and Cell ask for at least 0.5 pt, BMC and Genome Research 0.25 pt. The presets set
  `lines.min` accordingly.
- **Editable, embedded fonts** are required or recommended everywhere; panels use TrueType (Type 42)
  fonts in PDF and plain text in SVG.

## Nature

Source (direct):
[preparing figures, our specifications](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/),
[building and exporting figure panels](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/).

- Printed widths 89 mm (single column) and 183 mm (double column).
- Maximum height 170 mm, to leave space for the legend.
- Figures may be reduced in production; submit at the smallest appropriate size with all fonts between
  5 and 7 pt.
- Sans-serif fonts, preferably Helvetica or Arial; amino-acid sequences in Courier.
- Panel labels 8 pt bold, upright, lowercase (a, b, c).
- Do not outline text; embed TrueType 2 or 42 fonts; the guide gives
  `matplotlib.rcParams['pdf.fonttype'] = 42`.
- Main figures as vector files with editable layers: preferred `.ai`, `.eps`, `.pdf`; also layered
  Photoshop, plain `.svg`, `.ps`.
  Not accepted: `.jpeg`, `.tiff`, `.png`, TeX, and several drawing programs.
- Photographic images at 300 dpi minimum; 450 dpi or more recommended.
- RGB colour; avoid coloured text; use an accessible palette (the guide shows the Wong palette,
  bundled as `wong`).
- Axis lines and tick marks required; axis labels with units in parentheses; no background gridlines,
  drop shadows or patterns.

## Science

Source (archived):
[instructions for preparing an initial manuscript](https://www.science.org/content/page/instructions-preparing-initial-manuscript)
(2024 capture),
[instructions for preparing a revised manuscript](https://www.science.org/content/page/instructions-preparing-revised-manuscript)
(2026 capture).

- Printed width usually 5.7 cm (1 column), 12.1 cm (2 columns) or 18.4 cm (3 columns); simple graphs
  may be narrower.
- Lettering about 7 pt (2.5 mm high) after reduction and not smaller than 5 pt; avoid wide variation
  in type size.
- Sans-serif font whenever possible, Helvetica preferred.
- Part labels A, B, C in 10 pt bold, in the upper-left corner; avoid sub-part labels.
- Symbols at least 6 pt; line widths at least 0.5 pt at final size.
- No minor tick marks or grid lines; axes should not extend beyond the data range; do not repeat
  common axis labels.
- Avoid red with green, similar hues for different parts, greyscale, and coloured type.
- Revision formats in preferred order: vector PDF, EPS or AI; raster TIFF at 300 dpi or more; each
  figure as an individual file.

## Cell Press

Source (archived, 2026 capture):
[figure guidelines](https://www.cell.com/information-for-authors/figure-guidelines).

- Maximum widths for two-column formats: 8.5 cm (1 column), 11.4 cm (1.5 columns), 17.4 cm (full
  width).
  Three-column formats: 5.5 cm, 11.4 cm, 17.4 cm.
  STAR Protocols: 13.4 cm and 17.2 cm.
- Recommended maximum figure size 6.5 x 8 in (16.5 x 20 cm); each figure on a single page; at most 20
  MB per file.
- Each figure file includes all its panels; do not send panels as separate files; no titles or legends
  inside the file.
- TIFF and PDF preferred for production; EPS, JPEG and CDX also accepted.
- Embed fonts and use only Arial; text about 6-8 pt at print size; panels labelled with capital
  letters.
- Resolution at print size: 300 dpi colour or greyscale, 500 dpi black and white, 1,000 dpi line art.
- RGB colour; do not combine red and green; line weights 0.5-1.5 pt; grey fills 10-80 % and at least
  20 % apart.

## Nucleic Acids Research

Sources (secondary): [general instructions](https://academic.oup.com/nar/pages/general_instructions),
[author guidelines](https://academic.oup.com/nar/pages/author-guidelines).
Oxford Academic blocks automated access, and neither the live pages read through a fetch tool nor
archived copies showed a figure section.

- Reported: width at most 84 mm (single column) or 178 mm (double column); height at most 230 mm.
- Reported: plain sans-serif lettering, internally consistent, not smaller than 5 pt at final size.
- To confirm: file formats, line widths, panel label style, composite-file requirement.

## Genome Biology and BMC journals

Source (archived, 2026 capture):
[preparing your manuscript](https://genomebiology.biomedcentral.com/submission-guidelines/preparing-your-manuscript).

- Figures are resized to BMC standard dimensions: 85 mm (half page) or 170 mm (full page) wide, at
  most 225 mm high including the legend.
- About 300 dpi at final size; all text legible at these dimensions; all lines wider than 0.25 pt; all
  fonts embedded.
- Multi-panel figures as one composite file; closely cropped; keys inside the graphic; titles and
  legends in the manuscript.
- Vector figures preferably as PDF; maximum 10 MB per file.

## Genome Research

Sources (archived, 2026 captures):
[manuscript preparation](https://genome.cshlp.org/site/misc/ifora_mspreparation.xhtml),
[accepted manuscripts](https://genome.cshlp.org/site/misc/ifora_acceptedmss.xhtml),
[digital art guidelines](https://genome.cshlp.org/site/misc/ifora_digartsubm.xhtml).

- Helvetica or Arial, 8-10 pt; font sizes must not vary by more than 2 pt within a figure or across
  its panels.
- Panel tags A, B, C as 12 pt bold capitals (digital art guidelines and accepted-manuscript page).
  The initial-submission page says 10 pt; the preset follows the production value, 12 pt.
- Rules at least 0.25 pt; all fonts embedded; RGB colour.
- Raster resolution: line art 1,000-1,200 dpi, halftones 300 dpi, combinations 600-900 dpi; vector art
  has no resolution requirement.
- Figures are resized for publication, so no column width is given; keep graphics proportionate to the
  text.
- Multi-panel figures presented on separate pages are charged as separate figures.

## PLOS Genetics and PLOS Computational Biology

Sources (direct): [PLOS Genetics figures](https://journals.plos.org/plosgenetics/s/figures),
[PLOS Computational Biology figures](https://journals.plos.org/ploscompbiol/s/figures).

- Width 2.63-7.5 in (6.68-19.05 cm); height at most 8.75 in (22.23 cm), which is a full page without
  caption.
- To align with the text column of the PDF, keep the figure at most 5.2 in (13.2 cm) wide.
- TIFF or EPS only; TIFF with LZW compression, RGB 8 bit or greyscale, 300-600 dpi; at most 10 MB.
- Arial, Times or Symbol font only, 8-12 pt.
- All panels of a multi-part figure in a single page and a single file; panel labels such as (A) or
  (a).
- PLOS does not accept vector EPS generated by LaTeX; `plotplate export ... -o Fig1.tif` writes a
  compliant TIFF.
