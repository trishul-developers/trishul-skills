# Scatter

Finite paired coordinates, preserving zero/negative/coincident points; no dropping/coercing missing coordinates. Group field nonblank strings; use row `name` for tooltip identity and point annotations for individual labels; default formatting preserves distinct numbers. Categorical X: unique nonblank nonnumeric strings, no mixing numeric/category values. Numeric X can repeat; annotations then need unique stable spec.rowId and annotation rowId, not at (string/number identities distinct, max300-char strings). Absent IDs omit marks, never jump; uncertainty still requires unique X. Log coordinates/bounds positive; label axes and retain untransformed values, no epsilon. startAtZero affects linear Y only. Numeric domains cover observations/overlays; no category xDomain. References/annotations/Y-bars uncertainty ungrouped only. Fit only when requested: linear/quadratic unweighted least squares in original units per group, not log regression or point connections; spans observed range, clipped, no extrapolation/CI/significance inference. Linear needs2 distinct X, quadratic3; unstable/insufficient keeps points with unavailable note; filters recompute. No showValues/showLegend switches, bubble sizing, other fits, X uncertainty or all-point permanent labels. Nearest-X hover lists exact-X observations, scrolling if needed. Unsupported features use fallback.

```ts
export type ScatterSpec = AxisLabels &
  (
    | ({ series?: never } & References<"y" | "x"> & {
          uncertainty?: Uncertainty;
        })
    | ({ series?: string } & {
        [Key in keyof References | "uncertainty"]?: never;
      })
  ) & {
    type: "scatter";
    /** Least squares in original coordinates, independently per series. */
    fit?: "linear" | "quadratic";
    x: string;
    y: string;
    startAtZero?: boolean;
    xScale?: "linear" | "log";
    yScale?: "linear" | "log";
    xDomain?: Domain;
    yDomain?: Domain;
    yAxisPosition?: "left" | "right";
    colors?: ChartColors;
    valueFormat?: ValueFormat;
  };
export type ScatterChart = SingleChart & { spec: ScatterSpec };
```
