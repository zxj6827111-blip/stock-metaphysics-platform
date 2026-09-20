"use client";

import { Phase2Placeholder } from "@/components/shell/Phase2Placeholder";

export default function Page() {
  return (
    <Phase2Placeholder
      title={"系统设置"}
      subtitle={"数据源 · 术数引擎 · 出生模型 · 研究模式"}
      activeNav={"settings"}
      reason={"设置页属于 Phase 2。特别说明：切换出生模型必须生成「新版本」，不能覆盖历史结果 —— 该约束在后端已通过 stock_birth_profile 的唯一约束（stock_code + birth_basis + birth_profile_version）落地。"}
      planned={[
        "基础设置 / 数据源 / 术数引擎 / 出生模型 / 模型融合 / AI 解释器 / 古籍知识库 / 研究模式",
        "出生模型切换：上市首日开盘 / IPO 发行日 / 公司成立日 / 自定义",
        "版本管理与历史结果对比",
      ]}
      docRef={"uiux_spec_v1.md §26-27"}
    />
  );
}
