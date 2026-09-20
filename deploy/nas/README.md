# Phase 4 · NAS Docker 部署（隔离部署，不动现有服务）

> 目标机：飞牛 NAS（fnOS / Debian 12，x86_64，i7-7700 8 线程，16 GB 内存）
> 本目录产出**隔离部署**：新目录、新网络、新端口、新卷，**只读**挂载你已有的数据。
> **不会**修改、重启、删除 `stock-analyzer` / `hermes` / `openclaw` / `sing-box` 的任何东西。

---

## 0. 隔离边界（先看清这个再动手）

| 项目 | 本部署使用 | 你的现有服务使用 | 冲突？ |
|---|---|---|---|
| 目录 | `/vol1/docker/StockMetaphysics` | 各自目录 | 无 |
| 网络 | `smp-net`（专用 bridge） | 各自的网络 | 无 |
| API 端口 | **18080** | `stock-analyzer-api` 18001 | 无 |
| Web 端口 | **13000** | hermes 19119 / openclaw 18789 | 无 |
| 紫微服务 | 容器内部 8100（不对外） | —— | 无 |
| 数据卷 | `smp-data` / `smp-vendor`（命名卷） | 各自的卷 | 无 |
| 你的股票数据 | **`:ro` 只读挂载** | 自己读写 | 只读，不会写 |

**唯一会写你磁盘的地方**：`/vol1/docker/StockMetaphysics/`（本系统自己的目录）。
供应商原始数据以只读方式挂进容器，容器**不可能**修改它。

---

## 1. 前置检查

```bash
# 在 NAS 上执行
uname -m                          # 期望 x86_64
docker --version                  # 期望 20+（实测 28.5.2）
df -h /vol1 | tail -1             # 需要 ≥ 15 GB 空闲（数据约 1.5 GB + 镜像约 2 GB）
ss -ltnp | grep -E ':(18080|13000)\b' || echo "端口空闲 ✓"
ls -d /vol1/1000/股票历史数据/全A日K /vol1/1000/股票历史数据/复权因子
```

## 2. 上传代码

在**本机**（Windows）执行：

```bash
cd "E:/Software Development/stock-metaphysics-platform"
tar --exclude=.git --exclude=.venv --exclude=node_modules \
    --exclude=apps/web/.next --exclude=data/smp.sqlite3 \
    -czf /tmp/smp.tar.gz .
scp /tmp/smp.tar.gz zxj6827111@100.114.122.111:/tmp/
```

在 **NAS** 上执行：

```bash
mkdir -p /vol1/docker/StockMetaphysics
cd /vol1/docker/StockMetaphysics
tar -xzf /tmp/smp.tar.gz
```

## 3. 配置

```bash
cd /vol1/docker/StockMetaphysics/deploy/nas
cp .env.example .env
vi .env      # 按需改端口 / 数据路径
```

## 4. 一键部署（幂等，可重复执行）

```bash
cd /vol1/docker/StockMetaphysics/deploy/nas
bash deploy.sh
```

`deploy.sh` 会依次做：

1. 校验目录、端口、磁盘（只读检查，失败即停）
2. `docker compose config` 语法校验
3. 构建三个镜像（api / web / ziwei）
4. 启动容器（`docker compose up -d`）
5. 等待 healthcheck，轮询 `http://127.0.0.1:18080/api/v1/system/health`
6. **在容器内执行 Alembic migration + 种子数据**（古籍 + 交易所时段）
7. 打印访问地址与后续步骤

**不会**碰任何其它容器。脚本里没有 `docker system prune`、没有 `docker rm` 其它容器。

## 5. 构建全市场数据（一次性，约 15–25 分钟）

```bash
cd /vol1/docker/StockMetaphysics/deploy/nas
bash import-data.sh
```

它会在 `api` 容器内执行四步（全部读你的只读数据，写本系统自己的卷）：

| 步骤 | 命令 | 产出 |
|---|---|---|
| 1 | `phase4_import_vendor.py` | `daily_bars/valuation/adj_factor.parquet`（约 1.3 GB） |
| 2 | `phase4_build_valuation_snapshots.py` | 68 个 as_of 的 PIT 估值快照 |
| 3 | `phase4_build_universe.py` | `universe_memberships` 写入 `v4-full`（6,104 只） |
| 4 | `phase3_generate_birth_profiles.py --universe-version v4-full` | 18,312 条出生档案 |

> 你的 `/vol1/1000/股票历史数据` 是 **9-18 更新的**，比本机快照（7-17）新，
> 所以**在 NAS 上构建**能拿到最新数据 —— 这也是不重复下载的关键。

## 6. 验收

```bash
curl -s http://127.0.0.1:18080/api/v1/system/health
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:13000/
# 用一只 Phase 3 universe 外的票验证全市场数据确实进来了
curl -s "http://127.0.0.1:18080/api/v1/stocks/search?q=002008"
```

浏览器打开 `http://<NAS内网IP>:13000`，输入 `002008` 应能看到排盘（这正是本机之前报错的那只票）。

## 7. 常用运维

```bash
docker compose -f /vol1/docker/StockMetaphysics/deploy/nas/docker-compose.nas.yml ps
docker compose -f /vol1/docker/StockMetaphysics/deploy/nas/docker-compose.nas.yml logs -f api
docker compose -f /vol1/docker/StockMetaphysics/deploy/nas/docker-compose.nas.yml restart api
# 停止本系统（不动其它容器）
docker compose -f /vol1/docker/StockMetaphysics/deploy/nas/docker-compose.nas.yml down
```

## 8. 回滚

```bash
# 停止并删除本系统的容器与网络（卷保留，数据不丢）
docker compose -f deploy/nas/docker-compose.nas.yml down
# 彻底清理（含数据卷 —— 慎用）
docker compose -f deploy/nas/docker-compose.nas.yml down -v
rm -rf /vol1/docker/StockMetaphysics        # 删除本系统所有文件
```

---

## 9. 已知限制（部署后也依然存在）

| 限制 | 说明 |
|---|---|
| 行业 PIT 分类 | 供应商数据**没有**行业字段 → 行业中性化仍不可用（与 Phase 3 相同） |
| 退市股估值 | 308 只退市股只有 OHLCV，`size/value` 为 NaN（已按列披露覆盖率） |
| 全市场面板排盘 | 746,724 次排盘 ≈ 单机 5–6 小时；**一次性**，之后读缓存 |
| 单票排盘延迟 | 秒级（八字约 6 s，综合研判 < 1 s），每次现算 |
| LLM 叙事 | 需在 `.env` 配置 LLM API Key；未配置时仅该功能降级，其它页面正常 |
