# Phase 4E：用全市场与真实 size/value 重做 Phase 3E

> 同一套假设与对象定义（`config/phase3d_hypothesis_registry.yaml` 一个字未改），
> 只升级**样本**与**控制变量**。因此本文不是"换一套假设再搜一遍"，而是
> "同一套假设、更强的控制、更大的样本"。

## 口径差异

| | Phase 3E（冻结） | Phase 4E（本次） |
|---|---|---|
| universe | `v2-phase3a` 500 只 | `v4-full` **6,104 只** |
| 每时点股票数（样本外） | 中位 **220**（最小 165） | 中位 **5,503**（最小 5,219） |
| 校准 | `cal-v1`（TRAIN=500 只） | **`cal-v2`**（TRAIN=全市场，`fit_hash=bd47722ba1ea4799`） |
| size 口径 | `size_proxy_log_amount_20d`（20 日均成交额对数，**流动性代理**） | **`size_log_market_cap`**（真实总市值） |
| value 口径 | **不可得** | **`value_ep` = 1/pe_ttm、`value_bp` = 1/pb**（逐日 PIT） |
| 流动性 | 无 | `turnover_free_20d` |
| 样本外时点 | 15 个（`phase3-oos-v1`） | 15 个（同一 split） |
| 事件行数（样本外主持有期） | 3,186 | **78,029（24.5 倍）** |

风格暴露列：3E 为 `momentum_60d, momentum_120d, volatility_20d, volatility_60d,
size_proxy_log_amount_20d`；4E 为 `size_log_market_cap, value_ep, value_bp,
momentum_60d, momentum_120d, volatility_20d, volatility_60d, turnover_free_20d`。

## 暴露覆盖率（如实披露）

| 暴露 | 可用 / 缺失 | 覆盖率 |
|---|---|---|
| `size_log_market_cap` | 711,765 / 41,943 | **94.4%** |
| `value_ep` | 592,527 / 161,181 | **78.6%** |
| `value_bp` | 706,989 / 46,719 | **93.8%** |
| `momentum_60d` | 729,882 / 23,826 | 96.8% |
| `momentum_120d` | 716,415 / 37,293 | 95.1% |
| `volatility_20d` | 738,768 / 14,940 | 98.0% |
| `volatility_60d` | 729,543 / 24,165 | 96.8% |
| `turnover_free_20d` | 711,423 / 42,285 | 94.4% |

`value_ep` 覆盖率最低是**口径要求**的结果：`pe_ttm <= 0` 时取倒数会得到负的"收益率"，
因此一律置 NaN（见 `exposures_v2.safe_inverse`），不得用 0 冒充。
退市股没有估值（供应商日 K 不含退市股），其 size/value 一律 NaN，
`delisted_note = VALUATION_UNAVAILABLE_FOR_DELISTED`。

## 核心结果

### 1. 符号依然大量翻转 —— 换成真实控制变量也没变稳

| | 可比格子 | 原始超额与中性化后**符号不同** |
|---|---|---|
| Phase 3E | 54 | **31 个（57%）** |
| Phase 4E | 54 | **25 个（46%）** |

即：加入真实 size/value 后翻转比例只从 57% 降到 46%。**"原始超额"与"风格中性化后"
的符号依然不能互相替代**，任何只报其中一个的结论都不可靠。

### 2. 效应量级整体塌向 0

| 指标（样本外、主持有期） | Phase 3E | Phase 4E |
|---|---|---|
| 中性化后效应均值 范围 | [−0.0499, +0.0352] | **[−0.0060, +0.0281]** |
| 中性化后效应均值 **中位** | +0.0011 | **+0.0000** |
| 受控命中系数 中位 | +0.0049 | **+0.0001** |
| `factor_rank_ic` 中位 | +0.0127 | **+0.0013** |
| RankIC \|t\|>2 的个数 | **0 / 18** | **0 / 18** |

离散度大幅收窄（±5% → −0.6%~+2.8%），中位数恰好是 0：**一半对象在 0 以上、
一半在 0 以下，且幅度极小**。RankIC 掉了一个数量级，且两阶段都**没有任何一个显著**。

### 3. Phase 3E 里"看起来有正效应"的格子，全部塌到 0

样本外主持有期、`listing_open_v1`、受控命中系数（`controlled_hit_coefficient`）：

| 对象 | 3E | 4E |
|---|---|---|
| `huangli_calibrated` | **+0.0411** | −0.0039 |
| `bazi_huangli_calibrated` | **+0.0464** | +0.0023 |
| `ziwei_huangli_calibrated` | **+0.0512** | +0.0041 |
| `all_three_calibrated` | +0.0328 | +0.0198 |

这几个正是 3E 里唯一像"有东西"的格子。把它们放到全市场、真实 size/value 下重算，
**全部塌到 0 附近**。

## 怎么读这个结果

**这不是"3E 算错了"**，而是"3E 那些正数确实是抽样噪声"——500 只、220 只/时点、
用成交额代理 size、完全没有 value 的横截面，本来就不足以把那么小的效应从噪声里分出来。
全市场 + 真实控制变量把噪声挤掉了，于是正数归零。

**也不是"术数被证明有效"**——恰恰相反：**没有任何一个显著效应出现**，
且量级塌到 0 附近。这把"即使有效、效应也极小"的判断进一步收紧了。

## 仍然存在的限制（不可忽略）

1. **样本外仍只有 15 个独立日期**。按 Phase 4 的检验能力分析，这个设计能检出的
   最小效应约 **3.5%**；而观测到的效应中位数在 **1.4%** 量级 → **落在刻度以下**。
   换成全市场并不能提高日期维度的检验力（有效样本量是"日期数"，不是"股票数"）。
2. **`cal-v2` 与 `cal-v1` 的阈值不同，不可混用**；Phase 3 的产物仍基于 `cal-v1`，
   两者是并列的两个口径，不是替代关系。
3. `value_ep` 覆盖 78.6%，退市股无估值 —— 这两项在报告里必须与结果同时给出。
4. 本文档的对比数字来自 `phase3e_neutralization_results.csv` 与
   `phase4_neutralization_results.csv` 的**样本外 + 主持有期 + `listing_open_v1`** 切片。

## 产物与复现

```bash
# 全量面板 → cal-v2 → 标签 → 暴露 v2 → 中性化
python scripts/phase4_neutralization.py

# 产物
#   data/phase4_universe/phase4_neutralization_results.csv     （648 行）
#   data/phase4_universe/phase4_neutralization_meta.json
#   data/phase4_universe/phase4_label_cache.parquet
```

> 注：`scripts/phase4_neutralization.py` 的 docstring 列出了本文档，但脚本内**没有**
> 生成它的代码；本文档由结果表直接分析写成，数字可逐项回溯到上面的 CSV。
