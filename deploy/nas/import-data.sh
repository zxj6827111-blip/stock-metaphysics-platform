#!/usr/bin/env bash
# 在 api 容器内构建全市场数据（读只读挂载的供应商原始包，写本系统自己的卷）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="docker compose -f ${HERE}/docker-compose.nas.yml --env-file ${HERE}/.env"

step() { printf '\n=== %s ===\n' "$1"; }

step "1/4 供应商年包 → Parquet 仓库（约 8–12 分钟）"
${COMPOSE} exec -T api python scripts/phase4_import_vendor.py \
  --vendor-root /vendor/history

step "2/4 PIT 估值快照（68 个 as_of，约 1 分钟）"
${COMPOSE} exec -T api python scripts/phase4_build_valuation_snapshots.py

step "3/4 全量 universe v4-full（6,104 只）"
${COMPOSE} exec -T api python scripts/phase4_build_universe.py

step "4/4 全量出生档案（3 模型 × 6,104 只）"
${COMPOSE} exec -T api python scripts/phase3_generate_birth_profiles.py \
  --universe-version v4-full

cat <<'TIPS'

============================================================
全市场数据构建完成
------------------------------------------------------------
验收：
  curl -s "http://127.0.0.1:18080/api/v1/stocks/search?q=002008"
  浏览器打开前端 → 输入 002008 → 应能看到八字/紫微排盘

注意：
  * 全市场「排盘面板采集」是研究用途，约 5–6 小时，需要时再跑：
      docker compose -f docker-compose.nas.yml exec -T api \
        python scripts/phase4_collect_panel.py --parallel 6
    之后 `--merge` 合并。日常浏览不需要它。
  * Phase 3 的研究结论不受本步骤影响（它锚定 v2-phase3a 的 500 只）。
============================================================
TIPS
