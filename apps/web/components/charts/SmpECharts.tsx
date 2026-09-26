"use client";

/**
 * 全站唯一的 ECharts 挂载点。
 *
 * 两件事只在这里做一次，避免每个图表各写一套：
 *
 * 1. **关闭入场动画。** 这是研究终端，折线"长出来"的 300–400ms 对读数没有
 *    信息量，却让每一帧像素都不同 —— 视觉回归因此永远不确定。
 * 2. **登记渲染就绪。** 见 `@/lib/chartReadiness`：挂载或换数据时记一次待完成，
 *    收到 `finished`（或过完两帧屏障）后销账，测试据此等待而不是 sleep。
 */
import ReactECharts from "echarts-for-react";
import { useCallback, useEffect, useRef } from "react";

import { markChartRendered, registerChart } from "@/lib/chartReadiness";

export function SmpECharts({
  option,
  height,
  className,
  onEvents,
}: {
  option: Record<string, unknown>;
  height: number | string;
  className?: string;
  onEvents?: Record<string, () => void>;
}) {
  const tokenRef = useRef<string | null>(null);

  useEffect(() => {
    const { token, cancel } = registerChart();
    tokenRef.current = token;
    return () => {
      tokenRef.current = null;
      cancel();
    };
  }, [option]);

  const handleFinished = useCallback(() => {
    if (tokenRef.current) markChartRendered(tokenRef.current);
    onEvents?.finished?.();
  }, [onEvents]);

  return (
    <ReactECharts
      option={{ ...option, animation: false }}
      style={{ height, width: "100%" }}
      className={className}
      opts={{ renderer: "svg" }}
      notMerge
      onEvents={{ ...onEvents, finished: handleFinished }}
    />
  );
}
