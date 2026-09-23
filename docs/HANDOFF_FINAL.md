# HANDOFF_FINAL · 股票玄学多模型研究平台（Phase 2 交付）

> **给下一个接手者（人或 AI）的完整交接文档。**
>
> 读这份文档之前，请先读：`AGENTS.md` → `README.md` → `ARCHITECTURE.md` → 本文件。
>
> 验收结论见 [`docs/PHASE2_ACCEPTANCE_REPORT.md`](PHASE2_ACCEPTANCE_REPORT.md)。
>
> **UI 收尾阶段（2026-09-21 起）**：十页视觉精修与发布前验收见
> [`docs/UI_FINAL_POLISH_REPORT.md`](UI_FINAL_POLISH_REPORT.md)、
> [`docs/UI_FINAL_ACCEPTANCE_CHECKLIST.md`](UI_FINAL_ACCEPTANCE_CHECKLIST.md)、
> [`docs/UI_FINAL_RELEASE_READINESS.md`](UI_FINAL_RELEASE_READINESS.md)。
> 该阶段**未合并 main、未部署**，候选截图等待人工确认。

---

## 1. 当前状态（2026-09-19）

| 项 | 值 |
|---|---|
| **最终 commit SHA** | **`68a43f05b6156122366568a1ed0ad298aaa3c608`** |
| 版本 | `0.2.0` / phase `phase2` |
| 上游基线 | Phase 1 `6d4d5d7` + Phase 1.1 加固 |
| 测试 | **1003 pytest PASS / 44 Playwright PASS** |
| 因子 | 114（Phase 1 的 65 + 紫微的 49） |
| API 端点 | 39 |
| 数据库 | 17 张表 + Alembic（Phase 2 **未新增表**，复用 `chart_artifact` / `factor_observation` / `analysis_run`） |
| 引擎 | calendar / huangli / bazi / **ziwei**；liuyao / qimen 仍为预留 |
| 验收判定 | `PASS WITH CONDITIONS — PLATFORM V2 READY / RESEARCH CLAIMS BLOCKED` |

---

## 2. 一分钟理解系统

```
股票代码
  → StockBirthProfile（研究假设，不是事实）
  → 八字盘 / 紫微十二宫盘 / 黄历
  → 三套独立因子（B_* / Z_* / H_*）—— 全部确定性代码计算
  → 三个独立 EngineOpinion（互不借用因子）
  → ConsensusEngine（禁止平均）+ ConflictDetector（四层冲突）
  → 时间窗口（12 月 / 12 周，交易日聚合）
  → EvidenceBundle（唯一允许被解释层读取的数据）
  → AI Narrator（模板优先，LLM 需过 Guard）
  → ResearchStatus（历史统计的最终结论）
```

**这不是荐股系统。** 实测结论是：多模型共振在真实样本上
**没有显示出稳定的预测能力**（`INVALID_CONTROL` / `NO_SIGNAL`）。

---

## 3. 六阶段交付物

### 2A 紫微确定性计算

```
services/ziwei-service/      Node.js + TypeScript + iztro@2.6.1（精确锁定，MIT）
  src/chart.ts               纯函数排盘；variant → 性别参数解析
  src/cli.ts                 stdin/stdout 批量 JSON（**默认 transport**）
  src/server.ts              POST /internal/ziwei/{chart,batch}（部署 transport）
  Dockerfile                 多阶段构建

src/engines/ziwei/           Python Adapter（唯一接触服务的位置）
  transport.py               http → subprocess → unavailable 三级降级 + 显式字段映射
  ziwei_engine.py            ZiweiEngine(MetaphysicsEngine)
  constants.py               自持星曜/宫位静态表

src/core/schemas/ziwei.py    ZiweiChart 等
tests/fixtures/ziwei/*.json  8 组真实 iztro 输出快照
```

**必须记住**：

* 字段映射是**显式的**（不是通用驼峰转换）——服务端改名会立刻在测试中暴露；
* `variant_mode=not_applicable` 时引擎**拒绝排盘**（不默认性别）；
* `ZiweiPalace.index` 固定为地支顺序 `0 = 寅`（唯一稳定的宫位坐标）；
* 三方四正是索引算术 `[i, (i+6)%12, (i+8)%12, (i+4)%12]`，已对拍 iztro。

### 2B 紫微因子

49 个 `Z_*` 因子，11 个命名空间（LIFE / FIN / CAREER / MOVE / MUTAGEN /
TRINE / YEAR / MONTH / DAY / DECADE / AGE）。

* `rule_version`：定义 `zv1`；**观测**按 variant 后缀区分为 `zv1.fwd` / `zv1.rev`；
* 只有 4 个因子随 variant 变化（`Z_DECADE_001/002`、`Z_AGE_001/002`），
  由不变量测试锁定；
* 质量审计口径见 `src/factors/ziwei/audit.py`（**连续型因子不能用 activation_rate 判区分度**）。

### 2C 共识与分歧

`src/core/orchestration/consensus.py`：
`ConsensusEngine`（六分类，**禁止简单平均**）+ `ConflictDetector`（四层冲突）。

`src/research/consensus_research.py`：
11 个**预定义**组合（自由组合直接抛 `ValueError`）+ 打乱激活位置的负对照 +
Welch t 检验 + `MultipleTestingWarning`。

### 2D 时间窗口

`src/core/orchestration/timeline.py`：未来 12 月 / 12 周。
**周不是独立运限** —— 由 5 个交易日的流日结果聚合，口径版本 `agg-v1`。

### 2E 证据与解释

* `knowledge/ziwei/classical_seed.json`（13 条，与八字 43 条并存，loader 支持多域）；
* `EvidenceBundle`（`src/core/schemas/evidence.py` + `src/core/orchestration/evidence.py`）；
* `src/narrator/narrator.py` + `guard.py`（模板优先 + 幻觉守卫）。

### 2F UI

7 个新页面 + 综合页数据源切换 + 报告导出（见 `docs/ui-implementation-phase2.md`）。

---

## 4. 新增 API（9 个）

```
POST /api/v1/stocks/{code}/analysis/ziwei         紫微分析（需显式 variant）
POST /api/v1/stocks/{code}/analysis/multi         多模型综合研判（Phase 2 主入口）
GET  /api/v1/analysis/{id}/charts/ziwei           紫微盘面（按 variant 分开返回）
GET  /api/v1/analysis/{id}/opinions               三个独立观点
GET  /api/v1/analysis/{id}/timeline/months        未来 12 月
GET  /api/v1/analysis/{id}/timeline/weeks         未来 12 周
GET  /api/v1/analysis/{id}/evidence-bundle        证据包
POST /api/v1/analysis/{id}/narrative              AI 解释
GET  /api/v1/analysis/{id}/report?format=…        Markdown / HTML 报告
POST /api/v1/research/consensus                   多模型共振研究
```

---

## 5. 不得破坏的契约（Phase 1 + Phase 2）

### 5.1 接口

`MetaphysicsEngine` / `CalendarEngine` / `HuangliEngine` / `BaziEngine` /
**`ZiweiEngine`** / `MarketDataProvider` / `KnowledgeProvider` / `BacktestProvider`
的方法签名与返回类型。

### 5.2 数据字段

* `StockBirthProfile` 全部字段（含 `variant_mode` / `assumptions` / `data_quality`）；
* `FactorObservation` / `FactorSet` 字段名与语义；
* `MetaphysicsOpinion`（Phase 2 新增 `research_status` / `data_quality` / `assumptions`，
  均为可选）；
* `ConsensusSnapshot` / `ConflictSnapshot`（Phase 2 新增字段，`display_only` 保留）；
* `ZiweiChart` 全字段与宫位坐标系。

### 5.3 语义（最重要）

| # | 契约 |
|---|---|
| 1 | **不可用必须是 `null` / `"unavailable"`，绝不用 `0` 冒充** |
| 2 | 分数是**传统规则强度**，不是收益率、不是上涨概率 |
| 3 | 分歧不得被平均掩盖（`MIXED` 优先级最高） |
| 4 | 共识 ≠ 历史有效（`research_status` 必须与 `label` 同时呈现） |
| 5 | 紫微 **不默认性别**；无显式 variant 就拒绝排盘 |
| 6 | 两个紫微 variant **不是两条独立证据** |
| 7 | 宫位→金融含义映射是**研究假设**（`ziwei_stock_mapping_v1`） |
| 8 | 古籍检索必须同时返回支持与反证 |
| 9 | 负对照必须真的重排盘/重算；Jaccard > 0.9 判 `INVALID_CONTROL` |
| 10 | 没有负对照的"有效"不被承认 |
| 11 | `SUPPORTED_OUT_OF_SAMPLE` 仍被禁用（无样本外管线） |
| 12 | 业务层不得 import `lunar_python` / `akshare` / iztro |
| 13 | 所有窗口基于**实际交易日**，不退化回自然日 |
| 14 | 禁止发明"流周"；周是交易日聚合的结果 |

---

## 6. 常用命令

```bash
# 环境
make bootstrap && make migrate && make seed

# 紫微服务（首次必须执行）
make ziwei-install && make ziwei-build && make ziwei-smoke

# 服务
make api            # 后端 8000
make web            # 前端 3000
make web-build      # 生产构建

# 测试
make test                # 后端全部（1003 项）
make test-ziwei          # 紫微引擎 + 因子 + Golden
make test-ziwei-golden   # 仅紫微 Golden（iztro 升级后必跑）
make test-consensus      # 共识 / 分歧 / 时间窗口
make test-leak           # P0 防未来数据泄漏
make test-golden         # 全部 Golden
make test-ui             # Playwright（需 web 已启动）
make check               # typecheck + lint

# 研究
make research-real       # 20 股真实数据研究流水线
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/run_consensus_research.py
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/ziwei_factor_quality_audit.py

# UI 截图
cd apps/web && node scripts/capture-screenshots.mjs --live
```

---

## 7. 踩过的坑（务必先读）

| # | 坑 | 症状 | 处理 |
|---|---|---|---|
| 1 | **Next rewrite 会让 fetch 发送重复的 Content-Type** | `api.post` 同时传了 `content-type` 与 `request()` 的默认头 → 合并成 `"application/json, application/json"` → FastAPI 报 422 `model_attributes_type` | `api.post` **不要**再传 content-type（已修复并注释） |
| 2 | **str-Enum 的 `str()` 陷阱** | `str(VariantMode.FORWARD)` 得到 `"VariantMode.FORWARD"` 而不是 `"forward"` | 一律走 `ex_value()`；紫微因子层用 `_variant_key()` |
| 3 | **iztro 小限层没有 `stars` 字段** | `age.stars == []`，误以为"该宫无煞" | 如实保留为空；因子层走 `_unavailable` |
| 4 | **12 宫 vs 10 天干** | "宫干相邻差恒为 1（含环回）"是**错的** | 正确不变量：`stems[i] == stems[0] + i (mod 10)` |
| 5 | **经验判定带在随机数据上假阳性极高** | "差值 > 半个标准误"→ 11 个组合里 7 个假的 outperform | 改用 Welch t 检验（假阳性回到 ~1.5%） |
| 6 | **面板键必须唯一** | 重复 `(stock_code, as_of)` 会让 Jaccard 虚高 | 有 `CONSENSUS_DUPLICATE_PANEL_KEYS` 警告 |
| 7 | **同一天多次分析会串盘面** | 按 `(code, as_of, engine)` 查 artifact 会让八字分析"看到"多模型分析的紫微盘 | 只认 `analysis_run.chart_artifact_ids` 里登记的 chart_id |
| 8 | **`-0.0` 会制造假差异** | `-min(0/2,1)` → `-0.0`，JSON 里与 `0.0` 不等 | `_zobs` 里 `+ 0.0` 归一 |
| 9 | 紫微盘 JSON 约 17 KB/盘 | sessionStorage 可能超配额 | 失败时只保留内存缓存，不影响功能 |
| 10 | Alembic `alembic.ini` 必须纯 ASCII | 中文 Windows GBK 解码失败 | 不要在里面写中文 |
| 11 | **进程内日历缓存永不失效** | `for_exchange()` 只按交易所缓存，`reset_*()` 全仓库无调用方：改完 CSV 后运行中的 API 一直用旧日历 | provider 按来源文件 `mtime_ns`+大小失效（`src/core/stock/trading_calendar.py`） |
| 12 | **指纹用"区间+行数"识别不出内容变化** | 某日由休市改开市时区间与行数都不变 | 指纹必须对**内容**取哈希 |
| 13 | **`next build` 会摧毁 `next dev` 的产物** | 全站 `/_next/static` 400、页面永远加载中 | 用 `NEXT_DIST_DIR` 分目录 |
| 14 | **WAL 模式下直接复制 sqlite 文件会丢数据** | 副本里查不到刚写入的记录 | 用 `sqlite3` backup API（`output/ui-final/isolate_db.py`） |
| 15 | **`boundingBox()` 是相对视口** | 页面一有滚动，首屏几何结论就偏几十像素 | 几何一律换算为绝对文档坐标 |
| 16 | **Playwright 1440 项目只 match 一个 spec** | "配置里有 1440" ≠ "1440 已逐页验收" | 显式列出需要双视口覆盖的 spec |

---

## 9. 择日关系扫描 / 关系历史研究（bazi-relation-v3，2026-09-23 补充）

> 本节是 Phase 2 之后迭代的补充记录（PR #3），不改变上文 Phase 2 验收结论。

| 项 | 口径 |
|---|---|
| 关系规则版本 | `bazi-relation-v3`（`Settings.relation_rule_version` 为唯一来源，无硬编码） |
| 矩阵 schema | `relation-matrix-v2`：流年/流月/流日 × 股票年/月/日（3×3，股票时柱不参与） |
| 聚合范围 | 仅统计流日行（`aggregate_scope=external_day_row`），Date Scan 与 Relation Study 共用同一 helper `events_for_source_pillar(matrix, "day")` |
| 标准采样时点 | `12:00:00 Asia/Shanghai`（节气交界有 golden case 锁定） |
| 日期指纹 | `date-relation-fingerprint-v1`（与股票矩阵口径解耦，按设计保持 v1） |
| 关系目录 | 22 项，前端唯一来源是 `GET /api/v1/research/relation-catalog` |
| 证据 | `docs/calculation-differences-relation.md` + `docs/relation-v3-evidence/`（000001 全年 CSV 由 `tests/integration/test_relation_v3_evidence.py` 逐日行级复现回归锁定） |

**关键边界（读者最容易误读的地方）**：

* 喜用神仍来自**完整四柱原局**（`yongshen_basis=full_four_pillars`）：矩阵收窄为 3×3 ≠ "股票八字变成三柱"；喜忌部分仍可能间接受出生时辰模型影响。
* 以下模块**保持旧定义，未升级到 v3**：个股八字页的 `relations_with_external()`（4 柱外部关系），以及 `B_*` / `H_*` 因子。不要误以为"全部八字关系因子都已 v3"。
* `REL_*` 因子只表示事件命中次数、无涨跌方向；p-value 对照固定 `random_birth_date`（与页面展示的对照均值/上涨率同一面板）；BH 校正范围 `within_relation_split_horizon`，不代表跨关系类型联合校正。
* 全市场 Relation Study 必须显式 `allow_full_universe=true`，否则 API 返回 422；前端同样要求勾选确认。

---

## 10. 下一步建议

按价值排序：

1. **样本扩容**（不阻塞工程）：20 → 100 → 500 只，最终全 A point-in-time universe。
   当前 `BAZI_POS` 的 Jaccard = 0.945 很可能在更大样本上改善；
2. **出生模型对比研究**：`listing_open` vs `ipo_date` vs `company_foundation`
   三种基准分别回测 —— 这是本项目最大的单一假设；
3. **紫微第二实现源对拍**：Tianji 的许可证核实后可作为 cross-check engine；
4. **样本外验证管线**：解锁 `SUPPORTED_OUT_OF_SAMPLE`（需先写 ADR 并改状态机守卫）；
5. **行业/风格中性化**：区分"术数信息"与"行业暴露"；
6. **时间窗口的时序可视化**：需要先定义"分数的连续时间序列"语义，不能直接画折线；
7. **六爻 / 奇门**：预留接口在 `src/engines/liuyao` / `src/engines/qimen`；
8. **性能**：研究流水线仍同步执行，大规模股票池需引入任务队列。

---

## 11. 最后一句

Phase 2 交付的不是"更准的算命"，而是：

* **可审计**：每个数字都能追溯到盘面 → 因子 → 规则 → 证据；
* **可证伪**：共振、冲突、时间窗口都有独立负对照，且负对照失效会被显式抛出；
* **诚实**：实测结论是 `NO_SIGNAL` / `INVALID_CONTROL`，系统照原样输出。

> **不要为了让结果好看而修改计算。**
