# ADR-0006：UI fixture 模式与生产 runtime 分离

- **状态**：已接受（Phase 1）
- **日期**：2026-09-18
- **影响**：前端、UI 复刻流程、测试

## 背景

用户要求 UI 必须**尽可能 1:1 复刻**参考图（`doc/ui-reference/01_home.png` 等），
且必须达到"用户一眼看过去是同一个系统"的程度。

但这带来两个矛盾：

1. **参考图上的数字是设计稿的固定值**（600519 显示 1682.30、八字 84 分、紫微 79 分），
   而生产运行时这些必须来自真实 API；
2. **参考图上有紫微斗数卡片**，但 Phase 1 **明确不实现紫微引擎**。

同时，用户明确禁止作弊式复刻：

> 严格禁止 `background-image: reference.png`，也禁止把整页做成 `<img>`。

## 决策

引入**显式的双模式设计**：

| 模式 | 触发条件 | 数据来源 | 用途 |
|---|---|---|---|
| 生产 runtime（默认） | URL 无 `fixture` 参数 | 真实 API | 日常使用 |
| UI 复刻模式 | `?fixture=ui-reference` | `apps/web/lib/fixture.ts` | 逐像素比对参考图 |

具体约束：

1. **fixture 数据只存在于前端一个文件**（`lib/fixture.ts`），
   **不写入任何分析数据库**；
2. 页面结构由 `useSearchParams().get("fixture")` 决定，
   两种模式**复用完全相同的组件树**（只是数据源不同）——
   这保证了"复刻出来的界面"就是"生产界面"；
3. 生产模式下：
   * 紫微卡片显示「未启用」+ `score: null` + 明确原因，**绝不显示 0 分**；
   * 共识卡把紫微列在"未启用（不计入）"分区；
   * 时间窗口图与收益分布图底部有文字说明其为展示层示意；
4. fixture 模式下：紫微显示参考图中的 79 分，
   但页面右下角有**常驻浮标**：

   ```
   UI 复刻模式 · 固定演示数据 · 紫微为 Mock
   ```

   `title` 属性包含完整说明（"其中紫微斗数为纯展示 Mock，Phase 1 未实现该引擎。
   正式使用时请移除 URL 中的 ?fixture=ui-reference"）；
5. `apps/web/e2e/core-flow.spec.ts` 有测试断言该浮标存在，
   确保这个"诚实标识"不会被误删。

## 为什么不用 Storybook / MSW

| 方案 | 评估 |
|---|---|
| Storybook | 适合组件级开发，但不适合"整页 1:1 截图对比"流程 |
| MSW（Mock Service Worker） | 拦截网络请求返回 mock —— 可行，但会让"哪些数据是假的"变得隐蔽 |
| **URL 参数切换数据源** | 显式、可见、可测试、无需额外依赖；且能让"假数据"在 UI 上被标注出来 |

选择第三条，因为**"显式的假"比"隐蔽的假"安全**。

## 后果

**正面**

* 复刻与生产共用组件树，复刻结果就是生产结果；
* 假数据的存在位置、启用方式、影响范围都是显式的；
* 可以在没有后端的环境下做 UI 验收与 E2E 测试；
* 紫微的"未实现"状态在生产模式有明确的视觉表达。

**负面**

* `fixture.ts` 需要与组件的数据结构保持同步（类型由 `lib/types.ts` 约束）；
* URL 上多一个参数（可接受）。

## 相关

- [`docs/ui-implementation.md`](../ui-implementation.md) §5
- [`apps/web/lib/fixture.ts`](../../apps/web/lib/fixture.ts) 模块文档字符串
- [`apps/web/components/shell/AppShell.tsx`](../../apps/web/components/shell/AppShell.tsx) `FixtureBadge`
