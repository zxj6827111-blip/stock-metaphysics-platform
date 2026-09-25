"""通过唯一 CalendarSnapshot 组装 Fortune 时间上下文。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.core.fortune.ports import CalendarSnapshotProvider
from src.core.schemas.fortune import TemporalFortuneContext


def build_temporal_context(
    target_at: datetime,
    calendar_provider: CalendarSnapshotProvider,
    *,
    timezone: str = "Asia/Shanghai",
) -> TemporalFortuneContext:
    """历法只调用一次；年月日时全部由同一个快照提供。"""

    if target_at.tzinfo is None or target_at.utcoffset() is None:
        raise ValueError("target_at 必须带时区")
    local_at = target_at.astimezone(ZoneInfo(timezone))
    snapshot = calendar_provider.snapshot(local_at.replace(tzinfo=None))
    return TemporalFortuneContext(
        target_at=local_at,
        timezone=timezone,
        calendar_snapshot=snapshot,
    )
