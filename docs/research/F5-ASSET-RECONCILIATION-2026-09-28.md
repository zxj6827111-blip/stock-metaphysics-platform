# Fortune F5 候选资产对应表

- **核对日期**：2026-09-28
- **主仓库**：`codex/research-closure-remediation`，基线 `55dc4fd7f5d9976a995ee0176aa5f803b35a2ddd`
- **Fortune 工作树**：`codex/f5-research-closure`，HEAD `4345cdaa19c709a97ee15d963ec0e833ff268344`
- **状态约束**：仅清点与引用映射；不将 Fortune 工作树的未提交资产暂存、提交、删除或整体合并。

## 资产映射

| Fortune 候选资产 | 主仓库对应/状态 | 处理 |
|---|---|---|
| `src/research/fortune_f5/` 下的 contracts、dataset、features、outcomes、statistics、certification、artifact 与 remediation 模块 | 主仓库已有独立 W6 预注册实现和 W4/v2 事件研究链路；两者不是可直接互换的同一实现 | 不整体导入。候选模块依赖历史 F4 observation、PIT 与数据来源适配；保留在 Fortune 工作树，达到 ADR-0025 门槛后再逐项评估 |
| `tests/research/test_fortune_f5.py`、`test_fortune_f5b_certification.py`、`test_f5b1_remediation.py` | Fortune 候选模块的行为与来源验证 | 随候选代码保留；不把单测通过解释成全量真实数据认证 |
| `scripts/f5b_build_pit_universe.py`、`f5b1_build_assets.py`、`f5b1_generate_validation_sample.py` | PIT/security master 与 100 行 validation-sample 构建工具 | 作为后续来源准入工具保留；当前任务不运行全市场构建或扩大数据范围 |
| `docs/ADR/ADR-0021-stock-fortune-f5-historical-research.md` | 主仓库 ADR-0021 已接受且主题为 runtime readiness；同号 F5 文档是另一个工作树内的 Draft 候选 | 原件保持在 Fortune 工作树。主仓库已将跨工作树候选映射到 ADR-0025 Draft；今后择项迁入应引用 ADR-0025，不能覆盖主仓库 ADR-0021 |
| `docs/F5_DATASET_CERTIFICATION.md` | 当前资格结论仍为 `BLOCKED` / `READY_FOR_F5_EXPERIMENT=NO` | 作为限制和来源盘点证据保留；不升级研究资格 |
| `docs/STOCK_FORTUNE_ENGINE_V1_F5A.md` | 记录 F5-A 候选方法与早期环境状态 | 作为历史方法依据保留。文中“没有项目运行环境”的表述属于该工作树当时状态，不覆盖主仓库当前本地验收环境 |
| Fortune 工作树中被修改的 `docs/ADR/README.md` 及 `.pyc`，以及 `.codegraph/` | 属于该工作树未提交状态 | 保持原样，不纳入主仓库交付 |

## 已由主仓库继承或另行实现

- ADR-0022 已接受并规定版本化 v2 timeline、scan、event-study、dataset 和 experiment API；它不等同于旧 Fortune 候选 ADR-0021。
- ADR-0023、`config/f5_preregistered_experiments.yaml`、`config/f5_preregistered_002561_limited_v1.yaml`、`scripts/run_f5_preregistered_experiments.py` 与 `src/research/multipletesting/` 构成主仓库的 W6 冻结实验路径。具体资格与本次运行限制见 `docs/research/W6-2026-09-28.md` 和限域报告 `docs/research/W6-LIMITED-SCOPE-002561-2026-09-28.md`。
- 主仓库 W4 单证券限域数据与 v2 查询链路不包含历史全市场 PIT universe，也没有继承 Fortune F5-B.1 的未提交实现。

## W6 运行状态拆分

1. **统计算法测试**：冻结 W6 协议、置换/重采样函数、校正和状态表达的工程测试属于实现验证；它们证明算法代码可用，不等于真实样本检验已经执行。
2. **真实限域数据执行**：冻结报告中保留 78 项真实限域结果，结论为 `INSUFFICIENT_SAMPLE`。这些行只证明分类样本未达到预设样本门槛。
3. **未执行项目**：真实可置换日期数为 0，实际 permutation 次数为 0，bootstrap 次数为 0；因此置换、日期块 bootstrap 置信区间以及相应显著性推断均为 `NOT_RUN`。这不是“完整统计检验通过”。
4. **资格**：无 VALIDATION/OOS 有效结果；数据为单证券限域探索性范围，且 W2 完整 PIT 认证未通过。该批结果不具确认性或 OOS 资格。`F5-EXP-003` 未配置。

## 后续整合边界

当前 W0-W8 整改没有必须从 Fortune 工作树整合的代码资产。后续如启动 F5-B 全量准入，应以来源 crosswalk、raw/factor 物理检查、退市区间兼容、历史 F4 observation join、leakage 与可重放 dataset 为独立验收门；在这些条件具证据之前，F5 候选目录与脚本仅作为后续阶段资产保留。
