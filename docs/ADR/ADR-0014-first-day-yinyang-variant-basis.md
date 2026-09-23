# ADR-0014：首日阴阳 → 运限变体（把「股票阴阳」实现为显式假设）

- **状态**：已接受（代码 + 测试 + 实测证据均已落地）
- **日期**：2026-09-23
- **影响**：出生档案、八字引擎输出、`/api/v1/stocks/{code}/analysis/{bazi,multi}` 请求体、八字详情页 UI、CLI（`scripts/astrology_calendar.py`）
- **关联**：[ADR-0003](ADR-0003-no-gender-variant-mode.md)（股票无性别，**本 ADR 不取代它**）、[ADR-0010](ADR-0010-ziwei-no-gender-variant.md)（紫微方向）、[ADR-0013](ADR-0013-research-validity-boundary.md)（结论边界）

## 背景

1. 大运顺逆依赖性别（ADR-0003 背景）；股票没有性别。
2. 用户提供的权威表对每只标的都有**「首日涨跌标识」**：阳 = 首日收涨 / 阴 = 首日收跌。
   与性别不同，这是一个**可核对的市场事实**，且落库为
   `stock_master.first_day_pct_chg` / `first_day_yinyang`（迁移 `e6b2c8f4a91d`，实测 6104 只中
   5388 只有值：阳 3630 / 阴 1758 / 空 716）。
3. CLI（`scripts/astrology_calendar.py dayun`）早已按「阳→男命 / 阴→女命」起运，但**界面没有接入**，
   于是出现了两个后果：

   * **看不到大运**：八字页唯一的"大运"格子渲染的是 `da_yun_note` 的前 22 个字符
     （实测 `运限按 VariantMode.FORWAR`），`chart.da_yun` 这个数组从来没有被任何组件读过；
   * **方向与表格规则相反**：界面把 `variant_mode` 硬编码成 `forward`，对 1758 只"阴"标的
     给出了与「阴→女命→顺逆」相反的顺逆 —— 这比不显示更糟（伪精确）。

## 备选方案

| 方案 | 结果 | 结论 |
|---|---|---|
| A 保持现状，只补前端大运渲染 | 大运能显示，但 1758 只阴股方向错误 | 否决 |
| B 前端读 `first_day_yinyang` 自己映射 forward/reverse | 假设来源不进 `assumptions`、不可版本化、不可独立回测（§16.5） | 否决 |
| C 新增 `variant_basis`，由**后端**推导并登记 | 口径单一真源、进 assumptions、可版本化、缺数据可如实降级 | **采纳** |
| D 默认按男命起运 | 直接违反 §5 / ADR-0003 | 否决 |

B 另有一条硬理由：`AGENTS.md` §9.12 禁止前端重新计算术数口径，阴阳→顺逆属于引擎口径。

## 决策

1. 新增枚举 `VariantBasis`：`explicit`（**默认**，语义与之前完全一致）/ `first_day_yinyang`。
2. `first_day_yinyang` 的映射：**阳 → 男命假设 → `forward`；阴 → 女命假设 → `reverse`**。
   "阳男阴女顺行 / 阴男阳女逆行"这条细则仍由引擎按「性别 + 年干阴阳」自己算，本 ADR 不改它。
3. 推导**只读** `stock_master.first_day_yinyang`（`first_day_pct_chg` 仅用于文案）。
   公司名、行业、年干阴阳等一律不得参与 —— 不许"猜"性别。
4. 缺首日数据（实测 716 只）→ `variant_mode` 保持 `not_applicable`，**不输出大运**，
   并把缺口写进 `variant_note` 与 `assumptions`（§2.4：不可用就是不可用，不许用默认值顶替）。
5. 同时满足 §5 的四条要求：

   | §5 要求 | 落地 |
   |---|---|
   | 显式传入，不得默认 | 请求字段 `variant_basis`，默认 `explicit`；不推导=不输出大运 |
   | 写入 `assumptions` | `birth.variant_basis` + `birth.variant_mode`（含 `VARIANT_BASIS_VERSION`） |
   | 输出标注"基于假设规则" | `FIRST_DAY_YINYANG_DISCLAIMER`，出生档案与盘面 note 都带，界面原样展示 |
   | 不得纳入正式因子 | 测试硬断言：variant 变化时因子 `rule_score` / `normalized_value` / `direction` 完全不变 |

6. 规则版本 `VARIANT_BASIS_VERSION = "v1-first_day_yinyang"`；改映射或改表述必须提升（§11）。
   它**不**改动 `birth_profile_version` —— 出生时刻的推导方式没变，变的是运限假设的来源，
   两者各有版本，混在一起会让"为什么同一只票上个月算 X 今天算 Y"更难解释。
7. **单一真源**：`src/core/stock/variant_basis.py`。CLI 与 API 共用同一份映射
   （2026-09 的"界面显示不出大运"正是两套口径跑偏造成的）。
8. **冲突即报错**：`variant_basis=first_day_yinyang` 与显式 `variant_mode≠not_applicable`
   同时出现 → `422 BIRTH_PROFILE_ERROR`。推导方向唯一，不做"谁是主"的静默裁决（§15 / §26）。
9. **紫微端点不接受该 basis**（显式 422）：紫微方向的来源口径属 ADR-0010 范围，本轮不扩。
10. 综合研判（`/analysis/multi`）里推导出的方向**同时作用于八字与紫微**：
    它是"这只标的的运限往哪边走"这一个假设，不应该在两个引擎里给出两个方向。
    副作用（已知并接受）：缺首日数据的标的在 multi 下紫微为 `unavailable`，
    紫微页仍可用显式 forward/reverse 正常查看。
11. UI：八字页默认 `first_day_yinyang`；紫微页保持显式 forward/reverse 切换；
    大运由新增组件 `DaYunStrip` 渲染（当前大运高亮 + 10 步序列 + 假设来源 + 免责声明），
    `is_current` 由**后端**按 `as_of` 判定，前端不推演；lunar-python 的「起运前」占位行原样显示。

## 兼容性

* **API**：只新增可选请求字段 `variant_basis`（默认 `explicit`）→ 既有请求体行为一字不变，
  有测试锁定（`test_explicit_request_unchanged`）。无路径/字段改名，无 enum 语义变化。
* **数据库**：**无迁移**。推导结果落在既有 `variant_note` / `assumptions_json`。
* **唯一行为变化**：UI 默认请求从 `variant_mode=forward` 变为 `variant_basis=first_day_yinyang`。
  这是本 ADR 的目的；对"阳"标的（如 600519）结果不变，对"阴"标的顺逆方向改变。
* **视觉基线**：八字页新增一块大运区域 → `03-bazi` 的视觉截图必然变化，
  按 §21「视觉回归单独管理」处理，不伪造基线。

## 机器校验

* `tests/test_birth_profile.py::TestFirstDayYinyangBasis` —— 映射、缺数据不默认、冲突报错、explicit 路径不变；
* `tests/engines/test_bazi_engine.py::TestNoGenderContract` —— 假设记录、note 无 `VariantMode.` 枚举名、
  `is_current` 唯一、**因子不随 variant 变化**；
* `tests/integration/test_api_variant_basis.py` —— HTTP 契约（含紫微端点拒绝）；
* `tests/test_astrology_calendar.py` —— CLI 仍用同一口径（顺逆自检一致率）。

## 后果

**正面**

* 大运终于**可见且可解释**：假设来源（首日 +3.01% → 阳 → 男命）、当前大运、10 步序列、
  "不进入任何因子"的说明在同屏；
* 阴/阳标的的顺逆方向与用户表格规则一致，不再靠 `forward` 一个值兜住全市场；
* 假设被版本化（`v1-first_day_yinyang`）并可独立回测，为"两种 variant 谁更稳定"留了合法路径。

**负面**

* 界面从此会给每只标的显示一个"性别"假设 —— 必须靠免责声明与 UI 文案持续提醒它是假设；
* 缺首日数据的 716 只标的在 multi 链路下紫微变为不可用（可显式指定方向绕过）；
* 多了一个请求字段与一个规则版本需要维护。

**未做（明确的门槛）**

* 大运**仍未**进入任何因子：要进入必须先按 §5.4 把 `forward` / `reverse` 两种变体
  预先注册并回测（ADR-0003 的 Phase 2 计划仍然有效）；
* 关系级 / 事件级的"大运有效性"研究尚未开始，因此本 ADR 不产出任何市场结论。

## 相关

- [`AGENTS.md`](../AGENTS.md) §5（股票无性别）、§16.5（假设必须显式记录、版本化）
- [`docs/methodology.md`](../methodology.md) §4
- [`docs/astrology-calendar-tool.md`](../astrology-calendar-tool.md)（CLI 口径）
- `src/core/stock/variant_basis.py`、`src/core/schemas/common.py::VariantBasis`
