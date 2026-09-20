# Phase 3C · Factor / Opinion Calibration 方法学

- Calibration version: `research-calibration-v1`（Phase 3D 研究口径下记作 **`cal-v1`**，二者等价）；
  原始 `opinion.score` 不变。
- Universe: `v2-phase3a`，本次 `500` 只；快照截止 `2026-08-14`。
- TRAIN: `2010-01-01..2018-12-31`；Validation: `2019-01-01..2022-12-31`；OOS: `2023-01-01..2026-08-14`。
- 分区和 market phase 只由日历确定，不使用未来收益/benchmark。
- fit 只接受全体 TRAIN 原始 Factor/Opinion，冻结均值、标准差、经验分布和 P25/P75；Validation/OOS 只能 transform。
- `research_percentile`/`historical_percentile` 使用 TRAIN 参考分布；`cross_sectional_percentile` 只描述当前横截面；`z_score` 在常量参考分布时为 null；`rank_score` 是 0-100 研究刻度，不是收益概率。
- 行业状态：`POINT_IN_TIME_INDUSTRY_UNAVAILABLE`，Phase 3E 前不使用当前行业资料替代 PIT 行业。
- 常量/近常量只报告，不删除；正式 walk-forward 和 OOS gate 留到 Phase 3D。

## Calibration V1 冻结（Phase 3D 起生效）

Phase 3D 在**首次读取 OOS 收益标签之前**把上述校准冻结为 `cal-v1`：

| 项 | 值 |
|---|---|
| calibration_version | `cal-v1`（= `research-calibration-v1`） |
| fit_period | `2010-01-01 .. 2018-12-31` |
| fit_scope | `TRAIN_ONLY` |
| oos_labels_seen（冻结时） | `false` |
| 冻结内容 | P25/P75 方向阈值、z-score 均值/标准差、经验分位参考分布 |

* 冻结记录：`src/research/oos/calibration_freeze.py` 的 `FREEZE_V1`
  （+ 产物 `data/phase3_universe/phase3d_calibration_freeze.json`）。
* 三道断言：`assert_fit_within_train`（fit 不得越界）/ `assert_partition`（只能 TRAIN）/
  `assert_holdout_fit`（固定 holdout 只能 fit TRAIN、目标只能是 Validation/OOS）。
* **任何修改都必须新建 `cal-v2` 并重新定义 OOS 协议**，不得静默覆盖 `cal-v1`：
  否则无法解释"同一份数据为什么这次通过了样本外门"。
* Walk-forward 的逐 fold 校准使用独立版本号 `cal-wf-<年>`，并且**结构上禁止**复用
  `cal-v1`（见 [`walk-forward-methodology.md`](walk-forward-methodology.md) §2 第 4 条闸门）。
* Phase 3D 结果见 [`phase3d-oos-results.md`](phase3d-oos-results.md)。
