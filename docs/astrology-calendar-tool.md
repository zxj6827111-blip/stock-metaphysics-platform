# 术数日历工具（`scripts/astrology_calendar.py`）

> 只读的描述性工具：**不是**选股信号、不是因子、未经回测。
> 它的作用是回答"某个日期/时辰与某只票的原局形成什么关系"，而不是"该不该买"。
>
> 背景结论文档见 [`PHASE3_RESEARCH_REPORT.md`](PHASE3_RESEARCH_REPORT.md)：项目已验证过的
> 42 个假设在样本外**无一通过闸门**，且当前检验能力分辨不出 3.5% 以下的效应。
> 因此本工具的任何输出都**不得**被解释为涨跌方向。

## 四个视图

```bash
# ① 单票当日各时辰（只看交易时段相关的三个时辰，并标注与盘中重叠分钟）
python scripts/astrology_calendar.py intraday 600519
python scripts/astrology_calendar.py intraday 600519 --date 2026-09-21 --all-hours

# ② 单票未来逐日（自动跳过非交易日；可带大运）
python scripts/astrology_calendar.py forecast 600519 --days 30
python scripts/astrology_calendar.py forecast 600519 --days 30 --dayun

# ③ 给定日期/时辰反查全市场（先建原局缓存）
python scripts/astrology_calendar.py cache --limit 500
python scripts/astrology_calendar.py screen --date 2026-09-21 --hour 10 --top 20

# ④ 单票大运（按「首日阴阳 → 性别假设」起运）
python scripts/astrology_calendar.py dayun 600519
```

`screen` 的候选集来自原局缓存（`data/phase4_cache/astrology_natal_cache.pkl`）。
**缓存与出生档案版本绑定**：档案一改（例如上市日修正），旧缓存自动作废，
不会继续用上一套出生时刻算出来的盘。全市场 6,104 只约 5 分钟可建完。

## 「契合度」是什么，不是什么

**是**：原局喜用忌与外部干支刑冲合害的一次确定性归纳，**只用于浏览排序**。
**不是**：不是预测，也不是因子 —— 没有 `factor_id`、不进 `FactorSet`、不参与评分或共识、
**未经回测**（项目铁律：未经回测不得解释成利好）。

口径写死在代码里（`YONG_WEIGHT` / `REL_WEIGHT`），便于核对：

| 成分 | 权重 |
|---|---|
| 天干五行 | 用神 +3 / 喜神 +2 / 闲神 0 / 忌神 −3 |
| 地支五行 | 同上（各计一次） |
| 六合 / 三合 / 天干五合 | +2 |
| 相冲（地支） | −3 |
| 天干相冲 | −2 |
| 相刑 / 相害 | −2 |

> 每个关系类型都必须有非零权重：缺条目会被 `dict.get(..., 0)` **静默漏计**。
> `tests/test_astrology_calendar.py` 有断言守着这一点（该断言曾抓到"天干相冲"缺权重）。

## 实现上刻意「零发明规则」

| 环节 | 复用来源 |
|---|---|
| 年/月/日柱及其与原局的对照 | `BaziEngine.build_chart(birth, as_of=T)` 的现成输出 |
| 时柱 | 引擎自身的 `_build_temporal` / `_annotate_temporal` |
| 刑冲合害 | `rules.relations_with_external`（与流年/流月/流日同源） |
| 喜忌标注 | 引擎的用神分析结果 |

调用 `_build_temporal` 这类**私有方法是有意为之**：要的是引擎的规范口径。
一旦引擎重构会立刻 `AttributeError` 报错（响亮的失败），而不是静默算错。

## 交易日处理

接项目已有的 `src/core/stock/trading_calendar.py`。两种降级**显式标注**、绝不静默顶替：

* 实测日历覆盖范围内 → `observed_index_days`
* 超出覆盖（例如未来日期）→ 周末规则近似，输出里标 `weekend_rule_fallback(降级)`，
  并提示"节假日无法识别"

`forecast` 默认跳过非交易日；`--all-days` 可显示全部并标注实测非交易日。

## 运限（大运）与「首日阴阳」假设

用户提供的权威表带「首日涨跌标识」：**阳 = 首日收涨 / 阴 = 首日收跌**。
本项目把它实现为**显式假设**：

```
阳 → 男命（variant_mode=FORWARD）    阴 → 女命（variant_mode=REVERSE）
顺逆再由「性别 + 年干阴阳」决定：阳男阴女顺行、阴男阳女逆行
```

**这是假设，不是事实**（`AGENTS.md` §5：股票没有真实性别，禁止默认按男命起运）：

* `stock_master` 增加 `first_day_pct_chg` / `first_day_yinyang`（迁移 `e6b2c8f4a91d`）
* `variant_mode` 默认仍是 `not_applicable`，**默认不输出大运**；只有 `dayun` /
  `forecast --dayun` 这类显式请求才算
* 引擎把该假设写入 `assumptions`；每次输出都带「运限推演基于假设规则」声明
* **不进入任何正式因子**（未回测）。将来要进入，唯一合法路径是把
  `FORWARD` / `REVERSE` 当作两种变体**预先注册并回测**

**口径位置（2026-09-23 起）**：映射与免责声明已抽到单一真源
[`src/core/stock/variant_basis.py`](../src/core/stock/variant_basis.py)（`FIRST_DAY_YINYANG_TO_VARIANT`
/ `FIRST_DAY_YINYANG_DISCLAIMER` / `VARIANT_BASIS_VERSION`），本脚本 import 复用。
同一天 API 与界面也接通了同一口径：`variant_basis=first_day_yinyang`
（见 [ADR-0014](ADR/ADR-0014-first-day-yinyang-variant-basis.md)），八字详情页会直接显示
当前大运与 10 步序列。**CLI 与界面必须共用这份映射** —— 之前各有一套，正是
「界面上看不到大运、且阴股方向与表格规则相反」的成因。

验证：抽样 135 只，引擎的大运顺逆判定与「阳男阴女顺行 / 阴男阳女逆行」规则
**一致率 100.00%**。

## 已知限制

1. **契合度不是信号**：未回测，不得据此判断涨跌（反复强调是因为这是最容易误用的部分）。
2. **时辰层没有对应的注册因子**：黄历因子的注册口径是「日干支五行与喜用神关系、
   与原局日支的刑冲合合」，只到日；时辰层是本工具的**描述性扩展**。
3. **反查全市场不等于选股**：按日期筛出的清单每天都不一样，一年 250 个交易日
   就是 250 个互不相同的"策略"，事后总能挑出表现好的 —— 这是多重检验陷阱，
   也是 Phase 3F 引入 BH-FDR 校正的原因。
4. **出生档三选一**：同一只票有 3 套盘（上市日开盘 / 上市日收盘 / 上市前一周估），
   本工具默认 `listing_open_v1`，可用 `--model` 切换；三者的差异是研究口径问题，
   不是"哪个更准"。
