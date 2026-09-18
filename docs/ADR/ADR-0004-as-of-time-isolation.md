# ADR-0004：`as_of` 单向时间隔离与未来数据泄漏防护

- **状态**：已接受（Phase 1）
- **日期**：2026-09-18
- **影响**：研究层、行情层、标签、事件研究、因子

## 背景

任何历史回测系统最致命的错误是**未来数据泄漏**：用 as_of 之后的信息构造 as_of 时刻的"特征"。

在术数场景下有一个容易忽略的变体：

* 术数因子只依赖**出生时间**与**分析时刻**，看起来不可能泄漏；
* 但**出生时间本身**可能来自上市日期 —— 如果上市日期字段是在未来才知道的
  （例如数据源回填），就构成泄漏；
* 更常见的是**标签侧编写错误**：把 `ret_20d` 当成输入特征参与打分。

架构文档 §77 要求：

> 专门写 `test_no_future_data_access.py`，确保 as_of = 2020-01-01 时，
> 绝对不能获取 2020-01-02 以后信息作为输入特征。

## 决策

### 1. 单向时间轴

```
as_of 之前（含当日）  →  仅允许作为特征输入
as_of 之后          →  仅允许作为标签（label）
```

### 2. 唯一裁剪入口

```python
# src/market/normalization/frames.py
def clip_to_as_of(series: BarSeries, as_of: date) -> BarSeries:
    """把序列裁剪到 as_of 当日及之前。
    任何"截至 as_of 的特征计算"都必须先经过本函数。"""

# src/research/labels/forward_returns.py
def visible_slice(series: BarSeries, as_of: date) -> BarSeries:
    """as_of 及之前的行情 —— 任何特征计算的唯一合法输入。"""
```

### 3. 结构隔离

* `src/factors/` **不得** import 标签模块（AST 测试强制）；
* 因子计算的入参只有 `BaziChart` 与 `HuangliSnapshot`，
  **结构上不可能读到行情**；
* 标签模块只能读 as_of 之后的数据。

### 4. 缺失即缺失

标签数据不足时：

* `compute_labels` 抛 `InsufficientForwardData`（基准日之后完全无数据）；
* 单个持有期数据不足 → `ret_Nd = None` 且 `horizon_available["Nd"] = False`；
* **永远不用 0 填充**。

### 5. 事件与标签的对齐

`as_of` 可能落在非交易日。对齐规则：

```
因子观测 (stock_code, as_of_date) → 标签 trade_date（>= as_of 的第一个交易日）
```

未匹配到标签的观测**直接剔除**（`_align_observation_trade_dates`）。

## 验证方法：哨兵污染

`tests/test_no_future_data_access.py` 是 P0 级测试，包含 16 个用例，
核心是**哨兵污染法**：

```python
AS_OF = date(2020, 1, 1)

@pytest.fixture()
def contaminated(self, market):
    """把 as_of 之后的行情全部替换成 999999。"""
    series = market.get_daily_bars("600519", date(2018, 1, 1), date(2022, 12, 31))
    return series.model_copy(update={"bars": [
        b.model_copy(update={"close": 999999.0, "high": 999999.0, "low": 999999.0})
        if b.trade_date > AS_OF else b
        for b in series.bars
    ]})

def test_clipped_features_identical_under_contamination(self, market, contaminated):
    clean = clip_to_as_of(market.get_daily_bars(...), AS_OF)
    dirty = clip_to_as_of(contaminated, AS_OF)
    assert [b.close for b in clean.bars] == [b.close for b in dirty.bars]
```

**为什么这比"检查代码里有没有读未来"更强**：
它直接检验**行为** —— 如果任何特征路径意外读到了未来数据，数值就会变。

### 反向对照（同样重要）

```python
def test_labels_do_change_under_contamination(...):
    """标签应该受未来数据影响 —— 这证明标签确实来自未来。"""
    assert l_clean.ret_20d != l_dirty.ret_20d
```

如果标签也不变，说明标签实现有 bug（而不是"没有泄漏"）。
这个反向对照能捕捉到"标签读错数据源"这类错误。

### 其余用例分组

| 分组 | 检验内容 |
|---|---|
| `TestClipping` | 裁剪语义、保留元信息、`visible_slice` 与 `clip_to_as_of` 一致 |
| `TestSentinelContamination` | 污染后特征完全不变 |
| `TestFactorsAreMarketIndependent` | 因子输出中不含任何行情字段名 |
| `TestLabelIsolation` | 标签字段只向前看；因子模块不 import 标签模块 |
| `TestInsufficientDataHonesty` | 数据不足时抛异常 / 返回 `None`，绝不用 0 填充 |
| `TestEventStudyDirectionality` | 事件由 `trade_date` 决定，未来收益只从标签取 |

## 后果

**正面**

* 研究结论可信度的基础；
* 泄漏回归可被自动发现；
* `clip_to_as_of` 的存在让"特征侧"的写法有明确规范。

**负面**

* 每次特征计算都要显式裁剪，有额外的心智负担；
* `clip_to_as_of` 会产生新的 `BarSeries` 对象（内存拷贝，但序列规模小，可接受）。

## 相关

- [`AGENTS.md`](../../AGENTS.md) §6
- [`docs/methodology.md`](../methodology.md) §5
- [`tests/test_no_future_data_access.py`](../../tests/test_no_future_data_access.py)
