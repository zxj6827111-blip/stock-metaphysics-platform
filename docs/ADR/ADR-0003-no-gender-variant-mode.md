# ADR-0003：股票无性别 → `variant_mode`，默认 `not_applicable`

- **状态**：已接受（Phase 1）
- **日期**：2026-09-18
- **影响**：八字引擎、出生档案、因子体系、UI

## 背景

传统八字的大运顺逆规则依赖性别：

```
阳年男 / 阴年女 → 顺排
阴年男 / 阳年女 → 逆排
```

（出处见语料条目 `MLYY-0004`：《命理约言》"大运之顺逆，视年干阴阳与男女而异。"）

**股票没有性别。**

如果系统为了实现"完整功能"而默认填入"男命"，会产生一个**伪精确**的结果：
它看起来算出了大运，但那个大运没有任何依据；更糟的是，用户会把
"基于男命假设的大运"当成真实结论。

架构文档（§18）明确要求：

> 禁止系统偷偷填写"男"，然后继续计算。这会造成基础模型伪精确。

## 决策

引入 `variant_mode` 枚举：

```python
class VariantMode(str, Enum):
    FORWARD = "forward"
    REVERSE = "reverse"
    BOTH = "both"
    NOT_APPLICABLE = "not_applicable"   # 默认
```

具体规则：

1. **默认值**：`not_applicable`；
2. 该模式下 **`da_yun = []`**，不输出任何大运；
3. 该模式下大运**不参与任何 Phase 1 因子**；
4. 必须写入 `assumptions`（键名 `bazi.variant_mode`），
   内容说明"股票无真实性别，禁止默认按男命或女命起运"；
5. 只有显式传入 `forward` / `reverse` / `both` 时才计算大运，
   并且 `da_yun_note` 必须包含"假设"字样；
6. `StockBirthProfile.variant_mode` 与 `BaziChart.variant_mode` 保持一致并落库。

UI 表现（八字详情页）：

```
Variant A（阳男）  Variant B（阴女）   Phase 2 将并行回测两种假设
注：股票无天然性别，以下运限推演基于假设规则，请结合多模型综合判断。
运限假设：not_applicable
```

## 机器校验

`tests/engines/test_bazi_engine.py::TestNoGenderContract`：

```python
def test_variant_mode_defaults_to_not_applicable(...)
def test_da_yun_not_emitted_by_default(...)      # assert chart.da_yun == []
def test_assumption_recorded(...)                # assert "bazi.variant_mode" in keys
def test_explicit_variant_mode_computes_dayun(...)  # 显式声明时才计算
```

`tests/test_birth_profile.py::TestNoGender` 覆盖档案侧。

## 后果

**正面**

* 系统不会输出无依据的大运；
* 用户明确知道"哪些结论基于假设"；
* 为 Phase 2 的"顺排 vs 逆排谁更稳定"对比实验预留了完整数据结构。

**负面**

* Phase 1 的八字输出比"完整命盘"少了大运/小限；
* 需要向用户解释为什么没有大运（UI 与文档都做了说明）。

## Phase 2 计划

1. 对同一批股票分别用 `forward` / `reverse` 计算大运，生成两套因子；
2. 分别做事件研究与负对照；
3. 如果某一侧显著更优（或两者都无效），如实记录；
4. **在得到结论之前不得让大运进入正式评分**。

## 相关

- [`AGENTS.md`](../AGENTS.md) §5
- [`docs/methodology.md`](../methodology.md) §4
- `src/core/schemas/common.py::VariantMode`
- [ADR-0014](ADR-0014-first-day-yinyang-variant-basis.md)：2026-09-23 追加的
  `variant_basis=first_day_yinyang`（首日阴阳 → 男/女命假设）。**它不取代本 ADR**：
  本 ADR 的 6 条规则全部保持有效，ADR-0014 只补上"显式方向由谁选、依据是什么、怎么登记"。
