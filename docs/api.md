# API 参考 · Phase 1

> Base URL：`http://127.0.0.1:8000`
> 交互式文档：`/docs`（Swagger UI） · `/redoc` · 机器可读：`/openapi.json`
> 共 **30 个端点**。

---

## 0. 通用约定

### 0.1 错误格式

所有错误统一返回：

```json
{
  "error": {
    "code": "MARKET_PROVIDER_UNAVAILABLE",
    "message": "无法获取 600519 的行情数据",
    "detail": "ProxyError: Unable to connect to proxy",
    "retryable": true
  }
}
```

| `code` | HTTP | 说明 | 可重试 |
|---|---|---|---|
| `VALIDATION_ERROR` | 422 | 请求参数校验失败 | ❌ |
| `INVALID_REQUEST` | 422 | 业务参数非法（代码无法解析等） | ❌ |
| `BIRTH_PROFILE_ERROR` | 422 | 出生档案无法构造（缺少数据源等） | ❌ |
| `STOCK_NOT_FOUND` | 404 | 股票不存在 | ❌ |
| `NOT_FOUND` | 404 | 分析记录 / 实验不存在 | ❌ |
| `MARKET_INSUFFICIENT_DATA` | 422 | 行情数据不足 | ❌ |
| `MARKET_PROVIDER_UNAVAILABLE` | 503 | 第三方数据源不可达 | ✅ |
| `FUTURE_DATA_ACCESS` | 500 | **检测到未来数据访问（P0）** | ❌ |
| `INTERNAL_ERROR` | 500 | 未捕获异常 | ✅ |

### 0.2 时间参数

`as_of` 支持 `YYYY-MM-DD` / `YYYY-MM-DDTHH:MM:SS` / 带时区的 ISO8601。
带时区时会转换到 `Asia/Shanghai`，内部统一按 naive 本地时间处理。

### 0.3 不可用语义

**任何不可用字段返回 `null` / `"unavailable"`，绝不用 `0` 冒充。**
例：紫微在 Phase 1 返回 `available: false, score: null`。

---

## 1. 股票 `/api/v1/stocks`

### 1.1 `GET /api/v1/stocks/search`

搜索 A 股股票。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `q` | string | ✅ | 代码 / 名称 / 拼音片段（≥1 字符） |
| `limit` | int | | 默认 20，1–100 |

```bash
curl "http://127.0.0.1:8000/api/v1/stocks/search?q=茅台"
```

```json
{
  "items": [{
    "stock_code": "600519", "wind_code": "600519.SH", "name": "贵州茅台",
    "exchange": "SSE", "board": "主板", "listing_date": "2001-08-27"
  }],
  "total": 1, "query": "茅台", "source": "akshare", "is_degraded": false, "warnings": []
}
```

> `is_degraded: true` 表示当前运行在离线合成数据模式（`SMP_MARKET_PROVIDER=synthetic`）。

### 1.2 `GET /api/v1/stocks/{code}`

获取股票详情，并附带**已持久化**的出生档案（若存在）。

| 参数 | 说明 |
|---|---|
| `code` | 股票代码（`600519` / `600519.SH` / `sh600519` 均可） |
| `as_of` | 可选，用于读取对应时刻的档案 |

响应：`{ stock, birth_profile, session_key, warnings }`

### 1.3 `POST /api/v1/stocks/{code}/birth-profile`

构造 / 刷新股票出生档案。

```json
{
  "birth_basis": "listing_open",
  "variant_mode": "not_applicable",
  "override_datetime": null,
  "exchange_override": null,
  "persist": true
}
```

| 字段 | 取值 | 说明 |
|---|---|---|
| `birth_basis` | `listing_open`（默认）/ `ipo_date` / `company_foundation` / `first_trade` / `custom` | 见下方说明 |
| `variant_mode` | `not_applicable`（默认）/ `forward` / `reverse` / `both` | 股票无性别 |
| `override_datetime` | ISO8601 | 仅 `custom` 时使用 |

响应（`StockBirthProfile`）：

```json
{
  "stock_code": "600519",
  "exchange": "SSE",
  "birth_basis": "listing_open",
  "birth_datetime": "2001-08-27T09:30:00+08:00",
  "timezone": "Asia/Shanghai",
  "birth_profile_version": "v1",
  "evidence": {
    "listing_date": "2001-08-27",
    "first_trading_day": "2001-08-27",
    "session_name": "continuous_trading",
    "session_open_time": "09:30:00",
    "timezone": "Asia/Shanghai",
    "derivation": "listing_open = 上市首个正式交易日(2001-08-27) + SSE/DEFAULT 正式开盘(09:30) + Asia/Shanghai",
    "lookup_key": "SSE/DEFAULT"
  },
  "assumptions": [{
    "key": "birth.listing_open",
    "value": "2001-08-27T09:30:00+08:00",
    "reason": "股票不存在传统意义的出生时间；本系统以『上市首日正式开盘时刻』作为默认研究假设",
    "impact": "该假设本身是需要被历史回测检验的对象，而非既定事实"
  }],
  "data_quality": { "grade": "B", "score": 0.85, "notes": ["Phase 1 未接入独立交易日历表，交易日仅按周末规则校验"] },
  "variant_mode": "not_applicable",
  "variant_note": "股票不存在真实性别。运限顺逆依赖性别，因此 Phase 1 不启用大运，variant_mode=not_applicable；如需研究可显式切换为 forward/reverse/both。"
}
```

**各基准的可用性（重要）**

| `birth_basis` | 状态 | 说明 |
|---|---|---|
| `listing_open` | ✅ 默认 | 数据完整 |
| `custom` | ✅ | 需传 `override_datetime` |
| `ipo_date` | ⚠️ 降级 | Phase 1 无独立发行日数据源，用 `listing_date` 近似，`data_quality.grade = "C"` |
| `company_foundation` | ❌ 报错 | 返回 `BIRTH_PROFILE_ERROR`，**不猜测** |
| `first_trade` | ❌ 报错 | 需要历史逐笔数据，**不猜测** |

### 1.4 `POST /api/v1/stocks/{code}/birth-profile/compare`

对比不同出生基准的推导结果（Phase 2 做"出生模型谁更稳定"的接口雏形）。

```json
{
  "stock_code": "600519",
  "as_of": "2024-11-15T14:32:00",
  "baselines": [
    { "birth_basis": "listing_open", "ok": true, "birth_datetime": "2001-08-27T09:30:00+08:00", "quality": {...}, "evidence": {...} },
    { "birth_basis": "ipo_date", "ok": true, "birth_datetime": "2001-08-27T00:00:00+08:00", "quality": {...}, "evidence": {...} }
  ],
  "note": "不同出生基准的优劣必须由历史回测决定（见 docs/methodology.md），本接口不预设哪一种正确。"
}
```

---

## 2. 分析 `/api/v1/analysis`

### 2.1 `POST /api/v1/stocks/{code}/analysis/bazi`

**执行分析主链路**：股票 → 出生档案 → 历法 → 黄历 → 八字原盘 → 因子 → 落库。

```json
{
  "as_of": "2024-11-15T14:32:00",
  "horizon": "20d",
  "birth_basis": "listing_open",
  "variant_mode": "not_applicable",
  "variant_basis": "explicit",
  "huangli_days": 31,
  "persist": true
}
```

| 字段 | 取值 | 说明 |
|---|---|---|
| `variant_mode` | `not_applicable`（默认）/ `forward` / `reverse` / `both` | 运限顺逆；股票无性别，不得默认填 |
| `variant_basis` | `explicit`（默认）/ `first_day_yinyang` | 顺逆的**来源口径**（2026-09-23 新增，ADR-0014）：后者由 `stock_master.first_day_yinyang` 推导（阳→`forward`/男命、阴→`reverse`/女命），此时 `variant_mode` 必须保持 `not_applicable`，否则 `422 BIRTH_PROFILE_ERROR`；缺首日数据 → `not_applicable` + 原因，不输出大运 |

响应（`BaziAnalysisResponse`）：

```json
{
  "analysis_id": "AN-20241115143200-600519-a1b2c3",
  "stock": { ... },
  "birth_profile": { ... },
  "chart": {
    "year_pillar":  { "position": "year",  "ganzhi": { "stem": "辛", "branch": "巳", "text": "辛巳", "nayin": "白蜡金" },
                      "stem_ten_god": "正印",
                      "hidden_stems": [ {"stem":"丙","ten_god":"偏财","rank":"本气","weight":0.6}, ... ],
                      "hidden_ten_gods": ["偏财","偏印","七杀"], "di_shi": "绝" },
    "month_pillar": { ... }, "day_pillar": { ... }, "hour_pillar": { ... },
    "day_master": "壬", "day_master_wuxing": "水",
    "wuxing": { "scores": {...}, "percentages": {"木":11.76,"火":27.29,"土":12.59,"金":33.65,"水":14.71},
                "dominant": "金", "weakest": "木", "missing": [] },
    "day_master_analysis": { "strength_level": "中和", "balance_ratio": 0.4835, "confidence": 0.5,
                             "de_ling": false, "de_di": true, "de_shi": false },
    "pattern": { "primary": "偏印格", "category": "印格", "confidence": 0.72, "availability": "ok",
                 "method": "月令本气/透干取格（子平通行法）", "candidates": [...] },
    "yong_shen": { "yong_shen": ["木"], "xi_shen": ["火"], "ji_shen": [], "method": "扶抑法（主）+ 调候法（辅）",
                   "tiaohou_note": "春秋月生，寒暖适中，调候需求较低", "rationale": [...] },
    "relations": [ {"relation_type":"相刑","positions":["year","month"],...}, ... ],
    "current_year_pillar":  { "kind":"year",  "ganzhi":{"text":"甲辰"}, "stem_ten_god":"食神", "stem_is":"用神", ... },
    "current_month_pillar": { "kind":"month", "ganzhi":{"text":"乙亥"}, "clashes_with_natal":["year","hour"], ... },
    "current_day_pillar":   { "kind":"day",   "ganzhi":{"text":"癸未"}, ... },
    "variant_mode": "not_applicable", "da_yun": [], "da_yun_note": "大运顺逆由性别…",
    // variant_mode ∈ {forward, reverse, both} 时 da_yun 为 10 步：
    //   [{"start_year":2001,"end_year":2007,"ganzhi":"","start_age":1,"is_current":false},
    //    {"start_year":2008,"end_year":2017,"ganzhi":"乙未","start_age":8,"is_current":false}, ...]
    // 第一条是 lunar-python 的「起运前」占位行（ganzhi 为空串）；is_current 由后端按 as_of 判定。
    "engine_version": "smx-bazi-native-1.0.0", "assumptions": [...], "warnings": [...]
  },
  "huangli": { "primary": {...}, "days": [31 天], "raw_huangli": {...} },
  "factors": { "observations": [ 65 条 ], "rule_version": "v1", "engine_version": "..." },
  "opinion": {
    "engine": "bazi", "availability": "ok", "direction": 1, "score": 68.19, "confidence": 0.7408,
    "top_positive_reasons": [{"text":"…","factor_ids":["B_MONTH_001"],"rule_score":8.0}],
    "top_negative_reasons": [...],
    "factor_ids": ["B_NATAL_001", ...],
    "note": "该分数由传统规则强度聚合而成，属于研究性指标，**不代表收益率预测，也不代表上涨概率**。"
  },
  "versions": { "engine_version": "...", "rule_version": "v1", "config_version": "...",
                "birth_profile_version": "v1", "knowledge_version": "kb-1.0.0", ... },
  "warnings": []
}
```

> **`opinion.score` 的语义**：传统规则强度的加权聚合（0–100），
> **不是预期收益率，也不是上涨概率**。`top_positive_reasons` 中的 `factor_ids`
> 可以逐条追溯到因子定义与盘面依据。

> `POST /api/v1/stocks/{code}/analysis/multi` 的请求体与本节相同，`variant_basis`
> 在那里同时决定**八字大运顺逆**与**紫微大限方向**：推出来的方向是"这只标的的运限
> 往哪边走"这一个假设，不在两个引擎里给出两个方向（ADR-0014）。
> 紫微单端点 `/analysis/ziwei` 只接受 `variant_basis=explicit`（方向来源口径属 ADR-0010）。

### 2.2 `GET /api/v1/analysis/{analysis_id}`

获取分析运行上下文（含 `consensus` / `conflict` / `versions`）。

### 2.3 `GET /api/v1/analysis/{analysis_id}/charts/bazi`

获取八字原始盘面。

| 参数 | 说明 |
|---|---|
| `raw` | `true` 时返回未加工原盘（含 `input` / `assumptions` / `warnings` / `calculated_at`） |

```json
{
  "chart_id": "bazi-600519-20241115143200-a1b2c3",
  "engine": "bazi",
  "engine_version": "smx-bazi-native-1.0.0",
  "config_version": "cfg-2026.09",
  "birth_profile_version": "v1",
  "as_of": "2024-11-15T14:32:00",
  "chart": { ... }
}
```

### 2.4 `GET /api/v1/analysis/{analysis_id}/huangli`

```json
{
  "chart_id": "huangli-600519-...",
  "engine_version": "huangli-engine-1.0.0",
  "as_of": "2024-11-15T14:32:00",
  "huangli": {
    "primary": {
      "date": "2024-11-15", "solar_text": "2024-11-15 星期五", "lunar_text": "二〇二四年十月十五",
      "year_ganzhi": "甲辰", "month_ganzhi": "乙亥", "day_ganzhi": "癸未",
      "zodiac": "龙", "day_nayin": "杨柳木", "duty_officer": "成", "day_tian_shen": "明堂",
      "day_tian_shen_type": "黄道", "chong_desc": "(丁丑)牛", "sha_direction": "东",
      "pengzu_gan": "癸不词讼理弱敌强", "cai_shen_direction": "正南", "day_yi": [...], "day_ji": [...]
    },
    "days": [ ... 31 天 ... ]
  }
}
```

### 2.5 `GET /api/v1/analysis/{analysis_id}/factors`

| 参数 | 说明 |
|---|---|
| `direction` | `1` / `0` / `-1` 过滤方向 |
| `engine` | `bazi` / `huangli` |

响应（`FactorSet`）：65 条 `FactorObservation`。

### 2.6 `GET /api/v1/analysis/{analysis_id}/consensus`

**展示层**共识快照。

```json
{
  "display_only": true,
  "label": "POSITIVE_CONSENSUS", "label_cn": "正向共振",
  "participating_engines": ["bazi", "huangli"],
  "unavailable_engines": ["ziwei"],
  "directions": { "bazi": 1, "huangli": 1 },
  "mean_score": 63.46,
  "agreement": "中",
  "historical_validity": "未计算（Phase 1 不做正式 Consensus）",
  "data_quality": "A",
  "note": "Phase 1 未实现正式 ConsensusEngine。此处仅为**展示层**聚合…"
}
```

> `display_only` 恒为 `true`。**紫微不会出现在 `directions` 中，也不会被按 0 分计入。**

### 2.7 `GET /api/v1/analysis/{analysis_id}/conflicts`

展示层分歧快照（`display_only: true`）。

### 2.8 `GET /api/v1/analysis/{analysis_id}/evidence`

古籍证据包。**必然同时包含支持证据与反证。**

| 参数 | 说明 |
|---|---|
| `top_k` | 默认 6 |

```json
{
  "analysis_id": "AN-…",
  "driver_factors": [ {"factor_id":"B_NATAL_016","name":"身财对比","normalized_value":0.42,"direction":1} ],
  "evidence": {
    "query": { "query": "财星数量 身财对比", "factor_ids": [...], "topics": ["财星","旺衰"] },
    "supporting_evidence": [ {"entry_id":"DTS-0007","book":"滴天髓","chapter":"何知章",
                              "original_text":"何知其人富，财气通门户。",
                              "modern_note":"…","score":7.16,"authority_weight":1.4,
                              "stance":"supporting","edition":"公版通行本（清代刊本系统）",
                              "provenance":"明清以来广泛流传的命理经典，原文属公有领域。",
                              "license_status":"public_domain"} ],
    "counter_evidence": [ {"entry_id":"ZPZQ-0005","book":"子平真诠","original_text":"财格之贵，在于身强而任财。", ...} ],
    "neutral_evidence": [ ... ],
    "total_candidates": 14,
    "retrieval_method": "bm25 + topic_match + authority_weight + domain_filter",
    "knowledge_version": "kb-1.0.0",
    "note": "本系统同时检索支持与相反观点，以避免『先有结论后找古籍』。"
  },
  "disclaimer": "古籍条文只说明传统术数的说法，**不构成对股票收益的任何判断**。"
}
```

### 2.9 `GET /api/v1/analysis/{analysis_id}/backtest`

事件研究结果（在**已积累的因子观测与标签库**上执行）。

| 参数 | 说明 |
|---|---|
| `horizons` | 逗号分隔，默认 `5,10,20,60` |

```json
{
  "experiment_id": "ES-20260918153000-a1b2c3",
  "factor_ids": ["B_MONTH_001", "B_NATAL_001", ...],
  "logic": "any", "event_count": 112, "universe_size": 8,
  "date_from": "2021-01-01", "date_to": "2024-06-30",
  "horizons": [
    { "horizon": 5, "sample_count": 112, "up_rate": 0.491, "mean_return": 0.0057,
      "median_return": 0.0031, "std_return": 0.061, "mean_excess_return": null,
      "max_drawdown": null, "note": "样本数 112；超额收益/最大回撤/最大上涨仅在 20D 列给出（避免指标口径错配）" },
    { "horizon": 20, "sample_count": 112, "up_rate": 0.5625, "mean_return": 0.0196,
      "mean_excess_return": -0.0088, "max_drawdown": -0.192, "note": "样本数 112" }
  ],
  "methodology": "variant=real；事件 = 因子命中（logic=any, activation=nonzero）；…",
  "warnings": []
}
```

> **样本为 0 时不会给出任何数值**，`note` 中说明原因（如"尚未运行研究流水线"）。

**Phase 1.1 起新增字段**（向后兼容的可选字段）：

| 字段 | 说明 |
|---|---|
| `research_status` | 研究状态机输出：`NOT_RUN / NO_REAL_DATA / INSUFFICIENT_SAMPLE / INVALID_CONTROL / NO_SIGNAL / INCONCLUSIVE / WEAK_EVIDENCE / SUPPORTED_IN_SAMPLE`。合成/降级行情恒为 `NO_REAL_DATA`。 |
| `research_status_reasons` | 人类可读的状态理由（中文字符串数组） |
| `data_source` | 面板数据真相：标签行数 / 降级代码列表 / 是否真实数据 |
| `activation_stats` | 每只目标因子的激活统计（`total/activated/activation_rate`）；`activation_rate>95%` 或 `<0.5%` 触发 `LOW_DISCRIMINATION_FACTOR` 警告 |

### 2.10 `GET /api/v1/analysis/{analysis_id}/guide`

给前端的引擎可用性说明。

```json
{
  "analysis_id": "AN-…",
  "engines": [
    { "engine": "bazi", "display_name": "八字引擎", "available": true, "engine_version": "smx-bazi-native-1.0.0" },
    { "engine": "ziwei", "display_name": "紫微斗数引擎", "available": false, "engine_version": "",
      "reason": "Phase 2 实现。当前不提供任何紫微结果，也不以 0 分参与聚合。" }
  ],
  "phase": "phase1"
}
```

---

## 3. 研究 `/api/v1/research`

### 3.1 `POST /api/v1/research/run`

**端到端研究流水线**：面板构建 → 事件研究 → 四类负对照。

```json
{
  "universe": ["600519","000001","300750","600036","000858","601318","002594","688981","600000","601899"],
  "factor_ids": ["B_MONTH_001","B_MONTH_002","H_DAY_001"],
  "horizons": [5,10,20,60],
  "sample_step_months": 3,
  "date_from": "2021-01-01",
  "date_to": "2024-06-30",
  "run_negative_controls": true,
  "persist": true
}
```

响应：

```json
{
  "experiment_id": "EXP-20260918153000-a1b2c3",
  "event_study": { ... 见 2.9 ... },
  "negative_controls": {
    "experiment_id": "EXP-…",
    "factor_ids": ["B_MONTH_001", ...],
    "results": [
      { "kind": "random_birth_date", "verdict": "tie", "seed": 20260918,
        "real_mean_return_20d": 0.0193, "control_mean_return_20d": 0.0191,
        "real_up_rate_20d": 0.5625, "control_up_rate_20d": 0.5625,
        "delta_mean_return_20d": 0.00018, "delta_up_rate_20d": 0.0063,
        "verdict_note": "真实因子与对照无显著差异（平均收益差 0.0180%，上涨率差 0.63%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
        "horizon_stats": [ ... ] },
      { "kind": "shift_plus_7d", "verdict": "outperform", ... },
      { "kind": "shift_minus_7d", "verdict": "tie", ... },
      { "kind": "random_factor", "verdict": "tie", ... }
    ],
    "conclusion": "对照结果不一致：优于随机 1 类、无差异 3 类、弱于随机 0 类。结论为**不确定**，不能宣称有效性。"
  },
  "panel_stats": { "universe": [...], "sample_dates": [...], "observation_rows": 4550, "label_rows": 70 },
  "warnings": [],
  "duration_ms": 6900
}
```

**`verdict` 取值**：`outperform` / `tie` / `underperform` / `inconclusive`。

> **判定门槛**：20 日平均收益差 > 0.2% 且上涨率差 > 0 才算 `outperform`；
> 样本数 < 20 一律 `inconclusive`。
> **如果真实因子弱于随机，系统会输出 `underperform` 并写明"术数因子未显示正向信息量"。**

### 3.2 `GET /api/v1/research/labels/{code}`

获取个股在未来收益标签。

| 参数 | 说明 |
|---|---|
| `code` | 股票代码 |
| `as_of` | 特征基准日 |

```json
{
  "stock_code": "600519", "as_of": "2021-06-01", "trade_date": "2021-06-01",
  "ret_1d": 0.0041, "ret_5d": 0.0074, "ret_10d": 0.0153, "ret_20d": 0.0252, "ret_60d": 0.1128,
  "max_return_20d": 0.0432, "max_drawdown_20d": -0.0657,
  "bench_ret_20d": 0.0280, "excess_return_20d": -0.0028,
  "absolute_up_20d": true, "excess_up_20d": false, "strong_up_20d": false,
  "drawdown_controlled_up_20d": true,
  "horizon_available": { "1d": true, "5d": true, "10d": true, "20d": true, "60d": true },
  "extra_returns": {}
}
```

> ⚠️ **这些字段只能作为预测目标（label），绝不能作为 as_of 时刻的输入特征。**

### 3.3 `GET /api/v1/research/experiments`

历史研究实验列表。

### 3.4 `GET /api/v1/research/experiments/{experiment_id}`

实验详情（含 `results_by_variant`，按 real / 各对照组分组）。

### 3.5 `GET /api/v1/research/factor-definitions`

因子定义列表（研究向，支持 `category` 过滤）。

---

## 4. 古籍 `/api/v1/knowledge`

### 4.1 `GET /api/v1/knowledge/books`

书目列表（含 `_meta`：语料策略与校勘声明）。

### 4.2 `GET /api/v1/knowledge/entries`

条目列表。参数：`domain` / `school` / `book_id` / `limit` / `offset`。

### 4.3 `POST /api/v1/knowledge/search`

```json
{
  "query": "财星 财多身弱",
  "factor_ids": ["B_NATAL_002", "B_NATAL_016"],
  "topics": ["财星"],
  "domain": "bazi",
  "school": null,
  "book_id": null,
  "top_k": 5,
  "include_counter": true
}
```

响应同 §2.8 的 `EvidenceBundle`（含 `supporting_evidence` / `counter_evidence` / `neutral_evidence`）。

> `include_counter` 默认 `true`；即使显式关闭，系统也会在 `note` 中说明。

### 4.4 `GET /api/v1/knowledge/by-factors`

按因子 ID 检索证据。参数：`factor_ids`（逗号分隔）/ `top_k`。

### 4.5 `GET /api/v1/knowledge/stats`

知识库统计（条目数、按立场分布、按版权状态分布）。

---

## 5. 系统 `/api/v1/system`

### 5.1 `GET /api/v1/system/health`

```json
{ "status": "ok", "app": "股票玄学多模型研究平台", "version": "0.1.0", "phase": "phase1", "time": "..." }
```

### 5.2 `GET /api/v1/system/engines`

```json
{
  "phase": "phase1",
  "engines": [
    { "engine_id": "calendar", "display_name": "历法引擎", "available": true,
      "engine_version": "lunar-python-1.4.8", "third_party": "6tail/lunar-python",
      "third_party_commit": "v1.4.8 (PyPI release)" },
    { "engine_id": "bazi", "display_name": "八字引擎", "available": true,
      "engine_version": "smx-bazi-native-1.0.0",
      "third_party": "6tail/lunar-python（仅历法）+ 自研确定性规则内核",
      "third_party_commit": "v1.4.8 (PyPI release) / smx-bazi-native" },
    { "engine_id": "ziwei", "display_name": "紫微斗数引擎", "available": false,
      "unavailable_reason": "Phase 2 实现。当前不返回任何紫微结果，也不以 0 分参与聚合。" },
    { "engine_id": "liuyao", "available": false, "unavailable_reason": "仅预留接口" },
    { "engine_id": "qimen", "available": false, "unavailable_reason": "仅预留接口" }
  ],
  "market_provider": "akshare",
  "facts": { "factor_definitions": 65, "birth_profile_version": "v1", ... }
}
```

### 5.3 `GET /api/v1/system/data-quality`

数据库中的数据规模与质量分级。

### 5.4 `GET /api/v1/system/versions`

全部版本号（结果可追溯性所需）。

### 5.5 `GET /api/v1/system/phase1-status`

**诚实**列出 Phase 1 已实现与未实现项。

---

## 6. 其他

### 6.1 `GET /api/v1/factor-dictionary`

因子字典（含 `disclaimer` 与 `rule_version`）。

| 参数 | 说明 |
|---|---|
| `category` | `natal` / `year` / `month` / `day` / `cross` |
| `engine` | `bazi` / `huangli` |

---

## 7. 典型工作流

```bash
# 1. 搜索股票
curl "http://127.0.0.1:8000/api/v1/stocks/search?q=600519"

# 2. 构造出生档案
curl -X POST "http://127.0.0.1:8000/api/v1/stocks/600519/birth-profile" \
  -H "Content-Type: application/json" -d '{"birth_basis":"listing_open"}'

# 3. 执行分析
AID=$(curl -s -X POST "http://127.0.0.1:8000/api/v1/stocks/600519/analysis/bazi" \
  -H "Content-Type: application/json" \
  -d '{"as_of":"2024-11-15T14:32:00"}' | python -c "import sys,json;print(json.load(sys.stdin)['analysis_id'])")

# 4. 取各类结果
curl "http://127.0.0.1:8000/api/v1/analysis/$AID/charts/bazi?raw=true"
curl "http://127.0.0.1:8000/api/v1/analysis/$AID/huangli"
curl "http://127.0.0.1:8000/api/v1/analysis/$AID/factors?direction=1"
curl "http://127.0.0.1:8000/api/v1/analysis/$AID/evidence"
curl "http://127.0.0.1:8000/api/v1/analysis/$AID/backtest"

# 5. 运行研究流水线（事件研究 + 四类负对照）
curl -X POST "http://127.0.0.1:8000/api/v1/research/run" \
  -H "Content-Type: application/json" \
  -d '{"universe":["600519","000001","300750"],"factor_ids":["B_MONTH_001"],
       "horizons":[5,20],"sample_step_months":6,"date_from":"2021-01-01","date_to":"2024-06-30"}'
```

---

## 8. 未实现端点（Phase 2）

以下端点**不存在**，调用会返回 404：

```
POST /api/v1/stocks/{code}/analysis            # 多引擎联合分析
GET  /api/v1/analysis/{id}/charts/ziwei        # 紫微盘
GET  /api/v1/analysis/{id}/charts/liuyao       # 六爻卦
GET  /api/v1/analysis/{id}/charts/qimen        # 奇门盘
GET  /api/v1/analysis/{id}/export/markdown     # 导出
```

可访问 `/api/v1/system/phase1-status` 查看完整的未实现清单。
