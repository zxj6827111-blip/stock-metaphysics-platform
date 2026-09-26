"use client";

/**
 * 应用外壳：TopBar + Sidebar + 主内容区。
 *
 * 所有页面都必须通过 AppShell 渲染，禁止各页面各写一套导航（UI_RULES §2）。
 */

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { APP_FOOTER_CENTER, APP_FOOTER_LEFT, APP_FOOTER_RIGHT } from "@/lib/appMeta";
import { FIXTURE_QUERY_VALUE } from "@/lib/fixture";
import { FooterNote, TopBar } from "./TopBar";
import { Sidebar } from "./Sidebar";

export interface AppShellProps {
  children: React.ReactNode;
  activeNav?: string;
  dataStatus?: "ok" | "warn" | "bad";
  statusText?: string;
  asOf?: string;
  footerLeft?: string;
  footerCenter?: string;
  footerRight?: string;
}

function ShellInner({
  children,
  activeNav,
  dataStatus,
  statusText,
  asOf,
  // 版本号统一来自 lib/appMeta（不要再在页面里硬编码 v1.0.0 / v0.2.0）
  footerLeft = APP_FOOTER_LEFT,
  footerCenter = APP_FOOTER_CENTER,
  footerRight = APP_FOOTER_RIGHT,
}: AppShellProps) {
  const params = useSearchParams();
  const fixture = params.get("fixture") === FIXTURE_QUERY_VALUE;

  /**
   * 就绪信号：只有客户端首次 effect 跑完才为 true。
   *
   * 为什么需要它：Next.js 的流式 SSR 会先把整页内容放进
   * `<div hidden id="S:0">`，再由文档末尾的 `$RC("B:0","S:0")` 把它搬进
   * Suspense 边界；在这两个时刻之间，以及 React 完成 hydration 之前，
   * DOM 处于"服务端内容 + 客户端尚未接管"的中间态。
   * 自动化测试若在这个窗口里做严格模式断言，就可能看到中间态（而不是稳定终态）。
   *
   * 这个属性把"什么时候可以断言"变成**可观测的事实**：
   * 服务端渲染 `false`，客户端挂载后置为 `true`（SSR 与首次客户端渲染一致，
   * 因此不会引入 hydration 不一致；属性变化发生在 effect 之后）。
   * 测试应等待 `[data-app-ready="true"]` 再断言，而不是靠固定延时 ——
   * 延时既可能太短（看到中间态）也可能掩盖真正的挂载失败。
   */
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(true);
    /**
     * 图表就绪属性的初值。
     *
     * `data-charts-ready` 由 `lib/chartReadiness` 在图表登记时写；但**没有图表的页面**
     * 永远不会触发登记，属性就一直缺席，视觉测试会等它等到超时。
     * 这里补一个"当前没有待完成图表"的初值：React 先跑子组件 effect，
     * 所以真有图表时它已经写成 false，`??=` 不会把未完成的图表误标成完成。
     */
    const ds = document.documentElement.dataset;
    if (ds.chartsReady === undefined) ds.chartsReady = "true";
  }, []);

  return (
    <div
      className="relative z-10 flex h-screen flex-col overflow-hidden"
      data-app-ready={ready ? "true" : "false"}
      data-fixture-mode={fixture ? "fixture" : "live"}
      // 构建身份在编译期就被内联：视觉候选必须是 production，
      // 否则 Next dev 指示器与 HMR 浮层会混进像素差异。
      data-build-mode={process.env.NODE_ENV === "production" ? "production" : "development"}
    >
      <TopBar dataStatus={dataStatus} statusText={statusText} asOf={asOf} />
      <div className="flex min-h-0 flex-1">
        <Sidebar activeKey={activeNav} />
        <main className="smp-scroll min-w-0 flex-1 overflow-y-auto px-[14px] pb-2" data-anchor="main">
          {children}
          <FooterNote left={footerLeft} center={footerCenter} right={footerRight} />
        </main>
        {fixture ? <FixtureBadge /> : null}
      </div>
    </div>
  );
}

function FixtureBadge() {
  return (
    <div
      className="fixed bottom-2.5 right-4 z-50 flex items-center gap-2 rounded-full border px-3 py-1 text-[10.5px] shadow-lg"
      style={{
        borderColor: "rgba(224,164,88,0.42)",
        background: "rgba(12,22,30,0.94)",
        color: "var(--color-warn)",
      }}
      data-testid="fixture-banner"
      title="当前使用固定演示数据（fixture=ui-reference）以逐像素比对参考图；其中紫微斗数为纯展示 Mock，Phase 1 未实现该引擎。正式使用时请移除 URL 中的 ?fixture=ui-reference"
    >
      <span className="font-semibold">UI 复刻模式</span>
      <span style={{ color: "var(--color-ink-muted)" }}>固定演示数据 · 紫微为 Mock</span>
    </div>
  );
}

export function AppShell(props: AppShellProps) {
  return (
    <Suspense fallback={<div className="p-6 text-[13px]">加载中…</div>}>
      <ShellInner {...props} />
    </Suspense>
  );
}
