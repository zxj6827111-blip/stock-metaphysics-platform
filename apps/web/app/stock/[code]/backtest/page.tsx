"use client";

import { Phase2Placeholder } from "@/components/shell/Phase2Placeholder";

export default function Page() {
  return (
    <Phase2Placeholder
      title={"历史验证"}
      subtitle={"样本数 · 上涨率 · 超额收益 · 负对照"}
      activeNav={"backtest"}
      reason={"事件研究与四类负对照的后端已实现（POST /api/v1/research/run），但参考图 05_backtest_validation.png 的完整可视化属于第二轮 UI。"}
      planned={[
        "关键指标：样本数 / 上涨率 / 平均收益 / 中位数 / 超额收益 / 最大回撤 / IC / 稳定性",
        "收益分布、持有期收益、年度稳定性、牛熊震荡分组",
        "随机对照与出生日期平移对照并列展示",
        "样本内 / 样本外对比",
      ]}
      docRef={"uiux_spec_v1.md §22；doc/ui-reference/05_backtest_validation.png"}
    />
  );
}
