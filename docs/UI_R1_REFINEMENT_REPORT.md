# UI 整改 R1 交付报告（公共组件与三页收口）

- **分支**：`codex/ui-refinement-r1`
- **基线**：`main` @ `0f8489d`（= `fbe97f1` 已验证内容 + 复核任务书文档提交）
- **任务书**：[`docs/UI_REAUDIT_2026-09-21.md`](UI_REAUDIT_2026-09-21.md)
- **视觉参考**：`doc/ui-reference/01_home.png`、`02_integrated_analysis.png`、`03_bazi_detail.png`
- **范围**：仅前端（`apps/web/**`）与 `.gitignore`。**未改动**后端引擎、因子、行情源、研究算法、数据库与公开 API。

---

## 1. 合并与基线核实（任务书 §一、§三）

核实结果与任务书预设**不完全一致**，按事实执行：

| 项目 | 任务书预设 | 实测 |
|---|---|---|
| 当前分支相对 main | 22 个新增提交 | 与 `origin/main` **分叉**（25/27），但 `git diff HEAD origin/main` 为空、tree hash 相同（`05a5c110`） |
| 本地 main 领先远端 | 5 个提交 | 是；该 5 个提交的 patch-id 已全部存在于 `origin/main` |
| UI_REAUDIT 文档 | 尚未纳入 Git | 是（未入库） |

处置：
1. 复核任务书单独提交到当时分支（`ccef56a`，仅该文件，未执行 `git add .`）；
2. `main` 快进到 `origin/main`（`--ff-only` 因历史被 rebase 过而不可用，改以 `git switch -C main origin/main` 使分支指向**已验证**的同一个提交）；
   - 分支指针移动前记录了原 SHA `4d3a22d`（reflog 可恢复），并已确认无内容丢失：`git cherry origin/main main` 全部为 `-`、`git diff --diff-filter=D` 无删除；
3. 文档提交以 cherry-pick 落到 main（`0f8489d`），**合并后 main 的 tree 与被验证提交完全一致**（`c282fd2`）；
4. 正常推送（`fbe97f1..0f8489d`，fast-forward，未强推）。

> 期间 `git restore` 了 3 个被跟踪的 `__pycache__/*.pyc`（测试运行产生的字节码缓存，非源码改动）。

## 2. R1 修改内容

### R1-1 上下文栏：不再用横向滚动藏按钮

`apps/web/components/stock/StockContextBar.tsx`

- 移除 `overflow-x-auto whitespace-nowrap`；改为「可伸缩信息区（`flex-1 min-w-0 flex-wrap`）+ 固定操作区（`shrink-0`）」；
- 主行保留：股票标识 / 上市 / 出生模型 / 出生时刻 / 分析基准 / 数据质量；
  - 出生模型、出生时刻为 `hidden 2xl:flex`：**1672 显示在主行，1440 收进「详情」**；
- 操作区只保留主要操作（切换股票 / 重新计算 / 导出报告），两个 Phase 2 占位按钮移入详情；
- 新增「详情 ▾」按钮（`data-testid="context-details-toggle"`）：展开后给出出生档案**全部原始字段**（出生模型、出生时刻、时区、预测周期、运限假设、开市口径、推导说明），原始值一个不丢；
- 默认高度与既有验收标准对齐（1672 与 1440 均 ≤82px，展开前不撑高）。

### R1-2 公共展示缺陷

| 缺陷 | 处置 |
|---|---|
| 裸 `<strong>` 标签进正文 | `conflicts/page.tsx` 改为 JSX 片段（不再对后端字符串做 HTML 注入式渲染） |
| `none` / `forward` / `VALIDATED` 等内部码进正文 | 新增映射：`conflictLevelLabel`、`variantModeLabel`、`researchStatusLabel`；原始码放 `data-*` 属性与「来源与方法」折叠区 |
| ResearchStatus 中文不全 | `PageState.tsx` 覆盖后端 `status.py` 全部 11 个枚举值；未知状态显式标注「未知状态（码）」 |
| fixture 使用非法状态 `VALIDATED` | 全部改为合法值 `NOT_RUN`，并附「演示数据：未运行研究流水线」说明（不制造"验证通过"印象） |
| JSON 状态对象进正文 | `conflicts` 页改为中文状态 + 原始 JSON 字段进「来源与方法」 |
| 脚本路径 / API 路径进正文 | 新增 `components/shell/SourceMethod.tsx`（原生 `<details>`）；`conflicts`/`timeline`/`evidence`/`backtest`/`factors` 的相关路径与引擎版本移入折叠区 |
| 非支持标的 fixture 页 hydration 不一致 | `ResearchPage.tsx` 改用 `useSearchParams()`（服务端/客户端同源），不再依赖 `window` |
| 演示/真实来源未区分 | 顶栏状态区分「演示数据（固定样本）」与「数据正常」；古籍页标题按模式显示「演示语料固定样本」/「知识库检索返回」；「来源与方法」中标注语料来源与检索接口 |
| 页脚版本不一致（v1.0.0 / v0.2.0） | 新增 `lib/appMeta.ts` 单一来源，`AppShell` 默认值与 `factors` 页统一引用 |
| 时间窗口标题与实际不符 | 标题改为「共 N 个月/周（起始 ~ 结束）」由返回数据驱动；「下一周」按 `as_of` 与返回区间判定为「当前周（含分析基准日）」/「下一周（基准日之后）」 |

### R1-3 三页收口

- **首页**：Hero/搜索（60px 输入框）与能力卡（48px 图标、15px 标题）放大，卡片间距与行高调整；保持 2.1:1 栅格与 48px 宋体标题，不靠整体缩放；页脚由 y=745 下移到 y≈868（内容占首屏 92%）。
- **综合研判**：证据摘要 3 条 + 展开（**按立场轮询取样**，保证利多与利空同时进首屏，而不是只留支持证据）；`DataQualityBadge` 的风险提示前置到卡片头部下方并加 `data-testid="risk-summary"`；历史验证摘要卡头压缩。
- **八字**：时间结构改为「节点 + 贯穿连接线」（大运→流年→流月→流日），说明与运限假设并入卡头；正负因素各显示 3 条 + 展开（因子行与免责声明紧凑化）；四柱表行距与字号微调；古籍证据预览进入首屏。

### 其它

- `.gitignore` 增加 `output/`（本地检查产物 187MB 截图/日志，禁止整体入库）。

## 3. 验证结果

### 后端与迁移（合并前，在被验证提交上）

| 项目 | 结果 |
|---|---|
| `pytest -q` 全量 | **1301 passed**，1 warning，385.9s |
| 迁移 upgrade / downgrade / 二次 upgrade | 全部 rc=0（临时 SQLite 库，非研究库） |
| `alembic check`（schema 漂移） | `No new upgrade operations detected` |
| 新增迁移结构 | `e6b2c8f4a91d`：`stock_master` 增加两个 **nullable** 列（向后兼容，downgrade 可回滚） |

### 前端

| 项目 | 结果 |
|---|---|
| `tsc --noEmit` | 通过（0 error） |
| `next build`（生产） | 通过 |
| Playwright 全量（生产构建，1672×941 + 1440×900） | **91 passed / 0 failed** |
| 其中 R1 新增验收套件 `e2e/r1-refinement.spec.ts` | **17 passed** |
| fixture 页 console.error / pageerror / 真实 API 请求 | **0 / 0 / 0**（首页、综合、八字、分歧、时间窗口、古籍 + 002008 隔离页） |
| 真实模式（连隔离后端） | 正常路径 5 个真实 API、页面正常渲染；`evidence` 接口 404 时**不回退 fixture**（无 `EV-SUP-01`） |

### 首屏几何（1672×941，生产构建实测）

| 指标 | 任务书目标 | 实测 |
|---|---:|---:|
| 综合页 历史摘要标题 y | ≤730 | **693** |
| 综合页 风险摘要 y | ≤820 | **751** |
| 八字 正负因素 y | ≤720 | **678** |
| 八字 古籍证据 y | ≤900 | **867** |
| 上下文栏内部横向溢出 | 无 | 1411/1411（无溢出） |
| 主要按钮默认可见 | 是 | 是（`recalculate` / `switch-stock-btn` 均在容器内） |

## 4. 截图（本地，未入库）

脚本：`output/capture-r1.mjs`（冻结时钟、等待字体、含内部滚动后的下半页）；测量脚本：`output/measure-ui.mjs`。

| 文件 | 内容 |
|---|---|
| `output/r1/01-home-compare-836.png` 等 | 三页「参考图 / 当前实现」同尺寸对照 |
| `output/r1/0X-*-1672.png` | 三页 1672×941 首屏 |
| `output/r1/0X-*-1672-lower.png` | 三页滚动后的下半页 |
| `output/r1/0X-*-1440.png` | 三页 1440×900 |
| `output/r1/11-002008-huangli-fixture.png` | 非支持标的演示隔离页 |
| `output/r1/12-overview-live-isolated-api.png` | 真实模式（隔离后端） |
| `output/r1/13-evidence-partial-failure.png` | 真实模式部分失败（接口 404） |

## 5. 尚未完成的差距

1. **后七页布局未整改**（R2：紫微、因子字典、模型分歧、古籍证据；R3：历史验证、黄历、时间窗口）——本轮按任务书要求只做公共组件与前三页收口。
2. **紫微右侧观察栏、三方四正**未实现（属 R2 结构改动）。
3. **模型分歧页仅有"无冲突"fixture**，缺少显式"有冲突/不可用"演示场景（属 R2）。
4. **上下文栏交互（切换出生模型/预测周期）仍是 Phase 2 占位**，本轮只保证入口不被裁切并明确标注未实现。
5. **1440×900 下风险摘要 y=796**：任务书的几何目标以 1672×941 为默认验收视口，1440 下更早换行导致略低，仍满足 820 门限（796 ≤ 820）；未做逐视口的独立目标。
6. **CardBody 统一迁移未铺开**（任务书 §2 末条）：本轮只统一了被触及的卡片，未做全站 padding 迁移。

## 6. 未验证 / 需人工确认

- 未做像素级视觉回归基线（任务书 §4 明确：人工批准后才可作为基线）；本轮对照图为人工目视用。
- 紫微引擎依赖 `services/ziwei-service`（本机已构建），未在本轮做紫微页的专项视觉验收。
- 真实模式的数值正确性依赖隔离后端与 synthetic 行情，**不代表生产研究结论**。
