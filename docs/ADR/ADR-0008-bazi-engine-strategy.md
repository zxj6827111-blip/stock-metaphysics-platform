# ADR-0008 · 八字引擎策略：自研内核为 Canonical，bazi-pro 仅作 Phase 2 参考

| 项 | 值 |
|---|---|
| 状态 | **已接受（Phase 1.1 正式决策，替代 ADR-0002 的过渡措辞）** |
| 日期 | 2026-09-18 |
| 决策人 | Phase 1.1 验收负责人 |
| 关联 | [ADR-0002](ADR-0002-bazi-engine-backend.md)、[THIRD_PARTY.md](../../THIRD_PARTY.md) §1.3 |

## 背景

Phase 1 启动时曾假定"会接入第三方 bazi-pro"。Phase 1.1 验收重新评估这一假定，
在以下约束下做正式决策：

1. `new1234cq/bazi-pro` 仓库的 README/版权/提交历史大量指向原作者 `Minervaowl7/bazi-pro`，
   **无法确认当前账号与原作者的关系**；
2. **许可证未核实**（无明确 LICENSE 文件可追溯到原作者）；
3. 未无法在无网络环境下核实代码来源与签名；
4. 项目规则（AGENTS.md §12 / §13）：第三方代码必须经 Adapter 隔离；未核实许可证不得进入生产核心。

## 决策

**OPTION A：自研内核即 Canonical。**

```
八字引擎（生产）            = smx-bazi-native（完全自研，含规则内核 rules.py + 历法经本地 CalendarEngine 算法锁定）
bazi-pro                    = Phase 2 可选 reference（仅作"双引擎一致性校验"的参照物）
古籍藏经（Knowledge）        = 项目自持公版语料（knowledge/bazi/），不从任何第三方仓库复制
```

* Golden Case 36+ 项 + 对拍（lunar-python × 自研内核）已锁定当前行为；
* 若 Phase 2 未来 fork 并通过许可证核实，bazi-pro 可以作为 **第二个 engine**
  加入 `engine_version` 对比表，但这两个引擎必须满足同一 `MetaphysicsEngine` 契约，
  且任何分歧必须写入 `docs/calculation-differences-phase1.md`；
* **不允许**把 bazi-pro 代码搬进 `src/`、也不允许把四柱纳音等确定性口径"替换为 bazi-pro 的输出"
  而不留回归证据。

## 理由

| 维度 | 结论 |
|---|---|
| 许可证风险 | bazi-pro 许可证未核实 → **商用不可接受**，直接排除接入路径 |
| 来源可信度 | 账号历史与原作者不一致，无法建立信任链 |
| 工程现状 | 自研内核 1.0.0 已通过 129 项 golden + 46 项对拍；"为了接入而接入" 没有理由 |
| 可逆性 | 保留 `BaziProAdapter` 挂载点，Phase 2 若完成尽职调查可随时加入为参考实现 |

## 结论

* Canonical engine：`smx-bazi-native-1.0.0`（含后续小版本）。
* bazi-pro 当前状态：**不使用、不 fork、不复制、不信任**。
* Phase 2 若要重新评估：必须先完成（1）许可证核实、（2）作者关系确认、
  （3）代码 review，再写新 ADR。

参见：[ADR-0002](ADR-0002-bazi-engine-backend.md) 的"Phase 1 过渡决策"段在本 ADR 接受后被本决策取代。
