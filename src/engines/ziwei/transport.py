"""紫微排盘服务的传输层（Adapter 内部，业务层不可见）。

为什么需要三个 transport
-----------------------
紫微排盘由 Node.js + iztro 提供（``services/ziwei-service``）。但本项目的
研究流水线需要**批量**排盘（数十只股票 × 多个 as_of × 2 个 variant），
而测试必须能在没有常驻服务的情况下离线运行。因此按以下顺序降级：

    http        ``SMP_ZIWEI_SERVICE_URL`` 已设置 → 走常驻服务（Docker / 生产）
    subprocess  本机 ``node`` 可用且服务已构建 → 每次批量调用一个子进程（本地/研究/测试）
    none        两者皆不可用 → 引擎返回 ``Availability.UNAVAILABLE``，其余引擎继续

**故障隔离**（AGENTS.md / Phase 2 要求）：紫微不可用时，八字、黄历、历史数据
必须继续工作；紫微的 ``score`` 返回 ``None``，绝不填 0。

**确定性**：transport 只负责搬运 JSON，不做任何计算、重试改写或缓存污染。
缓存键包含全部输入（含 variant 与 as_of），保证不同变体不会互相覆盖。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from src.core.config import PROJECT_ROOT, settings
from src.core.schemas.ziwei import ZiweiChart

SERVICE_DIR = PROJECT_ROOT / "services" / "ziwei-service"
CLI_ENTRY = SERVICE_DIR / "dist" / "cli.js"

#: 单次批量调用的超时（秒）。研究批量排盘可能较大，给足余量。
_SUBPROCESS_TIMEOUT = 120
_HTTP_TIMEOUT = 30


class ZiweiTransportError(RuntimeError):
    """transport 层错误（网络 / 进程 / 解析）。"""


class ZiweiRequestError(ZiweiTransportError):
    """服务明确拒绝了某个请求（如 variant_mode 非法）。"""


class ZiweiTransport(ABC):
    """传输抽象。"""

    name: str = "abstract"

    @abstractmethod
    def available(self) -> bool:
        """当前环境是否可用（不做真实调用）。"""

    @abstractmethod
    def describe(self) -> str:
        """人类可读的可用性说明（写入 warnings）。"""

    @abstractmethod
    def batch(self, requests: list[dict]) -> list[ZiweiChart]:
        """批量排盘。请求与返回**按位置一一对应**，失败位置抛 ``ZiweiRequestError``。"""


class NullZiweiTransport(ZiweiTransport):
    """不可用占位：明确拒绝，不做任何伪造。"""

    name = "none"

    def __init__(self, reason: str = "") -> None:
        self.reason = reason or "紫微排盘服务不可用（未配置 SMP_ZIWEI_SERVICE_URL 且本机缺少 node 或服务未构建）"

    def available(self) -> bool:
        return False

    def describe(self) -> str:
        return self.reason

    def batch(self, requests: list[dict]) -> list[ZiweiChart]:
        raise ZiweiTransportError(self.reason)


def _payload(requests: list[dict]) -> str:
    return json.dumps({"requests": requests}, ensure_ascii=False)


def _parse_response(raw: str, expected: int) -> list[ZiweiChart]:
    """把服务返回的 JSON 解析为 ``ZiweiChart`` 列表。

    任何位置出错都必须**显式抛出**，禁止用空盘面填充 —— 一个"看起来正常但其实是空壳"
    的紫微盘比"不可用"危险得多。
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - 服务端故障路径
        raise ZiweiTransportError(f"紫微服务返回非法 JSON：{exc}; 原文前 200 字：{raw[:200]}") from exc

    results = data.get("results") or []
    errors = data.get("errors") or []
    if errors:
        first = errors[0]
        raise ZiweiRequestError(
            f"紫微排盘被拒绝（共 {len(errors)} 条，首条 index={first.get('index')}）：{first.get('message')}"
        )
    if len(results) != expected:
        raise ZiweiTransportError(
            f"紫微服务返回条数与请求不一致：期望 {expected}，实际 {len(results)}"
        )
    charts: list[ZiweiChart] = []
    for item in results:
        try:
            charts.append(ZiweiChart.model_validate(_camel_to_snake(item)))
        except Exception as exc:  # noqa: BLE001 - 契约不匹配必须显式失败
            raise ZiweiTransportError(f"紫微盘面契约不匹配：{type(exc).__name__}: {exc}") from exc
    return charts


def _camel_to_snake(payload: dict) -> dict:
    """把服务的 camelCase 契约映射为本项目 snake_case 模型。

    映射表是**显式**的（不是通用转换），这样服务端字段改名会立刻在测试中暴露，
    而不是被通用转换悄悄吞掉。
    """
    top = {
        "engine_version": payload.get("engineVersion", ""),
        "config_version": payload.get("configVersion", ""),
        "third_party": f"iztro {payload.get('iztroVersion', '')} (MIT, SylarLong/iztro)",
        "variant_mode": {
            "variant_forward": "forward",
            "variant_reverse": "reverse",
            "not_applicable": "not_applicable",
        }.get(str(payload.get("variantMode", "")), "not_applicable"),
        "variant_basis": payload.get("variantBasis", ""),
        "gender_parameter": payload.get("genderParameter", ""),
        "solar_date": payload.get("solarDate", ""),
        "lunar_date": payload.get("lunarDate", ""),
        "chinese_date": payload.get("chineseDate", ""),
        "time_index": int(payload.get("timeIndex", 0)),
        "time_name": payload.get("timeName", ""),
        "time_range": payload.get("timeRange", ""),
        "soul": payload.get("soul", ""),
        "body": payload.get("body", ""),
        "five_elements_class": payload.get("fiveElementsClass", ""),
        "soul_palace_branch": payload.get("soulPalaceBranch", ""),
        "soul_palace_index": int(payload.get("soulPalaceIndex", -1)),
        "body_palace_index": int(payload.get("bodyPalaceIndex", -1)),
        "sign": payload.get("sign", ""),
        "zodiac": payload.get("zodiac", ""),
        "natal_mutagens": [
            {
                "mutagen": m.get("mutagen", ""),
                "star": m.get("star", ""),
                "palace_index": int(m.get("palaceIndex", 0)),
                "palace_name": m.get("palaceName", ""),
            }
            for m in payload.get("natalMutagens", [])
        ],
        "palaces": [_palace(p) for p in payload.get("palaces", [])],
        "decadals": [
            {
                "palace_index": int(d.get("palaceIndex", 0)),
                "palace_name": d.get("palaceName", ""),
                "range": [int(x) for x in (d.get("range") or [])],
                "heavenly_stem": d.get("heavenlyStem", ""),
                "earthly_branch": d.get("earthlyBranch", ""),
            }
            for d in payload.get("decadals", [])
        ],
        "horoscope": _horoscope(payload.get("horoscope") or {}),
    }
    return top


def _star(s: dict) -> dict:
    return {
        "name": s.get("name", ""),
        "type": s.get("type", ""),
        "brightness": s.get("brightness", ""),
        "mutagen": s.get("mutagen", ""),
        "scope": s.get("scope", "origin"),
    }


def _palace(p: dict) -> dict:
    return {
        "index": int(p.get("index", 0)),
        "name": p.get("name", ""),
        "heavenly_stem": p.get("heavenlyStem", ""),
        "earthly_branch": p.get("earthlyBranch", ""),
        "is_body_palace": bool(p.get("isBodyPalace", False)),
        "is_original_palace": bool(p.get("isOriginalPalace", False)),
        "major_stars": [_star(s) for s in p.get("majorStars", [])],
        "minor_stars": [_star(s) for s in p.get("minorStars", [])],
        "adjective_stars": [_star(s) for s in p.get("adjectiveStars", [])],
        "changsheng12": p.get("changsheng12", ""),
        "boshi12": p.get("boshi12", ""),
        "jiangqian12": p.get("jiangqian12", ""),
        "suiqian12": p.get("suiqian12", ""),
        "decadal_range": [int(x) for x in (p.get("decadalRange") or [])],
        "ages": [int(x) for x in (p.get("ages") or [])],
        "trine_indices": [int(x) for x in (p.get("trineIndices") or [])],
    }


def _section(s: dict | None) -> dict | None:
    if not s:
        return None
    return {
        "scope": s.get("scope", ""),
        "index": int(s.get("index", -1)),
        "heavenly_stem": s.get("heavenlyStem", ""),
        "earthly_branch": s.get("earthlyBranch", ""),
        "name": s.get("name", ""),
        "mutagen": list(s.get("mutagen") or []),
        "palace_names": list(s.get("palaceNames") or []),
        "stars": [[_star(x) for x in row] for row in (s.get("stars") or [])],
        "nominal_age": s.get("nominalAge"),
    }


def _horoscope(h: dict) -> dict | None:
    if not h:
        return None
    return {
        "solar_date": h.get("solarDate", ""),
        "time_index": int(h.get("timeIndex", 0)),
        "decadal": _section(h.get("decadal")),
        "age": _section(h.get("age")),
        "yearly": _section(h.get("yearly")),
        "monthly": _section(h.get("monthly")),
        "daily": _section(h.get("daily")),
        "hourly": _section(h.get("hourly")),
    }


class SubprocessZiweiTransport(ZiweiTransport):
    """通过 ``node dist/cli.js`` 批量排盘（默认 transport）。"""

    name = "subprocess"

    def __init__(self, node_bin: str | None = None, cli_entry: Path | None = None) -> None:
        self.node_bin = node_bin or shutil.which("node") or ""
        self.cli_entry = cli_entry or CLI_ENTRY

    def available(self) -> bool:
        return bool(self.node_bin) and self.cli_entry.is_file()

    def describe(self) -> str:
        if not self.node_bin:
            return "本机未检测到 node，紫微服务不可用"
        if not self.cli_entry.is_file():
            return f"紫微服务未构建（缺少 {self.cli_entry}），请运行 make ziwei-build"
        return f"subprocess: {self.node_bin} {self.cli_entry.name}"

    def batch(self, requests: list[dict]) -> list[ZiweiChart]:
        if not requests:
            return []
        if not self.available():
            raise ZiweiTransportError(self.describe())
        try:
            proc = subprocess.run(  # noqa: S603 - 参数为固定列表，无 shell
                [self.node_bin, str(self.cli_entry)],
                input=_payload(requests),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=_SUBPROCESS_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ZiweiTransportError(f"紫微服务超时（>{_SUBPROCESS_TIMEOUT}s）") from exc
        except OSError as exc:
            raise ZiweiTransportError(f"无法启动紫微服务：{exc}") from exc

        if proc.returncode != 0:
            raise ZiweiTransportError(
                f"紫微服务退出码 {proc.returncode}；stderr：{(proc.stderr or '')[:400]}"
            )
        return _parse_response(proc.stdout, len(requests))


class HttpZiweiTransport(ZiweiTransport):
    """通过常驻 HTTP 服务排盘（Docker / 生产部署）。"""

    name = "http"

    def __init__(self, base_url: str, timeout: int = _HTTP_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.base_url)

    def describe(self) -> str:
        return f"http: {self.base_url}/internal/ziwei/batch"

    def batch(self, requests: list[dict]) -> list[ZiweiChart]:
        if not requests:
            return []
        import httpx

        url = f"{self.base_url}/internal/ziwei/batch"
        try:
            resp = httpx.post(url, json={"requests": requests}, timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001 - 任何网络异常都视为不可用
            raise ZiweiTransportError(f"紫微服务不可达：{type(exc).__name__}: {exc}") from exc
        if resp.status_code != 200:
            raise ZiweiTransportError(
                f"紫微服务返回 HTTP {resp.status_code}：{resp.text[:300]}"
            )
        return _parse_response(resp.text, len(requests))


def build_transport() -> ZiweiTransport:
    """按 ``http → subprocess → none`` 选择 transport。"""
    url = (settings.ziwei_service_url or "").strip()
    if url:
        http = HttpZiweiTransport(url)
        if http.available():
            return http
    sub = SubprocessZiweiTransport()
    if sub.available():
        return sub
    if url:
        return NullZiweiTransport(f"紫微 HTTP 服务 {url} 不可用，且本机 subprocess 通道不可用")
    return NullZiweiTransport()


__all__ = [
    "ZiweiTransport", "ZiweiTransportError", "ZiweiRequestError",
    "NullZiweiTransport", "SubprocessZiweiTransport", "HttpZiweiTransport",
    "build_transport", "SERVICE_DIR", "CLI_ENTRY",
]
