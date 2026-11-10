import * as echarts from "echarts/core";
import {
  BarChart,
  GaugeChart,
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
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";

echarts.use([
  AriaComponent,
  BarChart,
  DataZoomComponent,
  DatasetComponent,
  GaugeChart,
  GridComponent,
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
]);

export { echarts };
