# 股票玄学多模型研究平台 V1.0
## 总体架构、开源模块整合与实施方案

> 文档定位：可直接交给 Codex、Claude Code、OpenCode、ZCODE、WorkBuddy 等本地/云端 AI 编程助手分阶段实施。  
> 版本：V1.0  
> 日期：2026-09-17  
> 建议项目名：`stock-metaphysics-platform`

---

# 1. 项目定义

本项目不是一个普通“八字算股票”的工具，而是一套：

> **传统术数多模型 × 古籍知识库 × 股票历史行情 × 统计回测验证 × AI解释** 的股票研究平台。

用户最终只需要输入一只股票代码，例如：

```text
600xxx
000xxx
300xxx
```

系统自动完成：

1. 获取股票基础信息、交易所、上市日期等；
2. 构造股票“出生时间”研究档案；
3. 生成八字盘；
4. 生成黄历/日课信息；
5. 生成紫微斗数命盘；
6. 后续可扩展六爻、奇门遁甲、梅花易数等；
7. 每一种术数独立计算、独立给出原始盘面和解释；
8. 将每一种术数拆解成可量化因子；
9. 将因子与历史股价进行回测；
10. 对未来月份、未来交易周、未来交易日生成研究性“运势”；
11. 比较不同术数之间的共识与冲突；
12. 输出详细盘面、古籍依据、历史统计证据和 AI 解读。

---

# 2. 核心产品原则

整个系统必须坚持以下原则。

## 2.1 “盘面”和“评分”必须同时存在

后台需要评分，因为评分才能：

- 回测；
- 排序；
- 做统计；
- 比较不同股票；
- 比较不同月份；
- 学习不同因子的历史有效性。

但是前台不能只输出：

```text
本月：82分
下月：67分
```

最终必须同时输出：

### 八字

- 四柱；
- 日主；
- 五行强弱；
- 十神；
- 格局；
- 喜用神；
- 忌神；
- 合冲刑害；
- 流年；
- 流月；
- 流日；
- 当前运势结构；
- 古籍依据；
- 详细解释。

### 紫微斗数

- 十二宫；
- 主星；
- 辅星；
- 四化；
- 三方四正；
- 财帛宫；
- 官禄宫；
- 命宫；
- 迁移宫；
- 大限；
- 流年；
- 流月；
- 流日；
- 详细解释；
- 古籍依据。

### 黄历 / 日课

- 当日干支；
- 节气；
- 建除十二值；
- 黄黑道；
- 十二神；
- 彭祖百忌；
- 冲煞；
- 与股票原局之间的关系；
- 日课详细解释。

### 六爻（后续）

必须输出真实：

- 本卦；
- 变卦；
- 动爻；
- 世应；
- 六亲；
- 六神；
- 用神；
- 月建；
- 日辰；
- 旺衰；
- 卦象解释。

### 奇门（后续）

必须输出真实：

- 九宫局盘；
- 阴遁/阳遁；
- 局数；
- 九星；
- 八门；
- 八神；
- 天盘/地盘干；
- 值符；
- 值使；
- 宫位关系；
- 详细解释。

因此系统中统一使用：

```text
“原始术数盘 + 因子 + 分数 + 解释 + 古籍 + 历史验证”
```

而不是只有一个黑盒评分。

---

# 3. 项目最终用户体验

## 3.1 用户输入

首页只有一个核心输入：

```text
股票代码：600xxx
```

高级选项中允许选择：

```text
预测基准时间：当前
预测周期：
- 未来1周
- 未来4周
- 未来3个月
- 未来6个月
- 未来12个月

启用模型：
☑ 八字
☑ 紫微斗数
☑ 黄历
□ 六爻
□ 奇门
```

---

# 4. 最终输出页面设计

建议页面分为：

```text
综合研判
├── 八字
├── 紫微斗数
├── 黄历 / 日课
├── 六爻（未来）
├── 奇门（未来）
├── 古籍证据
├── 历史验证
└── 模型冲突
```

---

# 5. 综合研判页

综合页不能直接说：

> “这只股票一定会上涨。”

而应该显示研究模型的：

```text
术数共识方向
历史统计有效性
数据质量
模型分歧程度
```

示意：

```text
未来30天

八字            84   偏强
紫微斗数        79   偏强
黄历            73   偏强

术数共识        82   较强共振

历史同类状态：
样本数          186
未来20日上涨    63.4%
平均收益        +4.1%
平均超额收益    +2.3%

模型分歧：低
```

另外一个例子：

```text
未来30天

八字            83   偏强
紫微斗数        39   偏弱
黄历            52   中性

术数共识：分歧明显
```

系统必须明确告诉用户：

```text
八字认为有利的主要原因：
……

紫微斗数认为不利的主要原因：
……

黄历没有形成明显方向。

当前不存在明显多模型共振。
```

**禁止为了生成一个最终分数而掩盖分歧。**

---

# 6. “共识”和“历史有效性”必须分开

这是本项目非常重要的一条设计原则。

例如：

```text
八字：90
紫微：88
黄历：85
```

三个术数都认为偏强。

系统可以得到：

```text
术数一致性：95
```

但是如果历史回测发现：

```text
过去类似共振出现 40 次
随后20日上涨 21 次
上涨率 52.5%
```

那么必须显示：

```text
术数共识：高
历史验证：弱
```

反过来：

```text
术数共识：中等
历史验证：强
```

也应该如实显示。

因此最终至少存在三个不同指标：

```text
Consensus Score      术数共识
Empirical Score      历史统计有效性
Data Quality Score   数据质量
```

不能把三者混成一个神秘的“总分”。

---

# 7. 推荐总体架构

```text
                             ┌────────────────────┐
                             │      Web UI        │
                             │ Next.js / React    │
                             └─────────┬──────────┘
                                       │
                                       ▼
                             ┌────────────────────┐
                             │    FastAPI API     │
                             │   Orchestrator     │
                             └─────────┬──────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
      ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
      │ Stock Master │        │ Time Engine  │        │ Market Data  │
      │ 股票基础资料  │        │ 历法时间中心  │        │ AKShare      │
      └──────┬───────┘        └──────┬───────┘        └──────┬───────┘
             │                       │                        │
             └───────────────────────┼────────────────────────┘
                                     │
                                     ▼
                          ┌─────────────────────┐
                          │  Stock Birth Profile│
                          │   股票出生研究档案   │
                          └──────────┬──────────┘
                                     │
               ┌─────────────────────┼────────────────────────┐
               │                     │                        │
               ▼                     ▼                        ▼
        ┌────────────┐        ┌────────────┐          ┌────────────┐
        │ BaZi Engine│        │ZiWei Engine│          │Huangli     │
        │ bazi-pro   │        │ iztro      │          │lunar-python│
        └─────┬──────┘        └─────┬──────┘          └─────┬──────┘
              │                     │                        │
              │                     │                        │
        ┌─────▼──────┐        ┌─────▼──────┐          ┌─────▼──────┐
        │ BaZi Factors│       │ZiWei Factors│         │Date Factors│
        └─────┬──────┘        └─────┬──────┘          └─────┬──────┘
              │                     │                        │
              └─────────────────────┼────────────────────────┘
                                    │
                                    ▼
                          ┌──────────────────────┐
                          │ Factor Registry      │
                          │ 统一术数因子中心      │
                          └──────────┬───────────┘
                                     │
                     ┌───────────────┼────────────────┐
                     │               │                │
                     ▼               ▼                ▼
             ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
             │Fusion Engine │ │Backtest      │ │Knowledge/RAG │
             │多模型融合     │ │历史验证       │ │古籍证据中心  │
             └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
                    │                │                 │
                    └────────────────┼─────────────────┘
                                     ▼
                             ┌────────────────┐
                             │ Narrator / LLM │
                             │ AI解释器        │
                             └───────┬────────┘
                                     │
                                     ▼
                          ┌─────────────────────┐
                          │综合报告 / 月 / 周预测│
                          └─────────────────────┘
```

---

# 8. 当前建议使用的公开项目

## 8.1 lunar-python

GitHub：

```text
https://github.com/6tail/lunar-python
```

职责：

```text
公历 / 农历
干支
节气
八字基础时间
生肖
五行
十神基础数据
彭祖百忌
吉神方位
财神方位
胎神
冲煞
纳音
星宿
建除十二值星
十二神
黄道日
```

定位：

> 整个平台的“历法与时间基础设施”。

不建议复制源码。

使用：

```text
Python dependency + adapter
```

---

# 9. bazi-pro

当前可访问仓库：

```text
https://github.com/new1234cq/bazi-pro
```

注意：

原 README、版权和提交历史仍大量指向原 `Minervaowl7/bazi-pro`，
目前这个仓库更像迁移、镜像或保存版本，不能确认当前账号与原作者之间的官方关系。

因此建议：

> 在开始开发当天立即 fork / 镜像到自己的 GitHub 私有组织，并锁定 commit。

## 9.1 可以复用

重点保留：

```text
旺衰
五行力量
十神
藏干
格局
喜用神
忌神
刑冲合害
破格
调候
子平
盲派
新派
证据链
古籍检索
Hybrid Search
报告结构
```

## 9.2 不建议直接照搬

目前其中的人生运势分数不能直接作为股票涨跌模型。

例如：

```text
用神 +20
喜神 +10
忌神 -20
```

这种人为规则可以作为初始研究假设，但是不能直接定义：

```text
股票涨跌概率
```

股票评分必须进入新的：

```text
Stock Metaphysics Factor Engine
```

并接受历史数据验证。

---

# 10. bazi-pro 古籍能力必须重点保留

bazi-pro 当前包含较大的：

```text
classical_corpus.md
```

并已经包含：

```text
BM25
Embedding
FAISS
古籍权威权重
主题匹配
```

这是本项目非常有价值的一部分。

但是不要继续把古籍系统锁死在 `bazi-pro` 中。

应逐渐抽离成为：

```text
Metaphysics Knowledge Center
```

---

# 11. 紫微斗数：iztro

GitHub：

```text
https://github.com/SylarLong/iztro
```

当前建议它作为：

> 紫微斗数主计算引擎。

可以获取：

```text
十二宫
主星
辅星
四化
三方四正
大限
小限
流年
流月
流日
流时
动态星曜
飞星
```

建议：

```text
TypeScript 独立 service
```

例如：

```text
services/ziwei-service
```

由 Python 主 API 通过内部 HTTP 或进程调用。

不要为了统一语言而重新手写一套紫微排盘。

---

# 12. Tianji

GitHub：

```text
https://github.com/Zijian-Ni/tianji
```

当前可以作为：

```text
八字第二计算源
紫微第二计算源
六爻计算源
算法交叉验证工具
```

V1 不建议让 Tianji 和 bazi-pro 同时参与最终八字评分。

更好的作用是：

```text
bazi-pro 算结果
Tianji 再算一次

一致：
PASS

不一致：
标记 calculation_conflict
```

这样可以发现第三方算法实现差异。

---

# 13. AKShare

GitHub：

```text
https://github.com/akfamily/akshare
```

职责：

```text
股票基础信息
上市日期
A股行情
日K
成交量
换手率
指数数据
行业数据
其他市场数据
```

所有第三方数据必须经过：

```text
market/adapter.py
```

统一格式，禁止业务层直接到处调用 AKShare API。

---

# 14. 回测层

建议不要让系统强绑定某一个回测框架。

统一定义：

```python
class BacktestProvider:
    def evaluate_factor(...)
    def evaluate_signal(...)
    def evaluate_consensus(...)
```

V1 可以优先自己实现：

```text
pandas
numpy
duckdb
```

所需的事件研究和因子验证。

这已经能够完成：

```text
未来5日收益
未来10日收益
未来20日收益
未来60日收益
最大上涨
最大回撤
超额收益
上涨比例
```

## 14.1 vectorbt

可用于大规模研究：

```text
https://github.com/polakowo/vectorbt
```

但是在最终商业化前，需要再次确认其当前许可证和使用边界。

因此：

> V1 可以作为可选 research adapter，不让它进入核心业务依赖。

## 14.2 Backtrader

可以作为替代引擎研究。

同样需要根据最终发布方式审查 GPL 等许可要求。

---

# 15. 不建议现在直接接入的模块

## 奇门

目前公开 GitHub 有一些奇门实现，但成熟度、流派定义、测试程度相差很大。

V1：

```text
只留接口
不正式启用
```

接口：

```python
class QimenEngine(MetaphysicsEngine):
    ...
```

等八字、黄历、紫微整个闭环跑通后再做。

---

# 16. 股票“出生时间”是第一重要研究变量

传统术数以人的出生时间为基础。

股票不存在传统定义中的出生时间。

因此这不是一个“技术问题”，而是：

> 一个必须回测验证的研究假设。

建议建立：

```text
StockBirthProfile
```

至少支持以下候选：

### A. 上市首个交易日开盘时刻

V1 默认模型：

```text
上市日期
+
该交易所当日实际开盘时间
```

不要把 `09:30` 永久硬编码。

交易所交易时段由配置表决定：

```text
exchange_session_calendar
```

### B. 首笔真实成交时刻

如果未来可以获得历史逐笔数据，则建立第二个版本。

### C. IPO 发行日期

作为候选。

### D. 公司成立时间

作为候选。

---

# 17. 出生时间版本必须保留

每次分析必须记录：

```json
{
  "stock_code": "600xxx",
  "birth_basis": "listing_open",
  "birth_datetime": "YYYY-MM-DDTHH:mm:ss+08:00",
  "exchange": "SSE",
  "timezone": "Asia/Shanghai",
  "source": "...",
  "birth_profile_version": "v1"
}
```

未来可以回测：

```text
上市时间模型
vs
公司成立时间模型
vs
IPO发行时间模型
```

谁更稳定。

不能靠主观“玄学经验”提前宣布哪一种一定正确。

---

# 18. 一个非常关键的问题：股票没有性别

传统八字大运和部分紫微运限计算会涉及：

```text
性别
阴阳
顺逆
```

股票没有真实性别。

禁止系统偷偷填写：

```text
男
```

然后继续计算。

这会造成基础模型伪精确。

建议从第一天设计：

```text
variant_mode
```

例如：

```text
bazi_forward
bazi_reverse
ziwei_variant_a
ziwei_variant_b
```

或者：

```text
direction_mode = both
```

把不同顺逆方案都算出来。

然后分别回测。

最终如果历史研究发现：

```text
顺排版本稳定
逆排版本无效
```

再决定是否进入正式评分模型。

这部分必须在报告中显示：

```text
本结果基于：运限顺排假设 V1
```

---

# 19. 统一术数引擎接口

所有未来术数必须实现相同接口：

```python
class MetaphysicsEngine:

    engine_id: str
    engine_version: str

    def calculate_chart(context):
        ...

    def extract_factors(chart, context):
        ...

    def explain_rules(chart, factors):
        ...

    def build_evidence_query(chart, factors):
        ...

    def score(factors):
        ...
```

返回统一：

```json
{
  "engine": "bazi",
  "engine_version": "...",
  "chart": {},
  "factors": [],
  "opinion": {},
  "evidence_queries": [],
  "assumptions": [],
  "warnings": []
}
```

---

# 20. 原始盘面必须存储

这是整个系统以后能够审计的关键。

不要只保存：

```text
八字评分 = 83
```

必须保存：

```json
{
  "chart_id": "...",
  "engine": "bazi",
  "input": {},
  "raw_chart": {},
  "engine_version": "...",
  "calculated_at": "...",
  "config_version": "..."
}
```

这样未来规则升级后才能重新计算并比较。

---

# 21. 八字引擎

建议第一版从 bazi-pro 抽象出：

```text
NatalChart
Strength
TenGod
Pattern
YongShen
JiShen
Interactions
TemporalInteraction
```

输出示例：

```json
{
  "pillars": {
    "year": "...",
    "month": "...",
    "day": "...",
    "hour": "..."
  },
  "day_master": "...",
  "strength": "...",
  "pattern": "...",
  "yongshen": [],
  "jishen": [],
  "ten_gods": {},
  "relations": []
}
```

---

# 22. 八字股票因子

建议第一批因子分为 5 组。

## 22.1 原局结构

```text
B_NATAL_001 日主强弱
B_NATAL_002 财星数量
B_NATAL_003 财星透干
B_NATAL_004 财星得令
B_NATAL_005 食伤结构
B_NATAL_006 官杀结构
B_NATAL_007 印星结构
B_NATAL_008 比劫结构
B_NATAL_009 格局类型
B_NATAL_010 用神五行
```

## 22.2 流年

```text
B_YEAR_001 流年天干用神
B_YEAR_002 流年地支用神
B_YEAR_003 流年财星
B_YEAR_004 流年食伤
B_YEAR_005 流年冲原局
B_YEAR_006 流年合原局
B_YEAR_007 流年刑原局
B_YEAR_008 流年害原局
```

## 22.3 流月

```text
B_MONTH_001 流月天干喜忌
B_MONTH_002 流月地支喜忌
B_MONTH_003 财星引动
B_MONTH_004 食伤生财
B_MONTH_005 官杀变化
B_MONTH_006 三合
B_MONTH_007 六合
B_MONTH_008 冲
B_MONTH_009 刑
B_MONTH_010 害
```

## 22.4 流日

用于周度模型。

```text
B_DAY_001 ~ B_DAY_xxx
```

周度不是创造“流周”。

而是：

```text
周内交易日流日因子聚合
```

---

# 23. 紫微斗数股票因子

第一版不要把十二宫全部强行解释成企业概念。

先建立“研究映射”。

例如：

```text
命宫    → 股票主体
财帛宫  → 资金/价格表现假设
官禄宫  → 经营/行业地位假设
迁移宫  → 外部市场环境假设
福德宫  → 市场情绪假设
疾厄宫  → 风险事件假设
父母宫  → 控股/监管环境假设
交友宫  → 机构/合作/产业链假设
```

注意：

> 这些只是研究假设，不是传统紫微斗数的“股票官方解释”。

必须进入回测。

第一批因子：

```text
Z_FIN_001 财帛宫主星
Z_FIN_002 财帛宫吉曜数量
Z_FIN_003 财帛宫煞曜数量
Z_FIN_004 财帛宫化禄
Z_FIN_005 财帛宫化权
Z_FIN_006 财帛宫化科
Z_FIN_007 财帛宫化忌

Z_FIN_010 财帛宫三方四正
Z_FIN_011 财帛宫三方见禄
Z_FIN_012 财帛宫三方见忌

Z_CAREER_001 官禄宫结构
Z_LIFE_001 命宫结构

Z_YEAR_xxx 流年
Z_MONTH_xxx 流月
Z_DAY_xxx 流日
```

---

# 24. 黄历 / 日课因子

黄历模块不能只展示：

```text
宜嫁娶
忌动土
```

这种与股票没有明显关系的信息。

应该重点抽取：

```text
日干支
月干支
岁干支
建除十二值
黄黑道
冲煞
十二神
纳音
与股票八字原局关系
与日主喜用关系
```

例如：

```text
H_DAY_001 当日天干是否喜神
H_DAY_002 当日地支是否喜神
H_DAY_003 当日与股票日支冲
H_DAY_004 当日六合
H_DAY_005 当日三合
H_DAY_006 建日/除日/满日...
H_DAY_007 黄道/黑道
```

传统黄历信息照常展示。

股票含义由：

```text
Factor Mapping
```

独立定义。

---

# 25. 六爻应该如何加入

六爻与八字、紫微不同。

八字和紫微偏向：

```text
出生盘 + 时间推进
```

六爻更适合：

```text
某一时点
针对某一个具体问题起卦
```

股票平台中以后可以定义：

```text
问题：
“股票 600xxx 在未来20个交易日整体走势如何？”
```

为了可回测：

> 起卦过程必须可重复。

优先研究：

```text
时间起卦
```

而不是人为随机摇铜钱。

历史回测时必须使用：

```text
当时的 as_of 时间
```

重建卦象。

禁止用今天时间回测过去。

---

# 26. 奇门应该如何加入

奇门同样更适合：

```text
时点型预测
```

例如：

```text
2027-04-01 09:00

600xxx
未来5个交易日
```

生成当时局盘。

以后可以研究：

```text
生门
开门
休门
值符
值使
星
神
宫位
旺衰
```

与未来：

```text
5D
10D
20D
```

收益之间的关系。

---

# 27. 统一因子模型

所有因子必须使用统一 schema。

```json
{
  "factor_id": "B_MONTH_003",
  "engine": "bazi",
  "timestamp": "...",
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

其中：

```text
direction

+1 正向
 0 中性
-1 负向
```

---

# 28. 不要把“财星”简单等于股票上涨

这是整个项目必须防止的最大逻辑错误之一。

传统：

```text
财星
```

是命理概念。

不能直接定义：

```text
财星出现 = 股价上涨
```

系统应该建立研究假设：

```text
财星出现
→ Factor
→ 历史数据验证
→ 得到统计效果
```

因此平台中的“股票财运”定义为：

> **传统术数中与财、势、机会、资源相关的结构，在股票历史数据中的实验性综合表现。**

不是：

> “传统命理保证股票上涨”。

---

# 29. 古籍知识中心架构

目录：

```text
knowledge/
│
├── bazi/
│   ├── ziping/
│   ├── ditiansui/
│   ├── qiongtong/
│   ├── sanming/
│   └── ...
│
├── ziwei/
│   ├── classical/
│   ├── sanhe/
│   └── ...
│
├── liuyao/
│   ├── zengshanbuyi/
│   └── ...
│
├── qimen/
│
└── common/
    ├── wuxing/
    ├── ganzhi/
    └── calendar/
```

---

# 30. 古籍条目结构

不要仅保存 Markdown 大文本。

最终需要拆成结构化条目：

```json
{
  "entry_id": "...",
  "domain": "bazi",
  "school": "ziping",
  "book": "子平真诠",
  "chapter": "...",
  "topic": [
    "财星",
    "食神",
    "格局"
  ],
  "original_text": "...",
  "normalized_text": "...",
  "modern_note": "...",
  "authority_weight": 1.0,
  "edition": "...",
  "source": "...",
  "license_status": "verified",
  "provenance": "..."
}
```

紫微：

```json
{
  "domain": "ziwei",
  "book": "...",
  "topic": [
    "财帛宫",
    "武曲",
    "化禄"
  ]
}
```

---

# 31. 古籍版权必须单独处理

古籍原文可能属于公版内容。

但是：

```text
现代整理本
现代白话翻译
现代注释
数据库整理成果
```

未必可以自由商用。

因此每一条语料必须包含：

```text
provenance
edition
license_status
```

不要因为某个 GitHub 仓库用了它，就自动认为可以商业使用。

---

# 32. RAG 检索架构

沿用 bazi-pro 的思路：

```text
BM25
+
Embedding
+
FAISS
+
Authority Weight
+
Topic Match
```

但是增加：

```text
domain filter
school filter
book filter
```

例如紫微请求：

```text
domain = ziwei
```

绝不能把八字典籍混进来。

---

# 33. 必须允许“反证”

古籍检索不要只找支持当前结论的句子。

应该：

```text
supporting_evidence
counter_evidence
```

同时检索。

最终报告：

```text
支持依据：
《……》

相反观点：
《……》

本系统采用规则：
……
```

这样能够明显降低“先有结论、后找古籍”的问题。

---

# 34. AI 的职责

AI 只负责：

```text
组织语言
解释盘面
解释规则
整理古籍
解释历史统计
解释模型冲突
```

AI 禁止负责：

```text
算八字
算紫微
算四化
算流月
算流日
计算收益率
凭空生成古籍
自己改分数
```

计算结果全部由代码产生。

---

# 35. 给 AI 的输入必须是结构化证据包

例如：

```json
{
  "stock": {},
  "bazi_chart": {},
  "ziwei_chart": {},
  "huangli": {},
  "factor_results": [],
  "consensus": {},
  "backtest_stats": {},
  "classical_evidence": []
}
```

然后 AI 才生成解释。

---

# 36. AI Prompt 核心规则

系统 Prompt 至少包含：

```text
1. 只能解释给定的确定性计算结果。
2. 不得重新排盘。
3. 不得修改干支、宫位、四化、星曜、卦象。
4. 不得编造古籍。
5. 古籍只能使用 evidence 中给出的来源。
6. 当不同术数结论冲突时必须明确说明冲突。
7. 不得强行形成统一结论。
8. 必须区分“传统术数判断”和“历史统计验证”。
9. 不得把术数结果表述为确定的股价预测。
10. 不得生成自动买入/卖出指令。
```

---

# 37. 多模型融合引擎

统一输入：

```text
BaziOpinion
ZiweiOpinion
HuangliOpinion
LiuyaoOpinion
QimenOpinion
```

每个包含：

```json
{
  "direction": 1,
  "score": 82,
  "confidence": 0.71,
  "top_positive_reasons": [],
  "top_negative_reasons": [],
  "historical_validity": {}
}
```

---

# 38. 共识分类

不要只用最终平均分。

建议：

```text
STRONG_POSITIVE_CONSENSUS
POSITIVE_CONSENSUS
MIXED
NEUTRAL
NEGATIVE_CONSENSUS
STRONG_NEGATIVE_CONSENSUS
```

例如：

```text
八字    +
紫微    +
黄历    +

=> POSITIVE_CONSENSUS
```

```text
八字    +
紫微    -
黄历    0

=> MIXED
```

---

# 39. 权重不能永久人工指定

第一版可以：

```text
各模型等权
```

用于展示。

但研究层必须学习：

```text
每一种术数
每一个周期
每一种市场环境
```

的历史有效性。

未来例如可能得到：

```text
20日窗口

八字        IC 0.04
紫微        IC 0.02
黄历        IC 0.00
组合        IC 0.06
```

那么融合权重再根据：

```text
样本外结果
稳定性
样本数
```

确定。

禁止根据“哪个术数听起来更准”赋权。

---

# 40. 最重要的研究层

真正的核心资产不是：

```text
bazi-pro
iztro
lunar-python
```

而是：

```text
Stock Metaphysics Factor Database
```

即：

```text
股票
日期
术数盘
全部因子
未来收益
```

长期积累后形成类似：

```text
3000+ 股票
×
3000+ 交易日
×
100~500 术数因子
```

的大型研究数据库。

---

# 41. 行情标签

每天生成：

```text
ret_1d
ret_5d
ret_10d
ret_20d
ret_60d
```

同时：

```text
max_return_5d
max_return_20d
max_drawdown_20d
excess_return_20d
```

基准：

```text
沪深300
中证500
所属行业指数
```

---

# 42. “上涨”不能只有一个定义

研究时至少拆为：

```text
absolute_up
excess_up
strong_up
drawdown_controlled_up
```

例如：

```text
absolute_up:
future_20d_return > 0

excess_up:
future_20d_return - benchmark > 0

strong_up:
future_20d_return > 10%
```

这样才能避免市场整体牛市时所有术数都显得“很准”。

---

# 43. 回测必须防止的错误

必须处理：

```text
未来数据泄漏
幸存者偏差
退市股票遗漏
复权问题
停牌
涨跌停
上市初期异常
行业偏差
大盘趋势影响
重复试验
参数过拟合
```

---

# 44. 最关键的验证方式：负对照

必须加入：

### 随机出生时间

随机打乱股票上市日期。

如果：

```text
真实命盘表现
≈
随机命盘表现
```

说明命理因子没有信息量。

### 日期平移

例如：

```text
出生日期 +7天
出生日期 -7天
```

比较。

### 随机因子

生成随机分数。

与术数因子比较。

这个模块对系统可信度非常重要。

---

# 45. 样本外验证

禁止：

```text
2010-2026全部训练
然后还用2010-2026宣布效果
```

建议：

```text
2010-2018 研究
2019-2022 验证
2023-2026 样本外
```

或者：

```text
Walk Forward
```

---

# 46. 数据存储建议

V1 本地：

```text
SQLite        配置 / 股票资料 / 任务
DuckDB        研究查询
Parquet       历史行情 / 大规模因子
FAISS         古籍向量
```

以后多用户：

```text
PostgreSQL
Object Storage
Qdrant / pgvector
```

---

# 47. 主要数据表

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

engine_opinion
consensus_run

classical_book
classical_entry
evidence_link

backtest_experiment
backtest_result
backtest_metric
```

---

# 48. 建议 Monorepo 结构

```text
stock-metaphysics-platform/
│
├── apps/
│   ├── web/
│   │   └── Next.js
│   │
│   └── api/
│       └── FastAPI
│
├── services/
│   └── ziwei-service/
│       └── iztro adapter
│
├── src/
│   ├── core/
│   │   ├── schemas/
│   │   ├── time/
│   │   ├── stock/
│   │   └── orchestration/
│   │
│   ├── engines/
│   │   ├── bazi/
│   │   ├── huangli/
│   │   ├── ziwei/
│   │   ├── liuyao/
│   │   └── qimen/
│   │
│   ├── factors/
│   │   ├── registry.py
│   │   ├── bazi/
│   │   ├── ziwei/
│   │   ├── huangli/
│   │   └── fusion/
│   │
│   ├── market/
│   │   ├── providers/
│   │   └── normalization/
│   │
│   ├── research/
│   │   ├── labels/
│   │   ├── event_study/
│   │   ├── backtest/
│   │   ├── statistics/
│   │   └── validation/
│   │
│   ├── knowledge/
│   │   ├── ingest/
│   │   ├── retrieval/
│   │   └── evidence/
│   │
│   └── narrator/
│
├── knowledge/
│   ├── bazi/
│   ├── ziwei/
│   ├── liuyao/
│   └── qimen/
│
├── data/
│   ├── raw/
│   ├── normalized/
│   ├── factors/
│   └── backtests/
│
├── tests/
│   ├── engines/
│   ├── factors/
│   ├── research/
│   └── integration/
│
├── docs/
│   ├── ADR/
│   ├── factor_dictionary.md
│   ├── engine_contract.md
│   └── methodology.md
│
├── docker-compose.yml
├── pyproject.toml
├── package.json
└── README.md
```

---

# 49. bazi-pro 建议单独 Fork

不要把 bazi-pro 全部源码直接复制到主项目。

建议自己维护：

```text
your-org/bazi-pro-stock
```

主项目固定：

```text
commit SHA
```

调用。

这样：

```text
bazi-pro 原项目变化
```

不会突然破坏主系统。

---

# 50. API 设计

## 股票分析

```http
POST /api/v1/stocks/{code}/analysis
```

请求：

```json
{
  "as_of": "2027-04-01T09:00:00+08:00",
  "horizon": [
    "1w",
    "1m",
    "3m"
  ],
  "engines": [
    "bazi",
    "ziwei",
    "huangli"
  ]
}
```

---

# 51. 获取原始盘

```http
GET /api/v1/analysis/{id}/charts/bazi
GET /api/v1/analysis/{id}/charts/ziwei
GET /api/v1/analysis/{id}/charts/huangli
```

未来：

```http
GET /charts/liuyao
GET /charts/qimen
```

---

# 52. 获取综合判断

```http
GET /api/v1/analysis/{id}/consensus
```

---

# 53. 获取证据

```http
GET /api/v1/analysis/{id}/evidence
```

---

# 54. 获取历史验证

```http
GET /api/v1/analysis/{id}/backtest
```

---

# 55. 推荐前端页面

## 首页

```text
┌─────────────────────────────┐
│ 输入股票代码                 │
│ [ 600xxx              ]分析 │
└─────────────────────────────┘
```

---

# 56. 综合页

顶部：

```text
股票名称
股票代码
上市时间
出生时间研究版本
分析基准时间
```

下面：

```text
未来1周
未来1月
未来3月
```

分别展示。

---

# 57. 多模型共识卡

```text
┌────────────────────────────────┐
│ 未来30日                        │
│                                │
│ 八字      ↑ 84                 │
│ 紫微      ↑ 79                 │
│ 黄历      ↑ 73                 │
│                                │
│ 术数共识：正向共振              │
│ 一致性：高                      │
│ 历史有效性：中等                │
└────────────────────────────────┘
```

---

# 58. 原始术数盘不能隐藏

用户点击：

```text
查看八字原盘
```

直接显示：

```text
年柱
月柱
日柱
时柱
藏干
十神
纳音
旺衰
```

紫微：

```text
12宫格
```

六爻：

```text
六爻卦图
```

奇门：

```text
九宫盘
```

---

# 59. 解释层建议固定模板

每一种术数都按：

```text
一、原始盘面
二、当前时间结构
三、正向因素
四、负向因素
五、财运相关判断
六、时间窗口
七、古籍依据
八、历史统计
九、不确定因素
```

输出。

---

# 60. 综合报告模板

最终综合部分：

```text
一、结论摘要

二、八字判断
  1. 原局
  2. 当前流年
  3. 当前流月
  4. 财运
  5. 时间窗口
  6. 古籍

三、紫微斗数
  1. 命盘
  2. 财帛宫
  3. 官禄宫
  4. 四化
  5. 流年
  6. 流月
  7. 时间窗口
  8. 古籍

四、黄历
  1. 当前月份
  2. 重点日期
  3. 冲合
  4. 吉凶因素

五、多模型共识

六、多模型分歧

七、历史回测

八、未来重点时间窗口

九、风险与模型限制
```

---

# 61. 月度预测

优先实现。

例如：

```text
2027

1月  八字 58  紫微 62  黄历 55
2月  八字 66  紫微 70  黄历 61
3月  八字 82  紫微 79  黄历 75
4月  八字 87  紫微 84  黄历 80
5月  八字 61  紫微 46  黄历 55
```

视觉：

```text
人生K线 / 运势河流
```

可以借鉴 bazi-pro roadmap 中的理念。

---

# 62. 周度预测

传统八字没有“流周”。

不要自己制造一个“周柱”。

应该：

```text
流日
↓
交易周聚合
```

例如：

```text
周一  81
周二  73
周三  86
周四  79
周五  75

周度 = 聚合
```

紫微如果有：

```text
流日
```

同样聚合。

黄历天然按日计算。

---

# 63. 周聚合不要简单平均

未来可以研究：

```text
mean
median
min
max
positive_day_ratio
weighted_by_trading_day
```

然后通过历史验证确定哪种更稳定。

---

# 64. V1 技术栈

## Backend

```text
Python 3.11+
FastAPI
Pydantic
SQLAlchemy
DuckDB
Pandas
NumPy
PyArrow
```

Python 3.11+ 也更符合当前 AKShare 的要求。

---

# 65. Frontend

建议：

```text
Next.js
TypeScript
Tailwind
ECharts
Zustand
```

bazi-pro 已使用类似技术栈，可以参考其 UI 思路，但建议主平台重新建立统一前端。

---

# 66. 紫微服务

```text
Node.js
TypeScript
iztro
```

提供：

```http
POST /internal/ziwei/chart
```

主 FastAPI 调用。

---

# 67. 古籍检索

```text
jieba
BM25
sentence-transformers
FAISS
```

第一版可以直接复用 bazi-pro 的检索思路。

---

# 68. Docker

最终：

```text
docker compose up
```

启动：

```text
api
web
ziwei-service
```

V1 不需要 Redis、Kafka、Kubernetes。

不要过度设计。

---

# 69. 实施阶段

---

# Phase 0：项目冻结与审计

目标：

```text
建立可重复开发基础
```

任务：

- 创建主仓库；
- fork bazi-pro；
- 记录所有第三方 commit SHA；
- 建立 `THIRD_PARTY.md`；
- 建立许可证清单；
- 建立技术 ADR；
- Docker 基础；
- CI；
- 测试框架。

验收：

```text
全新机器可以一条命令启动
```

---

# Phase 1：股票代码 → 八字 + 黄历

这是 MVP 第一阶段。

实现：

```text
股票代码
↓
股票基础信息
↓
上市日期
↓
StockBirthProfile
↓
lunar-python
↓
四柱
↓
bazi-pro
↓
八字原盘
↓
黄历
```

此阶段暂时：

```text
不做 AI
不做紫微
不做最终预测
```

验收：

输入任意支持的 A 股代码。

必须稳定输出：

```text
股票基础资料
出生档案
四柱
十神
五行
格局
喜忌
流年
流月
黄历
```

---

# Phase 2：行情与历史标签

接入：

```text
AKShare
```

创建：

```text
daily bars
future labels
benchmark labels
```

验收：

任意一个历史日期能够计算：

```text
未来5日
10日
20日
60日
```

收益。

---

# Phase 3：八字因子系统

把八字拆成：

```text
50~100 个结构化因子
```

建立：

```text
factor_definition
factor_observation
```

每一个因子必须：

```text
有 ID
有定义
有版本
有来源
有解释
```

---

# Phase 4：八字历史回测

第一次回答真正关键的问题：

```text
这些因子到底有没有统计信息量？
```

输出：

```text
样本数
上涨率
平均收益
超额收益
最大回撤
IC
稳定性
```

必须加入随机对照。

---

# Phase 5：古籍知识中心

从 bazi-pro 中：

```text
迁出古籍
结构化
加 metadata
建立 BM25
建立 Embedding
建立 FAISS
```

先只支持：

```text
domain=bazi
```

---

# Phase 6：八字 AI 解释

此时才接 LLM。

AI 输入：

```text
确定盘面
确定因子
确定统计结果
确定古籍
```

AI 只负责解释。

---

# Phase 7：紫微斗数

加入：

```text
iztro
```

先完成：

```text
股票出生档案
↓
紫微原盘
```

解决：

```text
股票无性别
顺逆运限
```

的实验版本问题。

---

# Phase 8：紫微因子

拆解：

```text
财帛宫
官禄宫
命宫
四化
三方四正
大限
流年
流月
流日
```

形成：

```text
Z_xxx
```

---

# Phase 9：多模型融合

开始：

```text
八字
+
紫微
+
黄历
```

输出：

```text
共识
冲突
各自理由
```

---

# Phase 10：月度 / 周度预测 UI

实现：

```text
月份运势曲线
周度热力图
重点日期
```

用户点击任意月：

```text
查看八字依据
查看紫微依据
查看黄历依据
查看历史统计
查看古籍
```

---

# Phase 11：六爻

此时再引入。

优先：

```text
Tianji
```

并进行算法审计。

---

# Phase 12：奇门

最后加入。

先选择/自研一个经过大量案例验证的确定性排盘模块。

不要让 LLM 自己排奇门盘。

---

# 70. 推荐开发顺序

严格建议：

```text
八字
↓
八字回测
↓
古籍
↓
紫微
↓
多模型
↓
黄历增强
↓
六爻
↓
奇门
```

不是：

```text
一次性把所有术数都做出来。
```

原因：

如果八字的：

```text
出生时间
因子体系
回测方法
数据模型
```

都没有稳定，

同时开发五种术数，只会得到五套无法验证的系统。

---

# 71. 本项目最重要的代码资产

优先级从高到低：

## 1

```text
Factor Registry
```

## 2

```text
Stock Birth Profile
```

## 3

```text
Backtest / Validation
```

## 4

```text
Consensus Engine
```

## 5

```text
Metaphysics Knowledge Center
```

## 6

```text
Engine Adapter
```

第三方排盘库本身不是护城河。

---

# 72. 版本管理

每次结果必须记录：

```text
birth_profile_version
engine_version
factor_version
knowledge_version
fusion_version
market_data_version
narrator_prompt_version
```

否则未来无法解释：

> “为什么同一只股票上个月算83分，今天重新跑变成76分？”

---

# 73. 可重复性

任何一次历史预测必须可以用：

```text
stock_code
as_of
engine_version
config_version
```

重新生成完全相同结果。

---

# 74. 最重要的测试

## 排盘测试

准备黄金案例：

```text
Golden Cases
```

分别验证：

```text
四柱
节气
十神
紫微十二宫
四化
流年
流月
```

---

# 75. 双引擎测试

例如：

```text
bazi-pro
vs
Tianji
```

计算相同案例。

差异必须进入：

```text
docs/calculation-differences.md
```

禁止静默忽略。

---

# 76. 因子测试

每个因子：

```text
fixture
→
expected factor
```

---

# 77. 数据泄漏测试

专门写：

```text
test_no_future_data_access.py
```

确保：

```text
as_of = 2020-01-01
```

绝对不能获取 2020-01-02 以后信息作为输入特征。

---

# 78. 最终用户输出例子

以下只是产品格式示意，不代表任何真实股票结论。

```text
股票：XXXX
预测周期：未来20交易日

━━━━━━━━━━━━━━━━━━
一、多模型总览
━━━━━━━━━━━━━━━━━━

八字：
82 / 100
方向：偏强

紫微：
78 / 100
方向：偏强

黄历：
69 / 100
方向：温和偏强

术数一致性：
高

当前状态：
多模型正向共振

━━━━━━━━━━━━━━━━━━
二、八字
━━━━━━━━━━━━━━━━━━

原局：
XXXX XXXX XXXX XXXX

日主：
X

喜用：
X、X

当前流月：
XXXX

正向因素：
1. …
2. …
3. …

负向因素：
1. …
2. …

财运判断：
……

古籍：
《……》
“……”

历史验证：
类似状态 N=xxx
未来20日上涨率 xx%
平均收益 xx%

━━━━━━━━━━━━━━━━━━
三、紫微斗数
━━━━━━━━━━━━━━━━━━

命宫：
……

财帛宫：
……

官禄宫：
……

当前四化：
……

流月：
……

财运相关判断：
……

古籍：
……

━━━━━━━━━━━━━━━━━━
四、黄历 / 日课
━━━━━━━━━━━━━━━━━━

本月重点：
……

重点交易日：
……

冲合：
……

━━━━━━━━━━━━━━━━━━
五、模型分歧
━━━━━━━━━━━━━━━━━━

当前三套模型方向一致。

如果存在分歧：

八字认为……
但紫微认为……

造成分歧的核心原因是……

━━━━━━━━━━━━━━━━━━
六、历史统计
━━━━━━━━━━━━━━━━━━

同类八字：
……

同类紫微：
……

双模型共振：
……

三模型共振：
……

━━━━━━━━━━━━━━━━━━
七、结论
━━━━━━━━━━━━━━━━━━

传统术数模型当前形成较明显正向共识。

但历史样本有效性为……
因此属于：

“术数共识较强 / 统计支持中等”

而不是确定性价格预测。
```

---

# 79. “盘面展示”是硬性验收项

所有 AI 编程任务中加入：

> 禁止只实现分数而不实现原始盘面展示。

V1 必须：

```text
八字有四柱盘
紫微有十二宫盘
黄历有日课信息
```

未来：

```text
六爻有卦
奇门有九宫盘
```

---

# 80. “分歧展示”也是硬性验收项

禁止：

```text
八字 +90
紫微 -80
最终平均 55
```

然后告诉用户：

```text
“整体一般”
```

必须显示：

```text
重大分歧
```

并分别解释。

---

# 81. 未来更高级的融合方式

当拥有足够历史样本后，可以研究：

```text
八字 + 紫微
八字 + 黄历
紫微 + 黄历
八字 + 紫微 + 黄历
```

共振组合。

例如：

```text
单独八字信号
样本 N=1200
上涨率 54%

单独紫微信号
样本 N=900
上涨率 55%

八字+紫微同向
样本 N=310
上涨率 62%

八字+紫微+黄历同向
样本 N=120
上涨率 67%
```

这可能比单一术数评分更值得研究。

但是必须：

```text
样本外验证
```

之后才能进入正式权重。

---

# 82. 可加入传统技术分析，但必须独立

未来可以加入：

```text
MA
MACD
RSI
量价
趋势
波动率
资金流
```

形成：

```text
Metaphysics Model
vs
Technical Model
```

不要一开始混在一起。

这样才能回答：

> “玄学因子本身有没有增量信息？”

以后再研究：

```text
传统技术面 + 术数
```

是否改善。

---

# 83. 系统边界

平台定位：

```text
研究
实验
传统文化
量化验证
```

不是：

```text
自动交易系统
荐股系统
收益保证系统
```

至少 V1-V3 不接：

```text
券商自动下单
自动买卖
资金账户
```

---

# 84. 给本地 AI 的实施规则

把以下内容直接加入项目根目录：

```text
AGENTS.md
```

内容建议：

```text
1. 本系统所有术数排盘必须由确定性代码产生，禁止 LLM 计算。
2. LLM 只能解释结构化结果。
3. 每个引擎必须保留 raw_chart。
4. 每个因子必须有唯一 factor_id。
5. 每个因子必须有 version。
6. 每个结果必须记录 engine_version。
7. 所有历史测试必须遵守 as_of，不得读取未来数据。
8. 模型分歧不得被平均值隐藏。
9. 古籍必须带 source 和 provenance。
10. 不得编造古籍条文。
11. 第三方代码必须通过 adapter 接入。
12. 禁止在业务层直接依赖第三方对象。
13. 所有第三方依赖必须锁版本。
14. 新术数必须实现 MetaphysicsEngine 接口。
15. 新行情源必须实现 MarketDataProvider 接口。
16. 新回测框架必须实现 BacktestProvider 接口。
17. 所有计算必须有单元测试。
18. 所有关键算法必须有 Golden Case。
19. 不允许因为“输出更好看”而修改计算结果。
20. 所有结论必须可追溯到：盘面 → 因子 → 规则 → 证据。
```

---

# 85. 建议第一批开发 Ticket

## T001

创建 monorepo。

## T002

实现公共 schema。

## T003

实现 AKShare adapter。

## T004

实现股票基础资料解析。

## T005

实现 StockBirthProfile。

## T006

接入 lunar-python。

## T007

实现 HuangliEngine。

## T008

fork bazi-pro。

## T009

实现 BaziEngine adapter。

## T010

保存 raw_chart。

## T011

实现第一批八字因子。

## T012

实现行情标签。

## T013

实现 Event Study。

## T014

实现随机出生日期负对照。

## T015

迁移 bazi-pro 古籍。

## T016

实现统一 Knowledge Center。

## T017

实现 EvidenceRetriever。

## T018

实现 Narrator。

## T019

接入 iztro。

## T020

实现 ZiweiEngine。

## T021

实现紫微 raw_chart。

## T022

实现紫微第一批因子。

## T023

实现 ConsensusEngine。

## T024

实现 ConflictDetector。

## T025

实现综合页面。

## T026

实现月度运势曲线。

## T027

实现周度聚合。

## T028

实现历史统计页面。

## T029

加入 Tianji 双引擎验证。

## T030

准备六爻插件接口。

---

# 86. V1 MVP 的范围

真正第一版不要做得太大。

只做：

```text
A股
+
股票代码输入
+
上市时间研究档案
+
八字
+
黄历
+
历史行情
+
八字因子
+
历史验证
+
古籍
+
AI解释
```

V1.5：

```text
+ 紫微
```

V2：

```text
+ 多模型共识
+ 月/周预测
```

V3：

```text
+ 六爻
+ 奇门
```

---

# 87. 第一版完成的定义

输入：

```text
一只A股股票代码
```

系统自动：

```text
1 股票资料
2 出生档案
3 八字排盘
4 黄历
5 当前流年流月
6 八字财运相关结构
7 未来12个月评分
8 每月详细解释
9 古籍依据
10 历史同类状态统计
11 原始盘面
```

做到这里以后再接紫微。

---

# 88. 第二阶段完成的定义

加入紫微后：

```text
八字
紫微
黄历
```

全部输出：

```text
盘
分
理由
古籍
历史验证
```

然后实现：

```text
共识
冲突
```

这时才真正形成：

> **股票玄学多模型研究平台**

---

# 89. 开发决策总结

当前建议的核心组合：

```text
6tail/lunar-python
       │
       ├── 历法
       └── 黄历

new1234cq/bazi-pro
       │
       ├── 八字规则
       ├── 多流派
       └── 古籍框架

SylarLong/iztro
       │
       └── 紫微斗数

Zijian-Ni/tianji
       │
       ├── 六爻
       └── 第二计算源

akfamily/akshare
       │
       └── 股票行情

自研
       │
       ├── StockBirthProfile
       ├── Factor Registry
       ├── Backtest
       ├── Consensus
       ├── Conflict Detection
       ├── Stock Metaphysics Knowledge Center
       └── Narrator
```

---

# 90. 不建议采用的架构

不要：

```text
把6个GitHub项目源码全部复制进一个仓库。
```

不要：

```text
让GPT自己算命盘。
```

不要：

```text
只做一个0-100分。
```

不要：

```text
把财星直接等同于股价上涨。
```

不要：

```text
出现模型冲突后强行平均。
```

不要：

```text
用全部历史数据调参数后宣布预测有效。
```

---

# 91. 最终技术目标

最终系统应该回答的不只是：

> “600xxx 下个月运势多少分？”

而是：

```text
为什么八字认为它偏强？

具体是什么盘面？

哪几个流月因素触发？

古籍怎么说？

紫微是否同意？

紫微的财帛宫和四化怎么表现？

黄历是否同向？

三个术数有没有共振？

如果不同意，分歧在哪里？

类似历史状态出现过多少次？

后20个交易日实际上涨比例多少？

这种共振在样本外是否仍然有效？
```

如果这些问题全部能被回答，

这个项目才真正从：

> “玄学股票小工具”

升级成为：

> **可计算、可解释、可追溯、可回测、可扩展的股票玄学多模型研究平台。**

---

# 92. 最终一句话架构

> **第三方项目负责“算盘”，自研 Factor Engine 负责“把盘变成可研究变量”，Backtest Engine 负责“验证这些变量有没有历史信息量”，Knowledge Center 负责“说明古籍依据”，Consensus Engine 负责“判断多个术数是否共振或冲突”，LLM 最后只负责把以上确定性结果解释成人能看懂的研究报告。**

---

# 93. 供本地 AI 开始工作的首个总任务

建议不要把整份文档一次性要求 AI 全部实现。

第一个任务只下达：

```text
请阅读《股票玄学多模型研究平台 V1.0》架构文档。

当前只实施 Phase 0 和 Phase 1。

要求：

1. 创建 stock-metaphysics-platform monorepo。
2. 创建 FastAPI backend。
3. 建立 SQLite + DuckDB 基础。
4. 建立 StockMaster 和 StockBirthProfile schema。
5. 接入 AKShare，但必须通过 MarketDataProvider adapter。
6. 接入 lunar-python，但必须通过 CalendarEngine adapter。
7. 实现 HuangliEngine。
8. 预留 MetaphysicsEngine 抽象接口。
9. 接入我们 fork 后的 bazi-pro，但只能通过 BaziEngine adapter。
10. 输入股票代码后能够：
   - 获取股票信息；
   - 获取上市日期；
   - 构造 listing_open 出生档案；
   - 生成八字；
   - 生成黄历；
   - 保存 raw_chart。
11. 此阶段禁止实现 AI 解读。
12. 此阶段禁止实现综合评分。
13. 此阶段禁止实现紫微。
14. 所有计算编写单元测试。
15. 生成 README、架构说明、数据库说明和运行命令。
16. 所有依赖锁定版本与 commit。
17. 如果第三方库结果存在不确定性，不得自行猜测，必须记录 assumption/warning。

完成后输出：
- 项目目录；
- 已完成模块；
- 测试结果；
- 待解决问题；
- 下一阶段建议。
```

这会比直接让 AI：

```text
“帮我做一个股票算命网站”
```

可靠得多。

---

# 94. 开源项目参考

- lunar-python  
  https://github.com/6tail/lunar-python

- bazi-pro 当前可访问版本  
  https://github.com/new1234cq/bazi-pro

- iztro  
  https://github.com/SylarLong/iztro

- Tianji  
  https://github.com/Zijian-Ni/tianji

- AKShare  
  https://github.com/akfamily/akshare

- vectorbt（研究阶段可选）  
  https://github.com/polakowo/vectorbt

- backtrader（替代研究引擎候选，正式使用前审查许可证）  
  https://github.com/mementum/backtrader

---

# 95. 最后提醒

传统八字、紫微斗数、黄历、六爻、奇门与股票未来收益之间，并不存在经过现代金融科学确认的稳定因果关系。

因此本系统最重要的价值不应该建立在：

```text
“传统术数一定能预测股票”
```

这个前提上。

更合理的研究框架是：

```text
传统术数
↓
确定性计算
↓
结构化因子
↓
历史数据
↓
统计检验
↓
样本外验证
↓
保留有效信号 / 淘汰无效信号
```

最终让数据回答：

> 哪些传统术数结构在历史股票数据上存在稳定统计关系，哪些不存在。

这也是整个项目最值得长期积累的部分。
