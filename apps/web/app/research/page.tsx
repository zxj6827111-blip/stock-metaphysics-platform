"use client";

import { Phase2Placeholder } from "@/components/shell/Phase2Placeholder";

export default function Page() {
  return (
    <Phase2Placeholder
      title={"研究实验室"}
      subtitle={"选择因子与股票池，运行事件研究与负对照"}
      activeNav={"research"}
      reason={"研究流水线的后端已实现（POST /api/v1/research/run，包含随机出生日 / ±7 天 / 随机因子四类负对照），可以通过 OpenAPI 文档直接调用；图形化实验台属于第二轮 UI。"}
      planned={[
        "选择因子 / 股票池 / 目标窗口 / 市场区间",
        "运行事件研究、负对照、样本外测试",
        "保存与对比 Experiment",
      ]}
      docRef={"uiux_spec_v1.md §23"}
    />
  );
}
