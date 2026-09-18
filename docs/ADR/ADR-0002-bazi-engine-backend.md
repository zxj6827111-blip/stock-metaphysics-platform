# ADR-0002：Phase 1 八字计算使用自研确定性内核

- **状态**：已接受（Phase 1）；**Phase 2 需要重新评估**
- **日期**：2026-09-18
- **影响**：八字引擎、因子体系、Golden Case

## 背景

架构文档要求八字计算使用 `new1234cq/bazi-pro`（经 fork + 锁定 commit）。

实际情况：

1. 启动 Phase 1 时，仓库中**不存在** bazi-pro 的 fork；
2. bazi-pro 的 README / 版权 / 提交历史大量指向原作者 `Minervaowl7/bazi-pro`，
   **无法确认当前账号与原作者的官方关系**；
3. 未能核实其许可证状态（商业使用前必须核实）；
4. 无法在不联网核实的情况下"锁定一个明确 commit SHA"。

同时，Phase 1 的验收标准要求八字输出必须包含：
年柱/月柱/日柱/时柱/藏干/十神/纳音/五行/日主/旺衰/格局/喜神/用神/忌神/刑冲合害/流年/流月。

而其中：

* 四柱、藏干、十神、纳音、十二长生 → **lunar-python 已能可靠提供**；
* 五行力量、旺衰、格局、喜用忌、刑冲合害 → 属于**命理规则运算**，需要自研或引入 bazi-pro。

## 备选方案

| 方案 | 优点 | 缺点 |
|---|---|---|
| A. 直接从 GitHub 拉 bazi-pro 源码 | 功能现成 | 许可证未核实；无法锁 commit；可能引入大量不必要依赖；升级不可控 |
| B. 复制 bazi-pro 相关代码进主项目 | 无需外部依赖 | **违反 AGENTS.md §11**；后续无法跟进上游修复；版权风险 |
| C. 自研确定性规则内核 + 保留 adapter 挂点 | 完全可控、可测试、可版本化；无版权风险 | 需要自己实现规则；流派覆盖不如成熟项目 |
| D. 完全不实现格局/喜用忌，返回 unavailable | 最保守 | 验收标准明确要求这些字段存在或"明确 unavailable"，全部 unavailable 会大幅降低系统价值 |

## 决策

**采用方案 C。**

1. 实现 `smx-bazi-native-1.0.0`：
   * 历法部分用 `CalendarEngine`（lunar-python）；
   * **命理关系运算**（十神、藏干、十二长生、刑冲合害）在 `src/core/constants.py` 中自持；
   * **规则运算**（五行力量、旺衰、格局、喜用忌）在 `src/engines/bazi/rules.py` 中自研，
     全部为**纯函数**、可单测；
2. 所有规则输出 `rationale`（判定过程）与 `confidence`（置信度），
   无法可靠判定时返回 `unavailable`，**禁止猜测**；
3. `BaziEngine.metadata.third_party` 字段保留 `"6tail/lunar-python（仅历法）+ 自研确定性规则内核"`，
   并在 `notes` 中写明 bazi-pro 尚未 fork；
4. **保留 `backend` 概念**：Phase 2 可挂 bazi-pro adapter 做**双引擎交叉验证**，
   差异写入 `docs/calculation-differences.md`。

## 实现细节（关键规则）

| 规则 | 采用方法 | 置信度 | 备注 |
|---|---|---|---|
| 五行力量 | 天干 1.0（日干 0.8）；地支藏干本气/中气/余气 0.6/0.3/0.1；月支 ×1.5、日支 ×1.2 | 0.85 | **工程近似**，不是传统定论 |
| 旺衰 | 得令（月令旺）/ 得地（四支有根）/ 得势（帮扶占比） | 0.5–0.78 | 临界区间自动降置信度 |
| 格局 | 月令本气/中气/余气透干取格；不透则以本气取格；月令临官→建禄、帝旺→月刃 | 0.4–0.72 | 透干+0.14，多候选−0.12 |
| 喜用忌 | 扶抑法为主 + 调候法为辅 | 0.4–0.70 | 中和时用神取食伤 |
| 刑冲合害 | 查表两两匹配 + 三合/三会 | 0.6–0.85 | 确定性，无流派争议 |

## 后果

**正面**

* 全部规则可单测（`tests/engines/test_bazi_engine.py` 含 30+ 用例）；
* 无版权风险；
* 权重是显式常量，可以版本化调整并回测比较；
* 输出 `rationale` 与 `confidence`，避免"假装精确"。

**负面**

* 格局/喜用神的流派覆盖不如 bazi-pro（盲派、新派未实现）；
* 五行力量权重缺少权威依据（已在 `assumptions` 中声明）；
* Phase 1 无法做双引擎交叉验证。

**Phase 2 必须做的事**

1. fork bazi-pro 到自有组织，**核实许可证**，锁定 commit SHA；
2. 实现 `BaziProAdapter`，与 `smx-bazi-native` 并行计算同一批 Golden Case；
3. 差异逐条写入 `docs/calculation-differences.md`；
4. 如果 bazi-pro 的格局/喜用神更可靠，用它替换自研结果，
   **并提升 `bazi_engine_version`**；
5. 保留自研内核作为 fallback（bazi-pro 不可用时降级）。

## 相关

- [`THIRD_PARTY.md`](../THIRD_PARTY.md) §1.3
- [`src/engines/bazi/rules.py`](../../src/engines/bazi/rules.py) 模块文档字符串
- [`tests/engines/test_bazi_engine.py`](../../tests/engines/test_bazi_engine.py)
