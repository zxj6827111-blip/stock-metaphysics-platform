"""严格限定股票、日期、条件与数据版本的内部事件查询（W3）。

此模块供后续 v2 API / 面板使用；旧 v1 路由及其历史查询行为保持原样。
任何查询都必须明确给出单股/股票范围、日期区间、因子条件及各层版本。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import pandas as pd

HISTORICAL_RESEARCH_TIME = time(15, 0)


@dataclass(frozen=True)
class VersionedEventQuery:
    stock_codes: tuple[str, ...]
    date_from: date
    date_to: date
    factor_ids: tuple[str, ...]
    activation: str
    research_time: time
    engine_version: str
    rule_version: str
    config_version: str
    label_version: str
    bar_version: str
    factor_data_version: str
    price_basis: str
    direction_filter: int | None = None
    min_rule_score: float | None = None

    def validate(self) -> None:
        if not self.stock_codes or any(not str(code).strip() for code in self.stock_codes):
            raise ValueError("版本化历史查询必须显式指定至少一只股票")
        if self.date_from > self.date_to:
            raise ValueError("date_from 不能晚于 date_to")
        if self.research_time != HISTORICAL_RESEARCH_TIME:
            raise ValueError("新历史日频研究的 research_time 必须固定为 15:00 Asia/Shanghai")
        if not self.factor_ids or any(not str(fid).strip() for fid in self.factor_ids):
            raise ValueError("版本化历史查询必须显式指定因子条件")
        if self.activation not in {"any", "nonzero", "positive", "negative"}:
            raise ValueError("activation 必须显式为 any/nonzero/positive/negative")
        required_versions = (
            self.engine_version, self.rule_version, self.config_version,
            self.label_version, self.bar_version, self.factor_data_version, self.price_basis,
        )
        if any(not str(value).strip() for value in required_versions):
            raise ValueError("版本化历史查询缺少计算、标签或数据版本")
        if self.price_basis != "raw_times_factor":
            raise ValueError("新历史研究查询必须使用 raw_times_factor 价格口径")


def select_versioned_event_frames(
    observations: pd.DataFrame,
    labels: pd.DataFrame,
    query: VersionedEventQuery,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """按请求的身份、时间、条件和版本筛选，并拒绝重复键/跨版本连接。"""
    query.validate()
    observation_columns = {
        "stock_code", "as_of", "trade_date", "factor_id", "direction", "rule_score",
        "normalized_value", "engine_version", "rule_version", "config_version",
    }
    label_columns = {
        "stock_code", "trade_date", "label_version", "bar_version", "factor_version",
        "price_basis",
    }
    missing_obs = observation_columns - set(observations.columns)
    missing_labels = label_columns - set(labels.columns)
    if missing_obs or missing_labels:
        raise ValueError(
            f"版本化面板字段缺失：observations={sorted(missing_obs)}; labels={sorted(missing_labels)}"
        )

    obs = observations.copy()
    lab = labels.copy()
    obs["as_of"] = pd.to_datetime(obs["as_of"], errors="coerce")
    obs["trade_date"] = pd.to_datetime(obs["trade_date"], errors="coerce").dt.date
    lab["trade_date"] = pd.to_datetime(lab["trade_date"], errors="coerce").dt.date
    codes = set(query.stock_codes)
    factors = set(query.factor_ids)
    obs = obs[
        obs["stock_code"].astype(str).isin(codes)
        & obs["factor_id"].astype(str).isin(factors)
        & obs["trade_date"].between(query.date_from, query.date_to)
        & (obs["as_of"].dt.time == query.research_time)
        & (obs["engine_version"].astype(str) == query.engine_version)
        & (obs["rule_version"].astype(str) == query.rule_version)
        & (obs["config_version"].astype(str) == query.config_version)
    ].copy()
    lab = lab[
        lab["stock_code"].astype(str).isin(codes)
        & lab["trade_date"].between(query.date_from, query.date_to)
        & (lab["label_version"].astype(str) == query.label_version)
        & (lab["bar_version"].astype(str) == query.bar_version)
        & (lab["factor_version"].astype(str) == query.factor_data_version)
        & (lab["price_basis"].astype(str) == query.price_basis)
    ].copy()

    if query.direction_filter is not None:
        obs = obs[obs["direction"] == query.direction_filter]
    if query.min_rule_score is not None:
        obs = obs[pd.to_numeric(obs["rule_score"], errors="coerce") >= query.min_rule_score]
    if query.activation != "any":
        values = pd.to_numeric(obs["normalized_value"], errors="coerce")
        if query.activation == "nonzero":
            obs = obs[values.notna() & (values != 0)]
        elif query.activation == "positive":
            obs = obs[values.notna() & (values > 0)]
        else:
            obs = obs[values.notna() & (values < 0)]

    observation_key = [
        "stock_code", "trade_date", "factor_id", "engine_version", "rule_version", "config_version",
    ]
    if obs.duplicated(observation_key, keep=False).any():
        raise ValueError("版本化因子观测存在重复身份/日期/因子/版本键")
    if lab.duplicated(["stock_code", "trade_date"], keep=False).any():
        raise ValueError("版本化标签存在重复股票/日期键")
    return obs.reset_index(drop=True), lab.reset_index(drop=True)


def join_versioned_event_frames(
    observations: pd.DataFrame,
    labels: pd.DataFrame,
    query: VersionedEventQuery,
) -> pd.DataFrame:
    """执行已限定版本的股票/日期连接；无匹配结果保持空，不扩大查询范围。"""
    obs, lab = select_versioned_event_frames(observations, labels, query)
    return obs.merge(lab, on=["stock_code", "trade_date"], how="inner", validate="many_to_one")


__all__ = [
    "HISTORICAL_RESEARCH_TIME",
    "VersionedEventQuery",
    "join_versioned_event_frames",
    "select_versioned_event_frames",
]
