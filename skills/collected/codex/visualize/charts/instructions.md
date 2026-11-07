# Standard chart interface

Read this, the selected family and applicable guides in one batch, skipping already-read files. Use standard components for supported requests, otherwise main-skill fallback. Use listed paths directly; do not search source/minified libraries or reread already-read guides. Preserve an explicitly requested chart type. Author plain HTML/JSON; types below describe the interface, not a required build step.

## Runtime

```yaml
chart_base_url: "https://persistent.oaistatic.com/plugins/visualize/charts/1.1.6"
```

Import `mountChart` from `{{CHART_BASE_URL}}/element.js`; keep this pin. Use a section with data-viz-composition, an owned div with data-viz-container, and a script type="application/json" with data-viz-chart holding strict JSON. A module script imports mountChart, parses that JSON and passes the container and full config; it synchronously returns an element, rendering async. Update complete `chart.config`; nested mutation does not render. No `ready/update/dispose` handle. Keep controls outside, IDs unique and lookups consistent. Initialize defaults, mount once, update data/readouts; disable controls until ready or retain pending selections. Reveal hidden panels before mounting. Runtime owns geometry/theme/legend/tooltips/loading/errors and cleanup; clean up only your own listeners/timers. Keep the native legend and default palette unless the user requests customization. For custom legends, share explicit colors with spec.colors; --chart-\* variables are chart-scoped. Literal labels support `<`, `&` and quotes; escape `<` in script JSON as `\u003c`. Never change network policy/pin.

### Canonical mounting example

Use this wiring for every family; replace the data and `spec` using its guide. Resolve `{{CHART_BASE_URL}}` from the pin above before writing the HTML.

```html
<section id="monthly-usage" data-viz-composition>
  <div data-viz-container></div>
  <script type="application/json" data-viz-chart>
    {
      "id": "monthly-usage",
      "title": "Monthly usage (GB)",
      "spec": { "type": "area", "x": "month", "y": "usage", "yLabel": "GB" },
      "columns": ["month", "usage"],
      "rows": [
        ["Jan", 12],
        ["Feb", 18],
        ["Mar", 31]
      ]
    }
  </script>
</section>
<script type="module">
  import { mountChart } from "{{CHART_BASE_URL}}/element.js";
  const root = document.getElementById("monthly-usage");
  const config = JSON.parse(root.querySelector("[data-viz-chart]").textContent);
  const chart = mountChart(root.querySelector("[data-viz-container]"), config);
</script>
```

For controls, assign a complete configuration to `chart.config`; keep controls outside the chart container.

## Constraints not expressed by types

- Preserve data, precision, units, grain, populations and denominators. Numbers stay numbers; null is unknown where permitted, zero observed. No invented/dropped/rounded values or mixed detail/totals; label assumptions and material caveats visibly. Bind exact case-sensitive field names, not expressions. Tuple widths match columns; column names are nonempty/unique, excluding `__proto__`, `constructor`, `prototype`.
- Limits: 2,000 rows/chart, 2MB UTF-8 JSON before/after tuple expansion, 1MB HTML or tighter host limit. Request reviewed reduction if exceeded. IDs/titles nonempty ≤1,000 characters; description/summary ≤10,000; height 120–800px, default 280. Comparisons have 2–3 distinct IDs, only charts on wrapper. Empty rows valid.
- `valueFormat`: percent uses fractions, currency requires code without conversion; digit bounds integers 0–15, min≤max. Both fixed=2 pads, max alone rounds, min alone allows max15; omit for distinction-preserving defaults. Full display only, not data/geometry. Reject conflicting legacy settings. Supported by line/area/sparkline/bar except normalized, scatter Y, pie/heatmap/ranking/funnel/waterfall; not histogram/box plot/Sankey. Numeric X/categories/pie center/funnel percentages remain separate.
- `colors`: ≤40 nonblank keys of ≤160 characters, mapped by measure/series (single bar/pie also category). Opaque #RGB/#RRGGBB or var(--chart-1)…var(--chart-8), var(--positive), var(--negative), var(--secondary), var(--text). Line/area/bar/scatter/pie only. Absent identities ignored; others default. Keep mappings/scales stable across filters, match external swatches, support both themes and retain text labels.

## Public types

```ts
export type Scalar = string | number | boolean | null;
export type Domain = [number, number];
export type SortOrder = "original" | "ascending" | "descending";
export type ValueFormat = {
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
} & (
  | { style: "decimal" | "percent"; currency?: never }
  | { style: "currency"; currency: string }
);
export type ChartColors = Record<string, string>;
export type PointAnnotation = {
  kind: "point";
  id: string;
  field: string;
  label: string;
} & (
  | { at: string | number; rowId?: never }
  | { rowId: string | number; at?: never }
);
type References<Axis extends string = "y"> = {
  referenceLines?: { axis: Axis; value: number; label: string }[];
  referenceBands?: { axis: Axis; from: number; to: number; label: string }[];
  annotations?: PointAnnotation[];
  /** Stable string/numeric row identity; annotations use rowId instead of at. */
  rowId?: string;
};
type LineReferences = Omit<References<"y" | "x">, "referenceLines"> & {
  referenceLines?: (
    | {
        axis: "y" | "x";
        value: number;
        label: string;
        between?: never;
        fraction?: never;
      }
    | {
        axis: "x";
        value: string;
        label: string;
        between?: never;
        fraction?: never;
      }
    | {
        axis: "x";
        between: [string, string];
        fraction?: number;
        label: string;
        value?: never;
      }
  )[];
};
type Uncertainty<Style extends string = "bars"> = {
  lower: string;
  upper: string;
  style: Style;
  /** Supplied meaning, e.g. "95% confidence interval"; otherwise "Interval". */
  label?: string;
};
type Measures =
  | { y: string; series?: string }
  | { y: [string, ...string[]]; series?: never };
type SingleMeasure = { y: string | [string]; series?: never };
type MeasuredFeatures<Features> =
  | (Measures & { [Key in keyof Features]?: never })
  | (SingleMeasure & Features);
type AxisLabels = { xLabel?: string; yLabel?: string };
type Cartesian = AxisLabels & {
  x: string;
  showValues?: boolean;
  showLegend?: boolean;
  startAtZero?: boolean;
  yDomain?: Domain;
  yAxisPosition?: "left" | "right";
  valueDecimals?: number;
};
export type ChartData =
  | { columns?: never; rows: Record<string, Scalar>[] }
  | { columns: [string, ...string[]]; rows: Scalar[][] };
export type SingleChart = ChartData & {
  id: string;
  title: string;
  spec: StandardChartSpec;
  /** Charts 1.2.0+: set to false when the embedding block supplies the visible title and description. */
  showHeader?: boolean;
  description?: string | null;
  summary?: string | null;
  height?: number | null;
};
export type Comparison = {
  charts: [SingleChart, SingleChart] | [SingleChart, SingleChart, SingleChart];
} & { [Key in keyof SingleChart]?: never };
export type ChartConfig = (SingleChart & { charts?: never }) | Comparison;
export interface VisualizeChartElement extends HTMLElement {
  /** Assign a full envelope to update. Nested mutations alone do not render. */
  config: ChartConfig | null;
}
export declare function mountChart(
  container: HTMLElement,
  config: ChartConfig,
): VisualizeChartElement;
```

## Additional workflows

Read controls.md for inputs/calculations, composition.md for analysis/requested tables, coordinated.md for linked views/persistence, annotations.md for references/uncertainty. Read cartesian-inputs.md for line/area/bar/sparkline. Tables only when requested; never omit required visual layers.

After a successful write, run `python3 <skill-dir>/scripts/render.py /absolute/chart.html --check` once in the same tool execution when supported. Read the chart payload count. If a standard chart is built in JavaScript, validate the complete config passed to mountChart and representative configs assigned to chart.config using the control-state check in controls.md. Fix validation failures before delivery. Verify calculations and state transitions separately. Browser inspection is for concrete defects or explicit requests.
