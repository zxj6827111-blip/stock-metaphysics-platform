"use client";

/**
 * 顶部栏（参考图：全宽，高 ~68px）。
 * 左：Logo + 平台名 + 副标题；中：全局股票搜索；右：数据状态 + 时间 + 设置 + 头像。
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { FIXTURE_QUERY_VALUE } from "@/lib/fixture";
import { useEffect, useRef, useState } from "react";

import { BrandMark } from "../brand/BrandMark";
import { IconLing, IconSearch, IconSettings } from "./Icons";
import { StockSearch } from "../stock/StockSearch";
import { Astrolabe, MountainSilhouette, SealStamp } from "./Decorations";

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
  const searchParams = useSearchParams();
  const fixture = searchParams.get("fixture") === FIXTURE_QUERY_VALUE;

  useEffect(() => {
    if (fixture) {
      setClock("2024-11-15 15:00:27");
      return;
    }
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
  }, [asOf, fixture]);

  const dotColor =
    dataStatus === "ok"
      ? "var(--color-down)"
      : dataStatus === "warn"
        ? "var(--color-warn)"
        : "var(--color-up)";

  return (
    <header
      /* 高度 62px：十张参考图顶栏底边分别是 59..66（均值 62.1），与侧栏同理取统一产品 token，
     * 不逐页改。参考图里 Hero 直接接顶栏、无空隙，见 AppShell 的 main 内边距。 */
    className="relative z-20 flex h-[62px] shrink-0 items-center gap-4 border-b px-5"
      style={{
        borderColor: "var(--color-border)",
        background: "linear-gradient(180deg, rgba(12,24,34,0.96), rgba(9,19,29,0.92))",
      }}
      data-anchor="topbar"
    >
      {/* 品牌标 + 平台名（品牌标用独立的自绘矢量 Logo，不是放大的功能图标） */}
      <Link href="/" className="flex shrink-0 items-center gap-2.5" data-testid="brand">
        <BrandMark size={36} />
        <span className="flex flex-col leading-tight">
          <span
            className="smp-serif-title smp-gold-shimmer text-[20px] font-semibold tracking-[0.07em]"
            style={{ fontFamily: "var(--font-serif-cn)" }}
          >
            股票玄学多模型研究平台
          </span>
        </span>
      </Link>

      <span
        className="hidden shrink-0 text-[12px] tracking-[0.1em] lg:block"
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

/**
 * 页面 Hero 的有限变体。
 *
 * 参考图里十页的 Hero **不是同一张卡**：首页是接近半屏的大标题 + 搜索区，
 * 历史验证右侧是「历史统计 VS 传统术数」对照块，古籍页是书影，
 * 其余研究页是紧凑的标题 + 竖联 + 星盘。此前所有页共用一套尺寸与装饰，
 * 于是"统一外壳"变成了"抹掉每页构图"（复核任务书 §二.3）。
 *
 * 本轮只落地实际被使用的两档：
 *   * `default`  —— 既有页面保持原样，不因为改造而回归；
 *   * `research` —— 综合研判 / 黄历这类研究主页：更高的头部、更大的标题、
 *     更强的山峦层次，星盘右移并被卡片边界裁切（参考图就是这个效果）。
 * 首页 / 统计 / 证据三档留给各自的工作包接入，不在这里预先建空壳。
 */
export type HeroVariant = "default" | "research";

const HERO: Record<
  HeroVariant,
  {
    box: string;
    minH: number;
    title: string;
    subtitle: string;
    astrolabeSize: number;
    astrolabeClass: string;
    mountainOpacity: number;
    coupletSize: number;
  }
> = {
  default: {
    box: "px-4 py-2",
    minH: 104,
    title: "text-[40px]",
    subtitle: "text-[14px]",
    astrolabeSize: 214,
    astrolabeClass: "right-[126px]",
    mountainOpacity: 0.24,
    coupletSize: 13,
  },
  research: {
    // 参考图各页 Hero 高 107–121px（08 黄历 109、03 八字 117、07 分歧 121），
    // 所以变体差在**标题尺寸与装饰强度**，不是把头部垫高。
    box: "px-5 py-2",
    minH: 104,
    title: "text-[44px]",
    subtitle: "text-[14.5px]",
    astrolabeSize: 236,
    astrolabeClass: "-right-6",
    mountainOpacity: 0.34,
    coupletSize: 14,
  },
};

/** 页面级 Hero 标题区（参考图中首页/综合研判/八字/紫微/黄历等共用的大标题块）。 */
export function PageHero({
  title,
  subtitle,
  right,
  seal = "紫",
  couplet = ["观天时", "察地利", "究人道", "研规律"],
  motto = ["顺势而为", "知行合一"],
  showDecorations = true,
  variant = "default",
}: {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  seal?: string;
  couplet?: string[];
  /** 右侧竖排短句（参考图为两行四字）：每项一行。 */
  motto?: string[];
  showDecorations?: boolean;
  variant?: HeroVariant;
}) {
  const hero = HERO[variant];
  return (
    <div
      className={`relative mb-2 overflow-hidden rounded-[8px] border smp-card ${hero.box}`}
      style={{
        background: "linear-gradient(135deg, rgba(16,31,43,0.92) 0%, rgba(13,26,37,0.96) 100%)",
        borderColor: "var(--color-border)",
      }}
      data-testid="page-hero"
      data-anchor="page-hero"
      data-hero-variant={variant}
    >
      {/* 装饰层：星盘在竖联与题词之间，并让出各自的横向区间 ——
          三者都用绝对定位是为了复刻参考图中"星盘上下被卡片裁切"的效果，
          因此必须显式留白，不能靠内容自身撑开（否则会出现文字压在星盘上）。 */}
      {showDecorations && (
        <>
          <MountainSilhouette opacity={hero.mountainOpacity} />
          <Astrolabe
            size={hero.astrolabeSize}
            glow={true}
            className={`pointer-events-none absolute ${hero.astrolabeClass} top-1/2 -translate-y-1/2 hidden xl:block`}
          />
          {motto && motto.length > 0 && (
            <div
              className="pointer-events-none absolute right-4 top-1/2 hidden -translate-y-1/2 flex-col items-end gap-1 xl:flex"
              style={{ fontFamily: "var(--font-serif-cn)" }}
              aria-hidden="true"
            >
              {motto.map((line, i) => (
                <div
                  key={i}
                  className="text-[16px] leading-[22px] tracking-[0.18em]"
                  style={{ color: "var(--color-gold-strong)" }}
                >
                  {line}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <div
        className="relative z-10 flex items-center justify-between gap-4"
        style={{ minHeight: hero.minH }}
      >
        <div className="min-w-0">
          <h1
            className={`smp-serif-title smp-gold-shimmer ${hero.title} font-bold leading-[1.08] tracking-[0.04em]`}
            style={{
              color: "var(--color-gold-strong)",
              fontFamily: "var(--font-serif-cn)",
              textShadow: "0 2px 18px rgba(212,184,122,0.2)",
            }}
            data-testid="page-title"
          >
            {title}
          </h1>
          {subtitle ? (
            <p
              className={`mt-1.5 tracking-[0.1em] ${hero.subtitle}`}
              style={{ color: "var(--color-ink-sub)", fontFamily: "var(--font-serif-cn)" }}
            >
              {subtitle}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-4">
          {right}

          {showDecorations && couplet && couplet.length > 0 && (
            <div
              className="hidden shrink-0 select-none flex-row-reverse items-start gap-2 pr-1 sm:flex xl:mr-[420px]"
              style={{ fontFamily: "var(--font-serif-cn)" }}
              aria-hidden="true"
            >
              {couplet.map((col, idx) => (
                <div key={idx} className="flex flex-col items-center gap-1.5">
                  <div
                    className="leading-[16px] tracking-[0.22em]"
                    style={{
                      writingMode: "vertical-rl",
                      color: "rgba(212,184,122,0.85)",
                      fontSize: hero.coupletSize,
                    }}
                  >
                    {col}
                  </div>
                  {idx === couplet.length - 1 && seal ? (
                    <SealStamp text={seal} size={20} />
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
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
