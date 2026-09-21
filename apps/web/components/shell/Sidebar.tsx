"use client";

/**
 * 左侧导航（参考图：宽 231px，顶部与 TopBar 相接，底部有品牌标语）。
 *
 * 导航项结构与 uiux_spec §3 一致；未实现的模块（紫微/六爻/奇门）在
 * Phase 1 显示为 disabled 并带上"Phase 2"提示，而不是隐藏 —— 让用户
 * 明确知道系统边界。
 */

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
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
      { key: "overview", label: "综合研判", href: "/stock/600519/overview", icon: IconChart },
      { key: "timeline", label: "时间窗口", href: "/stock/600519/timeline", icon: IconCalendar },
    ],
  },
  {
    group: "术数分析",
    items: [
      { key: "bazi", label: "八字", href: "/stock/600519/bazi", icon: IconTaiji },
      { key: "ziwei", label: "紫微斗数", href: "/stock/600519/ziwei", icon: IconStar4 },
      { key: "huangli", label: "黄历 / 日课", href: "/stock/600519/huangli", icon: IconDiamond },
    ],
  },
  {
    group: "研究与证据",
    items: [
      { key: "backtest", label: "历史验证", href: "/stock/600519/backtest", icon: IconTrend },
      { key: "evidence", label: "古籍证据", href: "/stock/600519/evidence", icon: IconBook },
      { key: "conflicts", label: "模型分歧", href: "/stock/600519/conflicts", icon: IconNodes },
      { key: "research", label: "研究实验室", href: "/research", icon: IconFlask },
      { key: "factors", label: "因子字典", href: "/factors", icon: IconDatabase },
      { key: "settings", label: "系统设置", href: "/settings", icon: IconSettings, disabled: true, badge: "P2" },
    ],
  },
];

export function Sidebar({ activeKey }: { activeKey?: string }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const fixture = searchParams?.get("fixture");
  const suffix = fixture ? `?fixture=${fixture}` : "";

  // 提取当前正在查看的股票代码，使得侧栏链接自适应当前标的
  const match = pathname.match(/\/stock\/([^/]+)/);
  const currentCode = match ? match[1] : "600519";

  const getResolvedHref = (baseHref: string) => {
    let resolved = baseHref;
    if (resolved.startsWith("/stock/600519/")) {
      resolved = resolved.replace("/stock/600519/", `/stock/${currentCode}/`);
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
      className="relative z-10 flex w-[231px] shrink-0 flex-col border-r"
      style={{
        borderColor: "var(--color-border)",
        background:
          "linear-gradient(180deg, rgba(13,26,37,0.92) 0%, rgba(9,20,31,0.96) 100%)",
      }}
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
