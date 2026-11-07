# Sparkline

Compact ordered trend, axes/grid hidden; name quantity/units/time span nearby. Shared Cartesian bindings/display/domain; values default off, legend/tooltips available, preserve explicit null gaps, zero and isolated observations. No drag zoom/log/colors overrides/references/annotations/uncertainty. Use regular line for these features, precise axes or many series; unsupported requirements use fallback.

```ts
export type SparklineSpec = Cartesian &
  Measures & {
    type: "sparkline";
    valueFormat?: ValueFormat;
  };
export type SparklineChart = SingleChart & { spec: SparklineSpec };
```
