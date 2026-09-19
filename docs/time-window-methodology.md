# 时间窗口方法论（Time Window Methodology）

> 实现：`src/core/orchestration/timeline.py`、`src/core/schemas/timeline.py`
> 测试：`tests/timeline/test_time_windows.py`

---

## 1. 两条不可妥协的规则

### 1.1 禁止发明"流周"

传统术数有流年、流月、流日、流时，**没有"流周"**。

因此周度窗口不能凭空造一个运限层，而必须由该周内**交易日**的流日结果**聚合**得到：

```
周 = 从 as_of 之后第一个交易日开始，每 5 个交易日为一周
```

聚合口径必须版本化（`AGGREGATION_VERSION = "agg-v1"`），
并同时给出六个指标：

| 指标 | 含义 |
|---|---|
| `mean` | 周内交易日综合方向的均值 |
| `median` | 中位数（对极端日不敏感） |
| `min` / `max` | 极值（分布的两端） |
| `positive_day_ratio` | 偏强交易日占比 |
| `weighted_mean` | 按"当日可用引擎数"加权的均值 |

**为什么不能只给平均值**：「5 天里 3 天偏强 2 天偏弱」与「5 天一致偏强」
的平均值可能相同，但它们是完全不同的状态。

### 1.2 一切基于实际交易日

所有窗口（月 / 周 / 5D / 10D / 20D / 60D）必须落在
`TradingCalendarProvider` 给出的**真实交易日**上：

* 日历来源是**指数实测交易日**（`data/import/calendar/{SSE,SZSE}.csv`），
  由 `sh000001` / `sz399001` 的真实 K 线首日集合推导；
* 日历覆盖之外返回 `None`（不知道），**不允许用周末规则假装肯定**
  （Phase 1.1 的硬要求）；
* 覆盖不足时如实降级并产出 `TIMELINE_CALENDAR_PARTIAL` / `TIMELINE_NO_TRADING_DAY` 警告。

---

## 2. 月度窗口

* 未来 N 个月（默认 12），逐月**独立**产出：
  `bazi` / `ziwei` / `huangli` 三个 opinion + `consensus` + `conflict` +
  `research_status` + `data_quality`。
* **不是一个综合数字** —— 任务书 §25 明确要求逐月保留三模型判断。
* 打分时点：该月**最后一个交易日**（月内信息最完整）。
* `trading_days` 与 `sample_dates` 都来自交易日历，可审计。

---

## 3. 周度窗口

`WeekWindow` 字段：

| 字段 | 说明 |
|---|---|
| `week_index` | 未来第几周（1 = 下一周） |
| `week_start` / `week_end` | 该周首末**交易日** |
| `trading_days` | 交易日数（通常 5，遇假期更少） |
| `daily_results[]` | 每个交易日的 `DayResult`（三模型方向 + 综合方向） |
| `aggregation_method` | 口径说明（含"不使用自然周""传统没有流周"） |
| `aggregation_version` | 口径版本 |
| 六个聚合指标 | 见 §1.1 |

`DayResult.combined_direction` 由**可用引擎**的方向均值映射而来：

```
used = [d for d, score in ((bazi), (ziwei), (huangli)) if score is not None]
combined = direction_from_score(50 + mean(used) * 50)
```

不可用引擎**不参与**，也不当成 0 —— 把"不知道"当成 0 会系统性地把均值拉向中性。

---

## 4. 与历史验证的关系

时间窗口给出的是**传统规则强度**在未来时点上的**确定性计算结果**，
没有任何历史统计支持其预测能力。

因此每个响应都携带：

* `research_status`（默认 `NOT_RUN`）；
* `research_status_reasons`：固定包含"时间窗口给出的是规则强度在未来的分布，
  没有任何历史统计支持其预测能力。历史有效性必须由研究流水线回答。"

UI 必须原样展示这段文字（`timeline` 页面已实现）。

---

## 5. 计算成本

* 一个月窗口 = 1 次三模型打分（在该月最后交易日）；
* 一周窗口 = 该周交易日数（≤ 5）次三模型打分 + 1 次共识；
* 12 月 + 12 周 ≈ 12 + 60 + 1 ≈ 73 次打分。

每次打分含紫微排盘（子进程 transport 约 150–300 ms），因此一次完整窗口构建
约 20–40 秒。页面在加载时显示明确的 loading 文案，并且**不做后台静默刷新** ——
研究结果必须是"这一份"，不是"大概这一份"。

---

## 6. 已知限制

1. **未实现时序折线图**：参考图 10 有一条"未来周期时间轴"折线。
   本项目的分数是**规则强度聚合**、并非时间序列指标；
   硬画一条连续曲线会暗示"分数随时间连续演化"这一并不存在的性质。
2. **未实现日历热力图**：需要逐日吉凶分级口径，本项目不在 UI 造这套分级。
3. **未实现"最佳布局窗口 / 风险提示期"**：那属于投资建议范畴。
4. 紫微的 `both` variant 在时间窗口中只使用主 variant（与因子/观点层一致）。
5. 窗口内的共识使用该窗口的**代表性时点**，不是窗口内每日共识的聚合。
