"""只读研究视图的进程内结果缓存。

为什么需要它
------------
时间窗口 / 黄历视图都是**纯函数**：
``f(股票, as_of, 出生档案, 区间, 引擎与口径版本)``。
但其中紫微要启动 Node 排盘（约 0.09s/天）、黄历要逐日构造通书字段，
20 个交易日一次约 3 秒。页面每次打开都重算一遍是纯浪费，
也违反"页面读取不得触发重复重算"的要求。

缓存键的组成
------------
**必须**包含：股票/分析 id、区间参数、as_of、持有期/窗口数，以及
所有会影响结果的版本号（引擎版本、聚合口径、分类口径、序列化口径）。
少一个版本号就可能把旧口径的结果当成新口径返回 —— 那比慢更糟。

边界
----
* 只缓存**只读视图**，不缓存任何需要落库的写入路径；
* 有容量上限且是进程内的（重启即失效），不引入外部依赖；
* 命中与未命中都可在响应中看到（``cache`` 字段），不隐藏缓存行为。
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Callable, Hashable

#: 容量上限（条目数）。单个条目的 JSON 体积在几十 KB 量级，200 条足够一个研究会话。
DEFAULT_MAX_ENTRIES = 200


class ResultCache:
    """带容量上限的线程安全 LRU（进程内）。"""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self._max = max(1, int(max_entries))
        self._data: OrderedDict[Hashable, Any] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def key(self, *parts: Any) -> tuple:
        """构造缓存键。``None`` 与空串在这里**不等价**（区间参数语义不同）。"""
        return tuple(parts)

    def get_or_compute(self, key: Hashable, compute: Callable[[], Any]) -> tuple[Any, bool]:
        """返回 ``(值, 是否命中)``。"""
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self.hits += 1
                return self._data[key], True
        # 计算放在锁外：compute 可能耗时数秒，持锁会阻塞其它请求。
        # 代价是并发下同一键可能被算两次（幂等，仅浪费 CPU），换来的是不互相阻塞。
        value = compute()
        with self._lock:
            if key not in self._data:
                self._data[key] = value
                if len(self._data) > self._max:
                    self._data.popitem(last=False)
            else:
                value = self._data[key]
                self._data.move_to_end(key)
            self.misses += 1
        return value, False

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = 0
            self.misses = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


#: 各视图共用一个实例即可 —— 键里已经带了全部版本与区间信息。
TIMELINE_CACHE = ResultCache()
HUANGLI_CACHE = ResultCache()


def cache_descriptor(key: Hashable, hit: bool) -> dict:
    """把缓存状态写进响应，便于审计"这一份是刚算的还是缓存的"。"""
    return {"key": "|".join(str(p) for p in key), "hit": bool(hit)}


__all__ = ["ResultCache", "TIMELINE_CACHE", "HUANGLI_CACHE", "cache_descriptor"]
