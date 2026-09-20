"""紫微第二实现源（REFERENCE ONLY）—— Node 客户端。

定位与硬约束（GOAL §3G-2）
--------------------------
本模块**只能**用于"验证 iztro 排盘实现差异"：

* 不得进入 ``ConsensusEngine``；
* 不得与 iztro 一起构成"双重确认"（那不是两个独立证据，只是同一算法被抄了两遍）；
* 不得被业务层依赖 —— 它不属于六个核心接口中的任何一个。

降级策略（与紫微生产 transport 一致）
-------------------------------------
    node 可用 + 依赖已安装 → subprocess 调用 ``reference_chart.js``
    否则                   → 返回 ``REFERENCE_UNAVAILABLE``，交叉核对标记为
                             ``CROSSCHECK_UNAVAILABLE``，**不阻塞**后续阶段。

本模块不做任何计算、缓存或重试改写：它只搬运 JSON。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

from src.core.config import PROJECT_ROOT

#: 参考实现服务目录
REFERENCE_SERVICE_DIR = PROJECT_ROOT / "services" / "ziwei-reference-service"
REFERENCE_CLI = REFERENCE_SERVICE_DIR / "reference_chart.js"
REFERENCE_NODE_MODULES = REFERENCE_SERVICE_DIR / "node_modules" / "fortel-ziweidoushu"

#: 状态常量
REFERENCE_AVAILABLE = "REFERENCE_AVAILABLE"
REFERENCE_UNAVAILABLE = "REFERENCE_UNAVAILABLE"
CROSSCHECK_UNAVAILABLE = "CROSSCHECK_UNAVAILABLE"

#: 参考实现档案（写入报告）
REFERENCE_LIBRARY = "fortel-ziweidoushu"
REFERENCE_VERSION_PINNED = "1.3.4"
REFERENCE_SCHOOL = "中州派"
REFERENCE_LICENSE = "MIT"
REFERENCE_REPOSITORY = "https://github.com/airicyu/fortel-ziweidoushu"

#: subprocess 超时（秒）
_TIMEOUT = 180


@dataclass
class ReferenceStatus:
    """参考实现的可用性状态（写入产物与报告）。"""

    status: str
    library: str
    version: str
    school: str
    license: str
    repository: str
    node_binary: str = ""
    service_dir: str = ""
    detail: str = ""
    dependencies_installed: bool = False

    @property
    def available(self) -> bool:
        return self.status == REFERENCE_AVAILABLE

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "library": self.library,
            "version": self.version,
            "school": self.school,
            "license": self.license,
            "repository": self.repository,
            "node_binary": self.node_binary,
            "service_dir": self.service_dir,
            "dependencies_installed": self.dependencies_installed,
            "detail": self.detail,
            "enters_consensus_engine": False,
            "role": "REFERENCE_ONLY",
        }


def reference_status() -> ReferenceStatus:
    """检测参考实现是否可用（不发起真实调用）。"""
    node_binary = shutil.which("node") or ""
    dependencies = REFERENCE_NODE_MODULES.is_dir()
    if not node_binary:
        status, detail = REFERENCE_UNAVAILABLE, "本机未检测到 node，第二实现源不可用"
    elif not REFERENCE_CLI.is_file():
        status, detail = REFERENCE_UNAVAILABLE, f"缺少参考 CLI：{REFERENCE_CLI}"
    elif not dependencies:
        status, detail = (
            REFERENCE_UNAVAILABLE,
            f"参考实现依赖未安装：请执行 "
            f"`cd {REFERENCE_SERVICE_DIR.name} && npm install`",
        )
    else:
        status, detail = REFERENCE_AVAILABLE, f"subprocess: {node_binary} {REFERENCE_CLI.name}"
    return ReferenceStatus(
        status=status,
        library=REFERENCE_LIBRARY,
        version=REFERENCE_VERSION_PINNED,
        school=REFERENCE_SCHOOL,
        license=REFERENCE_LICENSE,
        repository=REFERENCE_REPOSITORY,
        node_binary=node_binary,
        service_dir=str(REFERENCE_SERVICE_DIR),
        dependencies_installed=dependencies,
        detail=detail,
    )


class ReferenceUnavailableError(RuntimeError):
    """参考实现不可用（缺 node / 缺依赖 / CLI 缺失）。"""


def run_reference(cases: list[dict], *, timeout: int = _TIMEOUT) -> dict[str, Any]:
    """批量排盘（参考实现）。

    Args:
        cases: ``[{"case_id": str, "solar": {"year","month","day"}, "time_branch": str,
                 "gender": "M"|"F", "config_type": "SKY"|"GROUND"|"HUMAN"}]``

    Returns:
        参考 CLI 的原始 JSON（含 ``results``）。

    Raises:
        ReferenceUnavailableError: 环境不可用或调用失败。
    """
    status = reference_status()
    if not status.available:
        raise ReferenceUnavailableError(status.detail)
    payload = json.dumps({"cases": cases}, ensure_ascii=False)
    completed = subprocess.run(
        [status.node_binary, str(REFERENCE_CLI)],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        cwd=str(REFERENCE_SERVICE_DIR),
        check=False,
    )
    if completed.returncode != 0:
        raise ReferenceUnavailableError(
            f"参考 CLI 退出码 {completed.returncode}：{completed.stderr[:400]}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ReferenceUnavailableError(
            f"参考 CLI 输出不是合法 JSON：{exc}；stdout 头 200 字符={completed.stdout[:200]!r}"
        ) from exc


@dataclass
class ReferenceChart:
    """一个案例的参考盘面（已归一化字段名，字形仍为繁体，由比较器归一化）。"""

    case_id: str
    ok: bool
    chart: dict = field(default_factory=dict)
    error: str = ""
    school: str = REFERENCE_SCHOOL
    library: str = REFERENCE_LIBRARY
    version: str = REFERENCE_VERSION_PINNED


def fetch_charts(cases: list[dict], *, timeout: int = _TIMEOUT) -> list[ReferenceChart]:
    """批量取参考盘面；单案例失败不抛异常（记录为 ``ok=False``）。"""
    payload = run_reference(cases, timeout=timeout)
    if "error" in payload:
        raise ReferenceUnavailableError(str(payload["error"]))
    out: list[ReferenceChart] = []
    for item in payload.get("results", []):
        out.append(ReferenceChart(
            case_id=str(item.get("case_id", "")),
            ok=bool(item.get("ok")),
            chart=item.get("chart") or {},
            error=str(item.get("error", "")),
            school=str(item.get("school", REFERENCE_SCHOOL)),
            library=str(item.get("reference_library", REFERENCE_LIBRARY)),
            version=str(item.get("reference_version", REFERENCE_VERSION_PINNED)),
        ))
    return out


__all__ = [
    "CROSSCHECK_UNAVAILABLE",
    "REFERENCE_AVAILABLE",
    "REFERENCE_CLI",
    "REFERENCE_LIBRARY",
    "REFERENCE_LICENSE",
    "REFERENCE_REPOSITORY",
    "REFERENCE_SCHOOL",
    "REFERENCE_SERVICE_DIR",
    "REFERENCE_UNAVAILABLE",
    "REFERENCE_VERSION_PINNED",
    "ReferenceChart",
    "ReferenceStatus",
    "ReferenceUnavailableError",
    "fetch_charts",
    "reference_status",
    "run_reference",
]
