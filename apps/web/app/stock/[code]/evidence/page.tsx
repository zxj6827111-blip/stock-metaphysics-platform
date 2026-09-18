"use client";

import { Phase2Placeholder } from "@/components/shell/Phase2Placeholder";

export default function Page() {
  return (
    <Phase2Placeholder
      title={"古籍证据"}
      subtitle={"支持依据与相反观点并列"}
      activeNav={"evidence"}
      reason={"KnowledgeProvider（BM25 + 权威权重 + 支持/反证）已实现并通过 API 暴露，综合研判页的『关键证据』卡片已可打开证据抽屉。独立的古籍检索页属于第二轮 UI。"}
      planned={[
        "三栏布局：术数体系/书目 · 检索结果 · 条目详情",
        "每条显示书名 / 章节 / 流派 / 原文 / 现代说明 / 来源 / 版本 / provenance / license_status",
        "支持当前规则 / 与当前规则相反 / 中性背景三分（不按吉凶染色）",
      ]}
      docRef={"uiux_spec_v1.md §21；doc/ui-reference/09_classics_evidence_search.png"}
    />
  );
}
