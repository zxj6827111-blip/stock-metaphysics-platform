# ADR-0009：紫微斗数引擎采用 iztro（Node.js 服务 + Python Adapter）

- **状态**：已接受（Phase 2A）
- **日期**：2026-09-19
- **影响**：紫微引擎、Node 服务、Docker、测试、第三方依赖清单
- **关联**：[ADR-0001](ADR-0001-adapter-isolation.md)、[ADR-0008](ADR-0008-bazi-engine-strategy.md)、[ADR-0010](ADR-0010-ziwei-no-gender-variant.md)

## 背景

Phase 2 需要紫微斗数排盘。候选方案有三：

| 方案 | 说明 |
|---|---|
| A. `SylarLong/iztro`（Node/TypeScript） | 生态成熟、star/palace/horoscope 数据完整 |
| B. 自研 Python 紫微内核 | 可控，但紫微的安星诀/四化表/流曜规则体量远大于八字规则，实现与校勘成本极高 |
| C. 不实现紫微 | 与 Phase 2 目标直接冲突 |

与 bazi-pro（[ADR-0008](ADR-0008-bazi-engine-strategy.md)）的关键区别在于**许可证与来源可核实性**：

| 核查项 | iztro | bazi-pro |
|---|---|---|
| LICENSE | **MIT**（npm registry 元数据 + 仓库 LICENSE） | 未核实 |
| 仓库归属 | `github.com/SylarLong/iztro`，与 npm 包作者一致 | 账号与原作者关系不清 |
| 可锁版本 | 是（`iztro@2.6.1`，精确版本） | 否 |
| 结论 | **可接入** | 排除 |

## 决策

**采用方案 A：iztro，经 `services/ziwei-service` + `ZiweiEngine` Adapter 接入。**

1. **锁定版本**：`iztro@2.6.1`（`package.json` 中使用精确版本，不用 `^`）。
2. **服务形态**：Node.js + TypeScript 独立服务
   * `src/chart.ts`：纯函数排盘，输出本项目自有的 `ZiweiChartResult`；
   * `src/cli.ts`：stdin/stdout 批量 JSON（**默认 transport**）；
   * `src/server.ts`：`POST /internal/ziwei/{chart,batch}`（部署 transport）。
3. **Python 侧只能经 Adapter 调用**：`src/engines/ziwei/`（`ziwei_engine.py` + `transport.py` + `constants.py`）。
   业务层不得出现任何 iztro 对象、字段名或 camelCase 键。
4. **原始盘面必须落库**：`chart_artifact.raw_chart` 保存完整 `ZiweiChart`（十二宫/星曜/四化/三方四正/大限小限/流年流月流日流时）。
5. **契约显式映射**：`transport.py::_camel_to_snake` 使用**显式字段映射表**而非通用驼峰转换 ——
   服务端改名会立刻在测试中暴露，而不是被通用转换悄悄吞掉。

### 为什么子进程是默认 transport

研究流水线需要批量排盘（数十只股票 × 多个 `as_of` × 2 个 variant）。若为 HTTP：

* 本地开发/测试必须额外管理一个常驻进程；
* 单元测试无法在"没有服务"的环境下判断"契约是否正确"与"服务是否不可用"的区别。

子进程 + **单次批量调用**既避免常驻服务，也避免 N 次进程启动开销。
HTTP transport 保留给 Docker / 生产部署。降级顺序固定：

```
http（SMP_ZIWEI_SERVICE_URL 已设置） → subprocess（node 可用且已构建） → none（unavailable）
```

### 故障隔离（硬要求）

紫微服务失败时：八字 / 黄历 / 历史数据必须继续运行；
紫微输出 `availability=unavailable`、`score=null`；`Consensus` 的
`available_engine_count` 降低；**禁止**把紫微按 0 分计入聚合。

## 后果

**正面**

* 紫微排盘数据完整（含流年/流月/流日/流时、三方四正、大小限），无需自研安星诀；
* 许可证明确（MIT），可商用前提清晰；
* 第三方隔离仍由机器校验（Python 侧永不 import iztro）；
* 服务可独立升级并被 Golden Case 锁定行为。

**负面**

* 项目首次引入 **Node.js 运行时依赖**（Phase 1 只有前端需要 Node）；
  Docker 镜像需要多一个服务，本地开发需要 `node` 与 `npm run build`；
* iztro 升级可能改变口径 → 必须重跑紫微 Golden Case，并把差异写入
  `docs/calculation-differences-phase2-ziwei.md`；
* `subprocess` 传输在极高并发下会成为瓶颈（当前研究规模不构成问题，已记录为已知限制）。

## 不做的事

* 不把 iztro 的源码或数据表复制进 `src/`（违反 ADR-0001 与许可证边界）；
* 不让 Python 侧解析 iztro 的 camelCase 字段名之外的内部结构；
* 不让 LLM 参与任何紫微计算。

## 相关

- [`THIRD_PARTY.md`](../../THIRD_PARTY.md) §1.6
- [`services/ziwei-service/`](../../services/ziwei-service/)
- [`src/engines/ziwei/`](../../src/engines/ziwei/)
