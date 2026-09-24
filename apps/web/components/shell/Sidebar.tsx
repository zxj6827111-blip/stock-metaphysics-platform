"use client";

/**
 * 左侧导航（顶部与 TopBar 相接，底部有品牌标语）。
 *
 * 宽度 210px：R1 版按「参考图 231px」定值，那个数来自有缺陷的测法
 * （在 x=200..261 窗口内找亮度跳变，等于把边界限制在了内容区里）。
 * R1.1 用背景→槽区亮度过渡逐页重测十张参考图，侧栏右边界分别是
 * 01=229 / 02=174 / 03=230 / 04=190 / 05=206 / 06=213 / 07=229 /
 * 08=203 / 09=204 / 10=209.5 —— 参考稿自身页间不一致（极差 56px）。
 * 取 210px 的**理由不是「所有参考图都是 210px」**：十张参考图的侧栏宽度本身
 * 就不一致（174..230，极差 56px），无约束下的 L1 median interval 约 206–209.5。
 * 正式 AppShell 需要**统一产品尺寸**，而既有 layout.spec 要求 sidebar >= 210px，
 * 因此在现有产品约束下取 210px 作为统一 Sidebar token（不逐页改、不为 02 单独改 174px）。
 *
 * 导航项结构与 uiux_spec §3 一致；未实现的模块（紫微/六爻/奇门）在
 * Phase 1 显示为 disabled 并带上"Phase 2"提示，而不是隐藏 —— 让用户
 * 明确知道系统边界。
 */

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { analysisContextSuffix } from "@/lib/analysisContext";

import { SidebarMountain } from "./Decorations";
import {
  IconBook,
  IconCalendar,
  IconChart,
  IconDatabase,
  IconDiamond,
  IconFlask,
  IconGrid,
  IconHome,
  IconLayers,
  IconLing,
  IconNodes,
  IconSettings,
  IconStar4,
  IconTaiji,
  IconTrend,
} from "./Icons";

interface NavItem {
  key: string;
  label: string;
  href: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  disabled?: boolean;
  badge?: string;
}

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "",
    items: [
      { key: "home", label: "首页", href: "/", icon: IconHome },
      { key: "overview", label: "综合研判", href: "/stock?target=overview", icon: IconChart },
      { key: "timeline", label: "时间窗口", href: "/stock?target=timeline", icon: IconCalendar },
    ],
  },
  {
    group: "术数分析",
    items: [
      { key: "bazi", label: "八字", href: "/stock?target=bazi", icon: IconTaiji },
      { key: "ziwei", label: "紫微斗数", href: "/stock?target=ziwei", icon: IconStar4 },
      { key: "huangli", label: "黄历 / 日课", href: "/stock?target=huangli", icon: IconDiamond },
    ],
  },
  {
    group: "研究与证据",
    items: [
      { key: "backtest", label: "历史验证", href: "/stock?target=backtest", icon: IconTrend },
      { key: "evidence", label: "古籍证据", href: "/stock?target=evidence", icon: IconBook },
      { key: "conflicts", label: "模型分歧", href: "/stock?target=conflicts", icon: IconNodes },
      { key: "research", label: "研究实验室", href: "/research", icon: IconFlask },
      { key: "factors", label: "因子字典", href: "/factors", icon: IconDatabase },
      { key: "settings", label: "系统设置", href: "/settings", icon: IconSettings, disabled: true, badge: "P2" },
    ],
  },
];

export function Sidebar({ activeKey }: { activeKey?: string }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  /**
   * 跨页面导航必须带上**整份分析上下文**，不只是 fixture。
   *
   * 之前只有 fixture 被拼进去，于是从"60d + ipo_date + 指定基准日"的综合研判
   * 点侧栏进八字页，落地页会静默回落到默认上下文 —— 用户在两个页面看到的
   * 其实是两次不同的分析，却没有任何提示。
   */
  const suffix = analysisContextSuffix(searchParams);

  // 仅在已经进入个股页面时沿用当前标的；没有标的则进入统一选择入口。
  const match = pathname.match(/\/stock\/([^/]+)/);
  const currentCode = match?.[1] ?? null;

  const getResolvedHref = (baseHref: string) => {
    let resolved = baseHref;
    const target = new URLSearchParams(baseHref.split("?")[1] ?? "").get("target");
    if (currentCode && target) {
      resolved = `/stock/${currentCode}/${target}`;
    }
    if (suffix && !resolved.includes("?")) {
      resolved = `${resolved}${suffix}`;
    }
    return resolved;
  };

  const isActive = (item: NavItem): boolean => {
    if (activeKey) return item.key === activeKey;
    if (item.disabled) return false;
    if (item.href === "/") return pathname === "/";
    const seg = item.href.split("/").filter(Boolean).pop();
    return !!seg && pathname.endsWith(seg);
  };

  return (
    <aside
      className="relative z-10 flex w-[210px] shrink-0 flex-col border-r"
      style={{
        borderColor: "var(--color-border)",
        background:
          "linear-gradient(180deg, rgba(13,26,37,0.92) 0%, rgba(9,20,31,0.96) 100%)",
      }}
      data-anchor="sidebar"
    >
      <nav className="smp-scroll flex-1 overflow-y-auto py-2">
        {NAV.map((group, gi) => (
          <div key={group.group || `g${gi}`} className={gi > 0 ? "mt-1" : ""}>
            {group.group ? (
              <div
                className="px-4 pb-1 pt-3 text-[10.5px] tracking-[0.16em]"
                style={{ color: "var(--color-ink-faint)" }}
              >
                {group.group}
              </div>
            ) : null}
            {group.items.map((item) => {
              const active = isActive(item);
              const Icon = item.icon;
              if (item.disabled) {
                return (
                  <div
                    key={item.key}
                    className="smp-nav-item smp-nav-item--disabled"
                    title={`${item.label}：Phase 2 实现`}
                    data-testid={`nav-${item.key}`}
                    aria-disabled="true"
                  >
                    <Icon size={16} className="smp-nav-icon shrink-0" />
                    <span className="flex-1 truncate">{item.label}</span>
                    {item.badge ? (
                      <span
                        className="rounded-[3px] border px-1 text-[9.5px] leading-[14px]"
                        style={{ borderColor: "var(--color-border-strong)", color: "var(--color-ink-faint)" }}
                      >
                        {item.badge}
                      </span>
                    ) : null}
                  </div>
                );
              }
              const resolvedHref = getResolvedHref(item.href);
              return (
                <Link
                  key={item.key}
                  href={resolvedHref}
                  className={`smp-nav-item ${active ? "smp-nav-item--active" : ""}`}
                  data-testid={`nav-${item.key}`}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon size={16} className="smp-nav-icon shrink-0" />
                  <span className="flex-1 truncate">{item.label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="px-4 py-3">
        <div className="smp-divider mb-3" />
        <SidebarMountain />
        <div className="mt-2 text-center select-none" style={{ fontFamily: "var(--font-serif-cn)" }}>
          <div
            className="text-[12px] tracking-[0.24em] font-medium leading-[19px]"
            style={{ color: "rgba(212,184,122,0.75)" }}
          >
            数据通天机
          </div>
          <div
            className="text-[12px] tracking-[0.24em] font-medium leading-[19px]"
            style={{ color: "rgba(212,184,122,0.75)" }}
          >
            理性见真章
          </div>
        </div>
      </div>
    </aside>
  );
}
