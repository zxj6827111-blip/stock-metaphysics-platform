# THIRD_PARTY.md · 第三方依赖与许可证清单

> 本文件记录全部第三方依赖、**锁定版本**、用途、接入方式与许可证状态。
>
> **规则（AGENTS.md §11）**：第三方代码必须通过 Adapter 接入；
> 业务层不得直接 `import`；所有依赖必须锁版本。

---

## 1. 术数与数据核心依赖（最重要）

### 1.1 lunar-python（历法与黄历）

| 项 | 值 |
|---|---|
| 用途 | 公历/农历、干支、节气、纳音、建除十二值、十二神、黄黑道、冲煞、彭祖百忌、吉神方位 |
| 仓库 | https://github.com/6tail/lunar-python |
| 锁定版本 | **1.4.8**（PyPI wheel） |
| 接入方式 | `CalendarEngine` Adapter（`src/engines/calendar/calendar_engine.py`）<br>`BaziEngine` 仅用于大运/胎元/命宫等辅助字段 |
| 业务层可见性 | ❌ 完全隔离 —— 业务层只消费 `CalendarSnapshot` |
| 许可证 | MIT |
| 版权 | Copyright (c) 6tail |
| 风险 | 黄历宜忌在不同通书间存在差异；节气边界精度依赖其内置算法 |
| 升级策略 | **必须先跑 `make test-golden`**；若结果变化，写入 `docs/calculation-differences.md` 并提升 `calendar_engine_version` |

**黄金案例锁定**：`tests/golden/test_golden_cases.py` 中的 8 组干支期望值、
6 组节气边界、结构性不变量（日柱 60 甲子推进 / 年柱一年一变 / 月柱一年十二变 / 五鼠遁）。

### 1.2 AKShare（股票行情）

| 项 | 值 |
|---|---|
| 用途 | 股票基础资料、上市日期、A 股日线行情、指数行情 |
| 仓库 | https://github.com/akfamily/akshare |
| 锁定版本 | **1.18.96** |
| 接入方式 | `AkshareMarketProvider`（`src/market/providers/akshare_provider.py`） |
| 业务层可见性 | ❌ 完全隔离 —— 业务层只消费 `StockMaster` / `BarSeries` |
| 许可证 | MIT |
| 版权 | Copyright (c) Albert King |
| 数据合规 | **AKShare 仅为数据接口封装，行情数据版权归原始数据源所有**；商业使用前需自行核实数据源条款 |
| 稳定性风险 | 高 —— 上游接口（东方财富/新浪）可能变更或限流。系统已实现 retry + 缓存 + 显式降级 |
| 升级策略 | 跑 `tests/market/test_normalization.py`；若字段名变化需同步更新 `CN_COLUMN_MAP` |

### 1.3 bazi-pro（**尚未接入**）

| 项 | 值 |
|---|---|
| 计划用途 | 八字格局、喜用神、多流派规则、古籍语料 |
| 候选仓库 | https://github.com/new1234cq/bazi-pro |
| 锁定 commit | **❌ 未锁定** |
| 当前状态 | **未接入**。Phase 1 使用自研确定性内核 `smx-bazi-native-1.0.0` |
| 决策依据 | 见 [`docs/ADR/ADR-0002`](docs/ADR/ADR-0002-bazi-engine-backend.md) |
| 许可证 | **未核实** —— 该仓库的 README/版权/提交历史大量指向原作者 `Minervaowl7/bazi-pro`，无法确认当前账号与原作者的关系。**商用前必须核实** |

**Phase 2 接入要求**：

1. 先 fork 到你自己的组织，**锁定 commit SHA**；
2. 只通过 `BaziEngine` adapter 调用（不得复制源码进主项目）；
3. 与自研内核做**双引擎交叉验证**，差异写入 `docs/calculation-differences.md`；
4. 古籍语料迁出前必须逐条核实 `license_status`。

### 1.4 其他规划中的第三方（Phase 2+）

| 项目 | 用途 | 仓库 | 许可证状态 |
|---|---|---|---|
| iztro | 紫微斗数排盘 | https://github.com/SylarLong/iztro | 未核实（MIT 声明待确认） |
| Tianji | 八字/紫微第二计算源、六爻 | https://github.com/Zijian-Ni/tianji | 未核实 |
| vectorbt | 大规模研究回测（可选） | https://github.com/polakowo/vectorbt | **需审查**（可能存在商业授权限制） |
| backtrader | 替代回测引擎 | https://github.com/mementum/backtrader | **GPL-3.0，商用需审查** |

> ⚠️ 上述四个项目**在 Phase 1 中完全没有被引用**，列在此处仅作 Phase 2 决策准备。

---

## 2. 后端依赖（Python）

全部锁版本，见 [`pyproject.toml`](pyproject.toml)。

### 2.1 Web / API

| 包 | 版本 | 用途 | 许可证 |
|---|---|---|---|
| fastapi | 0.141.1 | API 框架 | MIT |
| uvicorn[standard] | 0.53.0 | ASGI 服务器 | BSD-3-Clause |
| pydantic | 2.13.5 | 数据校验 | MIT |
| pydantic-settings | 2.15.0 | 配置管理 | MIT |
| python-multipart | 0.0.32 | 表单解析 | Apache-2.0 |

### 2.2 持久化

| 包 | 版本 | 用途 | 许可证 |
|---|---|---|---|
| sqlalchemy | 2.0.54 | ORM | MIT |
| alembic | 1.20.0 | Migration | MIT |

### 2.3 研究 / 数据

| 包 | 版本 | 用途 | 许可证 |
|---|---|---|---|
| numpy | 2.5.3 | 数值计算 | BSD-3-Clause |
| pandas | **≥2.3,<3.0** | 数据处理 | BSD-3-Clause |
| pyarrow | 25.0.1 | Parquet | Apache-2.0 |
| duckdb | 1.5.5 | 研究查询（OLAP） | MIT |

> **注意**：pandas 锁定在 2.x。pandas 3.0 存在大量 breaking change，
> Phase 1 不冒险升级；Phase 2 若需升级必须先全面回归。

### 2.4 古籍检索

| 包 | 版本 | 用途 | 许可证 |
|---|---|---|---|
| jieba | 0.42.1 | 中文分词 | MIT |
| rank-bm25 | 0.2.2 | BM25 检索 | Apache-2.0 |

> Phase 1 **不引入** `sentence-transformers` / `faiss`：
> 模型下载体积大、离线环境不可用。接口已按 `KnowledgeProvider` 抽象，Phase 2 可平滑替换。

### 2.5 基础设施

| 包 | 版本 | 用途 | 许可证 |
|---|---|---|---|
| tenacity | 9.1.4 | 重试（备用，当前用自研退避） | Apache-2.0 |
| httpx | 0.28.1 | HTTP 客户端（测试） | BSD-3-Clause |
| orjson | 3.12.0 | 快速 JSON（可选） | MIT / Apache-2.0 |

### 2.6 开发依赖

| 包 | 版本 | 用途 | 许可证 |
|---|---|---|---|
| pytest | 9.1.1 | 测试框架 | MIT |
| pytest-asyncio | 1.4.0 | 异步测试 | Apache-2.0 |
| pytest-cov | 7.1.0 | 覆盖率 | MIT |

---

## 3. 前端依赖（Node.js）

见 [`apps/web/package.json`](apps/web/package.json)。

| 包 | 版本 | 用途 | 许可证 |
|---|---|---|---|
| next | ^15.5.4 | React 框架 | MIT |
| react / react-dom | ^19.1.0 | UI 库 | MIT |
| echarts | ^6.1.0 | 图表 | Apache-2.0 |
| echarts-for-react | ^3.0.6 | ECharts React 封装 | MIT |
| zustand | ^5.0.8 | 状态管理 | MIT |
| tailwindcss | ^4.1.14 | 样式 | MIT |
| @tailwindcss/postcss | ^4.1.14 | PostCSS 插件 | MIT |
| typescript | ^5.9.0 | 类型系统 | Apache-2.0 |
| @playwright/test | ^1.55.0 | E2E 测试 | Apache-2.0 |

> **未引入第三方图标库**：`components/shell/Icons.tsx` 为内联 SVG，
> 避免额外运行时依赖与许可证问题。

---

## 4. 古籍语料版权

| 项 | 说明 |
|---|---|
| 收录范围 | **仅清代及以前刊行的公版原文** |
| 收录书目（7 本 43 条） | 滴天髓 / 渊海子平 / 三命通会 / 子平真诠 / 穷通宝鉴 / 神峰通考 / 命理约言 |
| 未收录 | 现代整理本、白话翻译、现代注释、数据库整理成果 |
| `modern_note` | **本项目自撰**的现代说明，不是古籍原文，也不引用任何未授权整理本 |
| 版权字段 | 每条带 `license_status`（全部为 `public_domain`）、`provenance`、`edition` |
| **校勘状态** | ⚠️ **Phase 1 未逐字对照权威刊本校勘**。语料的 `_meta.textual_criticism_warning` 中有明确声明。**正式发布前必须完成校勘。** |

> **不要因为某个 GitHub 仓库使用了某段古籍文本，就认为可以自由商用。**
> 古籍原文属公版，但现代整理、标点、翻译、注释通常仍有版权。

---

## 5. 数据来源与合规

| 数据 | 来源 | 合规说明 |
|---|---|---|
| A 股行情 | AKShare → 东方财富/新浪 | 仅供研究；商用前需核实数据源条款 |
| 股票基础资料 | AKShare → 东方财富 | 同上 |
| 交易所交易时段 | 公开交易规则整理（`config/exchange_session_calendar.json`） | 公开信息 |
| 古籍语料 | 公版古籍 | 见 §4 |
| 合成行情 | 本项目自研（`synthetic.py`） | 无版权问题，但**必须显式标注不可商用** |

---

## 6. 依赖更新流程

```bash
# 1. 更新版本
vim pyproject.toml          # 或 apps/web/package.json

# 2. 重新安装
uv pip install --python .venv -e ".[dev]"

# 3. 跑全部测试
make test

# 4. 跑 Golden Cases（关键！第三方排盘库升级必须跑）
make test-golden

# 5. 如果 Golden Case 失败：
#    a. 判断是"口径变化"还是"bug"
#    b. 口径变化 → 写 docs/calculation-differences.md
#    c. 提升 engine_version
#    d. 重新生成期望值并全量回归

# 6. 更新本文件的版本号
```

---

## 7. 依赖树快照（Phase 1 完成时）

```
Python: 3.12.14
  fastapi 0.141.1 / uvicorn 0.53.0 / pydantic 2.13.5
  sqlalchemy 2.0.54 / alembic 1.20.0
  numpy 2.5.3 / pandas 2.3.3 / pyarrow 25.0.1 / duckdb 1.5.5
  lunar-python 1.4.8          ← 术数核心
  akshare 1.18.96             ← 行情核心
  jieba 0.42.1 / rank-bm25 0.2.2
  httpx 0.28.1 / tenacity 9.1.4 / orjson 3.12.0
  pytest 9.1.1 / pytest-asyncio 1.4.0 / pytest-cov 7.1.0

Node: 24.14.0 (开发) / 22-alpine (Docker)
  next 15.5.25 / react 19.3.0
  echarts 6.1.0 / echarts-for-react 3.0.6
  tailwindcss 4.3.3 / typescript 5.x
  @playwright/test 1.63.0 (chromium-headless-shell 153)
```

> 完整锁定版本见 `pyproject.toml` 与 `apps/web/package-lock.json`。
