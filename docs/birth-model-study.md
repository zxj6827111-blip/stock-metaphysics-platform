# Phase 3B · Birth Model 对比研究

> 生成：2026-09-19T13:56:49
> Universe: ``v2-phase3a``（500 股）
> as_of 固定 = ``2026-08-14``（与 composite_none 快照截止对齐）
> author: Phase 3B pipeline (`scripts/phase3_birth_model_study.py`)

## A. 候选 Birth Model 定义

| Model | 定义 | 可用性 | 数据精度 |
|---|---|---|---|
| ``listing_open`` | 上市首日 09:30（``_v1``） | ✅ tushare_pit_universe | 高 |
| ``listing_close`` | 上市首日 15:00（``_v1``） | ✅ 同上 | 高 |
| ``ipo_date_approx`` | 上市日 - 7 自然日 09:30 | ✅（启发式） | 中（approximated=True） |
| ``company_foundation`` | 公司注册成立日 | ❌ UNAVAILABLE | 数据源不可得 |

## B. 三只真实股票 × 三模型的四柱演示

| 股票 | listing_open (年/月/日/时) | listing_close | ipo_approx |
|---|---|---|---|
| 000003 | 辛未/甲午/甲戌/己巳 | 辛未/甲午/甲戌/壬申 | 辛未/甲午/丁卯/乙巳 |
| 000004 | 庚午/丁亥/庚子/辛巳 | 庚午/丁亥/庚子/甲申 | 庚午/丁亥/癸巳/丁巳 |
| 000005 | 庚午/戊子/己酉/己巳 | 庚午/戊子/己酉/壬申 | 庚午/丁亥/壬寅/乙巳 |

**解读**：
- ``listing_open`` 和 ``listing_close`` **日柱相同，仅时柱不同**（09:30 vs 15:00 落在不同时辰）
- ``ipo_date_approx`` 的日柱整体平移 7 天，造成完全不同的四柱组合
- ``company_foundation`` 缺失，未落库（Phase 3 §3B-1 纪律）

## C. 因子区分度按模型统计

| Model | 因子数 | 常量因子数 | 平均 unique_ratio |
|---|---:|---:|---:|
| `ipo_approx_v1` | 97 | 2 | 0.0325 |
| `listing_close_v1` | 97 | 2 | 0.0324 |
| `listing_open_v1` | 97 | 2 | 0.0323 |

## D. Z_LIFE_006（身宫命同宫，Phase 1.1 历史常量）按模型复核

| Model | n | unique_ratio | is_constant |
|---|---:|---:|---|
| `ipo_approx_v1` | 500 | 0.0020 | True |
| `listing_close_v1` | 500 | 0.0020 | True |
| `listing_open_v1` | 500 | 0.0020 | True |

## E. 常量因子列表（按模型）

### ``ipo_approx_v1`` (共 2 个)

- `Z_LIFE_006`
- `Z_YEAR_001`

### ``listing_close_v1`` (共 2 个)

- `Z_LIFE_006`
- `Z_YEAR_001`

### ``listing_open_v1`` (共 2 个)

- `Z_LIFE_006`
- `Z_YEAR_001`

## F. 结论与 Phase 3B 纪律声明

1. 三个 birth model 在同一股票上产生**真正不同的四柱**（见 §B 示例）。
2. **factor 区分度**按模型差异详见 CSV 附表；任何对『哪个 birth model 更合理』的判断必须由 3D 以后的 OOS 检验来支撑——本报告**不下结论**。
3. ``company_foundation`` 缺失数据，**UNAVAILABLE**；不造数据。
4. BAZI_POS / Z_LIFE_006 等历史『CONSTANT』因子是否在换 birth model 后恢复区分度，见 csv 中对应行。
5. 本研究**不生成买卖建议**。全部 score 只是『传统规则强度』。
