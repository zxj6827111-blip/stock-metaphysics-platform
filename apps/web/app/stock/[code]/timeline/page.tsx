"use client";

import { Phase2Placeholder } from "@/components/shell/Phase2Placeholder";

export default function Page() {
  return (
    <Phase2Placeholder
      title={"时间窗口"}
      subtitle={"月 / 周 / 交易日三档时间窗口"}
      activeNav={"timeline"}
      reason={"月度与周度时间窗口属于 Phase 2。特别说明：传统八字没有『流周』，周度必须由**交易日流日因子聚合**得到，聚合方法需要版本化并回测比较。"}
      planned={[
        "未来 12 个月趋势图 + 月份排名 / 共识 / 分歧",
        "周度热力矩阵（周一~周五 + 周综合）",
        "聚合方法：mean / median / min / max / positive_day_ratio（版本化）",
        "点击某月/某周展开八字、紫微、黄历、古籍与历史统计依据",
      ]}
      docRef={"architecture_v1.md §61-63；uiux_spec_v1.md §11-13"}
    />
  );
}
