# W8 本机限域运行验收（2026-09-28）

## 验收范围

使用 W2/W4 已认证的 `SZSE.STK.002561` 限域数据，在本机启动 Ziwei、FastAPI 与 Next.js，检查真实页面到 API、历史研究结果和报告导出的链路。运行数据库是 `data/w8-local-runtime/smp.sqlite3` 迁移副本；原始 `data/smp.sqlite3` 未修改。行情提供方配置为 `vendor_parquet`，合成行情回退关闭。

本验收覆盖当前限域数据，不代表完整市场认证、确认性研究、OOS 验证、部署或商业化就绪。

## 运行前检查

| 检查 | 结果 |
|---|---|
| Python / Node | Python 3.12.14 / Node 24.14.0（CI 使用 Node 20；本次没有升级本机依赖） |
| 本机数据库 | `PRAGMA quick_check=ok`；唯一 Alembic head 为 `f3a9c26d71be` |
| 选择的数据集 | `w4-certified-002561-20120223-20180514-v2-label-ends`，1,513 行，`research_eligible=true`，`confirmatory_research_eligible=false` |
| 行情回退 | `SMP_MARKET_PROVIDER=vendor_parquet`；`SMP_ALLOW_SYNTHETIC_MARKET_FALLBACK=false` |
| 服务监听 | Ziwei `127.0.0.1:8100`、API `127.0.0.1:8000`、Web `127.0.0.1:3000` |

## 页面与 API 结果

真实 Playwright 测试运行命令：

```powershell
$env:NEXT_PUBLIC_SMP_RESEARCH_DATASET_ID = "w4-certified-002561-20120223-20180514-v2-label-ends"
npx playwright test e2e/w8-local-runtime.spec.ts --project=reference-1672x941 --workers=1
```

最终结果为 **4 passed**（14.3 秒）：

1. 首页分别展示实时行情截止日和 W4 历史数据范围、资格。
2. 历史研究页对日期范围和单股 `002561` 发出真实 v2 请求；下载 JSON 与页面 API 返回的 digest、范围及样本数一致。
3. 真实日期扫描查询 2026-09-29 的全市场关系，并从选中关系生成独立 W4 历史研究入口；扫描关系和历史统计保持为两个操作。
4. 研究实验室加载冻结的限域 W6 报告，时间轴调用本机 Fortune API。

另覆盖无匹配因子时返回 `INSUFFICIENT_SAMPLE`、模拟上游 503 时展示错误状态。历史 v2 API 对 2012-02-23 至 2013-02-23 的日期范围、20 日周期返回 243 条匹配观察，状态为 `EXPLORATORY_NOT_GATED`。实验报告 API 返回的 `report_digest` 与冻结报告文件 SHA-256 相同。

全市场日期扫描实际返回 `stock_total=5,796`，每次页面请求返回前 100 个匹配项；关系计数为六合 1,189、六冲 1,576、相害 1,615。该页面验证只证明日期扫描和 W4 导航链路可用，不把扫描股票池解释为已认证历史研究股票池。

## 服务状态与限制

本机 `/api/v2/system/readiness` 返回 `ready=true`、`status=degraded`：数据库和 Ziwei 通道就绪，但系统级 `research_data=not_certified`，因为当前实时行情提供方本身没有完整认证。W4 数据集详情接口则单独报告本限域数据 `research_eligible=true`、确认性资格为 `false`。两项状态对应不同数据面，不能互相替代。

全市场日期扫描的首次冷缓存页面请求没有在 E2E 的 180 秒等待内返回；之后同一查询命中服务端缓存，API 在约 0.65 秒内返回，最终页面链路通过。冷缓存扫描延迟是待跟进项，本次通过缓存命中不能证明冷启动性能达标。

W2 证书覆盖单一证券及 2012-02-23 至 2018-05-14 的 1,513 个观察日期。观察日期集合来自可用数据索引，并非官方交易日历；首日 09:30 仍是显式 `listing_open` 假设。完整 PIT 市场认证、确认性及 OOS 研究资格继续未通过，限域 W6 检验均为样本不足。详见 [W2 限域证书](W2-LIMITED-SCOPE-002561-2026-09-28.md)、[W4 数据审计](W4-LIMITED-SCOPE-002561-2026-09-28.md) 与 [W6 预注册报告](W6-LIMITED-SCOPE-002561-2026-09-28.md)。

## 其他验证与清理

- 后端限域证书、实验、历史数据集、v2 API 与未来数据测试：50 passed；Ruff 全部通过。
- 前端 `npm run typecheck` 与使用限域数据集配置的生产构建通过。
- 本地服务由 `scripts/local/stop-w8.ps1` 停止；W8 PID 记录已移除，检查端口 3000/8000/8100 没有监听进程。
- CI 未运行；本次没有推送或部署。

## W8 结论

**GO：限域数据的本机页面、API、报告和 Fortune 时间轴运行链路通过。** 冷缓存全市场日期扫描延迟应单独调查。完整市场、确认性/OOS、前瞻观察、商业化及独立视觉门仍不在本次限域资格之内。
