"""HuangliEngine —— 独立黄历 / 日课引擎（architecture §24、two_session_plan §6）。

设计要点
--------
1. 页面**不得**直接调用 lunar-python；所有黄历数据必须经本引擎产出结构化 Schema。
2. 原始黄历必须保存为 ``raw_huangli``（一等数据），并记录 ``engine_version`` /
   ``calculated_at``，便于未来审计。
3. 传统黄历信息（宜忌 / 建除 / 黄黑道 / 冲煞 / 彭祖百忌 …）与
   "股票研究映射"必须**分开展示** —— 后者属于因子层，不在本引擎内。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from src.core.config import settings
from src.core.schemas.calendar import HuangliDay, HuangliSnapshot
from src.core.schemas.common import Assumption, Availability, SourceRef, Warning_
from src.engines.base import EngineContext, EngineMetadata, MetaphysicsEngine
from src.engines.calendar.calendar_engine import CalendarEngine


class HuangliEngine(MetaphysicsEngine[HuangliSnapshot]):
    """黄历引擎。依赖 CalendarEngine 提供历法，自身只做"日课"结构化。"""

    metadata = EngineMetadata(
        engine_id="huangli",
        display_name="黄历引擎",
        engine_version=settings.huangli_engine_version,
        config_version=settings.config_version,
        third_party="6tail/lunar-python",
        third_party_commit="v1.4.8 (PyPI release)",
        notes="建除十二值 / 十二神 / 黄黑道 / 冲煞 / 彭祖百忌 / 星宿 / 吉神方位",
    )

    def __init__(self, calendar_engine: CalendarEngine | None = None) -> None:
        self._calendar = calendar_engine or CalendarEngine()

    # ------------------------------------------------------------------
    def calculate_chart(  # type: ignore[override]
        self,
        context: EngineContext,
        *,
        when: datetime | None = None,
        days: int = 1,
        **_: Any,
    ) -> HuangliSnapshot:
        """生成黄历快照。

        Args:
            when: 基准时刻，缺省取 ``context.as_of``。
            days: 需要同时返回的连续日数（从 ``when`` 当日开始）。
        """
        target = when or context.as_of
        if target is None:
            raise ValueError("HuangliEngine.calculate_chart 需要 when 或 context.as_of")
        return self.snapshot(target, days=days)

    # ------------------------------------------------------------------
    def snapshot(self, when: datetime, *, days: int = 1) -> HuangliSnapshot:
        warnings: list[Warning_] = []
        days = max(1, min(days, 400))

        primary_day = self._build_day(when)
        extra_days: list[HuangliDay] = []
        for offset in range(1, days):
            extra_days.append(self._build_day(when + timedelta(days=offset)))

        snapshot = HuangliSnapshot(
            engine_id=self.engine_id,
            engine_version=self.engine_version,
            config_version=settings.config_version,
            availability=Availability.OK,
            calculated_at=datetime.now(),
            primary=primary_day,
            days=[primary_day, *extra_days],
            assumptions=[
                "黄历字段来自 lunar-python 的确定性实现，不同流派黄历书可能存在差异",
                "宜忌（day_yi / day_ji）为传统黄历通书口径，与股票研究无直接映射关系",
            ],
            warnings=warnings,
            source=SourceRef(source="lunar-python", extra={"version": "1.4.8"}),
            raw_huangli=self._raw_payload(when, days),
        )
        return snapshot

    # ------------------------------------------------------------------
    def snapshots_for_window(
        self, *, start: datetime, offsets: list[int], window_days: int = 31
    ) -> dict[int, HuangliSnapshot]:
        """批量取多天的快照（用于逐日视图）。

        为什么需要它：``snapshot(when, days=31)`` 每次都会重新构造 31 天。
        逐日视图要算 20–60 天时会变成 O(n×31) 次历法调用。
        这里**只构造一次**覆盖 ``[start, start + max(offset) + window_days - 1]``
        的连续日历，再按 ``offsets`` 切片。

        与逐日调用 ``snapshot()`` 的结果**完全一致**（同一 ``_build_day`` 实现、
        同一 ``days`` 语义、同一时刻分量），差别只在调用次数 —— 由
        ``tests/engines/test_huangli_window_slices.py`` 断言逐字段相等。

        Args:
            start: 连续日历的起始时刻（时分参与 hour_ganzhi，必须与逐日调用一致）。
            offsets: 需要的偏移天数（相对于 ``start``），可乱序、可重复。
            window_days: 每天快照需要的长度（默认 31，与月聚合口径一致）。
        """
        if not offsets:
            return {}
        span = max(offsets) + window_days
        calendar_days = [self._build_day(start + timedelta(days=i)) for i in range(span)]
        out: dict[int, HuangliSnapshot] = {}
        for offset in set(offsets):
            slice_ = calendar_days[offset: offset + window_days]
            if not slice_:
                continue
            out[offset] = HuangliSnapshot(
                engine_id=self.engine_id,
                engine_version=self.engine_version,
                config_version=settings.config_version,
                availability=Availability.OK,
                calculated_at=datetime.now(),
                primary=slice_[0],
                days=list(slice_),
                assumptions=[
                    "黄历字段来自 lunar-python 的确定性实现，不同流派黄历书可能存在差异",
                    "宜忌（day_yi / day_ji）为传统黄历通书口径，与股票研究无直接映射关系",
                ],
                warnings=[],
                source=SourceRef(source="lunar-python", extra={"version": "1.4.8"}),
                raw_huangli={
                    "generated_at": datetime.now().isoformat(),
                    "engine_version": self.engine_version,
                    "primary": slice_[0].model_dump(mode="json"),
                    "batched_window": True,
                },
            )
        return out

    # ------------------------------------------------------------------
    def _build_day(self, when: datetime) -> HuangliDay:
        snap = self._calendar.snapshot(when)
        return HuangliDay(
            date=snap.solar.date,
            solar_text=f"{snap.solar.date.isoformat()} {snap.solar.weekday_cn}",
            lunar_text=snap.lunar.text,
            year_ganzhi=snap.year_ganzhi.text,
            month_ganzhi=snap.month_ganzhi.text,
            day_ganzhi=snap.day_ganzhi.text,
            hour_ganzhi=snap.hour_ganzhi.text,
            jieqi=snap.jieqi.name or snap.jieqi.prev_name,
            zodiac=snap.lunar.zodiac,
            day_nayin=snap.day_ganzhi.nayin,
            month_nayin=snap.month_ganzhi.nayin,
            year_nayin=snap.year_ganzhi.nayin,
            duty_officer=snap.duty_officer,
            day_tian_shen=snap.day_tian_shen,
            day_tian_shen_type=snap.day_tian_shen_type,
            day_tian_shen_luck=snap.day_tian_shen_luck,
            xiu=snap.xiu,
            xiu_luck=snap.xiu_luck,
            chong_desc=snap.chong_desc,
            sha_direction=snap.sha_direction,
            pengzu_gan=snap.pengzu_gan,
            pengzu_zhi=snap.pengzu_zhi,
            cai_shen_direction=snap.cai_shen_direction,
            xi_shen_direction=snap.xi_shen_direction,
            fu_shen_direction=snap.fu_shen_direction,
            tai_shen=snap.tai_shen,
            day_yi=list(snap.day_yi),
            day_ji=list(snap.day_ji),
        )

    # ------------------------------------------------------------------
    def _raw_payload(self, when: datetime, days: int) -> dict:
        """原始黄历快照（落库到 ``chart_artifact.raw_chart``）。"""
        primary = self._build_day(when)
        payload: dict[str, Any] = {
            "generated_at": datetime.now().isoformat(),
            "engine_version": self.engine_version,
            "primary": primary.model_dump(mode="json"),
        }
        # 单日查询不重复存 days，减小落库体积
        if days > 1:
            payload["days"] = [self._build_day(when + timedelta(days=i)).model_dump(mode="json")
                               for i in range(days)]
        return payload

    # ------------------------------------------------------------------
    def day_for(self, target: date) -> HuangliDay:
        """便捷方法：取某一天的黄历。"""
        return self._build_day(datetime(target.year, target.month, target.day))

    def collect_assumptions(self) -> list[Assumption]:
        return [
            Assumption(
                key="huangli.school",
                value="通书口径",
                reason="黄历宜忌在不同通书/流派间存在差异，本系统采用 lunar-python 内置口径",
                impact="宜忌字段仅作展示，不直接进入股票因子",
            ),
        ]


def get_huangli_engine() -> HuangliEngine:
    return HuangliEngine()
