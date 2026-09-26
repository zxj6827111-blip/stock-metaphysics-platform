"use client";

/**
 * 图表渲染就绪状态（视觉验收的确定性信号）。
 *
 * 为什么不能靠固定 sleep：`visual-reference.spec.ts` 此前只等 `data-app-ready`、
 * `document.fonts.ready` 和一个 loading 标记，而 ECharts 还带着 300–400ms 的
 * `animationDuration`。截图因此可能落在动画中间 —— 时间窗口页曾出现"曲线只画出
 * 左侧一段"的候选图，被误读成数据截断（docs/UI_INDEPENDENT_REVIEW_2026-09-22.md §五）。
 *
 * 做法：每个图表实例在挂载/换数据时登记一个待完成标记，销账后把
 * `data-charts-ready="true"` 写到 `<html>` 上；测试等这个属性，而不是等一个
 * 拍出来的毫秒数。
 *
 * 销账有两条路，先到先算，因此**不可能挂死**：
 *   1. ECharts 的 `finished` 事件；
 *   2. 两帧 `requestAnimationFrame` 屏障 —— 本项目已全局关闭图表入场动画
 *      （见 `components/charts/SmpECharts.tsx`），两帧之后画面必然稳定。
 * 第 2 条不是"固定 sleep"：它按帧对齐、不猜毫秒，慢机器上等得更久而不是更短。
 * 事件比登记早到时无所谓：那次渲染由帧屏障兜底销账。
 */

const pending = new Set<string>();
let seq = 0;

function publish() {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.chartsReady = pending.size === 0 ? "true" : "false";
  document.documentElement.dataset.chartsPending = String(pending.size);
}

/**
 * 登记一次图表渲染。返回 token 与 cancel（组件卸载 / 换数据时调用）。
 * 只在浏览器里调用，不在服务端渲染路径上调用。
 */
export function registerChart(): { token: string; cancel: () => void } {
  const token = `c${(seq += 1)}`;
  pending.add(token);
  publish();

  let raf2 = 0;
  const raf1 = requestAnimationFrame(() => {
    raf2 = requestAnimationFrame(() => {
      pending.delete(token);
      publish();
    });
  });

  return {
    token,
    cancel: () => {
      cancelAnimationFrame(raf1);
      if (raf2) cancelAnimationFrame(raf2);
      pending.delete(token);
      publish();
    },
  };
}

/** ECharts `finished` 回调：该实例这一轮渲染完成。 */
export function markChartRendered(token: string): void {
  if (pending.delete(token)) publish();
}

/** 当前待完成的图表数（测试与调试用）。 */
export function pendingChartRenders(): number {
  return pending.size;
}
