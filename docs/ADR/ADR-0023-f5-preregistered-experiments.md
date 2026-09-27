# ADR-0023：F5 首批预注册实验与可重放统计

- **状态**：Draft
- **日期**：2026-09-28
- **影响**：F5 历史研究、统计重采样、实验报告、W6 API 报告读取
- **关联**：[ADR-0004](ADR-0004-as-of-time-isolation.md)、[ADR-0013](ADR-0013-research-validity-boundary.md)、[ADR-0021](ADR-0021-runtime-readiness-and-fail-closed-calendar.md)、[ADR-0022](ADR-0022-versioned-research-v2-api.md)

## 背景

W6 首轮要求把实验条件、数据版本、排除规则、随机种子和检验族冻结后再读取对应分类结果，并保留负结果。现有 `multipletesting` 已提供日期分层置换、BH-FDR/Bonferroni、gate-v2 与旧 date bootstrap；后者按单日独立抽样，不能替代 W6 所需的连续 20 个交易日移动块。

当前可用的 W4 数据集是单证券工程样本，W2 仍未完成完整物理认证。此前的 W4 工程验收已披露少量标签汇总，因此本 ADR 和配置将该协议明确标为探索性预注册；不能声称样本在任何先导摘要之前完全未被查看。

## 决策

1. `config/f5_preregistered_experiments.yaml` 是冻结的 W6 协议版本 `f5-preregistered-v1`，固定 W4 dataset id 与 SHA-256、研究分区、条件、族大小、周期、检验尾部和种子。修改任一条件必须新建协议版本和实验 ID。
2. `F5-EXP-001` 检验 `B_DAY_005` 的十个明确 `raw_value` 类别；`F5-EXP-002` 检验 `B_DAY_003` 六合、`B_DAY_002` 六冲和 `B_DAY_008` 相害，均以未激活观察为补集、5/20 日为周期、无预设方向、双侧检验。族大小分别固定为 60 与 18，覆盖三个既有时间分区。
3. 主要推断指标使用同周期 benchmark excess return；调整后绝对收益仅作描述。缺失基准、降级标签或不完整窗口保持缺失，不以 0、原始收益或合成值替代主指标。
4. 置换复用 `permutation_test` 的日期分层零假设，W6 固定 2,000 次。bootstrap 新增连续日期移动块函数，固定 2,000 次、95% 区间和至少 20 个连续交易日块；少于两个可用块起点时不输出置信区间。
5. 检验族使用既有 BH 算法与 Bonferroni。预注册测试因缺数据而不可计算时，以 p=1 填充冻结族分母用于校正，但原始 p/q 仍返回 null，并显式报告不可用数，不能缩小检验族。
6. 负对照复用 `random_factor_control`，固定随机种子。由于其既有契约使用绝对收益，该结果仅标作诊断，不替代 excess-return 主分析或 gate-v2。
7. 时间分区隔离要求已保存 5/20 日 `label_end_date`。缺少任一标签终点时只保留描述统计，隔离推断和跨边界窗口判定均标为不可验证；若终点进入下一分区，该观察从本分区隔离结果中排除。
8. `F5-EXP-003` 保持未配置，不自动搜索组合。实验 JSON 写入固定 `settings.data_dir/research_experiments`；同一输入重放字节一致，遇到不同的既有报告时拒绝覆盖。
9. W2 未认证或 W4 dataset 不具备资格时，报告保持 `EXPLORATORY_NOT_GATED` / `INSUFFICIENT_SAMPLE`，不能由统计代码将其提升为历史有效或 OOS 支持。

## 后果

- 当前工程样本可以验证协议重放和状态表达；缺 benchmark 超额收益、分区终点或足够股票横截面时，正式置换、区间和 gate 保持不可用。
- 连续日期块 bootstrap 与旧 Phase 3F bootstrap 语义不同，使用独立函数和版本号，旧结果不变。
- 新一批认证范围必须创建独立 dataset/version 与新预注册版本，不能替换本次冻结的工程样本输入。

## 接受依据

待协议校验、置换/移动块统计、固定根报告读写和完整目标测试通过后记录 W6 commit、重放 digest 与实际样本限制。
