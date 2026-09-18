"use client";

import { Phase2Placeholder } from "@/components/shell/Phase2Placeholder";

export default function Page() {
  return (
    <Phase2Placeholder
      title={"紫微斗数"}
      subtitle={"十四主星 · 十二宫位 · 四化飞星"}
      activeNav={"ziwei"}
      reason={"紫微斗数引擎在 Phase 1 **明确不实现**（会话一禁止事项）。系统不会提供任何伪造的紫微结果，紫微也不会以 0 分参与任何聚合。"}
      planned={[
        "iztro 接入（services/ziwei-service，TypeScript 独立服务）",
        "4×4 十二宫盘面，含宫干支 / 主星 / 辅星 / 煞曜 / 四化 / 运限标记",
        "财帛宫、命宫、官禄宫轻度高亮",
        "大限 / 流年 / 流月 / 流日",
        "股票无性别 → 并行计算 variant_a / variant_b 两种顺逆假设并分别回测",
      ]}
      docRef={"architecture_v1.md §11 / §23；two_session_plan_v1.md §23-24"}
    />
  );
}
