# NOTE-001 · 开发 / 测试 / CI 现场手册

- **Status**: Current Operational Note
- **As-of**: 2026-09-23（最后一次对照代码与 CI 实测核实）
- **核实方式**: 读 `Makefile` / `pyproject.toml` / `.github/workflows/v51.yml` / 两个 `package.json` /
  `docker-compose.yml`，并在本机 `.venv` 实跑 `pytest --collect-only`
- **关联**: [`AGENTS.md`](../../AGENTS.md) §10 §12 · 新增 §15–§24 · [NOTE-002](NOTE-002-current-project-state-2026-09-23.md)

---

## 1. 环境事实（不是计划，是本机与 CI 的当前值）

| 项 | 值 | 来源 |
|---|---|---|
| Python 声明下界 | `>=3.11` | `pyproject.toml` `requires-python` |
| 实际开发/CI 版本 | **3.12** | `Makefile bootstrap` 用 `uv venv --python 3.12`；CI `python-version: "3.12"` |
| 本机 `.venv` | `.venv/Scripts/python.exe` = **Python 3.12.14** | 实跑确认 |
| ruff 目标版本 | `py311`（`line-length 110`） | `pyproject.toml [tool.ruff]` |
| Node（CI） | **20** | `setup-node@v4 node-version: "20"` |
| Node（本机） | v24.14.0 | 实跑确认；README 要求 `>=20` |
| 前端 | Next `^15.5.4` + React `^19.1.0` + echarts `^6.1.0` + zustand `^5.0.8` | `apps/web/package.json` |
| 紫微生产 | `iztro` **2.6.1**（精确锁） | `services/ziwei-service/package.json` |
| 紫微第二源 | `fortel-ziweidoushu` **1.3.4**，`package-lock.json` 按约定**不入库** | `services/ziwei-reference-service/package.json` + CI 注释 |

**Windows 强制项**：所有 Python 命令前 `PYTHONUTF8=1`。中文 Windows 默认 GBK，会让
`configparser` / 中文文件读取失败（`Makefile` 已 `export PYTHONUTF8 := 1`）。

**本机没有 `make`**：Git Bash 里 `command -v make` 为空。`AGENTS.md` §10 与各文档写的
`make test` / `make test-leak` 等，在本机必须展开成 §2 的等价命令。命令语法另注意：
用户默认 shell 是 PowerShell，`VAR=value cmd` 前缀写法在 PowerShell 下不成立（须 `$env:VAR=`）。

## 2. 后端：可直接复制的命令

```bash
# 依赖安装（首次或 pyproject 变更后）
uv venv --python 3.12 .venv
uv pip install --python .venv -e ".[dev]"

# 库与种子
PYTHONUTF8=1 .venv/Scripts/python.exe -m alembic upgrade head
PYTHONUTF8=1 .venv/Scripts/python.exe -m src.cli seed
PYTHONUTF8=1 .venv/Scripts/python.exe -m src.cli doctor      # 环境自检

# 全量后端测试（等价 make test）
PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q
# CI 的 backend-core job（排除需要已构建 node 服务的用例）
PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not ziwei_live"
# 只跑 P0 防未来数据泄漏（等价 make test-leak）
PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/test_no_future_data_access.py -v
# 只跑 Golden Cases（等价 make test-golden）
PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -m golden -v
# 紫微三件套（等价 make test-ziwei）
PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest \
  tests/engines/test_ziwei_engine.py tests/factors/test_ziwei_factors.py \
  tests/golden/test_ziwei_golden.py tests/golden/test_ziwei_cross_engine.py -v
# 共识 / 时间窗口
PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/consensus tests/timeline -v
# lint
PYTHONUTF8=1 .venv/Scripts/python.exe -m ruff check src apps tests
# 一键正式验收（含 UI 与因子审计；--skip-ui --skip-audit 为快速循环）
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/run_acceptance.py
```

**测试规模（As-of 2026-09-23，commit `81b6fbe`）**：`pytest --collect-only` 收集 **1816** 项，
其中 **28** 项带 `ziwei_live` 标记（被 CI backend-core 排除，改由 ziwei job 带真实服务跑）。
`HANDOFF_FINAL` 里"1003 pytest / 44 Playwright"是 Phase 2 交付时的历史数字，**不要引用**。

**markers（`pyproject.toml`）**：`golden` / `slow` / `network` / `integration` / `acceptance` /
`ziwei_live`。pytest 配置为 `--strict-markers --strict-config`，新标记必须登记。

## 3. 前端与紫微服务

```bash
cd apps/web
npm ci                    # 有 package-lock.json，CI 用 npm ci
npm run typecheck         # tsc --noEmit
npm run build             # next build
npm run dev               # 默认 127.0.0.1:3000
npx playwright test                          # 全部 e2e（需 web 已启动）
npx playwright test e2e/v51-regression.spec.ts e2e/date-scan-v3.spec.ts \
  --project=reference-1672x941 --workers=1   # CI 实际跑的两条
npm run visual:diff       # node scripts/visual-diff.mjs，十页像素门禁

cd services/ziwei-service
npm ci && npm run build && node dist/cli.js --smoke   # 等价 ziwei-smoke
```

e2e 现状：`apps/web/e2e/` 17 个 spec，2 个 project（`reference-1672x941` 默认，
`desktop-1440x900` 只匹配 `layout.spec.ts` + `viewport-1440-pages.spec.ts`）。
CI 的 e2e 用**确定性种子库**（`scripts/ci_seed_date_scan.py` + `SMP_E2E_SEEDED=1`），
不访问真实行情网络；端口固定 8101(api) / 3111(web)，且**显式 readiness 轮询**，
不允许用 `--retries` 掩盖竞态。

紫微链路必须同时验证：Node 构建 → 通道真实可用 → Python adapter → Golden → 跨引擎。
CI 在跑测试**之前**先用一段 Python 断言 `SubprocessZiweiTransport().available()` 与
`reference_status().available`，**不允许 silent skip 变成假绿**。

Docker：`ziwei`（容器网络内 8100，不对外）+ `api`（8000）+ `web`（3000）。
容器内没有 node，所以容器部署**必须**起 ziwei 服务（`SMP_ZIWEI_SERVICE_URL=http://ziwei:8100`）。

## 4. CI 现状与判定口径

唯一 workflow：[`.github/workflows/v51.yml`](../../.github/workflows/v51.yml)（名为 `V5.1 acceptance`）。
触发：`pull_request`、以及对 `main` 与 `codex/ui-final-polish-acceptance` 的 `push`。
Jobs（当前 5 个）：`backend core (python)`、`ziwei engine + golden (node services)`、
`frontend-typecheck`、`frontend-build`、`frontend e2e (seeded date-scan)`。

- **不要**按 README / PR 描述 / 记忆判断 CI，必须看当前 commit 的 run 与 job conclusion；
- 必须区分 `local PASS` / `CI PASS` / `CI SKIPPED` / `CI NOT RUN` / `CI FAILURE`；
- `visual-regression` job 已于 2026-09-23 从该 workflow 移除（**推迟，不是通过**），
  细节与真实 FAIL 数据见 [NOTE-002](NOTE-002-current-project-state-2026-09-23.md)。

## 5. 会咬人的坑（本轮/近期实测）

1. **`.pyc` 被 git 跟踪**：仓库里有 94 个 `__pycache__/*.pyc` 在版本控制中。
   任何一次 `pytest` 都可能把它们改脏，`git status` 于是出现与本任务无关的 ` M` 条目。
   收尾前跑 `git diff --name-only | grep __pycache__`，把**这些**路径 restore 掉再汇报。
2. **`.next` 会被 dev / start / build 互相覆盖**：正在服务的页面可能因一次 build 全站 500
   （接口仍 200）。删 `.next` 会弄坏正在跑的 dev。
3. **改 `SMP_API_BASE` 必须重新构建前端**：Next 的 rewrites 在构建期固化，运行时改无效。
4. **AKShare 不可达**：本仓库真实行情离线通道是腾讯 hfq / vendor Parquet（ADR-0012 与 Phase 4 通道），
   `synthetic` 只用于联调与降级测试，且必须带 `is_degraded`（见 ADR-0013 §5）。
5. **universe 不能重跑导入脚本**：`v2-phase3a` / `v4-full` 的重抽样会清空既有面板（见 ADR-0012）。
6. **`git status` 会在会话中途变化**：本仓库存在并行会话在同一分支上提交/强推的事实，
   开工前与收尾前各记一次 `HEAD`，不要用会话开头的快照描述当前状态。

## 6. 版本与提交约定

改了引擎/规则必须提升 `engine_version` / `rule_version` / `birth_profile_version` /
`config_version` / `knowledge_version` / `market_data_version`（`AGENTS.md` §11 的表）。
提交说明用 `git commit -F <file>` 传中文，避免 shell 引号与编码问题；
临时笔记文件不要用 `.md` / `.txt` 落在仓库根目录。
数据库字段变更必须走 Alembic（`migrations/versions/` 当前 4 个 revision），
**禁止只改 ORM 不改 migration**。
