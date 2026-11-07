/** Portable authoring API exported by a release's element.js.
 * Runtime validation additionally checks finite numbers, bindings, data shape,
 * semantic compatibility, and documented size/range limits. No build is needed
 * to author HTML; these developer types do not expose internal artifact APIs.
 */
export type Scalar = string | number | boolean | null;
export type JsonValue = Scalar | JsonValue[] | { [key: string]: JsonValue };
export type Domain = [number, number];
export type SortOrder = "original" | "ascending" | "descending";
export type ValueFormat = {
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
} & (
  | { style: "decimal" | "percent"; currency?: never }
  | { style: "currency"; currency: string }
);
/** Opaque #RGB/#RRGGBB or one of the documented theme variables. */
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
/** Wide measures bind a physical-axis tuple; long form binds one measure plus series. */
type Measures =
  | { y: string; series?: string }
  | { y: [string, ...string[]]; series?: never };
type SingleMeasure = { y: string | [string]; series?: never };
type MeasuredFeatures<Features> =
  | (Measures & { [Key in keyof Features]?: never })
  | (SingleMeasure & Features);
/** Labels always refer to the physical horizontal (x) and vertical (y) axes. */
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
export type LineSpec = Cartesian &
  MeasuredFeatures<
    LineReferences & {
      uncertainty?: Uncertainty<"bars" | "band">;
    }
  > & {
    type: "line";
    xScale?: "linear" | "log";
    yScale?: "linear" | "log";
    xDomain?: Domain;
    colors?: ChartColors;
    valueFormat?: ValueFormat;
  };
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
/** Bar bindings and labels name physical axes. Horizontal bars put categories on y. */
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
export type SparklineSpec = Cartesian &
  Measures & {
    type: "sparkline";
    valueFormat?: ValueFormat;
  };
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
export type HistogramSpec = AxisLabels & {
  type: "histogram";
  showValues?: boolean;
  showLegend?: boolean;
} & (
    | {
        input: "raw";
        x: string;
        y?: never;
        binLayout?: never;
        statistic?: never;
      }
    | {
        input: "binned";
        x: { lower: string; upper: string; label: string };
        y: string;
        /** Equal-width interval slots by default; proportional preserves numeric widths. */
        binLayout?: "equal" | "proportional";
        statistic?: "count" | "frequency" | "density";
      }
  );
export type WaterfallSpec = AxisLabels & {
  type: "waterfall";
  x: string;
  y: string;
  beginning: number;
  ending?: number;
  valueFormat?: ValueFormat;
};
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
export type RankingSpec = {
  type: "leaderboard" | "rankedList";
  category: string;
  value: string;
  sortOrder?: SortOrder;
  valueFormat?: ValueFormat;
};
export type FunnelSpec = {
  type: "funnel";
  category: string;
  value: string;
  valueFormat?: ValueFormat;
};
export type BoxPlotSpec = AxisLabels & {
  type: "boxPlot";
  x: string;
  y: string;
  yAxisPosition?: "left" | "right";
  /** Raw data only; reviewed five-number summaries already define their endpoints. */
  whiskers?: "tukey" | "minMax" | { percentiles: Domain };
};
export type SankeySpec = {
  type: "sankey";
  stages:
    | [string, string]
    | [string, string, string]
    | [string, string, string, string];
  value: string;
  colorByColumn?: false;
};
export type StandardChartSpec =
  | LineSpec
  | AreaSpec
  | StackedAreaSpec
  | BarSpec
  | StackedBarSpec
  | NormalizedBarSpec
  | SparklineSpec
  | ScatterSpec
  | PieSpec
  | HistogramSpec
  | WaterfallSpec
  | HeatmapSpec
  | RankingSpec
  | FunnelSpec
  | BoxPlotSpec
  | SankeySpec;
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
/** Only charts belongs on the comparison wrapper; metadata belongs on each chart. */
export type Comparison = {
  charts: [SingleChart, SingleChart] | [SingleChart, SingleChart, SingleChart];
} & { [Key in keyof SingleChart]?: never };
export type ChartConfig = (SingleChart & { charts?: never }) | Comparison;
export interface VisualizeChartElement extends HTMLElement {
  /** Assign a full envelope to update. Nested mutations alone do not render. */
  config: ChartConfig | null;
}
/** Synchronous return, asynchronous rendering. Owns/replaces container contents.
 * Later validation/loading errors appear in the element and window error stream.
 * Removal disconnects/disposes the chart; no public ready/update/dispose handle.
 */
export declare function mountChart(
  container: HTMLElement,
  config: ChartConfig,
): VisualizeChartElement;
export interface WidgetSnapshot {
  modelContent?: JsonValue;
  privateContent?: JsonValue;
}
export interface VisualizeStateHost {
  widgetState: WidgetSnapshot | null;
  /** Replaces the snapshot; optimistic local state, best-effort persistence. */
  setWidgetState(next: WidgetSnapshot): Promise<void>;
}
/** Local typing for hosted/standalone contexts without changing global Window. */
export type VisualizeWindow = Window & { openai?: VisualizeStateHost };
export type WidgetGlobalsEvent = CustomEvent<{
  globals: { widgetState?: WidgetSnapshot | null };
}>;
