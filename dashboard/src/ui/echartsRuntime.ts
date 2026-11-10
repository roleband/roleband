import * as echarts from "echarts/core";
import {
  BarChart,
  GaugeChart,
  HeatmapChart,
  LineChart,
  ScatterChart,
  SunburstChart,
} from "echarts/charts";
import {
  AriaComponent,
  DataZoomComponent,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  PolarComponent,
  TitleComponent,
  TooltipComponent,
  TransformComponent,
  VisualMapComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";

echarts.use([
  AriaComponent,
  BarChart,
  DataZoomComponent,
  DatasetComponent,
  GaugeChart,
  GridComponent,
  HeatmapChart,
  LegendComponent,
  LineChart,
  MarkLineComponent,
  PolarComponent,
  ScatterChart,
  SVGRenderer,
  TitleComponent,
  TooltipComponent,
  TransformComponent,
  SunburstChart,
  VisualMapComponent,
]);

export { echarts };
