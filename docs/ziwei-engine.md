# 紫微斗数引擎（ZiweiEngine）

> Phase 2A 交付。架构决策见 [ADR-0009](ADR/ADR-0009-ziwei-engine-iztro.md)（iztro 接入）
> 与 [ADR-0010](ADR/ADR-0010-ziwei-no-gender-variant.md)（无性别 → 方向 variant）。
> 口径差异记录见 [calculation-differences-phase2-ziwei.md](calculation-differences-phase2-ziwei.md)。

---

## 1. 一句话

**iztro（Node.js）排盘 → `services/ziwei-service` 输出 JSON → `ZiweiEngine` Adapter 转成
本项目 `ZiweiChart` → 落 `chart_artifact.raw_chart`。Python 业务层永远看不到第三方对象。**

---

## 2. 组件

```
services/ziwei-service/            Node.js + TypeScript + iztro@2.6.1（精确锁定）
  src/types.ts                     输出契约（本项目自有结构）
  src/chart.ts                     纯函数排盘；variant → 性别参数的解析
  src/cli.ts                       stdin/stdout 批量 JSON（默认 transport）
  src/server.ts                    POST /internal/ziwei/{chart,batch}（部署 transport）
  Dockerfile                       多阶段构建，运行期只带 iztro + dist

src/engines/ziwei/                 Python Adapter（唯一接触服务的位置）
  transport.py                     http → subprocess → unavailable 三级降级 + 显式字段映射
  ziwei_engine.py                  ZiweiEngine(MetaphysicsEngine)
  constants.py                     自持的星曜/宫位静态表（不依赖 iztro 的类型系统）

src/core/schemas/ziwei.py          ZiweiChart / ZiweiPalace / ZiweiStar / 运限层
tests/fixtures/ziwei/*.json        8 组真实 iztro 输出快照（Adapter 契约测试用）
```

---

## 3. 传输层与故障隔离

| transport | 触发 | 用途 |
|---|---|---|
| `http` | `SMP_ZIWEI_SERVICE_URL` 已设置 | Docker / 生产 |
| `subprocess` | 本机 `node` + `services/ziwei-service/dist/cli.js` 存在 | 本地开发、研究批量、测试 |
| `none` | 两者都不可用 | 引擎返回 `unavailable` |

**故障隔离的硬要求**：紫微失败时

* 八字 / 黄历 / 历史数据**继续正常运行**；
* 紫微观点的 `availability = "unavailable"`、`score = null`；
* `Consensus` 的 `available_engine_count` 相应降低；
* **绝不允许**把紫微按 `score = 0` 计入任何聚合。

传输层还有一个不显眼但重要的设计：**字段映射是显式的**（`_camel_to_snake`），
不是通用驼峰转换。服务端改名会立刻在测试中暴露，而不是被通用转换悄悄吞掉。

---

## 4. 股票没有真实性别

详见 [ADR-0010](ADR/ADR-0010-ziwei-no-gender-variant.md)。要点：

| `variant_mode` | 语义 | 实现参数（`gender_parameter`，仅审计） |
|---|---|---|
| `forward` | 强制顺行 | 阳年 → 男；阴年 → 女 |
| `reverse` | 强制逆行 | 阳年 → 女；阴年 → 男 |
| `both` | 两者分别计算、分别落库 | 两次独立排盘 |
| `not_applicable` | **拒绝排盘** | 抛 `ZiweiUnavailableError` |

`gender_parameter` 的语义是"实现该方向借用的规则参数"，
**不是**"这只股票是男性/女性"。UI 与报告中的措辞是「顺行假设 / 逆行假设」。

### variant 能区分什么、不能区分什么

实测（完整清单见 [calculation-differences-phase2-ziwei.md](calculation-differences-phase2-ziwei.md) D4）：

* **变**：大限年龄区间、小限年龄、长生十二神、博士十二神、运限的 `decadal`/`age` 层；
* **不变**：十二宫、全部星曜、生年四化、三方四正、流年/流月/流日/流时。

> ⚠️ 因此两个 variant **不是两条独立证据**。
> "顺行与逆行结论一致" **不能**当作双重确认 —— 它们共享绝大部分盘面。

---

## 5. `ZiweiChart` 保留了什么

| 类别 | 字段 |
|---|---|
| 输入 | `solar_date` / `lunar_date` / `chinese_date` / `time_index` / `time_name` / `time_range` |
| 命身 | `soul`（命主）/ `body`（身主）/ `five_elements_class` / `soul_palace_branch` / `soul_palace_index` / `body_palace_index` |
| 十二宫 | 每宫：宫名 / 宫干支 / 是否身宫 / 是否来因宫 / 主星 / 辅星 / 杂曜 / 长生·博士·将前·岁前十二神 / 大限区间 / 小限年龄 / **三方四正索引** |
| 四化 | `natal_mutagens`（禄权科忌各一，含落宫与落宫名） |
| 大限 | `decadals`（12 段） |
| 运限 | `horoscope.decadal / age / yearly / monthly / daily / hourly`（每层 12 宫名 + 12 组星曜 + 四化） |
| 元信息 | `engine_version` / `config_version` / `third_party` / `variant_mode` / `variant_basis` / `gender_parameter` / `assumptions` / `warnings` / `calculated_at` |

### 坐标系（重要）

`ZiweiPalace.index` 固定为**地支顺序**：`0 = 寅, 1 = 卯, … 11 = 丑`。
紫微命宫由寅起数，因此这是唯一稳定的宫位坐标。

三方四正为固定索引算术：`[i, (i+6)%12, (i+8)%12, (i+4)%12]`
（本宫 / 对宫 / 财帛位 / 官禄位），已对 iztro `surroundedPalaces` 逐宫对拍。

### 已知缺失（如实保留）

`horoscope.age`（小限层）在 iztro 中**不提供流曜**，`stars` 为空数组。
下游必须把"小限无流曜"当事实处理，**不得用其他层的星曜代替**。

---

## 6. 常用命令

```bash
make ziwei-install        # 安装依赖
make ziwei-build          # tsc → dist/
make ziwei-smoke          # 单次排盘自检
make ziwei-serve          # 启动 HTTP 服务（127.0.0.1:8100）
make test-ziwei           # 引擎 + 因子 + Golden
make test-ziwei-golden    # 只跑 Golden（iztro 升级后必跑）
```

重新抓取 Golden 快照（**先读脚本头部的警告**）：

```bash
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/capture_ziwei_fixtures.py
```

---

## 7. 已知限制

1. **没有第二实现源交叉验证**：Tianji 未接入（许可证未核实），
   因此紫微结论目前只有结构不变量与快照锁定，没有独立复核（见 `docs/model-limitations.md`）。
2. **子进程 transport 是每批一次进程启动**（约 150–300 ms）。研究批量因此按批调用；
   极高并发场景应切到 HTTP transport。
3. **紫微盘面 JSON 约 17 KB/盘**（含运限全层）。批量研究时注意 SQLite 体积。
4. **流时层（`hourly`）已采集但未进入任何因子**（预留）。
5. **iztro 升级会改变口径**：必须重跑 Golden 并把差异写入
   `docs/calculation-differences-phase2-ziwei.md`，同时提升 `ziwei_engine_version`。

---

## 8. 绝不妥协的三条

1. **LLM 不得计算紫微**（不得安星、不得算四化、不得推流年）。
2. **不得默认性别**。没有显式 variant 就没有紫微。
3. **不得用 0 分或空盘面冒充"不可用"或"中性"。**
