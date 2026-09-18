# ADR-0005：SQLite 主库 + DuckDB/Parquet 研究层

- **状态**：已接受（Phase 1）；Phase 2 需扩展
- **日期**：2026-09-18
- **影响**：数据库、研究查询、部署

## 背景

系统需要承载两类截然不同的负载：

| 负载 | 特征 | 规模 |
|---|---|---|
| **事务型** | 单行读写、约束、外键、幂等 upsert | 表数量多，单表行数小 |
| **分析型** | 大范围扫描、分组聚合、时间序列对齐 | `factor_observation` 可能到亿级行 |

架构文档 §46 建议：

```
V1 本地：SQLite（配置/资料/任务）+ DuckDB（研究查询）+ Parquet（历史行情/大规模因子）+ FAISS（古籍向量）
以后多用户：PostgreSQL + Object Storage + Qdrant/pgvector
```

## 决策

1. **SQLite 作为主库**：
   * 承载全部 16 张业务表；
   * 通过 SQLAlchemy 2.x + Alembic 管理 schema 与 migration；
   * 启用 `PRAGMA foreign_keys=ON` 与 `journal_mode=WAL`。

2. **DuckDB + Parquet 作为研究层**：
   * 依赖已锁定（`duckdb==1.5.5`、`pyarrow==25.0.1`）；
   * `src/core/config.py` 提供 `settings.duckdb_path` 与 `settings.parquet_dir`；
   * **Phase 1 未实际启用** —— 当前研究规模（10 只股票 × 每季度采样）
     用 SQLite 足够，过早引入会增加复杂度。

3. **不引入 ORM 之外的数据库**：Phase 1 不需要 Redis / MongoDB / 消息队列。

## 为什么不同时上 DuckDB

**"能用"不等于"该用"。** Phase 1 的研究流水线实际执行的是：

```
10 只股票 × 8 个采样日期 × 65 个因子 ≈ 5200 行因子观测
10 只股票 × 8 个采样日期            =   80 行标签
```

这个规模下 DuckDB 的向量化优势完全体现不出来，反而要维护
"SQLite 与 DuckDB 之间的数据同步"。**保持简单。**

## 迁移路径（Phase 2）

当出现以下任一信号时启用 DuckDB/Parquet：

| 信号 | 阈值参考 |
|---|---|
| 股票池扩大 | > 100 只 |
| 采样密度提高 | 每个交易日采样 |
| 因子观测行数 | > 5000 万 |
| 单次研究响应时间 | > 30 秒 |

迁移方案：

```
1. factor_observation → 按月分区写入 Parquet（data/factors/YYYY-MM.parquet）
2. DuckDB 直接查询 Parquet（无需导入）
3. SQLite 保留最近 N 天的观测用于在线查询
4. 研究层改为：DuckDB 出面板 → pandas 做统计
5. 多用户场景：SQLite → PostgreSQL（SQLAlchemy URL 切换即可，Alembic 支持）
```

## 后果

**正面**

* 零运维：无需数据库服务，`git clone` 即可运行；
* 备份简单（单文件 + WAL）；
* 本地开发体验好；
* 迁移路径清晰（SQLAlchemy 抽象 + Alembic）。

**负面**

* SQLite 的写并发能力有限（WAL 模式下单写多读）；
* 大表 JOIN 性能不如列存；
* 无原生分区/归档机制。

**当前可接受的理由**：Phase 1 是**单用户研究系统**，
写入主要发生在离线分析时，不存在写并发压力。

## 相关

- [`docs/database.md`](../database.md)
- [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md) §7（技术债 #2、#3）
