# Waterfall

Reconcile beginning + ordered signed movements = ending. beginning is required in spec; rows contain movements only, no start/end totals. Optional ending must reconcile; retain decimal precision, never manufacture adjustment or round before reconciling. Empty rows show empty state. Start/end bars, signed colors and value labels are built in. No second measure, grouping or uncertainty overlays; valueFormat changes display only. Rendering metadata must not overwrite authored fields.

```ts
export type WaterfallSpec = AxisLabels & {
  type: "waterfall";
  x: string;
  y: string;
  beginning: number;
  ending?: number;
  valueFormat?: ValueFormat;
};
export type WaterfallChart = SingleChart & { spec: WaterfallSpec };
```
