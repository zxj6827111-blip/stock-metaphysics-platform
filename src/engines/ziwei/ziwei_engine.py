"""``ZiweiEngine`` —— 紫微斗数引擎（Phase 2A）。

契约（与 CalendarEngine / HuangliEngine / BaziEngine 一致）
-------------------------------------------------------
* 实现 ``MetaphysicsEngine``；
* 输出本项目自有模型 ``ZiweiChart``，第三方对象在 Adapter 内被丢弃（ADR-0001）；
* 必须记录 ``engine_version`` / ``config_version`` / ``variant_mode`` /
  ``assumptions`` / ``calculated_at``，并落 ``chart_artifact.raw_chart``；
* **不做业务判断**：不产出分数、方向、共识。分数属于因子层（Phase 2B）。

股票无性别（ADR-0010）
---------------------
紫微的 ``gender`` 参数只影响**大限/小限顺逆**与**长生十二神顺逆**，
其余盘面（十二宫、星曜、四化、流年/流月/流日）与性别无关。
因此本引擎把这一自由度显式化为方向 variant：

    VariantMode.FORWARD  → 强制顺行（阳年用男命规则、阴年用女命规则）
    VariantMode.REVERSE  → 强制逆行（阳年用女命规则、阴年用男命规则）
    VariantMode.NOT_APPLICABLE → **拒绝排盘**（不提供任何默认性别）

``VariantMode.BOTH`` 由编排层调用两次并分别落库，**不得先平均盘面**。

故障隔离
--------
紫微服务不可用时抛 ``ZiweiUnavailableError``；编排层捕获后产出一个
``availability=unavailable``、``score=None`` 的观点，其余引擎继续运行。
**禁止**把不可用当成 0 分。
"""

from __future__ import annotations

import threading
from datetime import datetime

from src.core.config import settings
from src.core.schemas.common import (
    Assumption,
    Availability,
    VariantMode,
    Warning_,
)
from src.core.schemas.common import (
    Availability as _Avail,
)
from src.core.schemas.ziwei import ZiweiChart
from src.engines.base import EngineContext, EngineMetadata, MetaphysicsEngine
from src.engines.ziwei import constants as zc
from src.engines.ziwei.transport import (
    ZiweiRequestError,
    ZiweiTransport,
    ZiweiTransportError,
    build_transport,
)


class ZiweiUnavailableError(RuntimeError):
    """紫微排盘不可用（缺服务 / variant 不适用 / 服务报错）。绝不伪造成空盘面。"""


#: 时辰序号 → 小时区间（iztro 口径：0 = 早子时，12 = 晚子时）
TIME_INDEX_RANGES: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 3), (3, 5), (5, 7), (7, 9), (9, 11), (11, 13),
    (13, 15), (15, 17), (17, 19), (19, 21), (21, 23), (23, 24),
)


def hour_to_time_index(dt: datetime) -> int:
    """把时刻映射为 iztro 的 ``timeIndex``（0..12）。

    分区口径与 ``CalendarEngine`` 的十二时辰一致：
    23:00 之后为**晚子时**（index 12），而不是次日子时 ——
    紫微的晚子时归属是流派差异点，本项目在此**显式固化**并写入 assumptions。
    """
    hour = dt.hour
    for idx, (start, end) in enumerate(TIME_INDEX_RANGES):
        if start <= hour < end:
            return idx
    return 12  # pragma: no cover - 上面的区间已覆盖 0..24


class ZiweiEngine(MetaphysicsEngine[ZiweiChart]):
    """紫微斗数引擎（iztro adapter）。"""

    metadata = EngineMetadata(
        engine_id="ziwei",
        display_name="紫微斗数引擎",
        engine_version=settings.ziwei_engine_version,
        config_version="cfg-ziwei-2026.09",
        third_party="iztro 2.6.1 (MIT) via services/ziwei-service (Node.js subprocess/HTTP)",
        third_party_commit="npm:iztro@2.6.1",
        notes=(
            "紫微排盘由 iztro 计算，经 Adapter 转成本项目 ZiweiChart；"
            "业务层不接触任何第三方对象。股票无真实性别，运限顺逆以 direction variant 表达。"
        ),
    )

    def __init__(self, transport: ZiweiTransport | None = None) -> None:
        self._transport = transport or build_transport()
        self._lock = threading.Lock()
        self._last_warnings: list[Warning_] = []

    # ------------------------------------------------------------------
    # 可用性
    # ------------------------------------------------------------------
    @property
    def availability(self) -> Availability:
        return _Avail.OK if self._transport.available() else _Avail.UNAVAILABLE

    @property
    def transport_name(self) -> str:
        return self._transport.name

    def unavailable_reason(self) -> str:
        return "" if self._transport.available() else self._transport.describe()

    def collect_warnings(self) -> list[Warning_]:
        out = list(self._last_warnings)
        if not self._transport.available():
            out.append(Warning_(
                code="ZIWEI_SERVICE_UNAVAILABLE",
                message=f"紫微排盘服务不可用：{self._transport.describe()}。"
                        "紫微相关字段返回 unavailable，其余引擎不受影响。",
                severity="warning",
            ))
        return out

    def collect_assumptions(self) -> list[Assumption]:
        return [
            Assumption(
                key="ziwei.variant_mode",
                value="forward / reverse（由调用方显式指定）",
                reason="股票没有真实性别，紫微的运限顺逆无法由性别推导。",
                impact="两个 variant 的差异**仅限于大限/小限顺逆与长生十二神顺逆**；"
                       "十二宫、星曜、四化、流年/流月/流日与 variant 无关。"
                       "因此两个 variant 不是两条独立证据，研究时必须分别回测而不是当作双确认。",
            ),
            Assumption(
                key="ziwei.fix_leap",
                value=str(settings.ziwei_fix_leap),
                reason="闰月出生者的月支归属存在流派差异；本项目显式固定 iztro 的 fixLeap 口径。",
                impact="闰月前后出生时刻的命宫位置可能与其他流派不同。",
            ),
            Assumption(
                key="ziwei.time_index_sect",
                value="23:00-24:00 计为晚子时（timeIndex=12）",
                reason="早晚子时归属是已知流派差异点。",
                impact="23 点后出生（或流时）的时柱/命宫可能与其他流派相差一日。",
            ),
            Assumption(
                key="ziwei.stock_mapping",
                value=settings.ziwei_stock_mapping_version,
                reason="『财帛宫 = 股价』『官禄宫 = 公司经营』等映射**不是传统定论**，是本研究项目的假设。",
                impact="映射本身必须先经历史回测检验，不得在 UI/文档中表述为传统规定。",
            ),
        ]

    # ------------------------------------------------------------------
    # 主接口
    # ------------------------------------------------------------------
    def calculate_chart(  # type: ignore[override]
        self,
        context: EngineContext,
        *,
        birth_datetime: datetime | None = None,
        as_of: datetime | None = None,
        variant_mode: VariantMode | str = VariantMode.NOT_APPLICABLE,
        **kwargs: object,
    ) -> ZiweiChart:
        """排一张紫微盘。

        单次调用复用批量入口，保证研究批量排盘与运行时单盘排盘使用完全相同的
        请求构造、版本戳、assumptions 和 warning 口径。

        Raises:
            ZiweiUnavailableError: 服务不可用 / variant 不适用 / 服务拒绝请求。
        """
        charts = self.calculate_charts([{
            "context": context,
            "birth_datetime": birth_datetime,
            "as_of": as_of,
            "variant_mode": variant_mode,
            "stock_code": kwargs.get("stock_code", ""),
        }])
        return charts[0]

    def calculate_charts(self, requests: list[dict]) -> list[ZiweiChart]:
        """批量排紫微盘并按输入顺序返回。

        ``requests`` 每项必须含 ``context``，可选 ``birth_datetime`` / ``as_of`` /
        ``variant_mode`` / ``stock_code``。该入口只做请求编排与结果装配，不改变
        iztro 的计算口径；研究流水线用它减少重复启动 Node subprocess 的成本。
        """
        if not requests:
            return []
        if not self._transport.available():
            raise ZiweiUnavailableError(self._transport.describe())

        transport_requests: list[dict] = []
        prepared: list[tuple[EngineContext, datetime, datetime, VariantMode, str]] = []
        for item in requests:
            context = item.get("context")
            if not isinstance(context, EngineContext):
                raise ZiweiUnavailableError("紫微批量请求缺少 EngineContext。")
            birth = item.get("birth_datetime") or (context.extras or {}).get("birth_datetime")
            if not isinstance(birth, datetime):
                raise ZiweiUnavailableError("未提供有效 birth_datetime，无法排紫微盘。")
            raw_mode = item.get("variant_mode", VariantMode.NOT_APPLICABLE)
            mode = raw_mode if isinstance(raw_mode, VariantMode) else VariantMode(raw_mode)
            if mode == VariantMode.NOT_APPLICABLE:
                raise ZiweiUnavailableError(
                    "variant_mode=not_applicable 时不进行紫微排盘：紫微运限需要顺逆方向，"
                    "而股票没有真实性别。请显式指定 forward（顺行）或 reverse（逆行），"
                    "或 both（两者分别计算、分别保存，不得平均）。"
                )
            as_of_dt = item.get("as_of") or context.as_of or birth
            if not isinstance(as_of_dt, datetime):
                raise ZiweiUnavailableError("未提供有效 as_of，无法排紫微盘。")
            transport_requests.append({
                "solarDate": f"{birth.year}-{birth.month}-{birth.day}",
                "timeIndex": hour_to_time_index(birth),
                "variantMode": {
                    VariantMode.FORWARD: "variant_forward",
                    VariantMode.REVERSE: "variant_reverse",
                }.get(mode, "not_applicable"),
                "asOfDate": f"{as_of_dt.year}-{as_of_dt.month}-{as_of_dt.day}",
                "asOfTimeIndex": hour_to_time_index(as_of_dt),
            })
            prepared.append((
                context, birth, as_of_dt, mode,
                context.stock_code or str(item.get("stock_code") or ""),
            ))

        try:
            with self._lock:
                charts = self._transport.batch(transport_requests)
        except ZiweiRequestError as exc:
            raise ZiweiUnavailableError(f"紫微排盘被服务拒绝：{exc}") from exc
        except ZiweiTransportError as exc:
            raise ZiweiUnavailableError(f"紫微排盘失败：{exc}") from exc

        out: list[ZiweiChart] = []
        for chart, (_context, birth, as_of_dt, mode, stock_code) in zip(
            charts, prepared, strict=True,
        ):
            stamped = chart.model_copy(update={
                "stock_code": stock_code,
                "birth_datetime": birth,
                "as_of": as_of_dt,
                "engine_version": self.metadata.engine_version,
                "config_version": self.metadata.config_version,
                "assumptions": self.collect_assumptions(),
                "warnings": self._chart_warnings(chart, mode),
                "calculated_at": datetime.now(),
            })
            out.append(stamped)
        self._last_warnings = list(out[-1].warnings) if out else []
        return out

    def _chart_warnings(self, chart: ZiweiChart, mode: VariantMode) -> list[Warning_]:
        warnings: list[Warning_] = []
        if mode == VariantMode.BOTH:
            warnings.append(Warning_(
                code="ZIWEI_VARIANT_BOTH_NOT_SUPPORTED_HERE",
                message="BOTH 由编排层展开为两次独立排盘；本引擎一次只返回一个 variant。",
                severity="info",
            ))
        if len(chart.palaces) != 12:
            warnings.append(Warning_(
                code="ZIWEI_PALACE_COUNT_ANOMALY",
                message=f"十二宫数量异常：{len(chart.palaces)}（应为 12）。",
                severity="error",
            ))
        # 三方四正自校验（对拍 iztro 的 surroundedPalaces 与本地索引算术）
        for p in chart.palaces:
            expected = zc.trine_indices(p.index)
            if p.trine_indices and p.trine_indices != expected:
                warnings.append(Warning_(
                    code="ZIWEI_TRINE_INDEX_MISMATCH",
                    message=(f"{p.name}宫({p.index}) 三方四正索引 {p.trine_indices} "
                             f"与本地规则 {expected} 不一致，已按引擎输出为准并记录差异。"),
                    severity="warning",
                    context={"palace": p.name, "engine": p.trine_indices, "local": expected},
                ))
        if not chart.natal_mutagens:
            warnings.append(Warning_(
                code="ZIWEI_NATAL_MUTAGEN_MISSING",
                message="未解析出生年四化，紫微四化类因子将返回 unavailable。",
                severity="warning",
            ))
        return warnings

    # ------------------------------------------------------------------
    # MetaphysicsEngine 其余接口
    # ------------------------------------------------------------------
    def extract_factors(self, chart: ZiweiChart, context: EngineContext) -> list[dict]:
        """紫微因子由 ``src/factors/ziwei/compute.py`` 统一计算（Phase 2B）。

        这里保持空实现，避免出现"两套因子计算入口"。
        """
        return []

    def explain_rules(self, chart: ZiweiChart, factors: list[dict]) -> list[str]:
        soul = chart.palace_at(chart.soul_palace_index)
        trine = "、".join(p.name for p in chart.trine_of(chart.soul_palace_index)[1:])
        lines = [
            f"命宫在{chart.soul_palace_branch}（第 {chart.soul_palace_index} 宫），"
            f"命主{chart.soul or '未知'}、身主{chart.body or '未知'}，五行局{chart.five_elements_class or '未知'}。",
            f"命宫主星：{'、'.join(s.name for s in soul.major_stars) if soul and soul.major_stars else '空宫'}；"
            f"三方四正另见 {trine or '（缺）'}。",
            "生年四化：" + "；".join(
                f"{zc.MUTAGEN_CN.get(m.mutagen, m.mutagen)}{m.star}入{m.palace_name}"
                for m in chart.natal_mutagens
            ) if chart.natal_mutagens else "生年四化不可用。",
            "以上均为传统紫微斗数的结构性描述，不构成对股票收益的任何判断。",
        ]
        return lines

    def build_evidence_query(self, chart: ZiweiChart, factors: list[dict]) -> list[str]:
        """构造古籍检索查询词（紫微域）。"""
        queries: list[str] = []
        soul = chart.palace_at(chart.soul_palace_index)
        if soul and soul.major_stars:
            queries.extend(f"{s.name}坐命" for s in soul.major_stars[:3])
        for m in chart.natal_mutagens[:4]:
            queries.append(f"{zc.MUTAGEN_CN.get(m.mutagen, m.mutagen)}{m.star}")
        for name in ("财帛", "官禄", "迁移"):
            p = chart.palace_by_name(name)
            if p and p.major_stars:
                queries.append(f"{name}宫{'、'.join(s.name for s in p.major_stars[:2])}")
        return queries

    def score(self, factors: list[dict]) -> dict:
        """引擎自身不产出分数 —— 聚合属于 Opinion 层（见 analysis_service）。"""
        return {"score": None, "direction": 0, "confidence": 0.0}


__all__ = ["ZiweiEngine", "ZiweiUnavailableError", "hour_to_time_index", "TIME_INDEX_RANGES"]
