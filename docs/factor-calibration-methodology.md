# Phase 3C · Factor / Opinion Calibration 方法学

- Calibration version: `research-calibration-v1`；原始 `opinion.score` 不变。
- Universe: `v2-phase3a`，本次 `500` 只；快照截止 `2026-08-14`。
- TRAIN: `2010-01-01..2018-12-31`；Validation: `2019-01-01..2022-12-31`；OOS: `2023-01-01..2026-08-14`。
- 分区和 market phase 只由日历确定，不使用未来收益/benchmark。
- fit 只接受全体 TRAIN 原始 Factor/Opinion，冻结均值、标准差、经验分布和 P25/P75；Validation/OOS 只能 transform。
- `research_percentile`/`historical_percentile` 使用 TRAIN 参考分布；`cross_sectional_percentile` 只描述当前横截面；`z_score` 在常量参考分布时为 null；`rank_score` 是 0-100 研究刻度，不是收益概率。
- 行业状态：`POINT_IN_TIME_INDUSTRY_UNAVAILABLE`，Phase 3E 前不使用当前行业资料替代 PIT 行业。
- 常量/近常量只报告，不删除；正式 walk-forward 和 OOS gate 留到 Phase 3D。
