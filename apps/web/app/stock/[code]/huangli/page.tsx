"use client";

import { Phase2Placeholder } from "@/components/shell/Phase2Placeholder";

export default function Page() {
  return (
    <Phase2Placeholder
      title={"黄历 / 日课"}
      subtitle={"以日课之数，察天时之变"}
      activeNav={"huangli"}
      reason={"黄历引擎（HuangliEngine）在 Phase 1 已经实现并通过 API 暴露（GET /api/v1/analysis/{id}/huangli），但本页的正式视觉复刻尚未完成 —— 参考图 08_huangli_detail.png 属于第二轮 UI 范围。为避免本阶段只做半套设计，此处先保留占位，接口与数据已就绪。"}
      planned={[
        "阳历 / 农历 / 年月日干支 / 节气 / 生肖 / 纳音",
        "建除十二值 / 十二神 / 黄黑道 / 冲煞 / 彭祖百忌 / 吉神方位",
        "与该股票原局的关系（H_DAY_* 因子）单独分区展示",
        "传统黄历数据与股票研究映射严格分离",
      ]}
      docRef={"uiux_spec_v1.md §19；doc/ui-reference/08_huangli_detail.png"}
    />
  );
}
