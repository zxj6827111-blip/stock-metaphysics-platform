# ADR-0025：F5 历史研究候选资产保留与集成门槛

- **状态**：Draft
- **日期**：2026-09-28
- **影响**：Fortune F5 候选研究代码、数据来源认证、PIT 证券池及未来 observation dataset
- **关联**：[ADR-0013](ADR-0013-research-validity-boundary.md)、[ADR-0020](ADR-0020-stock-fortune-timeline-and-cross-section.md)、[ADR-0022](ADR-0022-versioned-research-v2-api.md)、[ADR-0023](ADR-0023-f5-preregistered-experiments.md)
- **资产清点**：[F5 资产对应表](../research/F5-ASSET-RECONCILIATION-2026-09-28.md)

## 背景

Fortune 工作树含有尚未提交的 F5-A/F5-B/F5-B.1 候选代码、测试、来源脚本和报告。该工作树的 F5 草案把自身编号为 ADR-0021；本仓库 ADR-0021 已是已接受的运行就绪决策。两个文件属于不同工作树，编号相同不表示内容相同或状态继承。

F5-B.1 的可用证据仍是有限的 PIT / 来源资产和 100 行真实验证样本。数据报告记载全量 raw/factor 物理审计未完成、factor 起点存在晚于 raw 的证券、退市端点语义未对齐，且没有真实 F4 profile/timeline observation join。因此这些资产尚不能构成可确认性研究数据集。

## 决策（待证据接受）

1. 本仓库 ADR-0021 保持“核心历法失败关闭与实例就绪状态”，状态不变。Fortune 工作树中的同号 F5 文件继续作为原始候选记录保留；任何被择项迁入本仓库的 F5 边界决策必须引用 ADR-0025，不得将该候选误认成或覆盖 ADR-0021。
2. Fortune 工作树中的 F5 代码、测试、脚本、文档和已有修改继续留在原工作树。此 ADR 不授权整目录合并、资产删除、工作树清理或把所有候选实现视为已接受。
3. 当前 W0-W8 交付不依赖整合 `src/research/fortune_f5/` 或 F5-B.1 全市场数据构建代码。对应代码与脚本保留为后续 F5 数据准入工作；在物理覆盖、F4 observation join、契约适配和完整可重放产物通过前，不将其接入正式研究主链。
4. F5 实验资格必须分开报告统计算法单测、真实限域数据实际运行的检验、未运行项目及原因，以及确认性/OOS 资格。78 项 `INSUFFICIENT_SAMPLE` 可以作为合法实验结果保留；置换和 bootstrap 实际次数为 0 时状态必须为 `NOT_RUN`，不能表述为统计检验通过。
5. `F5-EXP-003` 保持未配置；不得为生成显著结果而扩展股票池、改窗口、调整规则或自动搜索组合。

## 接受门槛

须有经核实的 PIT 与行情版本 crosswalk、必要行情和 factor 的全量物理覆盖、明确且兼容的退市区间语义、历史 F4 observation 与 PIT membership 的实际连接、未来数据隔离证据，以及固定输入可字节级重放的完整 dataset/artifact。满足前不得把候选资产标为已接受或授予确认性/OOS 资格。

## 状态

本 ADR 是本仓库对跨工作树编号冲突和资产集成边界的主索引，当前保持 Draft。原 Fortune 候选文件不因该映射改变其原工作树中的内容或 Draft 状态；具体来源与去向见资产对应表。
