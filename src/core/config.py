"""全局配置（环境变量 + 默认值）。

所有可调参数集中在此，禁止在业务代码里散落魔法值。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """平台运行配置。环境变量前缀 ``SMP_``。"""

    model_config = SettingsConfigDict(
        env_prefix="SMP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 基础 ---
    app_name: str = "股票玄学多模型研究平台"
    app_version: str = "0.2.0"
    phase: str = "phase2"
    debug: bool = False
    timezone: str = "Asia/Shanghai"

    # --- 路径 ---
    data_dir: Path = Field(default=PROJECT_ROOT / "data")
    knowledge_dir: Path = Field(default=PROJECT_ROOT / "knowledge")

    # --- 数据库 ---
    database_url: str = ""  # 留空则自动使用 data/smp.sqlite3

    # --- 引擎版本（结果可追溯性的核心；升级必须同步更新） ---
    birth_profile_version: str = "v1"
    # 日期关系扫描的 canonical 口径必须显式选择，不能按 updated_at 猜测。
    canonical_birth_basis: str = "listing_open"
    canonical_birth_profile_version: str = "v2-phase4b-listing_open"
    canonical_universe_version: str = "v4-full"
    relation_rule_version: str = "bazi-relation-v2"
    relation_fingerprint_version: str = "date-relation-fingerprint-v1"
    calendar_engine_version: str = "lunar-python-1.4.8"
    huangli_engine_version: str = "huangli-engine-1.0.0"
    bazi_engine_version: str = "smx-bazi-native-1.0.0"
    # Phase 2：紫微斗数（iztro 2.6.1 经 services/ziwei-service adapter 接入）
    ziwei_engine_version: str = "iztro-2.6.1+smx-1.0.0"
    # v1.1: 修正 B_YEAR_005/007/008 的关系类型接线错误（原：005≡010 三合重复、刑冲错位、害未计算）
    factor_rule_version: str = "v1.1"
    # Phase 2 紫微因子使用独立 rule_version：与八字因子的修复节奏解耦
    ziwei_factor_rule_version: str = "zv1"
    # 紫微股票的宫位→金融含义映射不是传统定论，必须版本化并可回测
    ziwei_stock_mapping_version: str = "ziwei_stock_mapping_v1"
    knowledge_version: str = "kb-1.1.0"
    config_version: str = "cfg-2026.09"
    market_data_version: str = "akshare-1.18.96"

    # --- 紫微服务 ---
    #: 常驻 HTTP 服务地址；留空则使用 node 子进程通道（见 src/engines/ziwei/transport.py）
    ziwei_service_url: str = ""
    #: 紫微排盘时使用的闰月口径（iztro fixLeap）。显式固定，避免随库默认值漂移。
    ziwei_fix_leap: bool = True

    # --- 行情 ---
    market_provider: str = "akshare"          # akshare | synthetic | offline（离线真实导入）
    market_cache_ttl_seconds: int = 12 * 3600
    market_retry_attempts: int = 3
    market_retry_backoff_seconds: float = 1.5
    market_request_timeout: int = 20
    # 网络不可用时是否允许降级到确定性合成行情（会显式标注 data_quality 降级）
    allow_synthetic_market_fallback: bool = True
    benchmark_index_code: str = "000300"      # 沪深300
    market_history_start: str = "2016-01-01"

    # --- 研究 ---
    label_horizons: tuple[int, ...] = (1, 5, 10, 20, 60)
    event_study_horizons: tuple[int, ...] = (5, 10, 20, 60)
    negative_control_seed: int = 20260918
    min_event_sample_size: int = 8

    # --- 其他 ---
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:1672",
    )

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(self.data_dir / 'smp.sqlite3').as_posix()}"

    @property
    def parquet_dir(self) -> Path:
        p = self.data_dir / "raw" / "parquet"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def duckdb_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "research.duckdb"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """测试用：清缓存后重新读取环境变量。"""
    get_settings.cache_clear()
    return get_settings()


settings = get_settings()

# 让 duckdb / 其他库使用统一时区
os.environ.setdefault("TZ", settings.timezone)
