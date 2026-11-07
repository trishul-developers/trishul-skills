# Funnel

Preserve ordered reviewed stage values/populations, no automatic sorting/aggregation. Null breaks ribbon, zero measured. Increasing/non-nested populations are allowed but must not imply conversion. Visible labels/values, responsive vertical layout; hover/focus shows value/share-first/change-previous, unavailable when denominator unknown/zero. Tap pins/Escape dismisses. valueFormat changes measures only, not conversion meaning. No showValues/grouping/reference/axis/sorting options. Multiple series/overlapping cohorts/custom stage calculations need fallback; a control may select a single reviewed cohort.

```ts
export type FunnelSpec = {
  type: "funnel";
  category: string;
  value: string;
  valueFormat?: ValueFormat;
};
export type FunnelChart = SingleChart & { spec: FunnelSpec };
```
