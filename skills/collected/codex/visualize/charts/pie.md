# Pie

Nonnegative mutually exclusive parts of a known whole. innerRadius 0 gives pie; 0≤radius<1 is a fraction, default54/82 gives donut. Max40 unique categories, positive finite total; negative/null/duplicate/all-zero invalid. Zero retained without arc; never automatic Other. Values default off, legend available; >8 categories alone is not a fallback reason. Tooltips give value and visible share; valueFormat formats measured values, not derived shares or caller-owned center. centerValue is explicit number/formatted string ≤1000 chars; centerLabel requires value, both donut-only and must fit. Legend toggles change shares but not center: visibly note "Shares reflect visible categories" and label fixed totals. External filters must update center if its meaning changes. Legacy decimals0–6 default1/currency must not conflict with valueFormat. Permanent labels that cannot fit need fallback; no grouping/nested pies/additional rings.

```ts
export type PieSpec = {
  type: "pie";
  category: string;
  value: string;
  /** Fraction of outer radius in [0, 1): 0 is solid; omitted preserves the 54/82 donut ratio. */
  innerRadius?: number;
  showValues?: boolean;
  showLegend?: boolean;
  currency?: string;
  valueDecimals?: number;
  colors?: ChartColors;
  valueFormat?: ValueFormat;
} & (
  | { centerValue?: number | string; centerLabel?: never }
  | { centerValue: number | string; centerLabel?: string }
);
export type PieChart = SingleChart & { spec: PieSpec };
```
