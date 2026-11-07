# Line

Ordered observations/calculated curves, zeros and explicit null gaps retained; isolated observations remain dots. Dates/numeric X ordered; use line to connect points, scatter for separate observations/fits. Shared Cartesian inputs cover bindings, display and domains. Values default off; legend available, linear Y starts at zero. Label log axes, keep original positive coordinates/bounds, never epsilon/transformed rows. Calculate requested curves separately from an explicit model; update complete config via controls.md, label assumptions/units. No automatic extrema/confidence intervals. Single-measure references/annotations and bars/band uncertainty only; bands use straight segments. No mixed layers, arbitrary drawing or second axis; use fallback for unsupported requirements.

```ts
export type LineSpec = Cartesian &
  MeasuredFeatures<
    LineReferences & {
      uncertainty?: Uncertainty<"bars" | "band">;
    }
  > & {
    type: "line";
    xScale?: "linear" | "log";
    yScale?: "linear" | "log";
    xDomain?: Domain;
    colors?: ChartColors;
    valueFormat?: ValueFormat;
  };
export type LineChart = SingleChart & { spec: LineSpec };
```
