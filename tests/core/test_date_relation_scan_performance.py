"""日期关系扫描热路径的口径和缓存兼容边界。"""

from __future__ import annotations

import random

import pytest

from src.core.orchestration.date_relation_scan import (
    _natal_cache_engine_compatible,
    _percentile_map,
)


def _legacy_percentile(value: int, values: list[int]) -> float | None:
    if not values:
        return None
    less = sum(1 for item in values if item < value)
    equal = sum(1 for item in values if item == value)
    return round((less + 0.5 * equal) / len(values) * 100, 2)


@pytest.mark.parametrize(
    "values",
    [
        [],
        [0],
        [-2, -2, 0, 4, 4, 4],
        [1, 2, 3, 4, 5],
    ],
)
def test_percentile_map_matches_previous_average_rank_semantics(values):
    ranks = _percentile_map(values)
    assert ranks == {
        value: _legacy_percentile(value, values)
        for value in set(values)
    }


def test_percentile_map_matches_previous_semantics_for_mixed_ties():
    rng = random.Random(20260929)
    values = [rng.randrange(-15, 16) for _ in range(250)]
    ranks = _percentile_map(values)
    assert all(
        ranks[value] == _legacy_percentile(value, values)
        for value in set(values)
    )


def test_only_the_explicit_natal_projection_version_is_compatible():
    assert _natal_cache_engine_compatible(
        "smx-bazi-native-1.0.0", "smx-bazi-native-1.0.2",
    )
    assert _natal_cache_engine_compatible(
        "smx-bazi-native-1.0.2", "smx-bazi-native-1.0.2",
    )
    assert not _natal_cache_engine_compatible(
        "smx-bazi-native-1.0.0", "smx-bazi-native-1.0.3",
    )
    assert not _natal_cache_engine_compatible(
        "", "smx-bazi-native-1.0.2",
    )
