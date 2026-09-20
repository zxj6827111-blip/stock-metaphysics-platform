# Phase 3D · Walk-forward 方法学

> 版本：`split_version = phase3-oos-v1`、fold 校准版本前缀 `cal-wf-<年>`
> 实现：`src/research/oos/walk_forward.py`；测试：`tests/research/test_walk_forward.py`

Walk-forward 回答一个固定 holdout 回答不了的问题：

> **如果每年都用"当时能看到的历史"重新标定一次，方向阈值是否还能保持区分度，
> 结果是否逐年稳定？**

它同时是本阶段最容易出现泄漏的环节，因此本文件先把纪律讲清楚，再讲结果口径。

---

## 1. P0 规则：每个 fold 必须重新拟合（GOAL §6）

```
Fold(test=2015):  train = 2010-01-01 .. 2014-12-31
                  → 只用这 5 年重新 fit percentiles / mean / std / 方向阈值
                  → 再 transform 2015
```

违规形态（GOAL 明确禁止）：

```
global_calibrator.transform(all_test_years)      # 用全体 TRAIN(2010–2018) 的阈值评估 2015
                                                 # → 2016–2018 的分布信息泄漏进 2015
```

合法形态只有一条路径：`calibrator.fit(fold_train)` → `calibrator.transform(fold_test)`。

## 2. 四道结构性闸门

实现不依赖调用方自觉，而是让违规**无法表达**：

1. **拟合帧由函数内部按日期过滤**（`as_of <= fold.train_end`），调用方无法传入"已经过滤好"的帧；
2. **`ResearchCalibrationLayer` 自带 `fit_max_as_of` 断言**：显式边界之外的样本直接 `raise`；
3. **transform 帧守卫**：测试帧必须严格位于 `fold.train_end` 之后且落在测试区间内，
   否则 `WalkForwardLeakError`（即使 fold 被伪造也会被拦下）；
4. **版本守卫**：fold 不得使用冻结的 holdout 校准版本（`cal-v1`）—— 
   "把 cal-v1 当作 fold 校准"正是 GOAL §6 禁止的泄漏形态，直接 `raise`。

此外每个 fold 记录 `calibration_fit_hash`（对分组数、均值、标准差、P25/P75 取
SHA256 前 16 位）。若某个实现偷偷复用同一个校准器，hash 会全部相同
→ 测试 `test_fit_hash_differs_across_folds` 与摘要字段 `fold_calibration_refit` 会立刻暴露。

## 3. Fold 结构

| 项 | 取值 |
|---|---|
| 类型 | 扩窗（expanding window）：训练起点固定 2010-01-01，终点逐年扩张 |
| 最短训练窗 | 5 年（与 GOAL §7 示例一致：Train 2010–2014 → Test 2015） |
| 测试年 | 2015 … 2026（共 **12** 个 fold；2026 为部分区间，止于快照截止日 2026-08-14） |
| 每 fold 记录 | `fold_id` / `train_period` / `test_period` / 股票数 / 事件数 / `calibration_version` / `calibration_fit_hash` / 负对照 / `research_status` / 各持有期统计 |

第一 fold 的推迟（2015 而非 2013）是**预注册决定**：训练窗不足 5 年时，
P25/P75 阈值不稳定，且 2010–2012 的样本量不足以支撑分组统计。
`expanding_folds(min_train_years=...)` 支持显式调整并会在记录中体现。

## 4. 两套协议的关系（重要，容易被误读）

| | 固定 holdout | walk-forward |
|---|---|---|
| 校准 | `cal-v1`（**一次**用 2010–2018 全体 TRAIN 拟合） | 逐 fold 重拟合（`cal-wf-2015` … `cal-wf-2026`） |
| 训练数据 | 只有 holdout 的 TRAIN 分区 | 测试年之前的**全部**样本 |
| 用途 | 最终一次性 OOS 判定（gate） | 稳定性诊断 |

两点必须明确：

1. **扩窗训练前缀会跨过 holdout 的 Validation 区段**（例如 test=2020 时
   train=2010..2019）。这不是泄漏 —— 它仍然严格早于测试年 ——
   而是 walk-forward 的定义。每个 fold 的 `fit_partitions` 字段如实记录
   实际用了哪些 holdout 分区，`freeze_bound_exceeded` 标记是否越过 cal-v1 的 fit 上界。
2. **测试年落在 OOS 区间的 fold 不是"纯样本外"**：test=2024 的 fold 用到了 2023 年的
   数据做训练。因此 walk-forward 结果用于回答"阈值是否稳定、方向是否逐年一致"，
   **不得**用来替代固定 holdout 的 OOS 判定。

## 5. 每个 fold 的评估内容

本阶段对 4 个 calibrated 对象（`bazi` / `ziwei` / `huangli` / `ALL_THREE`）
× 3 个出生模型 = 12 条 walk-forward 序列执行，每条 12 fold：

* 各持有期（5/10/20/60D）的事件数、平均超额收益；
* 主持有期 20D 的平均超额收益、上涨率、方向符号；
* **随机事件位置负对照**（200 次置换）：对照均值与单侧经验 p；
* `research_status`：`OUTPERFORM_CONTROL`（真实 > 对照 且 p < 0.05）/
  `NO_SIGNAL` / `NOT_RUN`。

raw 口径不做 walk-forward：raw 方向不依赖校准（阈值是运行时固定的 58/42），
逐 fold 重拟合对其事件集合没有任何影响，其逐年统计已由固定 holdout 的分区统计覆盖。

## 6. 阅读结果时的注意事项

* **fold 之间不独立**：扩窗意味着相邻 fold 的训练集高度重叠，测试年也共享市场环境。
  因此 `12 个 fold 里 8 个方向为正` 这类计数只能作为**描述性**证据，不能当成 8 次独立试验。
* **单年样本有限**：季度采样下每个测试年约 4 个采样点，事件数的跨年波动很大；
  报告同时给出事件数，避免把"某年只有 30 个事件"的均值当成稳定结论。
* **不做多重检验校正**：与固定 holdout 同理，12 条序列 × 12 fold 的 p 值未校正。
* walk-forward **不参与状态门**：`OOS_CANDIDATE_SUPPORTED` 只由固定 holdout 的
  `phase3d-oos-gate-v1` 判定。

## 7. 复现

```bash
# walk-forward 随主管线一起运行（逐 fold 重拟合，不缓存阈值）
python scripts/phase3d_oos_pipeline.py --skip-collect
# 只看 P0 纪律
python -m pytest tests/research/test_walk_forward.py tests/research/test_oos_no_leak.py -q
```

产物：`data/phase3_universe/phase3d_walkforward_results.csv`
（每行 = 一条序列的一个 fold，含 `calibration_fit_hash` 与 `fit_partitions`）。
