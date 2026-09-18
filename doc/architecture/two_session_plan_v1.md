# 股票玄学多模型研究平台：两次 AI 会话分布实施计划 V1.0

> 用途：将整个项目拆成两个独立但连续的 AI 编程会话完成。  
> 原则：第一会话建立“可运行、可测试、可重复”的研究底座；第二会话只在第一会话的稳定底座上增加紫微、多模型融合、完整 UI 和 AI 解读，不允许推翻第一阶段架构。  
> 推荐搭配：GPT-5.6 / Codex / Claude Code / OpenCode 等具备仓库读写与终端能力的编程 Agent。

---

# 1. 总体拆分逻辑

整个系统不要一次性让 AI 全做完。

正确拆法：

## 会话一：Foundation & BaZi Research Loop

目标：

```text
股票代码
→ 股票基础资料
→ StockBirthProfile
→ lunar-python
→ 黄历
→ bazi-pro
→ 八字原盘
→ 因子
→ AKShare
→ 历史标签
→ Event Study
→ 负对照
→ 古籍证据
```

完成后，即使还没有紫微和正式 UI，也已经有一个真实可验证的八字研究闭环。

---

## 会话二：Multi-Engine Productization

目标：

```text
在会话一稳定底座上
→ 接入紫微
→ 紫微因子
→ 黄历增强
→ ConsensusEngine
→ ConflictDetector
→ 共振历史统计
→ 月/周预测
→ AI Narrator
→ 正式完整 UI
→ 导出
```

最终形成完整产品。

---

# 2. 两个会话之间的强制交接

会话一结束必须生成：

```text
docs/HANDOFF_PHASE1.md
```

必须包含：

```text
当前 commit SHA
完成模块
未完成模块
数据库表
API 列表
第三方依赖与 commit/version
测试结果
已知问题
关键 ADR
第二阶段不得破坏的接口
第二阶段建议顺序
```

第二会话开始前必须先读取：

```text
README.md
ARCHITECTURE.md
AGENTS.md
THIRD_PARTY.md
docs/HANDOFF_PHASE1.md
docs/database.md
docs/api.md
docs/factor_dictionary.md
docs/methodology.md
UI/UX设计规范
总体架构方案
```

禁止第二会话跳过这些文件直接重构。

---

# 3. 会话一必须完成的内容

## 3.1 工程基础

完成：

```text
Monorepo
FastAPI
SQLite
DuckDB
Parquet
pytest
Docker Compose
环境变量
日志
CI或统一测试脚本
```

---

## 3.2 股票基础数据

实现：

```text
股票搜索
股票基础信息
股票代码规范化
交易所识别
上市日期
交易日历
```

必须通过：

```text
MarketDataProvider
```

封装 AKShare。

---

## 3.3 StockBirthProfile

默认模型：

```text
listing_open
```

计算逻辑：

```text
上市首个交易日
+
对应交易所配置中的正式开盘时刻
+
Asia/Shanghai
```

禁止业务代码写死：

```text
所有股票 = 09:30
```

必须有：

```text
exchange_session_calendar
```

支持未来扩展：

```text
ipo_date
company_foundation
custom
```

必须版本化。

---

# 4. 股票无性别问题：会话一就必须解决接口

股票没有真实“男命/女命”。

因此如果某些传统运限算法需要：

```text
性别
顺逆
```

必须：

```text
不自动填男
不自动填女
```

设计：

```text
variant_mode
```

例如：

```text
forward
reverse
both
not_applicable
```

会话一可以暂时不把顺逆大运用于最终股票因子，但数据结构必须支持未来比较不同假设。

---

# 5. lunar-python 接入

通过：

```text
CalendarEngine adapter
```

接入。

必须能输出：

```text
公历
农历
干支
节气
生肖
纳音
建除十二值
十二神
黄黑道
冲煞
彭祖百忌
```

---

# 6. HuangliEngine

建立独立：

```text
HuangliEngine
```

而不是页面直接调用 lunar-python。

保存：

```text
raw_huangli
engine_version
calculated_at
```

---

# 7. bazi-pro 接入

建议先 fork 到自己的仓库，例如：

```text
your-org/bazi-pro-stock
```

锁定 commit。

主项目只能通过：

```text
BaziEngine adapter
```

访问。

必须保存：

```text
raw_chart
engine_version
config_version
```

---

# 8. 会话一八字输出要求

至少：

```text
年柱
月柱
日柱
时柱
藏干
十神
纳音
五行
日主
旺衰
格局
喜神
用神
忌神
刑冲合害
当前流年
当前流月
```

如果某些字段 bazi-pro 无法可靠给出，必须：

```text
返回 unavailable
+
warning
```

禁止 AI 或业务层自行补算。

---

# 9. 会话一第一批因子

至少实现：

```text
30-50 个
```

建议分：

```text
B_NATAL_xxx
B_YEAR_xxx
B_MONTH_xxx
H_DAY_xxx
```

每个因子统一：

```json
{
  "factor_id": "B_MONTH_003",
  "name": "...",
  "engine": "bazi",
  "raw_value": "...",
  "normalized_value": 0.8,
  "direction": 1,
  "rule_score": 8,
  "confidence": 0.7,
  "rule_version": "v1",
  "evidence": [],
  "explanation": "..."
}
```

重要：

> 财星、食伤、合冲等只是研究变量，不能直接声明等于股价上涨。

---

# 10. 行情数据

AKShare 通过 adapter 接入。

至少统一字段：

```text
date
open
high
low
close
volume
amount
turnover
pct_change
```

支持：

```text
沪深300
```

作为基础 benchmark。

---

# 11. 历史标签

至少：

```text
ret_1d
ret_5d
ret_10d
ret_20d
ret_60d
max_return_20d
max_drawdown_20d
excess_return_20d
```

必须基于 as_of 严格防未来数据泄漏。

---

# 12. Event Study

输入：

```text
因子
或因子组合
```

输出：

```text
样本数
上涨率
平均收益
中位数收益
平均超额收益
最大回撤
```

V1 可以自研：

```text
pandas + numpy + duckdb
```

不强依赖 vectorbt。

---

# 13. 负对照

会话一必须实现：

```text
随机出生日期
出生日期 +7 天
出生日期 -7 天
随机因子
```

用于检验：

```text
真实命盘信号是否优于随机
```

这是硬性验收项。

---

# 14. 古籍知识中心一期

复用 bazi-pro 的古籍检索能力，但通过：

```text
KnowledgeProvider
```

接入。

条目必须至少有：

```text
book
chapter
topic
original_text
source
provenance
license_status
```

不允许因为 GitHub 中存在某段现代注释，就默认可以商业使用。

---

# 15. 会话一数据库

至少：

```text
stock_master
stock_birth_profile
exchange_session_calendar
market_bar_daily

engine_version
engine_run
chart_artifact

factor_definition
factor_observation

classical_book
classical_entry
evidence_link

backtest_experiment
backtest_result
```

---

# 16. 会话一最小 API

至少：

```http
GET  /api/v1/stocks/search
GET  /api/v1/stocks/{code}

POST /api/v1/stocks/{code}/birth-profile

POST /api/v1/stocks/{code}/analysis/bazi

GET  /api/v1/analysis/{id}/charts/bazi
GET  /api/v1/analysis/{id}/huangli
GET  /api/v1/analysis/{id}/factors
GET  /api/v1/analysis/{id}/backtest
GET  /api/v1/analysis/{id}/evidence
```

必须有稳定 schema 和 OpenAPI。

---

# 17. 会话一前端范围

只做开发验证台。

只要求：

```text
输入股票代码
显示股票基础资料
显示八字四柱
显示黄历
显示因子列表
显示回测摘要
```

不要在会话一做最终正式 UI。

原因：

> 正式 UI 必须等紫微、共识、冲突的数据 Contract 稳定后再一次性实现。

---

# 18. 会话一禁止事项

明确禁止：

```text
不接紫微
不接六爻
不接奇门
不做最终多模型共识
不接 LLM
不做会员
不做支付
不做复杂权限
不做自动交易
不为了漂亮 UI 重构底层
```

---

# 19. 会话一测试要求

至少：

```text
CalendarEngine test
HuangliEngine test
BaziEngine test
StockBirthProfile test
Factor calculation test
Market normalization test
Forward return label test
Event Study test
Negative control test
API integration test
test_no_future_data_access
Golden Cases
```

---

# 20. 会话一 Prompt

以下建议原样复制到第一个 AI 会话。

---

## 【会话一 Prompt】

你是本项目的首席架构师、Python 后端工程师、量化研究工程师与测试负责人。

我要开发一个“股票玄学多模型研究平台”，但当前只执行第一阶段：

**Foundation & BaZi Research Loop**

请先完整阅读我提供的：

1. 《股票玄学多模型研究平台 V1.0－总体架构与实施方案》
2. 《股票玄学多模型研究平台 UI/UX 完整设计规范 V1.0》
3. 当前项目仓库
4. bazi-pro fork
5. AGENTS.md（如存在）

你的任务不是一次性完成最终产品，而是建立以后可以安全接入紫微、六爻、奇门的稳定研究底座。

### A. 本阶段必须跑通的链路

股票代码
→ 股票基础资料
→ StockBirthProfile
→ lunar-python
→ HuangliEngine
→ bazi-pro
→ 八字 raw_chart
→ 八字/黄历因子
→ AKShare
→ 历史行情标签
→ Event Study
→ 负对照
→ 古籍证据

### B. 第三方隔离

必须定义并使用：

- CalendarEngine
- BaziEngine
- MarketDataProvider
- KnowledgeProvider
- BacktestProvider

业务层不得直接持有或调用第三方库对象。

### C. StockBirthProfile

默认：

listing_open

出生时间来自：

上市首个交易日
+
交易所 session 配置中的正式开盘时刻
+
Asia/Shanghai

禁止把 09:30 写死在所有股票业务逻辑里。

股票无性别。

如果传统算法需要性别/顺逆：

- 不允许偷偷填“男”
- 不允许偷偷填“女”
- 必须记录 assumption
- 必须设计 variant_mode
- 暂时可以不把大运顺逆纳入最终因子

### D. 八字

至少保存：

- 年柱
- 月柱
- 日柱
- 时柱
- 藏干
- 十神
- 纳音
- 五行
- 日主
- 旺衰
- 格局
- 喜神
- 用神
- 忌神
- 刑冲合害
- 当前流年
- 当前流月

所有结果保留：

raw_chart
engine_version
factor_version
birth_profile_version
config_version

### E. 黄历

至少：

- 阳历
- 农历
- 干支
- 节气
- 建除十二值
- 十二神
- 黄黑道
- 冲煞
- 纳音
- 彭祖百忌

### F. 因子

第一阶段至少实现 30-50 个八字/黄历因子。

每个因子必须有：

factor_id
name
engine
definition
raw_value
normalized_value
direction
rule_score
confidence
rule_version
evidence
explanation

不要把财星直接等于股票上涨。

所有术数因子只是研究变量。

### G. 行情与标签

AKShare 只能通过 MarketDataProvider。

至少支持：

ret_1d
ret_5d
ret_10d
ret_20d
ret_60d
max_return_20d
max_drawdown_20d
excess_return_20d

基准至少支持沪深300。

### H. 研究验证

至少实现：

Event Study
随机出生日期负对照
出生日期 ±7 天
随机因子负对照

必须实现：

test_no_future_data_access

### I. 古籍

优先复用 bazi-pro 现有检索机制。

但必须通过 KnowledgeProvider。

所有 evidence 必须包含：

book
chapter
topic
original_text
source
provenance
license_status

不得假设所有现代整理文本都能商用。

### J. 数据库

至少：

stock_master
stock_birth_profile
exchange_session_calendar
market_bar_daily
engine_version
engine_run
chart_artifact
factor_definition
factor_observation
classical_book
classical_entry
evidence_link
backtest_experiment
backtest_result

### K. API

实现：

GET /api/v1/stocks/search
GET /api/v1/stocks/{code}
POST /api/v1/stocks/{code}/birth-profile
POST /api/v1/stocks/{code}/analysis/bazi
GET /api/v1/analysis/{id}/charts/bazi
GET /api/v1/analysis/{id}/huangli
GET /api/v1/analysis/{id}/factors
GET /api/v1/analysis/{id}/backtest
GET /api/v1/analysis/{id}/evidence

### L. 前端

只做开发验证台：

1. 输入股票代码；
2. 显示股票资料；
3. 显示八字四柱；
4. 显示黄历；
5. 显示因子；
6. 显示回测摘要。

不要做最终 UI。

### M. 测试

必须覆盖：

CalendarEngine
HuangliEngine
BaziEngine
StockBirthProfile
Factor Engine
Market normalization
Label calculation
Event Study
Negative Control
No Future Leakage
API integration
Golden Cases

### N. 必须生成文档

README.md
ARCHITECTURE.md
AGENTS.md
THIRD_PARTY.md
docs/database.md
docs/api.md
docs/factor_dictionary.md
docs/methodology.md
docs/HANDOFF_PHASE1.md

HANDOFF_PHASE1.md 必须写清楚：

- 当前 commit SHA
- 已完成模块
- 未完成模块
- API
- DB
- 第三方版本
- 测试结果
- 已知问题
- 关键设计决策
- 第二阶段不得破坏的接口
- 第二阶段推荐实施顺序

### O. 禁止

不要接紫微。
不要接六爻。
不要接奇门。
不要接 LLM。
不要实现最终多模型共识。
不要做无关大重构。
不要接自动交易。

### P. 执行方式

先审计仓库并列实施 TODO。
然后直接编码，不要只给方案。
每完成一个可运行里程碑就运行测试。
遇到第三方算法不确定，不要猜测，记录 assumption/warning。
最终输出：

- 完成清单
- 测试结果
- 启动方式
- HANDOFF_PHASE1.md
- 剩余问题

---

# 21. 会话一验收标准

## 工程

- [ ] `docker compose up` 可启动；
- [ ] README 有完整启动步骤；
- [ ] 依赖锁版本；
- [ ] bazi-pro 锁定 commit；
- [ ] THIRD_PARTY.md 存在；
- [ ] 测试可统一运行。

## 股票输入

- [ ] 输入任意支持的 A 股代码可查询；
- [ ] 股票代码被规范化；
- [ ] 上市日期存在；
- [ ] 交易所识别正确；
- [ ] StockBirthProfile 持久化；
- [ ] birth_profile_version 存在。

## 八字

- [ ] 四柱真实计算；
- [ ] raw_chart 保存；
- [ ] 十神存在；
- [ ] 五行存在；
- [ ] 格局存在或明确 unavailable；
- [ ] 喜用忌存在或明确 unavailable；
- [ ] 流年存在；
- [ ] 流月存在；
- [ ] engine_version 可追溯。

## 黄历

- [ ] 干支；
- [ ] 节气；
- [ ] 建除；
- [ ] 十二神；
- [ ] 冲煞；
- [ ] 黄黑道或等价字段；
- [ ] raw_huangli 可查看。

## 因子

- [ ] 至少 30 个；
- [ ] 每个有 factor_id；
- [ ] 每个有定义；
- [ ] 每个有版本；
- [ ] observation 可持久化。

## 行情

- [ ] 日行情可获取；
- [ ] 统一格式；
- [ ] 可缓存；
- [ ] 支持沪深300；
- [ ] 历史查询不读取未来输入数据。

## 标签

- [ ] 1/5/10/20/60 日收益；
- [ ] 20日最大回撤；
- [ ] 20日超额收益。

## 回测

- [ ] Event Study；
- [ ] 随机出生日期；
- [ ] +7 天；
- [ ] -7 天；
- [ ] 随机因子；
- [ ] 输出样本数与收益统计。

## 古籍

- [ ] KnowledgeProvider；
- [ ] 书名；
- [ ] topic；
- [ ] provenance；
- [ ] license_status；
- [ ] evidence retrieval。

## API

- [ ] 所列 API 可调用；
- [ ] OpenAPI 可查看；
- [ ] 错误有结构化返回。

## 前端验证台

- [ ] 股票输入；
- [ ] 四柱；
- [ ] 黄历；
- [ ] 因子；
- [ ] 回测摘要。

## 测试

- [ ] `test_no_future_data_access` 通过；
- [ ] Golden Cases；
- [ ] integration tests；
- [ ] 全测试无失败。

## 交接

- [ ] `docs/HANDOFF_PHASE1.md` 完整；
- [ ] 第二阶段可以仅依靠仓库与 HANDOFF 接手。

---

# 22. 第二会话开始前必须给 AI 的材料

只需提供：

```text
1. Phase1 完整仓库
2. HANDOFF_PHASE1.md
3. ARCHITECTURE.md
4. AGENTS.md
5. THIRD_PARTY.md
6. docs/database.md
7. docs/api.md
8. docs/factor_dictionary.md
9. UI/UX完整设计规范
10. 总体架构方案
```

不需要把全部历史聊天重新粘贴。

---

# 23. 会话二必须完成的内容

## 23.1 紫微斗数

接入：

```text
SylarLong/iztro
```

通过：

```text
ZiweiEngine adapter
```

建议：

```text
Node/TypeScript 独立 service
```

保存：

```text
raw_chart
engine_version
variant_mode
assumptions
```

至少包含：

```text
十二宫
主星
辅星
煞曜
四化
三方四正
大限
流年
流月
流日
```

---

# 24. 紫微股票因子

至少：

```text
30-50 个
```

优先：

```text
财帛宫
官禄宫
命宫
迁移宫
四化
三方四正
大限
流年
流月
流日
```

要明确：

> “财帛宫对应股票资金/价格”的说法只是研究映射，不是传统紫微的确定性结论。

---

# 25. 黄历因子增强

至少：

```text
15-30 个
```

例如：

```text
H_DAY_001 当日天干与喜用关系
H_DAY_002 当日地支与原局冲
H_DAY_003 六合
H_DAY_004 三合
H_DAY_005 刑
H_DAY_006 害
H_DAY_007 建除
H_DAY_008 黄黑道
```

---

# 26. Opinion Contract

每个引擎统一返回：

```json
{
  "direction": 1,
  "score": 82,
  "confidence": 0.71,
  "top_positive_reasons": [],
  "top_negative_reasons": [],
  "factor_ids": [],
  "historical_validity": {}
}
```

---

# 27. ConsensusEngine

必须实现：

```text
STRONG_POSITIVE_CONSENSUS
POSITIVE_CONSENSUS
MIXED
NEUTRAL
NEGATIVE_CONSENSUS
STRONG_NEGATIVE_CONSENSUS
```

禁止只做：

```text
三个分数平均
```

---

# 28. ConflictDetector

至少输出：

```text
conflicting_engines
directions
reasons
conflicting_factor_ids
historical_conflict_stats
```

如果：

```text
八字 +85
紫微 -75
黄历 0
```

UI 必须显示：

```text
明显分歧
```

而不是：

```text
平均55
```

---

# 29. 共振历史统计

必须分别计算：

```text
八字单独
紫微单独
黄历单独
八字+紫微同向
八字+黄历同向
紫微+黄历同向
三模型同向
三模型冲突
```

输出不同持有期表现。

---

# 30. 月度预测

生成：

```text
未来12个月
```

每个月保留：

```text
八字 opinion
紫微 opinion
黄历 opinion
consensus
conflict
historical_validity
```

---

# 31. 周度预测

周度来自：

```text
交易日流日因子聚合
```

禁止发明“流周”。

至少支持聚合方法：

```text
mean
median
min
max
positive_day_ratio
```

默认方法必须版本化。

---

# 32. AI Narrator

此阶段才接 LLM。

输入必须是 Evidence Bundle：

```json
{
  "stock": {},
  "charts": {},
  "factors": [],
  "opinions": {},
  "consensus": {},
  "conflicts": [],
  "backtest_stats": {},
  "classical_evidence": []
}
```

LLM 禁止：

```text
重新排盘
修改干支
修改宫位
修改四化
修改因子
修改分数
编古籍
修改回测数字
隐藏冲突
```

LLM 只负责解释。

---

# 33. 正式 UI

严格按 UI/UX 设计规范实现：

```text
首页
综合研判
时间窗口
八字
紫微
黄历
模型分歧
历史验证
古籍证据
设置
```

必须存在组件：

```text
BaziChart
ZiweiChart
HuangliPanel
EngineScoreCard
ConsensusCard
ConflictCard
EvidenceDrawer
BacktestMetricCard
DataQualityBadge
```

---

# 34. 模型故障隔离

如果紫微服务失败：

```text
八字继续显示
黄历继续显示
紫微 = unavailable
综合页标记“紫微不可用”
```

禁止：

```text
紫微失败 = 0分
```

---

# 35. 双引擎验证

可以加入 Tianji 作为：

```text
八字第二计算源
紫微第二计算源
```

至少对 Golden Cases 做一次结果对比。

差异写入：

```text
docs/calculation-differences.md
```

不一致不能静默忽略。

---

# 36. 导出

至少：

```text
Markdown
HTML
```

内容：

```text
股票基础信息
综合研判
八字
紫微
黄历
共识
分歧
古籍
历史验证
方法限制
版本信息
```

PDF 可后续增强。

---

# 37. 会话二 Prompt

以下建议原样复制到第二个 AI 会话。

---

## 【会话二 Prompt】

你现在接手一个已经完成 Phase 1 的“股票玄学多模型研究平台”。

当前执行第二阶段：

**Multi-Engine Productization**

在任何编码之前，请先阅读：

1. README.md
2. ARCHITECTURE.md
3. AGENTS.md
4. THIRD_PARTY.md
5. docs/HANDOFF_PHASE1.md
6. docs/database.md
7. docs/api.md
8. docs/factor_dictionary.md
9. 《股票玄学多模型研究平台 UI/UX 完整设计规范 V1.0》
10. 《股票玄学多模型研究平台 V1.0－总体架构与实施方案》

### A. 最高原则

Phase 1 已经建立稳定底座。

不要重新设计：

- StockBirthProfile
- Factor Schema
- Engine Adapter Contract
- MarketDataProvider
- KnowledgeProvider
- BacktestProvider
- 已公开 API

如果确实存在阻塞性缺陷，先创建 ADR，说明：

- 问题
- 原因
- 兼容方案
- 风险

然后只做最小兼容修改。

### B. 本阶段完整链路

股票代码
→ 八字
→ 紫微
→ 黄历
→ 独立原始盘面
→ 独立因子
→ 独立 opinion
→ Consensus
→ Conflict
→ 历史验证
→ 古籍证据
→ AI解释
→ 正式完整 UI

### C. 紫微

使用 iztro。

建议 TypeScript 独立 service。

必须通过 ZiweiEngine adapter。

必须保存 raw_chart。

至少：

- 十二宫
- 主星
- 辅星
- 煞曜
- 四化
- 三方四正
- 大限
- 流年
- 流月
- 流日

不得由 LLM 排盘。

### D. 股票无性别

如果紫微或八字功能需要性别/顺逆：

- 不允许自动填男/女
- 使用 variant_mode
- 可以并行计算不同假设
- 每个结果记录 assumption
- 历史回测比较不同 variant

### E. 紫微因子

至少 30-50 个。

重点：

- 财帛宫
- 官禄宫
- 命宫
- 迁移宫
- 四化
- 三方四正
- 大限
- 流年
- 流月
- 流日

不要把股票与宫位映射写成传统术数定论。
它是研究假设。

### F. 黄历增强

生成 H_xxx 因子。

至少包含：

- 干支喜忌
- 与股票原局冲合
- 建除
- 十二神
- 黄黑道
- 纳音
- 其他可解释结构

### G. Opinion Contract

每个引擎统一：

{
  "direction": -1|0|1,
  "score": 0-100,
  "confidence": 0-1,
  "top_positive_reasons": [],
  "top_negative_reasons": [],
  "factor_ids": [],
  "historical_validity": {}
}

### H. ConsensusEngine

实现：

STRONG_POSITIVE_CONSENSUS
POSITIVE_CONSENSUS
MIXED
NEUTRAL
NEGATIVE_CONSENSUS
STRONG_NEGATIVE_CONSENSUS

禁止用简单平均覆盖分歧。

### I. ConflictDetector

至少：

- conflicting_engines
- directions
- reasons
- conflicting_factor_ids
- historical_conflict_stats

UI 必须展示。

### J. 历史验证

比较：

- 八字单独
- 紫微单独
- 黄历单独
- 八字+紫微
- 八字+黄历
- 紫微+黄历
- 三模型同向
- 三模型冲突

保留 Phase1 全部负对照。

### K. 月度 / 周度

月度：

未来12个月。

周度：

由交易日流日聚合。

禁止发明“流周”。

至少支持：

mean
median
min
max
positive_day_ratio

聚合方法版本化。

### L. AI Narrator

AI 只能解释 Evidence Bundle。

不得：

- 排八字
- 排紫微
- 算四化
- 算流月
- 算收益
- 改分
- 编古籍
- 隐藏模型冲突

必须区分：

“传统术数判断”
和
“历史统计验证”。

### M. UI

严格按照 UI/UX 规范实现：

- 首页
- 综合研判
- 时间窗口
- 八字
- 紫微
- 黄历
- 模型分歧
- 历史验证
- 古籍证据
- 设置

必须有：

- BaziChart
- ZiweiChart
- HuangliPanel
- EngineScoreCard
- ConsensusCard
- ConflictCard
- EvidenceDrawer
- BacktestMetricCard
- DataQualityBadge

### N. 综合页

首屏必须同时回答：

1. 各模型方向；
2. 是否共振；
3. 是否冲突；
4. 历史验证强弱；
5. 数据质量。

禁止只显示“综合85分”。

### O. 完整盘面

八字必须有四柱盘。
紫微必须有十二宫盘。
黄历必须有日课详情。

评分不能替代盘面。

### P. 故障隔离

任一引擎失败：

- 其他引擎继续
- 失败引擎显示 unavailable
- 不得按0分参与共识

### Q. 双引擎校验

允许使用 Tianji 作为第二计算源。

至少对一组 Golden Cases 做：

- 八字结果对比
- 紫微基础结果对比

差异写入：

docs/calculation-differences.md

### R. 导出

至少：

- Markdown
- HTML

必须包含：

- 股票基础信息
- 综合研判
- 八字
- 紫微
- 黄历
- 共识
- 分歧
- 古籍
- 回测
- 方法限制
- 版本信息

### S. 新增测试

至少：

ZiweiEngine test
ConsensusEngine test
ConflictDetector test
Month aggregation test
Week aggregation test
Narrator evidence-bound test
UI core flow e2e test
Engine failure isolation test

所有 Phase1 测试必须继续通过。

### T. 最终文档

生成：

docs/HANDOFF_FINAL.md
docs/calculation-differences.md
docs/ui-implementation.md
docs/consensus-methodology.md
docs/model-limitations.md

最终输出：

- 完成模块
- API变化
- UI页面
- 测试结果
- 已知限制
- 下一步可选扩展
- 最终启动方式

---

# 38. 会话二验收标准

## 紫微

- [ ] iztro 接入；
- [ ] ZiweiEngine adapter；
- [ ] raw_chart；
- [ ] 十二宫；
- [ ] 四化；
- [ ] 流年；
- [ ] 流月；
- [ ] 至少30个紫微因子。

## 多模型

- [ ] 八字独立 opinion；
- [ ] 紫微独立 opinion；
- [ ] 黄历独立 opinion；
- [ ] ConsensusEngine；
- [ ] ConflictDetector；
- [ ] 冲突不会被平均分隐藏。

## 历史验证

- [ ] 单模型统计；
- [ ] 两模型共振；
- [ ] 三模型共振；
- [ ] 冲突组合统计；
- [ ] Phase1 负对照仍可运行。

## 时间窗口

- [ ] 未来12个月；
- [ ] 周度聚合；
- [ ] 周度方法版本化；
- [ ] 点击月份可查看三模型详情。

## AI

- [ ] 只能解释结构化结果；
- [ ] 不能修改 raw_chart；
- [ ] 不能修改 score；
- [ ] 古籍来自 evidence；
- [ ] 冲突明确写出。

## UI

- [ ] 首页；
- [ ] 综合研判；
- [ ] 时间窗口；
- [ ] 八字；
- [ ] 紫微；
- [ ] 黄历；
- [ ] 模型分歧；
- [ ] 历史验证；
- [ ] 古籍证据；
- [ ] 设置；
- [ ] 1440px 桌面端无明显溢出；
- [ ] 1024px 可用；
- [ ] 移动端核心信息可读。

## 盘面

- [ ] 八字四柱盘；
- [ ] 紫微十二宫盘；
- [ ] 黄历日课；
- [ ] 不能只显示分数。

## 故障隔离

- [ ] 任一引擎失败不影响其他引擎；
- [ ] unavailable 不参与0分计算。

## 导出

- [ ] Markdown；
- [ ] HTML；
- [ ] 版本信息完整。

## 测试

- [ ] 所有 Phase1 测试仍通过；
- [ ] Phase2 新测试通过；
- [ ] E2E 主流程通过；
- [ ] 无 future leakage regression。

---

# 39. 两会话责任矩阵

| 模块 | 会话一 | 会话二 |
|---|---|---|
| Monorepo | 完成 | 不重做 |
| FastAPI | 完成 | 扩展 |
| StockMaster | 完成 | 使用 |
| BirthProfile | 完成 | 使用/variant |
| lunar-python | 完成 | 使用 |
| bazi-pro | 完成 | 使用 |
| 黄历基础 | 完成 | 因子增强 |
| 八字因子 | 完成 | 可扩展 |
| AKShare | 完成 | 使用 |
| 回测基础 | 完成 | 共振扩展 |
| 古籍八字 | 完成 | 扩展紫微 |
| 紫微 | 不做 | 完成 |
| Consensus | 不做 | 完成 |
| Conflict | 不做 | 完成 |
| AI Narrator | 不做 | 完成 |
| 开发验证台 | 完成 | 替换为正式UI |
| 完整UI | 不做 | 完成 |
| 月/周预测 | 不做 | 完成 |
| 导出 | 可不做 | 完成 |
| 六爻 | 只预留接口 | 可继续预留 |
| 奇门 | 只预留接口 | 可继续预留 |

---

# 40. 第一会话结束后人工检查

不要立刻开第二会话。

先人工检查：

```text
docker compose up
pytest
随机挑至少4只A股
不同上市年份
不同交易所/板块
八字是否稳定
黄历是否稳定
回测是否可复现
HANDOFF_PHASE1.md 是否完整
```

建议抽样：

```text
一只上交所老股
一只深交所老股
一只创业板股票
一只近年上市股票
```

---

# 41. 第二会话结束后人工验收场景

至少验证：

```text
场景1：三个模型全部同向
场景2：八字与紫微明显冲突
场景3：黄历中性
场景4：紫微服务失败
场景5：股票数据不完整
场景6：未来1个月
场景7：未来3个月
场景8：不同出生模型
```

每个场景都应该给出合理状态。

---

# 42. 两次会话的真正边界

一句话：

> **会话一负责“把研究做真”：数据、排盘、因子、回测、古籍。**

> **会话二负责“把产品做完整”：紫微、多模型共识与分歧、正式 UI、AI解释、月周时间窗口和导出。**

这样拆，第二会话不会重新发明第一阶段，第一会话也不会被 UI 和多模型复杂度拖垮。
