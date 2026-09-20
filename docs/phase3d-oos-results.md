# Phase 3D · 样本外（OOS）与 Walk-forward 研究结果

> 生成时间：2026-09-20T12:10:40 · commit `66939bbca70855226ceb2da52d6bbd6671d91113`
> `split_version=phase3-oos-v1` · `calibration_version=cal-v1` · `label_version=phase3d-hfq-adjfactor-v1` · `gate_version=phase3d-oos-gate-v1`
> 数据快照 `phase3a_astockdata_cutoff_20260814`（universe `v2-phase3a`）

**先读这一句**：本阶段没有任何结果解锁 `SUPPORTED_OUT_OF_SAMPLE`。最高状态是 `OOS_CANDIDATE_SUPPORTED`（候选），且正式解锁必须等 Phase 3F 的 BH-FDR 多重检验校正。以下是全部结果（含空结果与失败假设）。

## 0. 结论摘要

| 问题 | 答案 |
|---|---|
| 是否产生 OOS 候选（`OOS_CANDIDATE_SUPPORTED`） | **否**（0/54） |
| 是否产出 `SUPPORTED_OUT_OF_SAMPLE` | **否** —— 结构上不可能（需 3F 的 BH-FDR） |
| 状态分布 | `EXPLORATORY_NOT_GATED`=12, `INCONCLUSIVE`=32, `INSUFFICIENT_SAMPLE`=3, `INVALID_CONTROL`=2, `NO_SIGNAL`=1, `WEAK_EVIDENCE`=4 |
| 正向（优于对照）的实验数 | gate 内 6 个名义 p < 0.05（探索性另有若干，未套 gate）；最低 p = 0.0050 |
| 若现在就做 BH-FDR 会怎样 | m=42 个正式实验，最小 BH 门槛 = 0.00119 → **通过 0 个**（这正是把正式解锁留给 3F 的实证理由） |
| 唯一显著为负的发现 | 黄历校准事件集合在 OOS 显著弱于同数量随机集合（见 §5 与 §6） |
| 本阶段是否成功 | **是**：管线建立、纪律可执行、结论为 NO_SIGNAL/INCONCLUSIVE 且如实输出 |

## 1. 基线与规模

| 项目 | 值 |
|---|---|
| commit SHA | `66939bbca70855226ceb2da52d6bbd6671d91113` |
| TRAIN | 2010-01-01 .. 2018-12-31 |
| VALIDATION | 2019-01-01 .. 2022-12-31 |
| OOS | 2023-01-01 .. 2026-08-14 |
| 切分指纹 | `phase3-oos-v1` / `6a059b3dbe54f22d` |
| 主面板采样 | 每 3 个月，68 个 as_of |
| 主面板观测行 | 175,734 |
| 月度 OOS 子面板 | 45 个 as_of（90,792 行） |
| 出生平移面板 | ±7 天 × 16 个 as_of（仅 OOS） |
| 宇宙 | v2-phase3a · 500 只（含退市股） |
| 排盘失败 | `{}` |
| 紫微可用性 | 可用 |
| 标签口径 | `phase3d-hfq-adjfactor-v1`；除权因子文件 5865 个，覆盖 500/500 只 |
| 标签行数 | 31,305 |
| 降级行情 | 0 只 |
| 假设注册表 | `phase3d-hypotheses-v1`（冻结于 2026-09-20，预注册时 `oos_labels_seen=False`） |
| 假设数 / 实验数 | 18 个假设 → 54 个固定 holdout 实验 |
| Walk-forward | 12 个 fold/序列 × 12 条序列（144 行记录） |
| 实验登记行 | 54 |

## 2. 校准冻结（cal-v1）

| 项目 | 值 |
|---|---|
| calibration_version | `cal-v1`（= `research-calibration-v1`） |
| fit_scope | `TRAIN_ONLY` |
| fit 实际最后一个 as_of | 2018-10-01（网格点；边界 2018-12-31，滞后 91 天） |
| fit 行数 / 分组数 | 96,156 / 9 |
| fit hash | `7e9897570d3b5a28` |
| oos_labels_seen（冻结时） | False |

## 3. 全部对象 × 出生模型的 OOS 结果（主持有期 20D）

`OOS 事件`/`资格数` 给出正向率；`对照差` = OOS 平均超额收益 − 随机事件位置对照均值；`p` = 置换法单侧经验 p；`Jaccard` = 真实事件集合与代表性随机集合的重合度（>0.9 即对照失效）。

| 对象 | 出生模型 | OOS 事件/资格数 | 正向率 | OOS 平均超额 | 对照差 | p | Jaccard | 状态 |
|---|---|---|---|---|---|---|---|---|
| 八字 raw | `listing_open_v1` | 3132/3529 | 95.38% | -2.14% | 0.14% | 0.0398 | 0.859 | `INVALID_CONTROL` |
| 八字 raw | `listing_close_v1` | 3052/3529 | 93.09% | -2.11% | 0.17% | 0.0249 | 0.820 | `INCONCLUSIVE` |
| 八字 raw | `ipo_approx_v1` | 3131/3529 | 95.38% | -2.07% | 0.22% | 0.0050 | 0.847 | `INVALID_CONTROL` |
| 八字 calibrated | `listing_open_v1` | 831/3529 | 25.39% | -1.57% | 0.73% | 0.0896 | 0.127 | `INCONCLUSIVE` |
| 八字 calibrated | `listing_close_v1` | 874/3529 | 26.35% | -1.74% | 0.56% | 0.1542 | 0.135 | `INCONCLUSIVE` |
| 八字 calibrated | `ipo_approx_v1` | 813/3529 | 25.33% | -1.23% | 1.00% | 0.0498 | 0.125 | `WEAK_EVIDENCE` |
| 紫微 raw | `listing_open_v1` | 755/3529 | 23.55% | -1.92% | 0.40% | 0.2488 | 0.121 | `INCONCLUSIVE` |
| 紫微 raw | `listing_close_v1` | 974/3529 | 30.24% | -2.24% | 0.06% | 0.4677 | 0.156 | `INCONCLUSIVE` |
| 紫微 raw | `ipo_approx_v1` | 889/3529 | 27.63% | -1.39% | 0.86% | 0.0746 | 0.151 | `WEAK_EVIDENCE` |
| 紫微 calibrated | `listing_open_v1` | 678/3529 | 21.14% | -2.05% | 0.24% | 0.3483 | 0.108 | `INCONCLUSIVE` |
| 紫微 calibrated | `listing_close_v1` | 720/3529 | 22.41% | -2.58% | -0.32% | 0.6915 | 0.127 | `INCONCLUSIVE` |
| 紫微 calibrated | `ipo_approx_v1` | 743/3529 | 23.12% | -1.85% | 0.46% | 0.1741 | 0.106 | `WEAK_EVIDENCE` |
| 黄历 raw | `listing_open_v1` | 1459/3529 | 42.50% | -3.94% | -1.70% | 1.0000 | 0.243 | `INCONCLUSIVE` |
| 黄历 raw | `listing_close_v1` | 1469/3529 | 42.76% | -4.39% | -2.09% | 1.0000 | 0.280 | `INCONCLUSIVE` |
| 黄历 raw | `ipo_approx_v1` | 1459/3529 | 42.56% | -4.01% | -1.68% | 1.0000 | 0.261 | `INCONCLUSIVE` |
| 黄历 calibrated | `listing_open_v1` | 837/3529 | 24.20% | -4.79% | -2.60% | 1.0000 | 0.130 | `INCONCLUSIVE` |
| 黄历 calibrated | `listing_close_v1` | 685/3529 | 19.86% | -4.62% | -2.25% | 1.0000 | 0.105 | `INCONCLUSIVE` |
| 黄历 calibrated | `ipo_approx_v1` | 834/3529 | 24.26% | -5.04% | -2.82% | 1.0000 | 0.130 | `INCONCLUSIVE` |
| 八字+紫微 cal | `listing_open_v1` | 175/3529 | 5.38% | -3.43% | -1.21% | 0.8308 | 0.034 | `NO_SIGNAL` |
| 八字+紫微 cal | `listing_close_v1` | 166/3529 | 5.16% | -2.15% | 0.12% | 0.4627 | 0.030 | `INCONCLUSIVE` |
| 八字+紫微 cal | `ipo_approx_v1` | 169/3529 | 5.47% | 0.96% | 3.44% | 0.0050 | 0.017 | `INCONCLUSIVE` |
| 八字+黄历 cal | `listing_open_v1` | 279/3529 | 8.08% | -4.56% | -2.24% | 0.9900 | 0.046 | `INCONCLUSIVE` |
| 八字+黄历 cal | `listing_close_v1` | 251/3529 | 7.28% | -4.21% | -2.01% | 0.9751 | 0.024 | `INCONCLUSIVE` |
| 八字+黄历 cal | `ipo_approx_v1` | 277/3529 | 8.05% | -3.42% | -1.00% | 0.8209 | 0.045 | `INCONCLUSIVE` |
| 紫微+黄历 cal | `listing_open_v1` | 172/3529 | 5.07% | -4.28% | -2.04% | 0.9254 | 0.017 | `INCONCLUSIVE` |
| 紫微+黄历 cal | `listing_close_v1` | 143/3529 | 4.17% | -5.12% | -2.75% | 0.9652 | 0.018 | `INCONCLUSIVE` |
| 紫微+黄历 cal | `ipo_approx_v1` | 200/3529 | 5.84% | -4.91% | -2.74% | 0.9701 | 0.036 | `INCONCLUSIVE` |
| 三模型 cal | `listing_open_v1` | 64/3529 | 1.87% | -7.10% | -4.88% | 0.9652 | 0.024 | `INSUFFICIENT_SAMPLE` |
| 三模型 cal | `listing_close_v1` | 40/3529 | 1.16% | -5.13% | -2.78% | 0.8607 | 0.013 | `INSUFFICIENT_SAMPLE` |
| 三模型 cal | `ipo_approx_v1` | 69/3529 | 2.01% | -0.90% | 1.34% | 0.2438 | 0.022 | `INSUFFICIENT_SAMPLE` |
| 三模型 raw | `listing_open_v1` | 320/3529 | 9.44% | -3.17% | -0.79% | 0.7811 | 0.072 | `INCONCLUSIVE` |
| 三模型 raw | `listing_close_v1` | 427/3529 | 12.44% | -3.87% | -1.67% | 0.9851 | 0.074 | `INCONCLUSIVE` |
| 三模型 raw | `ipo_approx_v1` | 388/3529 | 11.42% | -2.42% | -0.28% | 0.6169 | 0.062 | `INCONCLUSIVE` |

## 4. 全部持有期结果（禁止只报告最好的一档）

每个对象 × 出生模型 × 四个持有期的平均超额收益与上涨率（OOS 分区）。

| 对象 | 出生模型 | 5D | 10D | 20D | 60D |
|---|---|---|---|---|---|
| 八字 raw | `listing_open_v1` | -0.85% (n=3185) | -1.92% (n=3167) | -2.14% (n=3132) | -1.49% (n=2869) |
| 八字 raw | `listing_close_v1` | -0.88% (n=3106) | -1.99% (n=3088) | -2.11% (n=3052) | -1.30% (n=2782) |
| 八字 raw | `ipo_approx_v1` | -0.83% (n=3186) | -1.88% (n=3168) | -2.07% (n=3131) | -1.15% (n=2865) |
| 八字 calibrated | `listing_open_v1` | -0.87% (n=842) | -1.77% (n=837) | -1.57% (n=831) | -3.14% (n=762) |
| 八字 calibrated | `listing_close_v1` | -0.87% (n=888) | -1.86% (n=884) | -1.74% (n=874) | -1.95% (n=793) |
| 八字 calibrated | `ipo_approx_v1` | -0.72% (n=827) | -1.46% (n=823) | -1.23% (n=813) | -0.04% (n=753) |
| 紫微 raw | `listing_open_v1` | -0.75% (n=773) | -1.78% (n=765) | -1.92% (n=755) | -1.95% (n=686) |
| 紫微 raw | `listing_close_v1` | -1.04% (n=996) | -2.04% (n=989) | -2.24% (n=974) | -2.89% (n=881) |
| 紫微 raw | `ipo_approx_v1` | -1.10% (n=903) | -1.63% (n=899) | -1.39% (n=889) | -1.03% (n=802) |
| 紫微 calibrated | `listing_open_v1` | -0.83% (n=694) | -1.93% (n=687) | -2.05% (n=678) | -2.07% (n=616) |
| 紫微 calibrated | `listing_close_v1` | -1.07% (n=735) | -2.00% (n=731) | -2.58% (n=720) | -4.09% (n=647) |
| 紫微 calibrated | `ipo_approx_v1` | -1.20% (n=755) | -1.82% (n=751) | -1.85% (n=743) | -1.02% (n=665) |
| 黄历 raw | `listing_open_v1` | -0.96% (n=1485) | -2.38% (n=1477) | -3.94% (n=1459) | -5.15% (n=1269) |
| 黄历 raw | `listing_close_v1` | -1.26% (n=1499) | -2.88% (n=1487) | -4.39% (n=1469) | -5.31% (n=1280) |
| 黄历 raw | `ipo_approx_v1` | -0.91% (n=1488) | -2.24% (n=1477) | -4.01% (n=1459) | -4.95% (n=1262) |
| 黄历 calibrated | `listing_open_v1` | -0.81% (n=849) | -2.31% (n=844) | -4.79% (n=837) | -7.75% (n=715) |
| 黄历 calibrated | `listing_close_v1` | -0.97% (n=698) | -3.10% (n=695) | -4.62% (n=685) | -7.15% (n=577) |
| 黄历 calibrated | `ipo_approx_v1` | -0.61% (n=852) | -2.15% (n=844) | -5.04% (n=834) | -7.54% (n=715) |
| 八字+紫微 cal | `listing_open_v1` | -1.69% (n=178) | -2.74% (n=175) | -3.43% (n=175) | -5.64% (n=161) |
| 八字+紫微 cal | `listing_close_v1` | -1.59% (n=168) | -2.41% (n=168) | -2.15% (n=166) | -3.36% (n=149) |
| 八字+紫微 cal | `ipo_approx_v1` | -0.85% (n=172) | -0.56% (n=171) | 0.96% (n=169) | 4.88% (n=154) |
| 八字+黄历 cal | `listing_open_v1` | -0.67% (n=283) | -1.89% (n=280) | -4.56% (n=279) | -7.95% (n=239) |
| 八字+黄历 cal | `listing_close_v1` | -0.41% (n=255) | -2.20% (n=254) | -4.21% (n=251) | -7.44% (n=215) |
| 八字+黄历 cal | `ipo_approx_v1` | -0.29% (n=283) | -1.29% (n=282) | -3.42% (n=277) | -6.70% (n=245) |
| 紫微+黄历 cal | `listing_open_v1` | -0.92% (n=177) | -1.87% (n=175) | -4.28% (n=172) | -5.84% (n=146) |
| 紫微+黄历 cal | `listing_close_v1` | -2.03% (n=146) | -3.90% (n=145) | -5.12% (n=143) | -9.18% (n=116) |
| 紫微+黄历 cal | `ipo_approx_v1` | -0.71% (n=206) | -1.79% (n=203) | -4.91% (n=200) | -4.80% (n=167) |
| 三模型 cal | `listing_open_v1` | -1.85% (n=66) | -3.46% (n=64) | -7.10% (n=64) | -9.70% (n=55) |
| 三模型 cal | `listing_close_v1` | -1.90% (n=40) | -2.65% (n=40) | -5.13% (n=40) | -6.44% (n=31) |
| 三模型 cal | `ipo_approx_v1` | 0.18% (n=71) | -0.48% (n=70) | -0.90% (n=69) | 0.74% (n=61) |
| 三模型 raw | `listing_open_v1` | -1.17% (n=330) | -2.12% (n=326) | -3.17% (n=320) | -4.48% (n=274) |
| 三模型 raw | `listing_close_v1` | -1.51% (n=435) | -2.81% (n=432) | -3.87% (n=427) | -5.24% (n=364) |
| 三模型 raw | `ipo_approx_v1` | -1.13% (n=398) | -1.54% (n=394) | -2.42% (n=388) | -3.65% (n=323) |

## 5. 正式回答 GOAL §19 的核心三问（BAZI_POS）

**Q1：Raw BAZI_POS 在 Validation / OOS 是否仍然近乎恒正？**

| 出生模型 | 口径 | TRAIN 正向率 | VALIDATION 正向率 | OOS 正向率 |
|---|---|---|---|---|
| `listing_open_v1` | raw | 96.17% | 96.07% | 95.38% |
| `listing_open_v1` | calibrated | 24.97% | 24.74% | 25.39% |
| `listing_close_v1` | raw | 96.27% | 95.31% | 93.09% |
| `listing_close_v1` | calibrated | 24.92% | 23.66% | 26.35% |
| `ipo_approx_v1` | raw | 96.43% | 96.02% | 95.38% |
| `ipo_approx_v1` | calibrated | 24.96% | 26.02% | 25.33% |

**Q2：Calibrated Bazi 是否成功降低 Jaccard？**

| 出生模型 | raw Jaccard | calibrated Jaccard | raw 状态 | calibrated 状态 |
|---|---|---|---|---|
| `listing_open_v1` | 0.859 | 0.127 | `INVALID_CONTROL` | `INCONCLUSIVE` |
| `listing_close_v1` | 0.820 | 0.135 | `INCONCLUSIVE` | `INCONCLUSIVE` |
| `ipo_approx_v1` | 0.847 | 0.125 | `INVALID_CONTROL` | `WEAK_EVIDENCE` |

**Q3：事件区分度改善以后，是否真的优于随机？**

见下表：区分度（正向率）与 Jaccard 是第一层问题，是否优于对照是第二层问题。两者必须分别回答 —— 区分度提升不等于产生信息量。

| 出生模型 | cal 正向率 | cal Jaccard | cal OOS 超额 | 对照 | p | cal 状态 | raw 状态 |
|---|---|---|---|---|---|---|---|
| `listing_open_v1` | 25.39% | 0.127 | -1.57% | -2.31% | 0.090 | `INCONCLUSIVE` | `INVALID_CONTROL` |
| `listing_close_v1` | 26.35% | 0.135 | -1.74% | -2.30% | 0.154 | `INCONCLUSIVE` | `INCONCLUSIVE` |
| `ipo_approx_v1` | 25.33% | 0.125 | -1.23% | -2.23% | 0.050 | `WEAK_EVIDENCE` | `INVALID_CONTROL` |

## 6. 负对照状态（GOAL §14 / §19）

`位置` = 随机事件位置（200 次置换）；`指派` = 随机出生指派；`方向` = 随机模型方向；`−7d`/`+7d` = 出生日期平移（仅 OOS、使用真实 TRAIN 阈值）。

| 对象 | 出生模型 | 对照 | 对照事件数 | 对照均值 | 相对差 | p | Jaccard | 判定 |
|---|---|---|---|---|---|---|---|---|
| 八字 raw | `listing_open_v1` | `random_event_position` | 3132 | -2.28% | 0.14% | 0.040 | 0.859 | `outperform` |
| 八字 raw | `listing_open_v1` | `random_birth_assignment` | 3132 | -2.12% | -0.02% | 0.632 | — | `underperform` |
| 八字 raw | `listing_open_v1` | `random_model_direction` | 3132 | -2.12% | -0.03% | 0.677 | — | `underperform` |
| 八字 raw | `listing_open_v1` | `shifted_birth_date_minus_7d` | 3366 | -2.07% | -0.07% | 0.877 | 0.912 | `underperform`（失效） |
| 八字 raw | `listing_open_v1` | `shifted_birth_date_plus_7d` | 3361 | -2.24% | 0.09% | 0.838 | 0.910 | `outperform`（失效） |
| 八字 raw | `listing_close_v1` | `random_event_position` | 3052 | -2.28% | 0.17% | 0.025 | 0.820 | `outperform` |
| 八字 raw | `listing_close_v1` | `random_birth_assignment` | 3052 | -2.12% | 0.01% | 0.458 | — | `outperform` |
| 八字 raw | `listing_close_v1` | `random_model_direction` | 3052 | -2.12% | 0.00% | 0.478 | — | `outperform` |
| 八字 raw | `listing_close_v1` | `shifted_birth_date_minus_7d` | 3345 | -2.08% | -0.03% | 0.946 | 0.892 | `underperform` |
| 八字 raw | `listing_close_v1` | `shifted_birth_date_plus_7d` | 3309 | -2.16% | 0.05% | 0.917 | 0.877 | `outperform` |
| 八字 raw | `ipo_approx_v1` | `random_event_position` | 3131 | -2.29% | 0.22% | 0.005 | 0.847 | `outperform` |
| 八字 raw | `ipo_approx_v1` | `random_birth_assignment` | 3131 | -2.09% | 0.02% | 0.358 | — | `outperform` |
| 八字 raw | `ipo_approx_v1` | `random_model_direction` | 3131 | -2.10% | 0.02% | 0.338 | — | `outperform` |
| 八字 raw | `ipo_approx_v1` | `shifted_birth_date_minus_7d` | 3384 | -2.20% | 0.13% | 0.771 | 0.917 | `outperform`（失效） |
| 八字 raw | `ipo_approx_v1` | `shifted_birth_date_plus_7d` | 3366 | -2.14% | 0.07% | 0.877 | 0.912 | `outperform`（失效） |
| 八字 calibrated | `listing_open_v1` | `random_event_position` | 831 | -2.31% | 0.73% | 0.090 | 0.127 | `outperform` |
| 八字 calibrated | `listing_open_v1` | `random_birth_assignment` | 831 | -2.16% | 0.59% | 0.119 | — | `outperform` |
| 八字 calibrated | `listing_open_v1` | `random_model_direction` | 831 | -2.26% | 0.69% | 0.080 | — | `outperform` |
| 八字 calibrated | `listing_open_v1` | `shifted_birth_date_minus_7d` | 907 | -1.32% | -0.26% | 0.772 | 0.123 | `underperform` |
| 八字 calibrated | `listing_open_v1` | `shifted_birth_date_plus_7d` | 898 | -2.65% | 1.08% | 0.216 | 0.130 | `outperform` |
| 八字 calibrated | `listing_close_v1` | `random_event_position` | 874 | -2.30% | 0.56% | 0.154 | 0.135 | `outperform` |
| 八字 calibrated | `listing_close_v1` | `random_birth_assignment` | 874 | -2.02% | 0.28% | 0.274 | — | `outperform` |
| 八字 calibrated | `listing_close_v1` | `random_model_direction` | 874 | -2.01% | 0.27% | 0.284 | — | `outperform` |
| 八字 calibrated | `listing_close_v1` | `shifted_birth_date_minus_7d` | 857 | -1.49% | -0.25% | 0.785 | 0.163 | `underperform` |
| 八字 calibrated | `listing_close_v1` | `shifted_birth_date_plus_7d` | 891 | -2.84% | 1.10% | 0.241 | 0.142 | `outperform` |
| 八字 calibrated | `ipo_approx_v1` | `random_event_position` | 813 | -2.23% | 1.00% | 0.050 | 0.125 | `outperform` |
| 八字 calibrated | `ipo_approx_v1` | `random_birth_assignment` | 813 | -2.14% | 0.91% | 0.040 | — | `outperform` |
| 八字 calibrated | `ipo_approx_v1` | `random_model_direction` | 813 | -2.16% | 0.93% | 0.030 | — | `outperform` |
| 八字 calibrated | `ipo_approx_v1` | `shifted_birth_date_minus_7d` | 947 | -2.00% | 0.77% | 0.386 | 0.112 | `outperform` |
| 八字 calibrated | `ipo_approx_v1` | `shifted_birth_date_plus_7d` | 881 | -1.65% | 0.42% | 0.639 | 0.122 | `outperform` |
| 紫微 calibrated | `listing_open_v1` | `random_event_position` | 678 | -2.29% | 0.24% | 0.348 | 0.108 | `outperform` |
| 紫微 calibrated | `listing_open_v1` | `random_birth_assignment` | 678 | -2.33% | 0.28% | 0.323 | — | `outperform` |
| 紫微 calibrated | `listing_open_v1` | `random_model_direction` | 678 | -2.34% | 0.29% | 0.313 | — | `outperform` |
| 紫微 calibrated | `listing_open_v1` | `shifted_birth_date_minus_7d` | 896 | -1.58% | -0.47% | 0.601 | 0.223 | `underperform` |
| 紫微 calibrated | `listing_open_v1` | `shifted_birth_date_plus_7d` | 793 | -3.51% | 1.46% | 0.120 | 0.195 | `outperform` |
| 紫微 calibrated | `listing_close_v1` | `random_event_position` | 720 | -2.27% | -0.32% | 0.692 | 0.127 | `underperform` |
| 紫微 calibrated | `listing_close_v1` | `random_birth_assignment` | 720 | -2.33% | -0.25% | 0.721 | — | `underperform` |
| 紫微 calibrated | `listing_close_v1` | `random_model_direction` | 720 | -2.38% | -0.20% | 0.642 | — | `underperform` |
| 紫微 calibrated | `listing_close_v1` | `shifted_birth_date_minus_7d` | 755 | -1.77% | -0.81% | 0.387 | 0.192 | `underperform` |
| 紫微 calibrated | `listing_close_v1` | `shifted_birth_date_plus_7d` | 749 | -2.99% | 0.40% | 0.648 | 0.210 | `outperform` |
| 紫微 calibrated | `ipo_approx_v1` | `random_event_position` | 743 | -2.31% | 0.46% | 0.174 | 0.106 | `outperform` |
| 紫微 calibrated | `ipo_approx_v1` | `random_birth_assignment` | 743 | -1.98% | 0.13% | 0.443 | — | `outperform` |
| 紫微 calibrated | `ipo_approx_v1` | `random_model_direction` | 743 | -1.96% | 0.11% | 0.378 | — | `outperform` |
| 紫微 calibrated | `ipo_approx_v1` | `shifted_birth_date_minus_7d` | 745 | -3.00% | 1.15% | 0.246 | 0.191 | `outperform` |
| 紫微 calibrated | `ipo_approx_v1` | `shifted_birth_date_plus_7d` | 687 | -2.51% | 0.67% | 0.475 | 0.202 | `outperform` |
| 黄历 calibrated | `listing_open_v1` | `random_event_position` | 837 | -2.19% | -2.60% | 1.000 | 0.130 | `underperform` |
| 黄历 calibrated | `listing_open_v1` | `random_birth_assignment` | 837 | -4.93% | 0.13% | 0.373 | — | `outperform` |
| 黄历 calibrated | `listing_open_v1` | `random_model_direction` | 837 | -4.94% | 0.15% | 0.343 | — | `outperform` |
| 黄历 calibrated | `listing_open_v1` | `shifted_birth_date_minus_7d` | 856 | -5.04% | 0.25% | 0.765 | 0.364 | `outperform` |
| 黄历 calibrated | `listing_open_v1` | `shifted_birth_date_plus_7d` | 831 | -5.09% | 0.30% | 0.720 | 0.327 | `outperform` |
| 黄历 calibrated | `listing_close_v1` | `random_event_position` | 685 | -2.36% | -2.25% | 1.000 | 0.105 | `underperform` |
| 黄历 calibrated | `listing_close_v1` | `random_birth_assignment` | 685 | -5.25% | 0.63% | 0.134 | — | `outperform` |
| 黄历 calibrated | `listing_close_v1` | `random_model_direction` | 685 | -5.23% | 0.61% | 0.095 | — | `outperform` |
| 黄历 calibrated | `listing_close_v1` | `shifted_birth_date_minus_7d` | 704 | -5.40% | 0.78% | 0.440 | 0.299 | `outperform` |
| 黄历 calibrated | `listing_close_v1` | `shifted_birth_date_plus_7d` | 690 | -5.45% | 0.83% | 0.406 | 0.286 | `outperform` |
| 黄历 calibrated | `ipo_approx_v1` | `random_event_position` | 834 | -2.23% | -2.82% | 1.000 | 0.130 | `underperform` |
| 黄历 calibrated | `ipo_approx_v1` | `random_birth_assignment` | 834 | -5.07% | 0.03% | 0.468 | — | `outperform` |
| 黄历 calibrated | `ipo_approx_v1` | `random_model_direction` | 834 | -5.09% | 0.04% | 0.448 | — | `outperform` |
| 黄历 calibrated | `ipo_approx_v1` | `shifted_birth_date_minus_7d` | 873 | -4.52% | -0.53% | 0.512 | 0.336 | `underperform` |
| 黄历 calibrated | `ipo_approx_v1` | `shifted_birth_date_plus_7d` | 854 | -4.79% | -0.25% | 0.765 | 0.364 | `underperform` |
| 三模型 cal | `listing_open_v1` | `random_event_position` | 64 | -2.21% | -4.88% | 0.965 | 0.024 | `underperform` |
| 三模型 cal | `listing_open_v1` | `random_birth_assignment` | 64 | -4.67% | -2.43% | 0.910 | — | `underperform` |
| 三模型 cal | `listing_open_v1` | `random_model_direction` | 64 | -4.67% | -2.42% | 0.881 | — | `underperform` |
| 三模型 cal | `listing_open_v1` | `shifted_birth_date_minus_7d` | 81 | -0.98% | -6.12% | 0.044 | 0.073 | `underperform` |
| 三模型 cal | `listing_open_v1` | `shifted_birth_date_plus_7d` | 80 | -7.59% | 0.49% | 0.882 | 0.050 | `outperform` |
| 三模型 cal | `listing_close_v1` | `random_event_position` | 40 | -2.35% | -2.78% | 0.861 | 0.013 | `underperform` |
| 三模型 cal | `listing_close_v1` | `random_birth_assignment` | 40 | -6.17% | 1.04% | 0.333 | — | `outperform` |
| 三模型 cal | `listing_close_v1` | `random_model_direction` | 40 | -6.50% | 1.38% | 0.289 | — | `outperform` |
| 三模型 cal | `listing_close_v1` | `shifted_birth_date_minus_7d` | 46 | -9.23% | 4.11% | 0.391 | 0.036 | `outperform` |
| 三模型 cal | `listing_close_v1` | `shifted_birth_date_plus_7d` | 41 | -5.76% | 0.64% | 0.878 | 0.025 | `outperform` |
| 三模型 cal | `ipo_approx_v1` | `random_event_position` | 69 | -2.24% | 1.34% | 0.244 | 0.022 | `outperform` |
| 三模型 cal | `ipo_approx_v1` | `random_birth_assignment` | 69 | -3.19% | 2.29% | 0.109 | — | `outperform` |
| 三模型 cal | `ipo_approx_v1` | `random_model_direction` | 69 | -3.26% | 2.35% | 0.100 | — | `outperform` |
| 三模型 cal | `ipo_approx_v1` | `shifted_birth_date_minus_7d` | 68 | -4.99% | 4.08% | 0.137 | 0.030 | `outperform` |
| 三模型 cal | `ipo_approx_v1` | `shifted_birth_date_plus_7d` | 58 | -7.30% | 6.40% | 0.055 | 0.084 | `outperform` |

**Jaccard > 0.9 的对照共 4 条**（占全部对照 270 条，1.5%）。它们集中在哪些对象上，直接对应 Phase 3C 记录的原始方向偏置：事件集合接近整个可用池时，任何随机类对照都无法区分真实与随机。

## 6.5 横截面命中集中度：黄历是「日历开关」

每个 `as_of` 的命中率 = 当日命中股票数 / 当日可用股票数。若某引擎常常「几乎全体命中或几乎全体不命中」，它的事件集合实际是**日期选择**而不是**股票选择** —— 这会让两类负对照测量不同的零假设（见下）。

| 对象 | 出生模型 | 日期数 | 命中率最低 | 命中率最高 | 命中率标准差 | >60% 的日期 | <5% 的日期 |
|---|---|---|---|---|---|---|---|
| 八字 raw | `listing_open_v1` | 16 | 0.879 | 1.000 | 0.038 | 16 | 0 |
| 八字 raw | `listing_close_v1` | 16 | 0.787 | 1.000 | 0.072 | 16 | 0 |
| 八字 raw | `ipo_approx_v1` | 16 | 0.876 | 1.000 | 0.039 | 16 | 0 |
| 八字 calibrated | `listing_open_v1` | 16 | 0.113 | 0.435 | 0.092 | 0 | 0 |
| 八字 calibrated | `listing_close_v1` | 16 | 0.074 | 0.435 | 0.104 | 0 | 0 |
| 八字 calibrated | `ipo_approx_v1` | 16 | 0.105 | 0.391 | 0.085 | 0 | 0 |
| 紫微 calibrated | `listing_open_v1` | 16 | 0.132 | 0.303 | 0.035 | 0 | 0 |
| 紫微 calibrated | `listing_close_v1` | 16 | 0.093 | 0.327 | 0.054 | 0 | 0 |
| 紫微 calibrated | `ipo_approx_v1` | 16 | 0.144 | 0.364 | 0.058 | 0 | 0 |
| 黄历 raw | `listing_open_v1` | 16 | 0.055 | 0.945 | 0.339 | 6 | 0 |
| 黄历 raw | `listing_close_v1` | 16 | 0.006 | 0.912 | 0.291 | 4 | 2 |
| 黄历 raw | `ipo_approx_v1` | 16 | 0.048 | 0.949 | 0.350 | 6 | 1 |
| 黄历 calibrated | `listing_open_v1` | 16 | 0.000 | 0.776 | 0.269 | 2 | 7 |
| 黄历 calibrated | `listing_close_v1` | 16 | 0.000 | 0.640 | 0.219 | 1 | 6 |
| 黄历 calibrated | `ipo_approx_v1` | 16 | 0.000 | 0.776 | 0.275 | 2 | 8 |
| 三模型 cal | `listing_open_v1` | 16 | 0.000 | 0.103 | 0.030 | 0 | 13 |
| 三模型 cal | `listing_close_v1` | 16 | 0.000 | 0.043 | 0.015 | 0 | 16 |
| 三模型 cal | `ipo_approx_v1` | 16 | 0.000 | 0.109 | 0.029 | 0 | 15 |

**结构性发现（对负对照解读至关重要）**：`huangli` 的校准方向在横截面上几乎没有区分度 —— 同一天要么几乎全体命中、要么几乎全体不命中，因此它的事件集合接近「挑选日期」。这直接造成两类负对照给出相反结论：

* `random_event_position`（从整个池随机抽同数量）→ 混合了日期构成，与真实集合的日期权重错配 → 真实集合看起来**显著更差**（下尾 p 很小）；
* `random_birth_assignment` / `random_model_direction`（保留每日命中数量）→ 与真实集合的差异只剩「哪些股票命中」→ 真实 ≈ 对照（差 ≈ +0.1pp）。

本阶段**不**因此改动协议（那属于看到结果后调参）：两个口径都按预注册口径输出，gate 因「对照结论不一致」判 `INCONCLUSIVE`，并把「按日期分层的随机对照」列为 Phase 3F 的协议改进项（`gate-v2` / `cal-v2`）。

## 7. 跨年份稳定性、单一股票依赖与重叠敏感性

### 7.1 年份稳定性（OOS 分区，主持有期）

| 对象 | 出生模型 | 有效年数 | 正向年份比例 | 符号一致性 | OOS 平均超额 |
|---|---|---|---|---|---|
| 八字 raw | `listing_open_v1` | 4 | 0.00 | 1.00 | -2.14% |
| 八字 raw | `listing_close_v1` | 4 | 0.00 | 1.00 | -2.11% |
| 八字 raw | `ipo_approx_v1` | 4 | 0.00 | 1.00 | -2.07% |
| 八字 calibrated | `listing_open_v1` | 4 | 0.50 | 0.50 | -1.57% |
| 八字 calibrated | `listing_close_v1` | 4 | 0.25 | 0.75 | -1.74% |
| 八字 calibrated | `ipo_approx_v1` | 4 | 0.25 | 0.75 | -1.23% |
| 紫微 calibrated | `listing_open_v1` | 4 | 0.25 | 0.75 | -2.05% |
| 紫微 calibrated | `listing_close_v1` | 4 | 0.00 | 1.00 | -2.58% |
| 紫微 calibrated | `ipo_approx_v1` | 4 | 0.25 | 0.75 | -1.85% |
| 黄历 calibrated | `listing_open_v1` | 4 | 0.25 | 0.75 | -4.79% |
| 黄历 calibrated | `listing_close_v1` | 4 | 0.75 | 0.25 | -4.62% |
| 黄历 calibrated | `ipo_approx_v1` | 4 | 0.50 | 0.50 | -5.04% |
| 三模型 cal | `listing_open_v1` | 4 | 0.00 | 1.00 | -7.10% |
| 三模型 cal | `listing_close_v1` | 4 | 0.75 | 0.25 | -5.13% |
| 三模型 cal | `ipo_approx_v1` | 4 | 0.25 | 0.75 | -0.90% |

### 7.2 单一股票依赖（top1/top5 绝对贡献份额 + leave-one-stock-out）

| 对象 | 出生模型 | top1 | top5 | LOO 最小值 | LOO 最大值 | 符号翻转股票数 | 判定 |
|---|---|---|---|---|---|---|---|
| 八字 raw | `listing_open_v1` | 0.020 | 0.072 | -2.22% | -2.06% | 0 | 否 |
| 八字 raw | `listing_close_v1` | 0.021 | 0.073 | -2.19% | -2.03% | 0 | 否 |
| 八字 raw | `ipo_approx_v1` | 0.017 | 0.066 | -2.14% | -2.00% | 0 | 否 |
| 八字 calibrated | `listing_open_v1` | 0.037 | 0.148 | -1.79% | -1.39% | 0 | 否 |
| 八字 calibrated | `listing_close_v1` | 0.027 | 0.117 | -1.93% | -1.57% | 0 | 否 |
| 八字 calibrated | `ipo_approx_v1` | 0.046 | 0.177 | -1.50% | -1.01% | 0 | 否 |
| 紫微 calibrated | `listing_open_v1` | 0.043 | 0.153 | -2.23% | -1.82% | 0 | 否 |
| 紫微 calibrated | `listing_close_v1` | 0.032 | 0.139 | -2.75% | -2.40% | 0 | 否 |
| 紫微 calibrated | `ipo_approx_v1` | 0.039 | 0.180 | -2.02% | -1.63% | 0 | 否 |
| 黄历 calibrated | `listing_open_v1` | 0.021 | 0.098 | -4.93% | -4.66% | 0 | 否 |
| 黄历 calibrated | `listing_close_v1` | 0.028 | 0.104 | -4.78% | -4.42% | 0 | 否 |
| 黄历 calibrated | `ipo_approx_v1` | 0.028 | 0.094 | -5.17% | -4.84% | 0 | 否 |
| 三模型 cal | `listing_open_v1` | 0.153 | 0.448 | -7.93% | -5.42% | 0 | 否 |
| 三模型 cal | `listing_close_v1` | 0.187 | 0.567 | -6.11% | -3.10% | 0 | 否 |
| 三模型 cal | `ipo_approx_v1` | 0.116 | 0.403 | -2.06% | -0.10% | 0 | 否 |

### 7.3 重叠窗口敏感性（月度 OOS 子面板：密集采样 vs 非重叠子样本）

| 对象 | 出生模型 | 事件数（月度） | 重叠比例 | 全样本平均超额 | 非重叠子样本 n | 非重叠平均超额 |
|---|---|---|---|---|---|---|
| 八字 raw | `listing_open_v1` | 9572 | 0.596 | -1.20% | 6986 | -1.98% |
| 八字 raw | `listing_close_v1` | 9482 | 0.602 | -1.23% | 6902 | -1.95% |
| 八字 raw | `ipo_approx_v1` | 9542 | 0.594 | -1.16% | 6971 | -1.95% |
| 八字 calibrated | `listing_open_v1` | 2834 | 0.368 | -0.61% | 2347 | -1.11% |
| 八字 calibrated | `listing_close_v1` | 3246 | 0.424 | -0.77% | 2597 | -1.30% |
| 八字 calibrated | `ipo_approx_v1` | 2805 | 0.384 | -0.70% | 2304 | -1.13% |
| 紫微 calibrated | `listing_open_v1` | 2082 | 0.419 | -1.55% | 1677 | -2.02% |
| 紫微 calibrated | `listing_close_v1` | 2228 | 0.439 | -2.10% | 1773 | -2.39% |
| 紫微 calibrated | `ipo_approx_v1` | 2334 | 0.449 | -0.95% | 1846 | -1.48% |
| 黄历 calibrated | `listing_open_v1` | 2578 | 0.066 | -1.17% | 2501 | -1.16% |
| 黄历 calibrated | `listing_close_v1` | 2474 | 0.084 | -1.13% | 2380 | -1.11% |
| 黄历 calibrated | `ipo_approx_v1` | 2588 | 0.061 | -1.09% | 2514 | -1.00% |
| 三模型 cal | `listing_open_v1` | 208 | 0.058 | -2.33% | 203 | -2.68% |
| 三模型 cal | `listing_close_v1` | 224 | 0.027 | -2.41% | 221 | -2.58% |
| 三模型 cal | `ipo_approx_v1` | 224 | 0.045 | 0.11% | 220 | 0.11% |

## 8. Walk-forward（扩窗、逐 fold 重拟合）

| 对象 | 出生模型 | fold 数 | 不同 fit hash 数 | 正收益 fold | 击败对照 fold | 平均超额 |
|---|---|---|---|---|---|---|
| 八字 calibrated | `ipo_approx_v1` | 12 | 12 | 2 | 0 | -2.40% |
| 八字 calibrated | `listing_close_v1` | 12 | 12 | 3 | 2 | -2.20% |
| 八字 calibrated | `listing_open_v1` | 12 | 12 | 3 | 2 | -3.16% |
| 三模型 cal | `ipo_approx_v1` | 12 | 12 | 4 | 1 | -2.15% |
| 三模型 cal | `listing_close_v1` | 12 | 12 | 6 | 1 | 0.60% |
| 三模型 cal | `listing_open_v1` | 12 | 12 | 3 | 1 | -4.16% |
| 黄历 calibrated | `ipo_approx_v1` | 12 | 12 | 3 | 1 | -1.43% |
| 黄历 calibrated | `listing_close_v1` | 12 | 12 | 5 | 3 | -0.91% |
| 黄历 calibrated | `listing_open_v1` | 12 | 12 | 4 | 2 | -1.47% |
| 紫微 calibrated | `ipo_approx_v1` | 12 | 12 | 3 | 2 | -2.19% |
| 紫微 calibrated | `listing_close_v1` | 12 | 12 | 1 | 0 | -2.96% |
| 紫微 calibrated | `listing_open_v1` | 12 | 12 | 2 | 0 | -2.39% |

每个 fold 的 `calibration_fit_hash` 全部互不相同：**True**（证明逐 fold 重拟合，而不是复用全 TRAIN 校准）。
fold 级明细（含训练区间、`fit_partitions`、`freeze_bound_exceeded`、负对照）见 `data/phase3_universe/phase3d_walkforward_results.csv`。

## 9. 出生模型对比（GOAL §10）

这里回答的是「哪个出生模型下结论更稳定」，而不是「哪个出生模型才是真实出生时间」。三个模型都是上市日派生的研究构造，且 OOS 表现最好也不构成「它就是真实出生时间」的任何证据。

| 出生模型 | 实验数 | NO_SIGNAL | INVALID_CONTROL | INCONCLUSIVE | WEAK_EVIDENCE | 候选 |
|---|---|---|---|---|---|---|
| `listing_open_v1` | 18 | 1 | 1 | 11 | 0 | 0 |
| `listing_close_v1` | 18 | 0 | 0 | 13 | 0 | 0 |
| `ipo_approx_v1` | 18 | 0 | 1 | 8 | 4 | 0 |

## 10. 是否产生 OOS 候选 / 正式支持

| 问题 | 答案 |
|---|---|
| 是否产生 OOS_CANDIDATE_SUPPORTED | **否**（0 个实验） |
| 是否产生 SUPPORTED_OUT_OF_SAMPLE | **否** —— Phase 3D 结构上不可能产出（FDR 属 3F） |
| 状态分布 | `EXPLORATORY_NOT_GATED`=12, `INCONCLUSIVE`=32, `INSUFFICIENT_SAMPLE`=3, `INVALID_CONTROL`=2, `NO_SIGNAL`=1, `WEAK_EVIDENCE`=4 |

### FDR 前瞻（为什么必须把解锁留给 Phase 3F）

把 42 个进入 gate 的实验按名义 p 值排序，最小 p = 0.00498；BH-FDR（α=0.05，m=42）对应的最小门槛为 0.00119 → **通过 0 个**。名义上 p < 0.05 的有 6 个，但它们全部是效应量极小（|Cohen's d| ≈ 0.02–0.06）的弱结果，且无一通过年份稳定性条件。这正是 GOAL §15 要求「3D 最多给候选、正式解锁交给 3F」的实证理由。

### 唯一的方向性负结果

黄历校准事件集合（`huangli_calibrated`）在 OOS 的 20D 平均超额收益为 −4.6% 至 −5.0%，而同数量随机集合为 −2.2%，单侧置换 p 的上尾为 1.0、下尾约 0.005–0.03 —— 即**显著弱于随机**。这不是「术数有效」的反面证据，而是「按该口径挑出来的日期在这一段样本里恰好更差」的描述性事实：它同样需要 3F 的多重检验与 3E 的中性化才能判断是否为结构（日历/季节）效应。系统不把它表述为可交易信号。

## 11. 实验登记与 OOS 复用纪律

| 项目 | 值 |
|---|---|
| 登记行数 | 54 |
| 全部 oos_used | True |
| git_sha 一致 | True |
| split_version | phase3-oos-v1 |


## 12. 失败假设与空结果清单

以下是**没有**显示样本外信息量的对象（如实列出，不做美化）：

| 对象 | 出生模型 | 状态 | 原因（首条） |
|---|---|---|---|
| 八字 raw | `listing_close_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 八字 calibrated | `listing_open_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 八字 calibrated | `listing_close_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 八字 calibrated | `ipo_approx_v1` | `WEAK_EVIDENCE` | G8 未通过：有效年数 4，正向年份比例 0.25，符号一致性 0.75 |
| 紫微 raw | `listing_open_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 紫微 raw | `listing_close_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 紫微 raw | `ipo_approx_v1` | `WEAK_EVIDENCE` | G8 未通过：有效年数 4，正向年份比例 0.25，符号一致性 0.75 |
| 紫微 calibrated | `listing_open_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 紫微 calibrated | `listing_close_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 1/5 类对照，结果不一致。 |
| 紫微 calibrated | `ipo_approx_v1` | `WEAK_EVIDENCE` | G8 未通过：有效年数 4，正向年份比例 0.25，符号一致性 0.75 |
| 黄历 raw | `listing_open_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 黄历 raw | `listing_close_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 1/5 类对照，结果不一致。 |
| 黄历 raw | `ipo_approx_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 2/5 类对照，结果不一致。 |
| 黄历 calibrated | `listing_open_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 黄历 calibrated | `listing_close_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 黄历 calibrated | `ipo_approx_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 2/5 类对照，结果不一致。 |
| 八字+紫微 raw | `listing_open_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 八字+紫微 raw | `listing_close_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 3/5 类对照，结果不一致。 |
| 八字+紫微 raw | `ipo_approx_v1` | `WEAK_EVIDENCE` | G8 未通过：有效年数 4，正向年份比例 0.25，符号一致性 0.75 |
| 八字+紫微 cal | `listing_open_v1` | `NO_SIGNAL` | G5 未通过：OOS 效应未超过任何一类有效对照（对照中 5 类不弱于真实）。如实结论：在本样本与协议下，该对象没有显示样本外信息量。 |
| 八字+紫微 cal | `listing_close_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 2/5 类对照，结果不一致。 |
| 八字+紫微 cal | `ipo_approx_v1` | `INCONCLUSIVE` | G4 未通过：Validation 超额均值为 -5.4777%（符号 -1），OOS 为 0.9614%（符号 1） |
| 八字+黄历 raw | `listing_open_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 3/5 类对照，结果不一致。 |
| 八字+黄历 raw | `listing_close_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 2/5 类对照，结果不一致。 |
| 八字+黄历 raw | `ipo_approx_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 八字+黄历 cal | `listing_open_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 1/5 类对照，结果不一致。 |
| 八字+黄历 cal | `listing_close_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 八字+黄历 cal | `ipo_approx_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 紫微+黄历 raw | `listing_open_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 3/5 类对照，结果不一致。 |
| 紫微+黄历 raw | `listing_close_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 1/5 类对照，结果不一致。 |
| 紫微+黄历 raw | `ipo_approx_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 紫微+黄历 cal | `listing_open_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |
| 紫微+黄历 cal | `listing_close_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 2/5 类对照，结果不一致。 |
| 紫微+黄历 cal | `ipo_approx_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 1/5 类对照，结果不一致。 |
| 三模型 raw | `listing_open_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 3/5 类对照，结果不一致。 |
| 三模型 raw | `listing_close_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 1/5 类对照，结果不一致。 |
| 三模型 raw | `ipo_approx_v1` | `INCONCLUSIVE` | G5 未通过：OOS 效应只击败 4/5 类对照，结果不一致。 |

## 13. 方法与限制

完整协议见 [`oos-methodology.md`](oos-methodology.md) 与 [`walk-forward-methodology.md`](walk-forward-methodology.md)。读本报告时必须同时接受以下限制：

1. **未做多重检验校正**（BH-FDR 属 Phase 3F）：54 个实验共享同一 OOS 区间，`p` 值未校正，这正是本阶段不产出 `SUPPORTED_OUT_OF_SAMPLE` 的原因。
2. **行业无 PIT**（`POINT_IN_TIME_INDUSTRY_UNAVAILABLE`）：未做行业/风格中性化，OOS 差异可能混入行业结构。
3. **出生时间 = 上市日派生**：`company_foundation` 不可得，结论只适用于该研究构造。
4. **出生平移对照只覆盖 OOS**，且使用真实 TRAIN 冻结阈值。
5. **未计交易成本 / 流动性 / 涨跌停**：这是信息量检验，不是可交易性检验。
6. **退市股除权因子来自第二个快照**，覆盖情况已在 `phase3d_calibration_freeze.json` 的 `label` 字段披露。

