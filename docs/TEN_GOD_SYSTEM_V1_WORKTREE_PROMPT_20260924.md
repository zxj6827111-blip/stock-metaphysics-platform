# 本地 AI 执行提示词：Ten God System V1 独立 Worktree 实施

你现在要在仓库 `zxj6827111-blip/stock-metaphysics-platform` 中实施 **十神系统 V1.0**。

本任务与另一个正在进行的 UI 视觉整改任务并行。你的首要责任除了正确实现功能，还包括：

1. **绝不污染现有 UI 工作树**；
2. **使用独立 git worktree**；
3. **遵守仓库 AGENTS.md / ARCHITECTURE.md / ADR / tests 规则**；
4. **不得把传统十神和“日期×股票三干关系矩阵”混为一谈**；
5. **不得破坏已有 `/api/v1/**` 契约**；
6. **在并行 UI 分支合并前，不得抢改已知重叠文件**。

---

## 一、先读取本地实施合同

项目根目录应放置：

`docs/TEN_GOD_SYSTEM_V1_IMPLEMENTATION_PLAN_20260924.md`

先完整阅读它。

它是本任务的**实施与验收合同**。

若本地尚未存在该文件，先停止，要求提供该文件；不要凭本提示词自行缩减方案。

同时必须阅读：

- `AGENTS.md`
- `ARCHITECTURE.md`
- `README.md`
- `docs/ADR/README.md`（若存在）
- 与 Bazi / Calendar / Relation / Trading Calendar / Research API 相关的文档和 ADR
- `docs/calculation-differences*.md`
- 当前相关 tests

---

# 二、不得直接在当前 UI 工作树开工

先在当前仓库只做只读检查：

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git fetch origin --prune
git worktree list
```

禁止：

```bash
git stash
git reset --hard
git clean -fd
git checkout .
```

不要修改当前工作树中的任何文件。

---

# 三、新建独立 worktree

默认分支：

`feat/ten-god-system-v1`

默认 worktree：

`../stock-metaphysics-ten-god-v1`

如果该 branch/worktree 不存在：

```bash
git worktree add ../stock-metaphysics-ten-god-v1 \
  -b feat/ten-god-system-v1 \
  origin/main
```

如果 branch 已存在：

```bash
git worktree add ../stock-metaphysics-ten-god-v1 feat/ten-god-system-v1
```

进入新 worktree：

```bash
cd ../stock-metaphysics-ten-god-v1
git status --short
git rev-parse HEAD
git rev-parse origin/main
```

记录：

- WORKTREE_PATH
- BRANCH
- BASE_SHA
- ORIGIN_MAIN_SHA

同时检查远端并行 UI 分支：

`codex/ui-visual-parity-r1`

记录它当前 HEAD（若存在）。

---

# 四、并行 UI 冲突纪律

编制任务书时已知并行 UI 分支修改过：

- `apps/web/components/bazi/BaziChart.tsx`
- `apps/web/app/stock/[code]/bazi/page.tsx`
- `apps/web/lib/api.ts`
- `apps/web/lib/types.ts`
- `src/core/schemas/bazi.py`
- `src/engines/bazi/bazi_engine.py`
- 以及其他 UI shell/dataSource 文件

在 UI 分支尚未合并进 `origin/main` 前：

## 允许修改

- 新的十神 docs
- 新的十神 Schema 文件
- 新的十神 orchestration/service 文件
- 新的十神 API endpoint
- 新 tests
- `src/core/config.py` 的十神独立版本字段
- 当前 UI 分支未修改且确有必要的 relation/research 后端文件

## 禁止修改

- `apps/web/components/bazi/BaziChart.tsx`
- `apps/web/app/stock/[code]/bazi/page.tsx`
- `apps/web/lib/api.ts`
- `apps/web/lib/types.ts`
- `src/core/schemas/bazi.py`
- `src/engines/bazi/bazi_engine.py`

这些文件此阶段可以阅读和审计，但不能改。

如果实现后端时发现“必须改”这些文件才能继续：

**停止，汇报阻塞，不要抢改。**

---

# 五、传统十神唯一口径

股票自己的日干是固定日主。

例如股票：

`壬申 · 乙巳 · 癸未`

则：

`癸 = day_master`

所有传统十神都按：

```python
ten_god(stock_day_master, other_stem)
```

计算。

必须复用：

`src/core/constants.py::ten_god()`

不得复制第二份算法。

---

# 六、五类十神定义

1. 原局天干十神：
   - 股票原局其他天干相对股票日主
2. 原局藏干十神：
   - 原局地支藏干相对股票日主
3. 流年十神：
   - 流年天干相对股票日主
4. 流月十神：
   - 流月天干相对股票日主
5. 流日十神：
   - 流日天干相对股票日主

流年/月/日地支的藏干，也分别相对股票日主计算十神。

---

# 七、明确禁止的错误算法

不得把以下算法叫“标准十神”：

“当天日干分别与股票年干、月干、日干比较，然后得到三个十神”。

这只能作为未来实验性：

`date-stock stem relation matrix`

现有 3×3：

`流年/流月/流日 × 股票年/月/日`

继续用于冲、合、刑、害、破、生克、伏吟、反吟等关系。

它不是传统十神时间轴。

---

# 八、先审计当前实现

必须确认并记录：

1. `src/core/constants.py`
   - `TEN_GODS`
   - `TEN_GOD_GROUP`
   - `BRANCH_HIDDEN_STEMS`
   - `ten_god()`

2. `src/engines/bazi/bazi_engine.py`
   - `_build_pillar()`
   - 原局天干十神
   - 藏干十神
   - 日柱“日主”显示

3. `src/core/schemas/bazi.py`
   - `TemporalPillar.stem_ten_god`
   - `branch_ten_gods`

4. `src/core/relations/date_relation.py`
   - `build_day_stem_verdict()`
   - 必须确认是：
     `ten_god(day_master, day_stem)`

5. `src/core/orchestration/date_relation_scan.py`
   - 已有 `day_stem_verdict`
   - 现有 request 只支持 `relation_type`

6. `apps/web/components/research/RelationStockTable.tsx`
   - 已展示流日十神与流日喜忌

7. `BaziChart.tsx`
   - 当前“十神”行是否仍只显示 `hiddenTenGods`
   - 只记录，UI 合流前不改

8. `BaziEngine._year_range/_month_range`
   - 是否仍是公历年、公历月
   - 只记录，UI 合流前不改该文件

9. `CalendarEngine`
   - 年柱是否 `getYearInGanZhiExact`
   - 月柱是否 `getMonthInGanZhiExact`
   - `jieqi.prev_at/next_at/current_at`

10. `TradingCalendarProvider`
    - observed
    - published
    - out_of_coverage
    - weekend fallback

先输出审计结果再开始改代码。

---

# 九、TG-0：合同落库

如果实施合同尚未 commit：

提交一个纯文档 commit：

```text
docs(ten-god): freeze v1 implementation and acceptance contract
```

此 commit 不得包含业务代码。

---

# 十、TG-1：十神合同与 Golden Case

只做后端基础，不做 UI。

## 新增

建议：

`src/core/schemas/ten_god.py`

在 config 中新增：

`ten_god_rule_version = "ten-god-v1"`

实现 catalog 所需 Schema/常量映射。

## 不得

- 不重写 `ten_god()`
- 不修改旧 API
- 不修改并行 UI 重叠文件

## 必须新增 100 组测试

10 个日主 × 10 个天干 = 100 组。

除了逐表验证，还要有结构性不变量：

每个日主的 10 个 other_stem 必须恰好得到十种十神各一次。

## 必须加入用户 Golden Case

股票：

`壬申 · 乙巳 · 癸未`

日主：

`癸`

原局：

- 壬 = 劫财
- 乙 = 食神
- 癸 = 比肩关系；盘面显示日主

申藏：

- 庚 = 正印
- 壬 = 劫财
- 戊 = 正官

巳藏：

- 丙 = 正财
- 庚 = 正印
- 戊 = 正官

未藏：

- 己 = 七杀
- 丁 = 偏财
- 乙 = 食神

日期一：

`丙午 · 丁酉 · 庚子`

- 流年丙 = 正财
- 流月丁 = 偏财
- 流日庚 = 正印
- 午藏丁己 = 偏财、七杀
- 酉藏辛 = 偏印
- 子藏癸 = 比肩

日期二：

`丙午 · 丁酉 · 辛丑`

- 流日辛 = 偏印
- 丑藏己癸辛 = 七杀、比肩、偏印

日期三：

`丙午 · 丁酉 · 壬寅`

- 流日壬 = 劫财
- 寅藏甲丙戊 = 伤官、正财、正官

TG-1 完成后运行：

```bash
make test
make test-golden
make test-leak
```

提交：

```text
test(ten-god): lock canonical ten-god contract and golden cases
```

---

# 十一、TG-2：股票 → 十神时历后端

建议新增：

- `src/core/orchestration/ten_god_calendar.py`
- 必要的 helper 模块
- 新 integration tests

新增 API：

```text
GET /api/v1/research/ten-gods/catalog
GET /api/v1/research/ten-gods/stocks/{code}/calendar
```

## stock calendar 必须返回

### natal

- 四柱
- day_master
- day_master_wuxing
- 原局天干十神
- 原局藏干十神

### years

默认未来 10 年：

- ganzhi
- stem_ten_god
- branch hidden stems + ten gods
- start_at
- end_at
- timezone
- wuxing_role
- verdict

### months

默认未来 24 节气月：

- ganzhi
- stem_ten_god
- branch hidden stems + ten gods
- exact start_at/end_at
- timezone
- wuxing_role
- verdict

### days

默认未来 365 自然日：

- date
- ganzhi
- stem_ten_god
- ten_god_group
- branch hidden stems + ten gods
- wuxing_role
- verdict
- is_trading_day
- calendar source
- authoritative/degraded status
- degraded_reason

---

# 十二、时间边界必须严谨

## 流年

不是 1 月 1 日。

按 `CalendarEngine.year_ganzhi` 实际换柱，等价于立春换年。

区间：

`[立春, 下一立春)`

## 流月

不是公历 1 号。

按 `CalendarEngine.month_ganzhi` 实际换柱，只在十二“节”换月。

区间：

`[本次换月节气, 下一换月节气)`

## 流日

日级产品固定：

`12:00:00 Asia/Shanghai`

与现有 Date Scan 一致。

## 第三方隔离

十神 service 不得直接 import `lunar_python`。

只能通过 `CalendarEngine`。

---

# 十三、自然日与交易日

底层一定生成完整自然日。

禁止：

“因为页面默认交易日，所以后端只生成交易日”。

每个自然日必须保留。

交易日状态复用：

`src/core/stock/trading_calendar.py`

未知必须是未知，不能伪装成 false。

weekend fallback 必须明确 degraded。

---

# 十四、TG-2 测试

至少覆盖：

- 2024 立春前后
- 惊蛰
- 清明
- 立夏
- 芒种
- 小暑
- 立秋
- 白露
- 寒露
- 立冬
- 大雪
- 小寒
- 交节前后
- 365 天
- 闰年 366 天
- observed 日历
- published 日历
- out_of_coverage
- weekend fallback

运行：

```bash
make test
make test-golden
make test-leak
```

提交：

```text
feat(ten-god): add stock temporal calendar api
```

---

# 十五、TG-3：日期 → 全市场十神扫描

新增：

```text
POST /api/v1/research/ten-gods/date-scan
```

禁止直接修改已有：

```text
POST /api/v1/research/date-scan
```

的公开 request/response 契约。

## 新 request 支持

- date
- universe
- birth_basis
- birth_profile_version
- ten_god
- ten_god_group
- wuxing_role
- verdict
- relation_type
- sort
- offset
- limit

## 权威流日十神

严格：

```python
ten_god(stock_day_master, target_day_stem)
```

不要从 3×3 relation cell 中聚合出“十神”。

## 复合筛选

例如：

```text
ten_god = 正财
verdict = 匹配
relation_type = 六合
```

语义是 AND。

过滤必须发生在分页前。

counts 必须基于定义清楚的集合。

---

# 十六、未来日期 universe

历史日期继续 PIT。

未来日期不能假装知道未来上市/退市。

若 target_date 超出可证据化范围：

- 使用 latest known canonical universe
- 输出：
  - universe_mode
  - universe_as_of
  - future_universe_assumption
- UI 后续必须显示说明

---

# 十七、TG-3 测试

必须证明：

1. 单个股票结果与 `build_day_stem_verdict()` 一致；
2. 正财过滤只返回正财；
3. 十神组过滤一致；
4. verdict 与十神独立；
5. relation_type + ten_god 是 AND；
6. 过滤先于分页；
7. count 一致；
8. unavailable 不用 0 冒充；
9. 旧 `/api/v1/research/date-scan` contract 没变。

运行：

```bash
make test
make test-golden
make test-leak
```

提交：

```text
feat(ten-god): add market date scan filters
```

---

# 十八、TG-3.5：UI 合流门

完成 TG-1～TG-3 后，不要马上改 UI。

先检查：

```bash
git fetch origin --prune
git log --oneline --decorate -n 20 origin/main
git branch -r
```

确认并行 UI 分支是否已经合并到 main。

## 如果未合并

停止。

输出：

```text
TEN_GOD_BACKEND_READY = YES
TEN_GOD_UI_PHASE_BLOCKED_BY_PARALLEL_UI = YES
```

等待用户决定。

## 如果已合并

执行：

```bash
git rebase origin/main
```

处理冲突。

禁止：

- 整文件覆盖
- 用旧 main 的 BaziChart 覆盖 UI 分支新版本
- 用旧 api.ts/types.ts 覆盖 UI 分支

rebase 后重新：

```bash
make test
make test-golden
make test-leak
make typecheck
```

---

# 十九、TG-4：前端实施

只有 TG-3.5 通过后才开始。

新增：

`/stock/[code]/ten-gods`

建议组件：

- TenGodNatalPanel
- TenGodYearTable
- TenGodMonthTable
- TenGodDayCalendar
- TenGodFilters
- TenGodLegend

## 页面必须

### 原局

- 天干十神
- 藏干
- 藏干十神
- 日主清晰

### 流年

- 未来 10 年

### 流月

- 未来 24 节气月

### 流日

- 未来 365 自然日
- 默认仅交易日
- 可切全部日期
- 30 / 90 / 180 / 365
- 十神筛选
- 十神组
- 五行角色
- 喜用匹配

## Date Scan

给 `/research/date-scan` 加：

- 十神
- 十神组
- 五行角色
- 喜用匹配

所有枚举从 catalog 读取。

前端不得计算十神。

---

# 二十、BaziChart 最终修正

UI 合流后检查最新 `BaziChart.tsx`。

如果仍然是：

`十神 -> hiddenTenGods`

必须拆成：

- 天干十神
- 藏干
- 藏干十神

不要只改 label 不改数据。

---

# 二十一、TG-4 测试

运行：

```bash
make typecheck
make web-build
make test
make test-golden
make test-leak
```

运行相关 Playwright。

必须加 E2E：

- stock ten-gods route
- 默认交易日
- 切全部日期
- ten god filter
- verdict filter
- Date Scan ten god filter
- loading / empty / error
- calendar coverage warning
- 同一股票同一日期两入口结果一致

提交：

```text
feat(web): add ten-god calendar and scan filters
```

---

# 二十二、最终 TG-5

执行仓库正式验收矩阵。

至少：

```bash
make test
make test-golden
make test-leak
make typecheck
make web-build
```

如果环境允许：

```bash
make test-ui
```

不要修改视觉门禁阈值来“做绿”。

当前视觉 parity 是独立任务；十神任务不得：

- 改 reference PNG
- 提高视觉 diff 阈值
- 自动接受 candidate
- 用 continue-on-error 掩盖失败

---

# 二十三、最终必须输出的验收报告

最终回复严格包含：

## 1. Git

- worktree path
- branch
- base SHA
- final SHA
- commits

## 2. 算法

- ten_god_rule_version
- 日主方向
- 100/100 映射结果
- 用户三组 Golden Case 结果

## 3. 时间

- 立春测试
- 十二节月柱测试
- exact boundary 结果
- timezone

## 4. 股票→日期

- 10 年
- 24 月
- 365 日
- 自然日数
- 默认交易日
- 交易日日历来源/覆盖

## 5. 日期→股票

- 十神过滤
- 十神组
- 喜用
- relation_type 复合
- counts/pagination

## 6. API

- 新端点
- 旧 v1 date-scan 是否零契约破坏

## 7. UI

- 新页面
- Date Scan
- BaziChart
- E2E

## 8. 测试

逐条命令和 PASS/FAIL。

## 9. 性能

- cold
- warm
- cache
- fallback counts
- test machine

## 10. 并行 UI

- UI branch 何时合流
- rebase SHA
- 冲突文件
- 如何解决
- 是否有整文件覆盖：必须 NO

## 11. 已知限制

不能写“全部完成”然后把限制藏起来。

---

# 二十四、停止条件

以下任一情况立即停止并汇报，不要自行扩大修改面：

1. worktree 会写到原 UI 工作树；
2. 需要修改并行 UI 重叠文件但 UI 分支尚未合并；
3. 当前 main 与任务书基线存在影响十神语义的新改动；
4. `ten_god()` 与文档传统口径不一致；
5. CalendarEngine 的 Exact 年/月柱行为变化；
6. 交易日历未来覆盖不足且产品会因此给出假交易日；
7. 旧 v1 API 必须破坏才能继续；
8. Golden Case 出现无法解释的方向冲突；
9. 测试失败原因不清楚；
10. 发现需要新的 ADR。

停止时输出：

```text
TEN_GOD_IMPLEMENTATION_BLOCKED = YES
BLOCKER = ...
SAFE_TO_CONTINUE_WITHOUT_DECISION = NO
```

不要猜。

---

# 二十五、核心原则再重复一次

这次任务最重要的不是“多加几个筛选框”，而是建立一套不会再次混淆的十神语义。

最终系统必须做到：

```text
股票自己的日干 = 固定日主

原局天干 ─┐
原局藏干 ─┤
流年天干 ─┤
流月天干 ─┼─> 全部相对固定日主计算十神
流日天干 ─┤
流年藏干 ─┤
流月藏干 ─┤
流日藏干 ─┘
```

而：

```text
日期年/月/日 × 股票年/月/日
```

继续是“关系矩阵”，不是传统十神中心。

实现、API、UI、测试、文档必须全都服从这一点。
