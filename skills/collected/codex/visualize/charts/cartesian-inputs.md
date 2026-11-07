# Cartesian semantics

The shared types define bindings/options. Wide measures bind a nonempty tuple to y (x for horizontal bars); long form uses one measure plus series. Long series: nonblank text and every category/series combination. No duplicate coordinates, ambiguous labels or series names overwriting the category field. Measures share comparable units; preserve observed zeros/permitted null gaps. Never stack missing/overlapping/non-additive measures.

Numeric/date trends are ordered; calendar categories use calendar order. Other bar categories retain supplied order unless sortOrder changes it. Comparable panels/domains cover all filter states/stack totals; bars include zero, normalized stacks [0,1]. Legend toggles are local; normalized shares renormalize visible parts, so label "Share of visible categories". Preserve all series, change layout if crowded.

valueDecimals: integer 0–15 caps fractional digits without padding or changing data/ticks; percent precision follows conversion, compact labels apply precision after abbreviation, tooltips stay full. Otherwise precision increases from six significant digits to distinguish values.

Log Y: line/unstacked area. Log X/xDomain: numeric line only. Label log axes; logged values/bounds positive, explicit null Y gaps permitted. No epsilon, dropped values or transformed logs. startAtZero incompatible with log Y. No log bars/stacks. Follow family restrictions for overlays; stacks/sparkline reject them. Unsupported mixed layers/dual axes/label placement use fallback.
