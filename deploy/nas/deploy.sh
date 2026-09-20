#!/usr/bin/env bash
# 股票玄学多模型研究平台 · NAS 一键部署（幂等，可重复执行）
#
# 只做四件事：校验 → 构建 → 启动 → 初始化数据库。
# **不会**操作本系统之外的任何容器 / 镜像 / 卷。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="docker compose -f ${HERE}/docker-compose.nas.yml --env-file ${HERE}/.env"
API_PORT="$(grep -E '^SMP_API_PORT=' "${HERE}/.env" 2>/dev/null | cut -d= -f2 || echo 18080)"
WEB_PORT="$(grep -E '^SMP_WEB_PORT=' "${HERE}/.env" 2>/dev/null | cut -d= -f2 || echo 13000)"
VENDOR_PATH="$(grep -E '^SMP_VENDOR_HOST_PATH=' "${HERE}/.env" 2>/dev/null | cut -d= -f2 || echo /vol1/1000/股票历史数据)"

step() { printf '\n=== %s ===\n' "$1"; }
ok()   { printf '  [✓] %s\n' "$1"; }
die()  { printf '  [✗] %s\n' "$1" >&2; exit 1; }

step "0. 前置校验（全部只读）"
[ -f "${HERE}/.env" ] || die "缺少 ${HERE}/.env（先 cp .env.example .env）"
ok ".env 存在"

case "$(uname -m)" in
  x86_64) ok "架构 x86_64" ;;
  *) die "架构为 $(uname -m)；镜像按 amd64 构建，请确认是否能运行" ;;
esac

command -v docker >/dev/null || die "未找到 docker"
ok "docker $(docker --version | awk '{print $3}' | tr -d ,)"

for port in "$API_PORT" "$WEB_PORT"; do
  if ss -ltn 2>/dev/null | grep -qE ":${port}\b"; then
    die "端口 ${port} 已被占用（改 .env 里的 SMP_API_PORT / SMP_WEB_PORT）"
  fi
done
ok "端口 ${API_PORT} / ${WEB_PORT} 空闲"

[ -d "$VENDOR_PATH" ] || die "供应商数据路径不存在：${VENDOR_PATH}"
[ -d "${VENDOR_PATH}/全A日K" ] || die "缺少 全A日K 目录：${VENDOR_PATH}/全A日K"
[ -f "${VENDOR_PATH}/复权因子/复权因子_后复权.zip" ] || die "缺少后复权因子包"
ok "供应商数据齐备（只读挂载）"

avail_gb="$(df -BG --output=avail "${HERE}" | tail -1 | tr -dc '0-9')"
[ "${avail_gb:-0}" -ge 15 ] || die "磁盘空闲 ${avail_gb}G < 15G"
ok "磁盘空闲 ${avail_gb}G"

step "1. compose 语法校验"
${COMPOSE} config >/dev/null
ok "docker-compose.nas.yml 合法"

step "2. 构建镜像（首次约 5–10 分钟）"
${COMPOSE} build
ok "镜像构建完成"

step "3. 启动容器"
${COMPOSE} up -d
ok "容器已启动"

step "4. 等待 API 健康"
for i in $(seq 1 60); do
  if curl -sf -m 3 "http://127.0.0.1:${API_PORT}/api/v1/system/health" >/dev/null 2>&1; then
    ok "API 健康（第 ${i} 次探测）"; break
  fi
  [ "$i" -eq 60 ] && die "API 60 次探测仍不健康，请查看：${COMPOSE} logs api"
  sleep 3
done

step "5. 初始化数据库（migration + 种子数据 + 基准指数）"
${COMPOSE} exec -T api python -m alembic upgrade head
${COMPOSE} exec -T api python -m src.cli seed
# 基准指数（沪深300）来自仓库内 data/import/ 的 Phase 1 快照：
# SQLite 里必须有它，否则 excess_return（超额收益）无法计算。
# 全市场个股行情由供应商 Parquet 仓库提供，不在此处重复导入。
${COMPOSE} exec -T api python -m src.cli import-market
ok "数据库已初始化（含基准指数）"

cat <<TIPS

============================================================
部署完成
------------------------------------------------------------
  前端     http://<NAS内网IP>:${WEB_PORT}
  API      http://<NAS内网IP>:${API_PORT}/docs
  健康检查 curl -s http://127.0.0.1:${API_PORT}/api/v1/system/health
------------------------------------------------------------
下一步（一次性，约 15–25 分钟）：
  bash ${HERE}/import-data.sh

查看日志：
  ${COMPOSE} logs -f api
============================================================
TIPS
