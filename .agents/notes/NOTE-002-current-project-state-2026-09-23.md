# NOTE-002 · 阶段事实快照（2026-09-23）

- **Status**: Current Operational Note（阶段事实，**不是**永久架构规则；过期请新开一篇）
- **As-of**: 2026-09-23
- **核实方式**: 本地 `git` / `gh` 实查 + 读 `docs/` 现有报告；未重跑视觉回归与完整 CI
- **关联**: [NOTE-001](NOTE-001-development-test-and-ci.md) · [ADR-0013](../../docs/ADR/ADR-0013-research-validity-boundary.md) · [`AGENTS.md`](../../AGENTS.md) §15 §16

---

## 1. 交付坐标（实查值）

| 项 | 值 | 怎么核实的 |
|---|---|---|
| 远端 | `github.com/zxj6827111-blip/stock-metaphysics-platform`（**public**） | `git remote -v` |
| 分支 | `codex/ui-final-polish-acceptance` | `git branch --show-current` |
| HEAD | **`81b6fbe`** `ci(visual): 将 visual-regression 移出 V5.1 acceptance 的 CI scope` | `git rev-parse HEAD` |
| PR | **#3 OPEN**，head `81b6fbe`，base `main`，`mergeable = MERGEABLE`，30 commits | `gh pr view 3` |
| 本地 vs 远端 | 0 ahead / 0 behind | `git rev-list --count` |

> **本会话内 HEAD 移动过**：会话开始时是 `7404781`，期间存在并行会话在同一分支上提交并推送
> （`7404781 → 81b6fbe`）。任何人引用本快照前先 `git rev-parse HEAD` 复核；
> 不要对同名分支做 `reset` / 删分支 / 强推。

## 2. CI 现状（必须与"视觉回归"分开读）

当前 HEAD `81b6fbe` 的两个 run（push `35866014100`、pull_request `35866022059`，2026-09-23T13:17Z）
**5 个 job 全部 pass**：`backend core (python)` / `ziwei engine + golden (node services)` /
`frontend-typecheck` / `frontend-build` / `frontend e2e (seeded date-scan)`。

**这不代表视觉问题被解决。** 前一个 HEAD `7404781` 的两个 run（08:25Z）里
`visual-regression` 是 **FAILURE**，其余 5 个 job pass；`81b6fbe` 的做法是把这个 job 从
workflow 中**移出**（commit 说明原话：**"非通过，为推迟"**）。

本项目已就此事做出的决定（属于**阶段处置**，因此写在这里而不是 `AGENTS.md` 永久规则）：

> Visual Regression 单独作为后续视觉专项处理，**不得**因为独立视觉基线失败，
> 把一个与视觉无关、功能测试已通过的任务扩大成视觉整改任务；
> 但也**不得**删除、伪造或隐藏真实 FAIL 数据与门禁工具链。

真值现状：`docs/UI_VISUAL_PARITY_V5.md` 记录的**十页差异率 39.95% – 57.15%，全部 FAIL**
（本轮**未重新测量**，只引用该文档）。门禁工具链完整保留：`doc/ui-reference/*.png`、
`apps/web/scripts/visual-diff.mjs`、`apps/web/e2e/visual-reference.spec.ts`。
计划是在独立的 `ui-visual-parity` 分支上把它恢复为独立 CI job 并作为该分支的通过前提。

**结论边界**：PR #3 目前"CI 全绿"的含义是**功能范围全绿**，不是"UI 视觉可发布"。
该文档自身结论行仍是 `FAIL / 不允许 merge PR #3`（就视觉而言）。

## 3. 研究结论现状（不得因功能开发被改写）

`docs/PHASE3_RESEARCH_REPORT.md`：

- **`SUPPORTED_OUT_OF_SAMPLE = 0`** —— 42 个正式 gate 实验，族内 BH-FDR 通过 **0** 个，
  Bonferroni 通过 **0** 个；
- 多引擎共振：**`MULTI_ENGINE_NO_SIGNAL`**；
- 表述：术数因子（八字/紫微/黄历及共振）在该样本与协议下**没有显示可复现的样本外信息量**。

Phase 3/4 的阶段性限制（校准后仍偏正、前向记账需长周期、退市股敏感性等）见
`docs/phase3-model-limitations.md`、`docs/phase3d-oos-results.md`、`docs/PHASE3_RESEARCH_REPORT.md`。
**这些都是已发布的阶段性事实**：改进算法或 UI 之后必须重跑才能更新，
不允许因为"现在功能更全了"就顺手改掉旧结论（ADR-0013 §4）。

## 4. 已在 2026-09-23 前后关闭的缺口（勿再当作待办）

`docs/FUNCTIONAL_AUDIT_2026-09-22.md` 是 09-22 的时点审计，正文里多条已被 **relation v3** 关闭
（该文档顶部已加"后续状态"说明）：

| 旧缺口 | 现在的真实链路（已核对存在） |
|---|---|
| "日期 → 全市场入口不存在" | `POST /api/v1/research/date-scan`（`apps/api/routers/research.py:111`）+ `src/core/orchestration/date_relation_scan.py` + 前端 `apps/web/app/research/date-scan/page.tsx` |
| "无关系指纹" | `GET /api/v1/research/date-relations/{target_date}`（`date-relation-fingerprint-v1`） |
| 外部路径缺半合/三会/组合型关系 | `src/core/relations/date_relation.py` 的 3×3 日期关系矩阵（目录 22 项，含伏吟/反吟/天合地合/天克地冲），`GET /api/v1/research/relation-catalog` |
| 只有引擎级回测 | `POST /api/v1/research/relation-study`（REL_* 关系级事件研究 + 负对照） |

## 5. 仍然成立的已知缺口（**只报告，本轮不修**）

| # | 缺口 | 证据（本轮实查） | 风险 |
|---|---|---|---|
| G1 | 出生档案选择不确定：`version=None` 时按 `updated_at desc` 取第一条，没有 canonical 版本常量 | `src/core/orchestration/analysis_service.py:1142-1152` | **高**：不同股票可能落到不同出生模型，而时柱会变（09:30 vs 15:00 时柱不同 → 喜用神从木变土） |
| G2 | `relations_with_external()`（个股八字页的 4 柱外部关系）**没有任何测试**，且**未升级**到 v3 口径 | 全仓 `tests/` 内 0 命中该符号；函数在 `src/engines/bazi/rules.py` | 中：最常被 UI 展示的关系路径无回归保护；容易被误读成"八字关系因子已全部换代" |
| G3 | 历法 `_safe(..., "甲子")` 静默兜底：异常时返回一个**看起来合法**的干支 | `src/engines/calendar/calendar_engine.py:121-122` | **高**：产出错误盘面而不报错，违反 §2.4 不可用语义的精神 |
| G4 | `direction_from_score` 的 58 / 42 阈值仍是硬编码，未经回测背书 | `src/core/orchestration/analysis_service.py:103-109` | 高：Phase 3 已证 OOS 无支持，阈值不应被读成"预测能力" |
| G5 | 标签体系只有收益 + 最大回撤，缺波动/趋势/反转/成交量/极端事件维度 | `src/research/labels/`（`forward_returns` / `horizon_returns` / `panel` / `store`）目录内无相关字段 | 中：关系类特征只能验证"涨跌"，无法验证"扰动/协同"语义 |
| G6 | `README.md` 已明显滞后于代码 | 仍写"Phase 1 不实现紫微"、39 个端点、368 项测试、`docs/ADR/` "11 篇" | 中：本轮所有"照 README 就错"的判断都源于此；`AGENTS.md` §15 规定以代码为准 |
| G7 | 94 个 `__pycache__/*.pyc` 被 git 跟踪 | `git ls-files "*.pyc" \| wc -l` = 94 | 低但持续：任何测试运行都会污染工作树，评审噪音大 |
| G8 | `docs/ADR/README.md` 索引此前缺 0012 行（本轮登记 0013 时顺手补齐） | 该表原止于 0011，而 `ADR-0012-*.md` 已提交 | 低 |

## 6. 本轮（2026-09-23 规则初始化）做了什么、没做什么

做了：`AGENTS.md` 追加 §15–§24（不重编号）；新建 `.agents/notes/`（README + NOTE-001 + NOTE-002）；
新建 `docs/ADR/ADR-0013-research-validity-boundary.md` 并在 `docs/ADR/README.md` 登记。

没做（**明确的范围决定**）：

* 没有采纳"在 `.agents/notes/` 下另建 `ADR-001…003`"的写法——会与既有 `docs/ADR/ADR-0001…0012`
  形成两套编号；任务书要求的三个主题里，时间隔离与引擎隔离**已有** ADR-0004 / 0001 / 0009 / 0011，
  只有"研究有效性边界"缺正式决策，故新增 ADR-0013；
* 没有引入 Note 结构门禁脚本（`check_notes.mjs`），避免与规则文档混在同一次提交；
* 没有 commit / push / merge / deploy；
* 没有修改任何业务代码、测试、CI、依赖、数据库、UI；
* 未修 G1–G7，只登记。
