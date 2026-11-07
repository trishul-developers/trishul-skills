# Bar

Compare categories. Bindings and labels follow physical x/y axes. Multiple measures group ordinary bars or form stack parts. Signed values/null gaps/zeros work in ordinary/grouped bars; stacks require complete nonnegative additive parts. 100% stacks take original counts with positive category totals; legend toggles renormalize visible parts: visibly note "Shares reflect visible categories". All value axes linear and include zero. Single-measure bar/horizontalBar support references/annotations and bars uncertainty; horizontal value references follow the horizontal axis. Shared Cartesian inputs cover bindings, order, display and domains. Separate incomparable units/populations; never sum overlapping populations. Values default off, native legend available. Max 40 vertical/38 horizontal categories; horizontal height ≥40+20×categories (800 for 38). Labels wrap/hover; use fallback if required full labels cannot fit, never silently abbreviate/drop. No automatic Other grouping or overlays on grouped/stacked/normalized bars.

```ts
type BarOptions = {
  sortOrder?: SortOrder;
  colors?: ChartColors;
};
type HorizontalMeasures =
  | { x: string; series?: string }
  | { x: [string, ...string[]]; series?: never };
type HorizontalSingleMeasure = { x: string | [string]; series?: never };
type HorizontalMeasuredFeatures<Features> =
  | (HorizontalMeasures & { [Key in keyof Features]?: never })
  | (HorizontalSingleMeasure & Features);
type HorizontalCartesian = Omit<Cartesian, "x" | "yDomain"> & {
  y: string;
  xDomain?: Domain;
};
export type BarSpec = BarOptions & { valueFormat?: ValueFormat } & (
    | (Cartesian &
        MeasuredFeatures<References & { uncertainty?: Uncertainty }> & {
          type: "bar";
        })
    | (HorizontalCartesian &
        HorizontalMeasuredFeatures<
          References<"x"> & { uncertainty?: Uncertainty }
        > & { type: "horizontalBar" })
  );
export type StackedBarSpec = BarOptions & { valueFormat?: ValueFormat } & (
    | (Cartesian & Measures & { type: "stackedBar" })
    | (HorizontalCartesian &
        HorizontalMeasures & { type: "horizontalStackedBar" })
  );
export type NormalizedBarSpec = BarOptions &
  (
    | (Cartesian & Measures & { type: "stackedBar100" })
    | (HorizontalCartesian &
        HorizontalMeasures & { type: "horizontalStackedBar100" })
  );
export type BarChart = SingleChart & {
  spec: BarSpec | StackedBarSpec | NormalizedBarSpec;
};
```
