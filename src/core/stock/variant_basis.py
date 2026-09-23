"""运限变体来源（``VariantBasis``）的**单一真源**：首日阴阳 → 顺逆假设。

为什么单独一个模块
------------------
``VariantMode`` 只说"顺排/逆排/不适用"，不说**这个方向凭什么**。股票没有真实性别
（``AGENTS.md`` §5），所以每个顺逆都必须能回答依据。本项目允许的唯一依据是
用户权威表里的**上市首日涨跌标识**：

    阳（首日收涨） → 男命假设 → 阳男顺行 / 阴年逆行
    阴（首日收跌） → 女命假设 → 阳年逆行 / 阴女顺行

顺逆再由"性别 + 年干阴阳"决定，这部分由引擎自己算（``BaziEngine._da_yun``），
本模块只负责"阴阳 → 变体 + 可追溯元数据"。

纪律（``AGENTS.md`` §5、ADR-0014）
----------------------------------
1. **这是假设，不是事实**：必须写入 ``assumptions``，输出必须带免责声明；
2. **缺数据不猜**：没有 ``first_day_yinyang`` 时返回不可用语义（``not_applicable``
   + 原因），不许用"默认男命"顶替（§2.4）；
3. **不进入任何因子**：要进入必须先按 §5.4 把两种 variant 分别注册并回测；
4. 改口径必须提升 ``VARIANT_BASIS_VERSION``（§11）。

CLI（``scripts/astrology_calendar.py``）与 API 共用本模块，避免两套口径跑偏 ——
2026-09 的"界面显示不出大运"就是 CLI 与界面各有一套口径造成的。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.schemas.common import Assumption, VariantMode
from src.core.schemas.stock import StockMaster

#: 「首日阴阳 → 运限变体」假设的规则版本。改映射或改表述都必须提升它。
VARIANT_BASIS_VERSION = "v1-first_day_yinyang"

#: 首日涨跌标识 → 运限变体（顺排/逆排）。
FIRST_DAY_YINYANG_TO_VARIANT: dict[str, VariantMode] = {
    "阳": VariantMode.FORWARD,
    "阴": VariantMode.REVERSE,
}

#: 首日涨跌标识 → "性别"假设标签。**只用于展示**，不是股票的真实性别。
FIRST_DAY_YINYANG_TO_GENDER: dict[str, str] = {
    "阳": "男命",
    "阴": "女命",
}

#: 任何使用该假设的输出都必须带上这句话（``AGENTS.md`` §5.3）。
FIRST_DAY_YINYANG_DISCLAIMER = (
    "运限推演基于假设规则：股票无真实性别，「阳（首日收涨）→男命 / 阴（首日收跌）→女命」"
    "是本项目的显式假设，非事实；该口径未回测，不进入任何正式因子，"
    "不得据此判断涨跌。"
)


@dataclass(frozen=True)
class VariantDerivation:
    """一次「首日阴阳 → 运限变体」推导的结果，附带可追溯元数据。"""

    #: 推导出的变体；数据缺失时为 ``NOT_APPLICABLE``（不输出大运）。
    variant_mode: VariantMode
    #: 是否成功推导。``False`` 时 ``variant_mode`` 必为 ``NOT_APPLICABLE``。
    available: bool
    #: 人话说明，直接进 ``StockBirthProfile.variant_note``，前端原样展示。
    note: str
    #: 要写进 ``assumptions`` 的条目（数据缺失时记录缺口本身）。
    assumptions: list[Assumption] = field(default_factory=list)


def _pct_text(pct: float | None) -> str:
    """涨跌幅 → ``+3.01%`` / ``-10.87%``；缺失返回空串。"""
    return "" if pct is None else f"{pct * 100:+.2f}%"


def derive_variant_from_first_day(stock: StockMaster) -> VariantDerivation:
    """由 ``stock.first_day_yinyang`` 推导运限变体。

    只读输入：``first_day_yinyang``（阳/阴）与 ``first_day_pct_chg``（仅用于说明文案）。
    其它任何字段都不参与 —— 尤其**不得**回退到年干阴阳、股票名称、行业等去"猜"性别。
    """
    yinyang = (stock.first_day_yinyang or "").strip()
    variant = FIRST_DAY_YINYANG_TO_VARIANT.get(yinyang)
    pct_text = _pct_text(stock.first_day_pct_chg)

    if variant is None:
        return VariantDerivation(
            variant_mode=VariantMode.NOT_APPLICABLE,
            available=False,
            note=(
                "缺上市首日涨跌标识（stock_master.first_day_yinyang），无法按首日阴阳推导"
                "运限顺逆；本次不输出大运，也不以任何默认性别顶替。"
            ),
            assumptions=[
                Assumption(
                    key="birth.variant_basis",
                    value="first_day_yinyang:unavailable",
                    reason="请求按首日阴阳推导运限，但该标的缺上市首日涨跌数据",
                    impact=(
                        "variant_mode 保持 not_applicable，不输出大运；"
                        f"规则版本 {VARIANT_BASIS_VERSION}"
                    ),
                )
            ],
        )

    gender = FIRST_DAY_YINYANG_TO_GENDER[yinyang]
    pct_clause = f"（首日 {pct_text}）" if pct_text else ""
    return VariantDerivation(
        variant_mode=variant,
        available=True,
        note=(
            f"首日涨跌标识「{yinyang}」{pct_clause} → 按本项目显式假设记为{gender} → "
            f"variant_mode={variant.value}。{FIRST_DAY_YINYANG_DISCLAIMER}"
        ),
        assumptions=[
            Assumption(
                key="birth.variant_basis",
                value=f"first_day_yinyang:{yinyang}",
                reason=(
                    "传统运限顺逆依赖性别，股票无真实性别；本项目以「上市首日涨跌」作为"
                    "阴阳依据的显式假设（非事实）"
                ),
                impact=(
                    f"推导出 variant_mode={variant.value}（{gender}假设）；"
                    f"规则版本 {VARIANT_BASIS_VERSION}；不进入任何因子"
                ),
            ),
            Assumption(
                key="birth.variant_mode",
                value=variant.value,
                reason=f"由首日涨跌标识「{yinyang}」推导（{gender}假设），非股票真实性别",
                impact=(
                    "运限顺逆依赖该假设；必须与 explicit 路径分别回测，"
                    "Phase 1/2 均不纳入正式因子"
                ),
            ),
        ],
    )
