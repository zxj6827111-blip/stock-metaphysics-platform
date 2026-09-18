"use client";

/**
 * 顶部栏（参考图：全宽，高 ~68px）。
 * 左：Logo + 平台名 + 副标题；中：全局股票搜索；右：数据状态 + 时间 + 设置 + 头像。
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { IconLing, IconSearch, IconSettings, IconTaiji } from "./Icons";
import { StockSearch } from "../stock/StockSearch";

export function TopBar({
  dataStatus = "ok",
  statusText = "数据正常",
  asOf,
}: {
  dataStatus?: "ok" | "warn" | "bad";
  statusText?: string;
  asOf?: string;
}) {
  const [clock, setClock] = useState<string>(asOf ?? "--");
  const router = useRouter();

  useEffect(() => {
    if (asOf) {
      setClock(asOf);
      return;
    }
    const tick = () => {
      const d = new Date();
      const p = (n: number) => String(n).padStart(2, "0");
      setClock(
        `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(
          d.getMinutes(),
        )}:${p(d.getSeconds())}`,
      );
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [asOf]);

  const dotColor =
    dataStatus === "ok"
      ? "var(--color-down)"
      : dataStatus === "warn"
        ? "var(--color-warn)"
        : "var(--color-up)";

  return (
    <header
      className="relative z-20 flex h-[68px] shrink-0 items-center gap-4 border-b px-5"
      style={{
        borderColor: "var(--color-border)",
        background: "linear-gradient(180deg, rgba(12,24,34,0.96), rgba(9,19,29,0.92))",
      }}
    >
      {/* Logo */}
      <Link href="/" className="flex shrink-0 items-center gap-2.5" data-testid="brand">
        <span
          className="flex h-9 w-9 items-center justify-center rounded-full"
          style={{
            color: "var(--color-gold)",
            border: "1px solid var(--color-gold-dim)",
            background: "radial-gradient(circle at 50% 40%, rgba(212,184,122,0.20), transparent 70%)",
          }}
        >
          <IconTaiji size={20} />
        </span>
        <span className="flex flex-col leading-tight">
          <span
            className="text-[19px] font-semibold tracking-[0.06em]"
            style={{ color: "var(--color-ink)" }}
          >
            股票玄学多模型研究平台
          </span>
        </span>
      </Link>

      <span
        className="hidden shrink-0 text-[11.5px] tracking-[0.1em] lg:block"
        style={{ color: "var(--color-ink-muted)" }}
      >
        以古鉴今 · 多模型共研 · 发现市场的另一重规律
      </span>

      {/* 全局搜索 */}
      <div className="flex flex-1 justify-center px-2">
        <div className="w-full max-w-[620px]">
          <StockSearch variant="bar" />
        </div>
      </div>

      {/* 右侧状态 */}
      <div className="flex shrink-0 items-center gap-3">
        <div className="flex items-center gap-1.5">
          <span
            className="inline-block h-[7px] w-[7px] rounded-full"
            style={{ background: dotColor, boxShadow: `0 0 6px ${dotColor}` }}
          />
          <span className="text-[12px]" style={{ color: "var(--color-ink-sub)" }}>
            {statusText}
          </span>
        </div>
        <span style={{ color: "var(--color-border-strong)" }}>|</span>
        <span className="smp-num text-[12px]" style={{ color: "var(--color-ink-sub)" }}>
          {clock}
        </span>
        <button
          type="button"
          className="flex h-8 w-8 items-center justify-center rounded-full transition-colors"
          style={{ color: "var(--color-ink-sub)", border: "1px solid var(--color-border-strong)" }}
          title="系统设置（Phase 2）"
          onClick={() => router.push("/settings")}
          data-testid="topbar-settings"
        >
          <IconSettings size={15} />
        </button>
        <span
          className="flex h-8 w-8 items-center justify-center rounded-full text-[12px]"
          style={{
            color: "var(--color-gold)",
            border: "1px solid var(--color-gold-dim)",
            background: "var(--color-gold-ghost)",
          }}
          title="本地研究账号"
        >
          <IconLing size={14} />
        </span>
      </div>
    </header>
  );
}

/** 页面级 Hero 标题区（参考图中首页/综合研判/八字页共用的大标题块）。 */
export function PageHero({
  title,
  subtitle,
  right,
  seal,
}: {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  seal?: string;
}) {
  return (
    <div className="relative mb-3 flex items-start justify-between gap-4 px-1 pt-1">
      <div className="min-w-0">
        <h1
          className="text-[40px] font-bold leading-[1.12] tracking-[0.04em]"
          style={{
            color: "var(--color-gold-strong)",
            textShadow: "0 2px 18px rgba(212,184,122,0.18)",
          }}
          data-testid="page-title"
        >
          {title}
        </h1>
        {subtitle ? (
          <p className="mt-1.5 text-[13px] tracking-[0.06em]" style={{ color: "var(--color-ink-sub)" }}>
            {subtitle}
          </p>
        ) : null}
      </div>
      {right}
      {seal ? (
        <span
          className="absolute right-2 top-1 flex h-7 w-7 items-center justify-center rounded-[3px] text-[11px]"
          style={{
            color: "#f0d9b0",
            background: "linear-gradient(180deg,#8d2f28,#6d211c)",
            border: "1px solid #a8453b",
          }}
        >
          {seal}
        </span>
      ) : null}
    </div>
  );
}

/** 页面底部免责声明条。 */
export function FooterNote({ left, center, right }: { left: string; center: string; right: string }) {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <footer
      ref={ref}
      className="mt-3 flex items-center justify-between gap-4 border-t px-1 pt-2.5 text-[11.5px]"
      style={{ borderColor: "var(--color-border)", color: "var(--color-ink-faint)" }}
    >
      <span data-testid="footer-left">{left}</span>
      <span className="flex items-center gap-3">
        <span style={{ color: "var(--color-border-strong)" }}>—</span>
        <span>{center}</span>
        <span style={{ color: "var(--color-border-strong)" }}>—</span>
      </span>
      <span>{right}</span>
    </footer>
  );
}
