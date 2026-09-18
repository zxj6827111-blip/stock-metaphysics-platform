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
    app_version: str = "0.1.0"
    phase: str = "phase1"
    debug: bool = False
    timezone: str = "Asia/Shanghai"

    # --- 路径 ---
    data_dir: Path = Field(default=PROJECT_ROOT / "data")
    knowledge_dir: Path = Field(default=PROJECT_ROOT / "knowledge")

    # --- 数据库 ---
    database_url: str = ""  # 留空则自动使用 data/smp.sqlite3

    # --- 引擎版本（结果可追溯性的核心；升级必须同步更新） ---
    birth_profile_version: str = "v1"
    calendar_engine_version: str = "lunar-python-1.4.8"
    huangli_engine_version: str = "huangli-engine-1.0.0"
    bazi_engine_version: str = "smx-bazi-native-1.0.0"
    factor_rule_version: str = "v1"
    knowledge_version: str = "kb-1.0.0"
    config_version: str = "cfg-2026.09"
    market_data_version: str = "akshare-1.18.96"

    # --- 行情 ---
    market_provider: str = "akshare"          # akshare | synthetic
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
