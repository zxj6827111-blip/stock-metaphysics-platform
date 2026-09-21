# UI 最终收尾 · 发布就绪检查

- **检查对象**：`codex/ui-final-polish-acceptance`（基线 `e2ef2dd`）
- **检查范围**：**本项目已有或明确指定的环境**。任务书**未指定部署目标**，
  因此本文件不选择部署目标，只完成"本地生产验收 + 发布前配置核查"。
- **结论**：本地生产构建与运行**通过**；目标环境相关项标注为"部署目标未指定"。

---

## 1. 生产配置与环境变量

| 变量 | 默认值 | 生产注意 | 状态 |
|---|---|---|---|
| `SMP_API_BASE` | `http://127.0.0.1:8000` | **构建期固化**（`next.config.mjs` 的 `rewrites`）；改它必须重建，运行时改无效 | 已验证（本轮即通过重建切换后端） |
| `NEXT_DIST_DIR` | `.next` | 本轮新增：验收构建写 `.next-e2e`，避免与 `next dev` 互毁产物 | 已验证 |
| `NEXT_PUBLIC_SMP_API_BASE` | 未设置 → 走 `/api/backend` 反代 | 若要前端直连后端（跨域），需设置并重建，同时把前端源加入后端 CORS | 已核查 |
| `SMP_DATA_DIR` | `<repo>/data` | 决定 `smp.sqlite3` 位置；生产应指向持久卷 | 已核查 |
| `SMP_DATABASE_URL` | 空 → `sqlite:///<data_dir>/smp.sqlite3` | 若要换 PostgreSQL 需同步 Alembic 迁移 | 已核查 |
| `SMP_MARKET_PROVIDER` | `akshare` | **生产必须显式设置**：`offline`（`data/import/` 离线真实快照）或 `vendor_parquet`（供应商全市场仓库）；本环境 AKShare 不可达 | **重要**：默认值在本环境不可用 |
| `SMP_ALLOW_SYNTHETIC_MARKET_FALLBACK` | `true` | **生产建议设为 false**：否则网络/源不可达时会静默降级为合成行情（响应里会标注 `NO_REAL_DATA`，但页面仍有数） | **重要** |
| `SMP_VENDOR_DATA_DIR` / `SMP_VENDOR_ROOT` | 默认 `data/vendor` / `data/vendor_shipped` | vendor_parquet 通道的仓库路径；仓库缺失时**显式报错**而不是静默回退 | 已验证 |
| `SMP_ZIWEI_SERVICE_URL` | 空 → Node 子进程通道 | 生产常驻服务时填 `http://127.0.0.1:8100`；两者都需要 `services/ziwei-service` 已构建 | 已核查 |
| `SMP_CORS_ORIGINS` | `http://localhost:3000` / `127.0.0.1:3000` / `localhost:1672` | 前端经 Next 反代时**不涉及浏览器跨域**；若前端直连需补条目 | 已核查 |
| `SMP_LLM_*` | 未设置 | 未配置时 LLM 解释功能不可用；本平台**不依赖 LLM 出结果**（铁律 1/2） | 已核查 |

## 2. 服务地址与健康检查

| 项 | 值 | 状态 |
|---|---|---|
| API 健康检查 | `GET /api/v1/system/health` → `{"status":"ok",...}` | 已验证（8101） |
| 引擎状态 | `GET /api/v1/system/engines` | 已核查 |
| 数据质量 | `GET /api/v1/system/data-quality` | 已核查 |
| 交易日历三层覆盖 | `GET /api/v1/system/trading-calendar?exchange=SSE` | 已验证（含 `verified` 与来源 URL） |
| 紫微服务 | `services/ziwei-service`（Node + iztro 2.6.1），`npm run build` → `dist/`，`--smoke` 自检 | 已核查（隔离实例下紫微盘正常产出 12 宫） |
| 前端反代 | `/api/backend/:path*` → `SMP_API_BASE/:path*` | 已验证（200） |

## 3. 数据库、数据卷与缓存目录

| 项 | 说明 | 状态 |
|---|---|---|
| 迁移 | `alembic upgrade head`（`make migrate`）；启动时会检查 schema 就绪 | 已核查 |
| 共享研究库 | `data/smp.sqlite3`（约 650 MB，含 184 万条日线、6,104 只标的、56 个研究实验） | **生产不可随意重跑导入**：`stock_master` 的清空重抽样会改变研究宇宙（见项目记忆与 Phase 3 约束） |
| 数据库副本 | 验收用 `sqlite3 backup API` 生成一致快照（WAL 模式下直接复制文件会丢未 checkpoint 的内容） | 已验证（`output/ui-final/isolate_db.py`） |
| 缓存目录 | 进程内 LRU（`TIMELINE_CACHE` / `HUANGLI_CACHE`，上限 200 条）；无外部缓存依赖 | 已核查；缓存键含引擎/口径/日历内容指纹（本轮修） |
| 日历文件 | `data/import/calendar/{SSE,SZSE}.csv`（实测，只增不删）+ `published/{SSE,SZSE}.csv` + `_meta.json` | 已验证；**运行实例会按文件 mtime 自动重载**（本轮修） |
| 供应商数据 | `data/vendor/*.parquet`（全市场日线/复权/估值）+ `data/vendor_shipped/delisted_bars.parquet`（退市股） | 已验证 |

## 4. fixture 是否会误入正常运行

| 检查 | 结论 |
|---|---|
| 启用条件 | 只有 URL 显式带 `?fixture=ui-reference` 才启用（`lib/fixture.ts` 的 `isFixtureActive()`） |
| 演示模式是否访问真实后端 | **否**：十页初始加载与交互 0 个 `/api/` 请求（`manifest.fixture_api_calls` 为空，既有 spec 亦逐页断言） |
| 演示数据是否会被当成真实结论 | 顶部状态栏显示「演示数据（固定样本）」；导出文件逐份标注「【演示数据】」 |
| 非支持标的 | 稳定唯一的错误卡（含进入真实模式的链接），不会静默回退 |
| 正常模式失败是否回退 fixture | **否**：真实模式失败走错误态 + 重试，不回退演示数据 |
| fixture 数据来源 | 由 `scripts/capture_ui_fixtures.py` 从真实来源冻结（真实古籍检索结果、真实因子注册表、真实实验），冻不了的给空态 |

## 5. 生产日志与错误反馈

| 项 | 结论 |
|---|---|
| API 日志 | uvicorn access log + `smp.api` 结构化行（启动、schema、分析 id） |
| 前端错误 | 分区错误态（`SectionState`）+ 页级错误（`PageError`）+ 导出失败反馈；不吞错 |
| 十页 console.error / pageerror | **0**（生产构建下实测） |
| 后端失败请求 | 真实模式验收中 0 条 4xx/5xx（`real-mode-live.spec.ts` 断言） |

## 6. 发布步骤（本地已验证部分）

```bash
# 0) 前置：Python 3.12 venv + 前端依赖
make bootstrap

# 1) 数据库
make migrate
make seed                     # 古籍语料 + 交易所时段配置

# 2) 行情通道（本环境 AKShare 不可达，必须显式指定）
export SMP_MARKET_PROVIDER=vendor_parquet     # 或 offline（data/import/ 离线真实快照）
export SMP_ALLOW_SYNTHETIC_MARKET_FALLBACK=false

# 3) 紫微服务
make ziwei-install && make ziwei-build && make ziwei-smoke
make ziwei-serve              # 常驻 127.0.0.1:8100；或设 SMP_ZIWEI_SERVICE_URL

# 4) 后端
make api                      # 127.0.0.1:8000

# 5) 前端生产构建（构建期固化 SMP_API_BASE！）
cd apps/web
SMP_API_BASE=http://127.0.0.1:8000 npm run build
npm run start                 # 127.0.0.1:3000
```

> **两条容易踩的坑**（本项目已实测）：
> 1. `SMP_API_BASE` 是**构建期**写进 rewrites 的，运行时改环境变量无效，必须重建；
> 2. `next build` 与 `next dev` 共用 `.next` 会互相摧毁产物 —— 需要并存时用 `NEXT_DIST_DIR` 分开。

## 7. 验证步骤（本地已完成）

```bash
# 后端
PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q                 # 1396 passed
PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/test_no_future_data_access.py -q
PYTHONUTF8=1 .venv/Scripts/python.exe -m ruff check src apps tests # 23 项，与基线一致

# 前端
cd apps/web && npx tsc --noEmit                                    # 0 error
SMP_API_BASE=<api> NEXT_DIST_DIR=.next-e2e npx next build          # 成功
SMP_WEB_BASE=http://127.0.0.1:3111 SMP_E2E_LIVE_API=1 npx playwright test

# 真实数据验收（隔离实例）
PYTHONUTF8=1 .venv/Scripts/python.exe output/ui-final/real_acceptance.py http://127.0.0.1:8101

# 候选截图与 manifest
node output/ui-final/capture-final.mjs http://127.0.0.1:3111 output/ui-final/candidate --label=candidate-r4
```

## 8. 回滚步骤

1. **代码回滚**：本分支未合并 main。回滚 = 不合并 / `git checkout main`（main 仍为 `0f8489d`，未被本轮触碰）。
2. **前端回滚**：保留上一版构建产物，切回后用 `NEXT_DIST_DIR` 指向旧目录重启即可（无需重新构建）。
3. **数据回滚**：本轮**未修改**共享数据库内容（全部验收走副本）；日历文件为**只增不删**的增量更新，
   如需回退可用 git 恢复 `data/import/calendar/**` 后重启 API（provider 会按 mtime 重新加载）。
4. **配置回滚**：本轮只新增 `NEXT_DIST_DIR` 一个可选项，未改任何默认值语义。

## 9. 部署目标：未指定

任务书未指定部署目标，且项目文档中提到过多个候选环境。**本轮不自行选择目标**，因此以下均**未执行**：

- 目标主机与容器编排落地（`docker-compose.yml` 与 `deploy/` 仅做静态核查）
- 反向代理 / TLS / 域名
- 数据卷迁移与数据库备份策略
- 生产环境变量注入与密钥管理

要推进部署，需要先明确目标环境，再按 §6 的步骤执行，并在该环境重跑 §7 的验证。
