"use client";

import { Phase2Placeholder } from "@/components/shell/Phase2Placeholder";

export default function Page() {
  return (
    <Phase2Placeholder
      title={"因子字典"}
      subtitle={"因子定义 · 版本 · 历史表现"}
      activeNav={"factors"}
      reason={"因子定义的后端已实现（GET /api/v1/factor-dictionary，Phase 1 共 65 个因子），本页为第二轮 UI。"}
      planned={[
        "表格：Factor ID / 名称 / 术数 / 层级 / 方向 / 版本 / 状态 / 样本数 / 历史 IC",
        "详情：定义 / 计算规则 / 对应代码 / 古籍来源 / 历史表现 / 版本历史",
        "启用 / 停用开关（带审计记录）",
      ]}
      docRef={"uiux_spec_v1.md §24；doc/ui-reference/06_factor_dictionary.png"}
    />
  );
}
