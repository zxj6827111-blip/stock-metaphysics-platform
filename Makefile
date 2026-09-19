# 股票玄学多模型研究平台 · Phase 1 统一命令入口
#
# Windows 用户请在 Git Bash 下运行；所有 Python 命令都带 PYTHONUTF8=1，
# 避免中文 Windows 上 configparser / 文件读取的 GBK 解码问题。

PY ?= .venv/Scripts/python.exe
WEB := apps/web
export PYTHONUTF8 := 1

.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# 环境
# ---------------------------------------------------------------------------
.PHONY: bootstrap
bootstrap: ## 创建 Python 3.12 虚拟环境并安装后端 + 前端依赖
	uv venv --python 3.12 .venv
	uv pip install --python $(PY) -e ".[dev]"
	cd $(WEB) && npm install --no-fund --no-audit
	@echo "完成。下一步：make migrate && make seed"

.PHONY: migrate
migrate: ## 执行数据库 migration（Alembic）
	$(PY) -m alembic upgrade head

.PHONY: migration
migration: ## 生成新的 migration（用法：make migration m="add xxx"）
	$(PY) -m alembic revision --autogenerate -m "$(m)"

.PHONY: seed
seed: ## 写入种子数据（古籍语料 + 交易所时段配置）
	$(PY) -m src.cli seed

# ---------------------------------------------------------------------------
# 开发
# ---------------------------------------------------------------------------
.PHONY: api
api: ## 启动后端 API（http://127.0.0.1:8000，文档 /docs）
	$(PY) -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --reload

.PHONY: web
web: ## 启动前端（http://127.0.0.1:3000）
	cd $(WEB) && npm run dev

.PHONY: web-build
web-build: ## 构建前端生产包
	cd $(WEB) && npm run build

# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------
.PHONY: test
test: ## 运行全部后端测试
	$(PY) -m pytest -q

.PHONY: test-verbose
test-verbose: ## 运行全部后端测试（详细）
	$(PY) -m pytest -v

.PHONY: test-golden
test-golden: ## 只运行 Golden Cases
	$(PY) -m pytest -m golden -v

.PHONY: test-leak
test-leak: ## 只运行防未来数据泄漏测试（P0）
	$(PY) -m pytest tests/test_no_future_data_access.py -v

.PHONY: test-cov
test-cov: ## 运行测试并生成覆盖率报告
	$(PY) -m pytest --cov=src --cov=apps --cov-report=term-missing --cov-report=html

.PHONY: test-ui
test-ui: ## 运行 Playwright UI 端到端测试（需要 web 已启动）
	cd $(WEB) && npx playwright test

.PHONY: test-ui-install
test-ui-install: ## 安装 Playwright 浏览器
	cd $(WEB) && npx playwright install chromium

.PHONY: test-all
test-all: test test-ui ## 运行全部测试（后端 + UI）

.PHONY: test-ziwei
test-ziwei: ## 只运行紫微引擎 + 紫微因子 + 紫微 Golden Cases
	$(PY) -m pytest tests/engines/test_ziwei_engine.py tests/factors/test_ziwei_factors.py tests/golden/test_ziwei_golden.py -v

.PHONY: test-ziwei-golden
test-ziwei-golden: ## 只运行紫微 Golden Cases（iztro 升级后必跑）
	$(PY) -m pytest tests/golden/test_ziwei_golden.py -v

.PHONY: test-consensus
test-consensus: ## 只运行 Opinion / Consensus / Conflict / 时间窗口测试
	$(PY) -m pytest tests/consensus tests/timeline -v

# ---------------------------------------------------------------------------
# 紫微服务（Node.js + iztro）
# ---------------------------------------------------------------------------
.PHONY: ziwei-install
ziwei-install: ## 安装紫微服务依赖（services/ziwei-service）
	cd services/ziwei-service && npm install --no-fund --no-audit

.PHONY: ziwei-build
ziwei-build: ## 构建紫微服务（tsc → dist/）
	cd services/ziwei-service && npm run build

.PHONY: ziwei-smoke
ziwei-smoke: ## 紫微服务自检（单次排盘）
	cd services/ziwei-service && node dist/cli.js --smoke

.PHONY: ziwei-serve
ziwei-serve: ## 启动紫微 HTTP 服务（默认 127.0.0.1:8100）
	cd services/ziwei-service && node dist/server.js

.PHONY: acceptance
acceptance: ## Phase 1 正式一键验收（编译/全量测试/泄漏/Golden/事件集区分度/负对照/隔离/lint/审计/UI）
	PYTHONUTF8=1 $(PY) scripts/run_acceptance.py

.PHONY: acceptance-core
acceptance-core: ## 快速验收循环（跳过 UI 与因子审计）
	PYTHONUTF8=1 $(PY) scripts/run_acceptance.py --skip-ui --skip-audit

.PHONY: import-market
import-market: ## 校验并导入 data/import/ 真实行情快照到数据库
	$(PY) -m src.cli import-market

.PHONY: research-real
research-real: ## 在真实导入快照上跑 20 股研究流水线（真实数据 smoke research）
	$(PY) scripts/run_real_research.py

# ---------------------------------------------------------------------------
# 代码质量
# ---------------------------------------------------------------------------
.PHONY: typecheck
typecheck: ## 前端 TypeScript 类型检查
	cd $(WEB) && npx tsc --noEmit

.PHONY: lint
lint: ## Python lint（ruff）
	$(PY) -m ruff check src apps tests

.PHONY: check
check: typecheck lint ## 类型检查 + lint

# ---------------------------------------------------------------------------
# UI 复刻验收
# ---------------------------------------------------------------------------
.PHONY: shots
shots: ## 生成 1672x941 三页截图并与参考图对比（web 需已启动）
	cd $(WEB) && node scripts/capture-screenshots.mjs

.PHONY: shots-live
shots-live: ## 用真实 API 数据截图（api + web 均需已启动）
	cd $(WEB) && node scripts/capture-screenshots.mjs --live

# ---------------------------------------------------------------------------
# 研究
# ---------------------------------------------------------------------------
.PHONY: research
research: ## 运行研究流水线（事件研究 + 四类负对照）
	$(PY) -m src.cli research

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
.PHONY: docker-up
docker-up: ## docker compose 启动 api + web
	docker compose up --build

.PHONY: docker-down
docker-down: ## 停止并移除容器
	docker compose down

.PHONY: docker-test
docker-test: ## 在容器内运行测试
	docker compose run --rm api python -m pytest -q

# ---------------------------------------------------------------------------
.PHONY: clean
clean: ## 清理构建产物（保留 data/）
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
	rm -rf $(WEB)/.next $(WEB)/test-results $(WEB)/playwright-report
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

.PHONY: help
help: ## 显示所有可用命令
	@echo "股票玄学多模型研究平台 · Phase 1"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
