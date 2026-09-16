---
name: plotting-conventions
description: Rules for creating or editing any plotting/figure code in this project. Use before writing or reviewing matplotlib/seaborn code, annotations, axis choices, or statistics shown on a plot.
---

# Plotting conventions

Checklist to (re-)read before editing any plotting script. General rules, not specific
to any one figure or dataset. Update this file itself if a rule stops applying.

## Annotations and flagging a specific point

- Never add explanatory prose as a floating annotation/callout box pointing at a
  datapoint (`ax.annotate(long text, arrowprops=...)`). Explanations belong in the
  panel/axis title.
- To flag a specific point (excluded, low-quality, structurally different from the
  rest), change its visual encoding instead: a distinct marker shape, an asterisk
  appended to its label, bold/color on its label, or a legend entry. Never a text box
  on the plot.
- If a flag needs explaining, put a short note in the title ("\* = ..."), not next to
  the point.

## Titles vs. legends

- Correlation/fit statistics (Pearson r, Spearman rho, p-values) go directly in the
  panel title whenever a fit line or correlation is the point of that panel, not only
  inside a legend entry.
- Keep legend entries short once stats are in the title. Do not duplicate the same
  text twice.

## Axes

- For a categorical/count x-axis with natural integer semantics (e.g. "# files
  removed"), default to true-value spacing showing the full range (every integer
  tick, including ones with no data), rather than compressing to only the observed
  values. Gaps are real. Do not hide them.
- If a panel plots a fit/regression line, the fit and the display must use the same x
  representation. Mixing them (fit on the true value, display on a remapped/ordinal
  axis, or vice versa) bends an actually-straight line.
- A remapping applied to declutter a different panel (e.g. ordinal spacing for a
  box-plus-jitter panel) must not get silently reused in a panel whose main point is a
  regression fit.

## Statistics and sampling

- Do not manufacture precision by bootstrap-resampling from very few discrete
  underlying values (e.g. resampling-with-replacement from ~10 replicates thousands of
  times). Prefer showing the real/raw spread (standard deviation, individual real
  fits) when the underlying sample is that small.
- Same logic applies to tile/subsample-level bootstrapping: if a pool is much smaller
  than the target resample size, resampling adds no real information. Flag that point
  distinctly rather than reporting a misleadingly tight or shifted confidence
  interval for it.

## Formatting

- Large integers shown on a plot (counts, N values) use thousands separators
  (`f"{n:,}"`), not raw digit strings.
- Avoid loaded terminology. Do not call some results "honest"/"dishonest" to contrast
  calibration quality. Use neutral, accurate phrasing ("correctly calibrated",
  "appropriately reflects the uncertainty").

## Process

- When a fix for one problem risks reintroducing a previously-fixed one (for example
  an axis tradeoff), state the tradeoff explicitly rather than silently picking a
  side.
