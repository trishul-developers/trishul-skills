# Box Plot

Choose raw observations or one reviewed ordered five-number summary/category, never mix. Summary minimum≤lowerQuartile≤median≤upperQuartile≤maximum; y names quantity; omit whiskers, preserve endpoints, cannot infer outlier counts. Raw quartiles linearly interpolated; observations outside whiskers remain visible/in domains/tooltips. minMax uses full range/no outliers. Percentile whiskers use observed endpoints or quartile for sparse cases, not interpolated endpoints; [0,100]=minMax. Signed/decimal/single/zero-width valid; missing/nonfinite require reviewed decision. No notches/grouping/log/references/valueFormat. Category cannot use minimum/lowerQuartile/median/upperQuartile/maximum/spread/lowerWhisker/upperWhisker/outliers/whiskerLabel/sampleCount. Check units/order/quartiles/whiskers.

```ts
export type BoxPlotSpec = AxisLabels & {
  type: "boxPlot";
  x: string;
  y: string;
  yAxisPosition?: "left" | "right";
  /** Raw data only; reviewed five-number summaries already define their endpoints. */
  whiskers?: "tukey" | "minMax" | { percentiles: Domain };
};
export type BoxPlotChart = SingleChart & { spec: BoxPlotSpec };
```
