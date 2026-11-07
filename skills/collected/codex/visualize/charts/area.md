# Area

Use area for a filled trend or supplied density; stackedArea for complete nonnegative additive components. No stacked rates/averages/overlapping populations/signed or missing values. Unstacked nulls remain gaps. Preserve a meaningful baseline (linear Y normally includes zero); use line if fill misleads. Values default off, legend available unless false. Only unstacked area accepts log Y/single-measure overlays; neither supports log X/uncertainty/custom layers. Family capability takes precedence over shared type names.

```ts
export type AreaSpec = Cartesian &
  MeasuredFeatures<References> & {
    type: "area";
    yScale?: "linear" | "log";
    colors?: ChartColors;
    valueFormat?: ValueFormat;
  };
export type StackedAreaSpec = Cartesian &
  Measures & {
    type: "stackedArea";
    colors?: ChartColors;
    valueFormat?: ValueFormat;
  };
export type AreaChart = SingleChart & { spec: AreaSpec | StackedAreaSpec };
```
