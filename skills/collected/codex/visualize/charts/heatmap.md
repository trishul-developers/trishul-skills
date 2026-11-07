# Heatmap

Grid of category pairs: x=column, y=row, value=number. Each coordinate unique; duplicates need reviewed aggregation. Null/absent cells unknown, zero observed; hiding missing cells never imputes or reduces grid size. Full Cartesian grid≤2000 cells. Order lists unique; colorDomain finite increasing (rate fractions commonly[0,1]); rates need reviewed denominator and comparisons need intentional shared domain. missingValues only gap; no color-stop/interpolation/imputation settings. Preserve authored field names and original values; valueFormat affects measured display only.

```ts
export type HeatmapSpec = AxisLabels & {
  type: "heatmap";
  x: string;
  y: string;
  value: string;
  xOrder?: (string | number)[];
  yOrder?: (string | number)[];
  colorDomain?: Domain;
  hideMissingCells?: boolean;
  showValues?: boolean;
  missingValues?: "gap";
  valueFormat?: ValueFormat;
};
export type HeatmapChart = SingleChart & { spec: HeatmapSpec };
```
