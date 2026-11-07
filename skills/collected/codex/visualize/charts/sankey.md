# Sankey

Reviewed additive counts along complete mutually exclusive ordered paths: one row per complete path, 2–4 distinct stage fields with nonblank strings; value separate positive safe-integer count. Total exactly representable. Duplicate full paths need reviewed aggregation; shared partial paths sum into links. Empty rows valid. Preserve population/scope, distinguish labels within each stage. Native node labels/count/share tooltips; local selection highlights, not cross-chart filtering/persistence. Max12 nodes/stage,96 links; height needs24px margins+16px between+12px per node (344 for12); limits are not readability guarantees. No skipped stages/overlapping populations/ratios/currency/source-target edge tables/Cartesian options. colorByColumn fixed false; counts cannot be formatted as rates/currency.

```ts
export type SankeySpec = {
  type: "sankey";
  stages:
    | [string, string]
    | [string, string, string]
    | [string, string, string, string];
  value: string;
  colorByColumn?: false;
};
export type SankeyChart = SingleChart & { spec: SankeySpec };
```
