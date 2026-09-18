# ADR-0001：第三方引擎必须经 Adapter 隔离

- **状态**：已接受（Phase 1）
- **日期**：2026-09-18
- **影响**：全局架构约束

## 背景

本平台依赖三类第三方能力：

1. **历法**：lunar-python（公历/农历/干支/节气/黄历）
2. **行情**：AKShare（股票资料/日线）
3. **八字规则与古籍**：bazi-pro（尚未接入）

这些库都有各自的 API 风格、对象模型与版本节奏。如果业务层直接调用：

* 升级库会导致业务代码大面积改动；
* 无法在测试中替换为确定性 Stub；
* 无法保证"业务层只消费本项目自己的语义"；
* 不同库的同名字段语义可能不同（例如"月柱"在不同库里换月口径可能不同）。

## 决策

**所有第三方能力必须通过 Adapter 接入；业务层不得持有第三方对象。**

六个核心接口：

| 接口 | 位置 |
|---|---|
| `MetaphysicsEngine`（基类） | `src/engines/base.py` |
| `CalendarEngine` | `src/engines/calendar/` |
| `HuangliEngine` | `src/engines/huangli/` |
| `BaziEngine` | `src/engines/bazi/` |
| `MarketDataProvider` | `src/market/providers/` |
| `KnowledgeProvider` | `src/knowledge/retrieval/` |
| `BacktestProvider` | `src/research/backtest/` |

允许 `import lunar_python` 的位置仅有三处（白名单）：

```
src/engines/calendar/calendar_engine.py
src/engines/bazi/bazi_engine.py          # 仅大运/胎元/命宫等辅助字段
src/market/providers/akshare_provider.py # akshare
```

## 实现方式

1. **Schema 层**：所有引擎输出本项目自己定义的 Pydantic 模型
   （`CalendarSnapshot` / `HuangliSnapshot` / `BaziChart` / `BarSeries` / `StockMaster`），
   第三方对象**在 Adapter 内部被转换为这些模型后即被丢弃**。
2. **原始数据保留**：`CalendarSnapshot.raw_source`、`HuangliSnapshot.raw_huangli`
   保留第三方原始输出，但**只用于审计**，业务层禁止读取。
3. **机器校验**：`tests/test_third_party_isolation.py` 用 AST 静态分析强制：
   * `src/factors` / `src/research` / `src/knowledge` / `apps/*` 不得 import 第三方库；
   * Schema 模块的类型注解中不得出现第三方类型名。
4. **失败隔离**：`MarketDataProvider` 内部实现重试 + 缓存 + 降级链，
   并向业务层抛出**结构化错误**（`MarketDataError` 子类），不泄漏第三方异常类型。

## 后果

**正面**

* 更换历法库/行情源只需重写一个 Adapter，业务层零改动；
* 测试可以注入确定性 Stub（`SyntheticMarketProvider`）；
* 第三方升级导致的破坏被限制在 Adapter 层；
* "业务层不依赖第三方对象"这一约束可被自动验证。

**负面**

* 需要维护一层转换代码（约 600 行）；
* 第三方新增字段需要手动加入 Schema 才能使用；
* `raw_source` 会增大存储（但这是审计必需）。

**权衡理由**：转换层的成本是**一次性**的，而耦合的代价是**持续**的。

## 相关

- [`AGENTS.md`](../AGENTS.md) §2、§4
- [`THIRD_PARTY.md`](../THIRD_PARTY.md)
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) §2
