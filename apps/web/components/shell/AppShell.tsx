"use client";

/**
 * 应用外壳：TopBar + Sidebar + 主内容区。
 *
 * 所有页面都必须通过 AppShell 渲染，禁止各页面各写一套导航（UI_RULES §2）。
 */

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { APP_FOOTER_CENTER, APP_FOOTER_LEFT, APP_FOOTER_RIGHT } from "@/lib/appMeta";
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
  const fixture = params.get("fixture") === "ui-reference";

  return (
    <div className="relative z-10 flex h-screen flex-col overflow-hidden">
      <TopBar dataStatus={dataStatus} statusText={statusText} asOf={asOf} />
      <div className="flex min-h-0 flex-1">
        <Sidebar activeKey={activeNav} />
        <main className="smp-scroll min-w-0 flex-1 overflow-y-auto px-[14px] pb-2 pt-2.5">
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
