# Phase 3 · 交接文档（HANDOFF）

> 交接对象：接手 Phase 4 的工程师 / 研究者。
> 读这份文档的顺序：**先读「§1 一分钟状态」，再读「§6 不准做的事」，最后按需查表。**

---

## 1. 一分钟状态

| 项目 | 值 |
|---|---|
| 分支 | `feature/phase3-research-validation` |
| 基线 commit | `981bdac201735c18772d34dde6efa41d1de19b72`（3H 冻结；3E `e7e67e4` / 3F `3787e8c` / 3G `b1a6577`）|
| tag | `phase3-research-v1.0`（annotated，指向 3H 冻结提交）|
| 研究结论 | **`MULTI_ENGINE_NO_SIGNAL`** / **`SUPPORTED_OUT_OF_SAMPLE = 0`** |
| 最终定性 | `PASS WITH CONDITIONS — RESEARCH PIPELINE READY / EVIDENCE INCONCLUSIVE` |
| 一句话 | 管线成熟可用；证据本身为负。`PASS` 仅代表研究管线成熟，**绝不等于术数有效**。 |

**Phase 3 到底完成了什么**：把"术数是否有效"这个问题从**不可证伪**变成了**可证伪，
并且已经证伪到当前数据能支持的极限** —— 500 只无偏股票（含 333 只退市股）、
2010–2026、54 个预注册实验、逐 fold 重拟合、日期分层置换、族内 BH-FDR、
9 个稳健性维度、24 个案例的跨实现核对。

---

## 2. 版本矩阵（任何结论都必须带上这些版本号）

| 类型 | 版本 | 位置 |
|---|---|---|
| `dataset_version` | `phase3a_astockdata_cutoff_20260814` | `src/research/oos/splits.py` |
| `universe_version` | `v2-phase3a`（500 = 333 退市 + 167 在市） | 同上 |
| `split_version` | `phase3-oos-v1`（fingerprint `6a059b3dbe54f22d`） | 同上 |
| `label_version` | `phase3d-hfq-adjfactor-v1` | `src/research/labels/horizon_returns.py` |
| `calibration_version` | `cal-v1`（`fit_hash 7e9897570d3b5a28`，fit 至 2018-10-01） | `src/research/oos/calibration_freeze.py` |
| `hypothesis_registry` | `phase3d-hypotheses-v1`（18 假设，预注册时未见 OOS 标签） | `config/phase3d_hypothesis_registry.yaml` |
| `multiple_testing` | `mt-v1`（6 个族，冻结于结果之前） | `config/phase3f_multiple_testing_families.yaml` |
| `gate_v1` | `phase3d-oos-gate-v1`（最高只给候选） | `src/research/oos/gates.py` |
| `gate_v2` | `phase3f-oos-gate-v2`（A–L，唯一解锁路径） | `src/research/multipletesting/gate_v2.py` |
| `neutralization` | `phase3e-neutralization-v1` | `src/research/neutralization/runner.py` |
| `exposure` | `phase3e-exposures-v1` | `src/research/neutralization/exposures.py` |
| `industry` | `phase3e-industry-v1` | `src/research/neutralization/industry.py` |
| `market_neutral` | `phase3e-market-neutral-v1` | `src/research/neutralization/benchmark.py` |
| `bazi_engine_version` | `smx-bazi-native-1.0.0` | 引擎模块 |
| `ziwei_engine_version` | `iztro-2.6.1+smx-1.0.0` | 引擎模块 |
| `huangli_engine_version` | `huangli-engine-1.0.0` | 引擎模块 |
| `factor_rule_version` | `v1.1` | `src/core/config.py` |
| 紫微参考实现 | `fortel-ziweidoushu` 1.3.4（中州派，MIT，**REFERENCE ONLY**） | `services/ziwei-reference-service/` |

---

## 3. 数据与产物清单

### 3.1 数据库（`data/smp.sqlite3`）

| 表 | 行数（实测） |
|---|---:|
| `market_bar_daily`（全部） | 1,841,884 |
| ├ `astockdata_composite_none`（canonical） | 1,737,363 |
| └ `IDX000300`（基准） | 5,214 |
| `universe_memberships`（`v2-phase3a`） | 500（其中退市 333） |
| `stock_birth_profile` | 1,501（3 模型 × 500 只） |

### 3.2 研究产物（`data/phase3_universe/`）

| 前缀 | 内容 |
|---|---|
| `phase3d_*` | OOS 结果 / 实验登记 / 负对照 / 年份稳定 / 重叠敏感性 / walk-forward / 冻结记录 |
| `phase3e_*` | 648 行中性化结果 + 逐日黄历日期表（18 个）+ 暴露覆盖率 |
| `phase3f_*` | 72 行多重检验结果 + 族内校正 + 324 行稳健性切片 + 运行摘要 |
| `phase3g_*` | 24 案例跨实现差异登记 + 案例明细 + 核对摘要 |
| `phase3d_cache/` | 观测面板分片（主 / 月度 / 平移 ±7 天），**采集耗时数小时，不要删** |

### 3.3 文档地图

| 文档 | 内容 |
|---|---|
| [`PHASE3_RESEARCH_REPORT.md`](PHASE3_RESEARCH_REPORT.md) | **26 章最终报告（从产物自动生成）** |
| [`phase3-model-limitations.md`](phase3-model-limitations.md) | 20 条限制，逐条给出解除条件 |
| [`oos-methodology.md`](oos-methodology.md) | 固定 holdout 协议 |
| [`walk-forward-methodology.md`](walk-forward-methodology.md) | 扩窗 + 逐 fold 重拟合的四道闸门 |
| [`factor-calibration-methodology.md`](factor-calibration-methodology.md) | `cal-v1` 冻结 |
| [`neutralization-methodology.md`](neutralization-methodology.md) | 市场/行业/风格中性化 |
| [`huangli-date-effect-analysis.md`](huangli-date-effect-analysis.md) | 黄历日期效应（P0 统计修正） |
| [`multiple-testing-methodology.md`](multiple-testing-methodology.md) | BH-FDR / bootstrap / 分层置换 / gate-v2 |
| [`ziwei-cross-engine-differences.md`](ziwei-cross-engine-differences.md) | 紫微第二实现源差异登记 |
| [`data-coverage-phase3.md`](data-coverage-phase3.md) | 数据覆盖与质量告警 |

---

## 4. 复现方法（逐条可执行）

```bash
# 0. 环境（Windows：Git Bash；PYTHONUTF8=1 必须）
PY=.venv/Scripts/python.exe
export PYTHONUTF8=1

# 1. 全量测试（≈7 分钟，1253+ 项）
$PY -m pytest -q

# 2. 泄漏 / 金案例 / 第三方隔离
$PY -m pytest tests/test_no_future_data_access.py tests/test_third_party_isolation.py -q
$PY -m pytest tests/golden -q

# 3. 3E 中性化（≈100 秒，只用 3D 缓存，不重新采集）
$PY scripts/phase3e_neutralization.py

# 4. 3F 多重检验（≈120 秒，5000 次置换/实验；冒烟可加 --limit-stocks 60 --smoke）
$PY scripts/phase3f_multiple_testing.py

# 5. 3G 跨实现核对（≈10 秒；先装参考实现依赖）
cd services/ziwei-reference-service && npm install && cd ../..
$PY scripts/phase3g_ziwei_crosscheck.py

# 6. 重新生成 3H 报告（从产物，不跑统计）
$PY scripts/phase3h_write_report.py

# 7. 3D 管线（**会重新读取 OOS**，仅在确认需要时跑；务必带 --reuse-cache）
$PY scripts/phase3d_oos_pipeline.py --reuse-cache --skip-collect
```

> 3E/3F/3G 都**不会**重新采集面板，也不重新读取 OOS 标签 —— 它们读取 3D 的产物。
> 只有第 7 步会再次读取 OOS，因此默认不要跑。

---

## 5. Phase 4 的建议（按性价比排序）

### 5.1 优先做（高价值、低风险）

1. **退市股收益独立复核**（对应限制 #8）：`universe_subset` 在 31/42 个实验中符号不一致，
   这是最重要的一条。做法：换一个独立数据源重建 333 只退市股的复权收益，逐日对拍。
2. **行业 PIT 分类**（限制 #2）：拿到带生效日期的申万/中信历史，建立
   `IndustryClassificationProvider`，重跑 3E 的行业中性化。这是当前**最大的未排除解释**。
3. **PIT 基本面**（限制 #4/#5）：接入 `total_mv` / `circ_mv` / `pe_ttm` / `pb`，
   把 size 从"流动性代理"升级为真实市值，并补上 value 维度。
4. **成本模型 + 可交易性模拟**（限制 #7）：把"信息量检验"升级为"可交易性检验"。
   注意：这一步**只有在先找到正效应之后才有意义** —— 现在是 0 个，因此优先级低于 1–3。

### 5.2 可选（会扩展研究自由度，需要新的预注册）

5. **更密的采样网格**（限制 #17）：月度/周度 + 重叠修正，提升检出力。
   代价：引入新的多重检验维度，必须新建 `mt-v2` 与新的假设注册表。
6. **族划分敏感性分析**（限制 #11）：预注册多种族划分方案并全部报告。
7. **Phase 4 的新术数分支**（六爻 / 奇门）：**必须**先建 `MetaphysicsEngine` 实现、
   完成 Phase 1 级的单元测试与金案例，然后走完整的预注册 → 冻结 → OOS 流程。
   不允许"直接接到 Phase 3 的 OOS 上试一下"。

### 5.3 不建议做

* **不要**重新调 `cal-v1` 或 P25/P75 去追 OOS 表现 —— 那会让 Phase 3 的全部纪律作废；
* **不要**为了让 FDR 通过而拆族、换持有期、换出生模型；
* **不要**删掉失败的假设或空结果；
* **不要**把 `fortel-ziweidoushu` 接进 `ConsensusEngine`（它是 REFERENCE ONLY，有测试守着）。

---

## 6. 不准做的事（硬约束，违反即 Phase 3 的研究结论作废）

1. `cal-v1` 已冻结（`fit_max_as_of = 2018-10-01`）。任何改动必须新建 `cal-v2`
   并**重新定义整个 OOS 协议**。
2. Phase 3D 的 OOS 已被读取（54 条实验 `oos_used = true`）。再次使用同一 OOS 区间
   必须新建版本并附 `RESEARCH_REUSE_WARNING`。
3. `config/phase3d_hypothesis_registry.yaml` 的命中定义、方向、持有期、对照类型**不得修改**。
   新增假设请新建 `hypothesis_id`（例如 `-002`），旧条目原样保留。
4. `config/phase3f_multiple_testing_families.yaml` 的族划分**不得修改**；
   改动必须新建 `mt-v2`。
5. `gate-v1` 与 `gate-v2` 必须**同时报告**，禁止只留更好看的那一版。
6. 参考实现（`src/engines/ziwei/reference/`）**只能**用于研究核对：
   不得进入 `ConsensusEngine`、不得被业务层依赖（`tests/golden/test_ziwei_cross_engine.py` 守着）。
7. `SUPPORTED_OUT_OF_SAMPLE` 只能由 `gate_v2` 的 A–L 全部通过时产出；
   `src/research/status.py::assess_research_status`（样本内判定）**永不**返回它。
8. 任何不可用字段必须返回 `null` / `"unavailable"`，**禁止用 0 冒充**。

---

## 7. 已知的坑（踩过的）

| 坑 | 表现 | 规避 |
|---|---|---|
| `ResearchCalibrationLayer.transform` 的索引错位 | 传入切片帧时静默写错行 | 已在 3D 修复（`reset_index`）+ 回归测试；不要移除 |
| 行级 p 值 | 同一日期 200 只股票被当独立样本 → 虚假显著 | 一律用日期分层口径；见限制 #12 |
| 黄历的"日期选择器"结构 | 两类负对照给出相反结论 | 双口径并排报告；见限制 #13 |
| `BAZI_POS` 高激活 | 原始方向 94%–96.6% 为正 → 负对照失效 | Jaccard 硬断言；不要用原始方向做研究 |
| iztro 晚子时显示不一致 | `lunar_date` 显示当日但星曜按次日安放 | 不影响因子（不含农历日字符串）；见 3G 报告 |
| 硬编码开盘时刻 | `tests/test_birth_profile.py` 会失败 | 开盘/收盘时刻只能来自 `exchange_session_calendar` |
| Windows 中文编码 | configparser / 文件读取 GBK 解码失败 | 所有 Python 命令带 `PYTHONUTF8=1` |
| SQLAlchemy `autoflush=False` | upsert 幂等性错 | 先 `db.flush()` |
| Next.js rewrites 构建期固化 | 改 `SMP_API_BASE` 无效 | 重建前端 |
| 参考实现依赖 | 未 `npm install` 时 3G 记 `REFERENCE_UNAVAILABLE` | `cd services/ziwei-reference-service && npm install` |

---

## 8. 关键数字速查（Phase 4 引用时直接用）

| 数字 | 值 |
|---|---:|
| universe | 500 只（333 退市 + 167 在市） |
| 行情行数（canonical） | 1,737,363 |
| 主面板观测行 | 175,734（500 × 3 模型 × 68 as_of × 3 引擎，扣 PIT 资格） |
| 标签行数 | 31,305（3D）/ 24,646（3E 主面板 68 as_of） |
| 预注册假设 / 实验 | 18 / 54 |
| OOS 有效日期（20D） | 15 |
| 正式 gate 实验 | 42 |
| **BH-FDR 通过** | **0**（正式）/ 1（探索性，不解锁） |
| **Bonferroni 通过** | **0**（正式）/ 1（探索性） |
| **`SUPPORTED_OUT_OF_SAMPLE`** | **0** |
| `style_r2_mean`（OOS 20D） | 0.1992 |
| 稳健性最弱维度 | `universe_subset`：31/42 符号不一致 |
| 紫微跨实现一致率 | 95.75%（2280 项中 2183 项） |
| 测试数 | 1253+（pytest）；40（Playwright，未在本阶段改动前端） |

---

## 9. 最后一句

Phase 3 的结论是**负的**，但它是**可信的负结论**：这套管线能识别并拒绝
"看起来有信号"的结果（BAZI_POS 的分布偏置、黄历的日期选择器结构、
名义 p < 0.05 的 6 个实验）。它同样会在真有信号时给出可复现的正结论 ——
**这正是它值得交接的原因**。

*创建于 2026-09-20*
