"use client";

import { Phase2Placeholder } from "@/components/shell/Phase2Placeholder";

export default function Page() {
  return (
    <Phase2Placeholder
      title={"模型分歧"}
      subtitle={"禁止用平均分掩盖分歧"}
      activeNav={"conflicts"}
      reason={"正式 ConflictDetector 属于 Phase 2。Phase 1 在综合研判页提供了**展示层**的分歧快照（GET /api/v1/analysis/{id}/conflicts）。在紫微引擎接入之前，多模型分歧矩阵没有完整的三方数据。"}
      planned={[
        "三模型分歧矩阵（八字 / 紫微 / 黄历两两方向对比）",
        "主要冲突规则与其因子依据",
        "历史上该类冲突组合的出现次数与未来 5/10/20/60 日表现",
      ]}
      docRef={"architecture_v1.md §80；uiux_spec_v1.md §20"}
    />
  );
}
