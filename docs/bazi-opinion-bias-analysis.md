# Phase 3C · BAZI_POS 偏置诊断与 Factor / Opinion 分布审计

> 生成时间：2026-09-20T07:04:13
> Universe：`v2-phase3a`（500 只）
> 采样：18 个日历点，2010-01-01..2026-08-14，步长 12 个月
> Calibration：`research-calibration-v1`；fit 仅使用 TRAIN `2010-01-01..2018-12-31`

## 结论先行

- `BAZI_POS` 正向率是八字 Opinion 的方向分布，不是上涨概率、预期收益率或有效性证据。
- 原始 Opinion score/direction 和 Factor 原值未被修改；Calibration 只追加研究派生列。
- Validation/OOS 只使用全体 TRAIN 冻结的 P25/P75 阈值；正式 OOS Pipeline 留到 Phase 3D。
- 行业切片状态：`POINT_IN_TIME_INDUSTRY_UNAVAILABLE`；Phase 3E 尚未提供 PIT 行业。

## BAZI_POS 总体诊断

| birth model | n | raw +1 | raw 0 | raw -1 | raw +1 rate | cal +1 | cal 0 | cal -1 | cal +1 rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `listing_open_v1` | 7612 | 7336 | 276 | 0 | 96.4% | 1974 | 3828 | 1810 | 25.9% |
| `listing_close_v1` | 7612 | 7156 | 456 | 0 | 94.0% | 1943 | 3817 | 1852 | 25.5% |
| `ipo_approx_v1` | 7616 | 7359 | 257 | 0 | 96.6% | 2030 | 3720 | 1866 | 26.7% |

## 时间切片与完整审计

运行时方向阈值仍为 score >= 58 / <= 42；完整 year/market_phase/partition 统计在 `phase3c_opinion_distribution.csv`。
Factor 摘要行：**5814**；Opinion 摘要行：**153**。
单点失败：`{}`。

## Calibration 审计

Factor fit groups=342，Opinion fit groups=9；fit_max_as_of=2018-12-31。
常量 TRAIN 参考分布显式返回 unavailable/null，不用 0 冒充。

## 研究边界

本报告只回答分布偏置与 TRAIN-only 校准纪律，不回答术数是否有效；未读取未来收益标签，也没有用 OOS 调阈值。
