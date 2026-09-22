"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

const TABS = [
  { href: "/research/date-scan", label: "择日关系扫描", key: "date-scan" },
  { href: "/research/relation-study", label: "关系历史研究", key: "relation-study" },
  { href: "/research/experiments", label: "历史实验", key: "experiments" },
] as const;

export function ResearchNav() {
  const pathname = usePathname();
  const search = useSearchParams();
  const fixture = search?.get("fixture");
  return (
    <nav className="mb-2 flex flex-wrap items-center gap-1 border-b px-1" style={{ borderColor: "var(--color-border)" }} data-testid="research-nav">
      {TABS.map((tab) => {
        const active = pathname === tab.href || (tab.key === "date-scan" && pathname === "/research");
        const href = fixture ? `${tab.href}?fixture=${encodeURIComponent(fixture)}` : tab.href;
        return (
          <Link
            key={tab.href}
            href={href}
            className="border-b-2 px-3 py-2 text-[12.5px] transition-colors"
            style={{
              borderColor: active ? "var(--color-gold)" : "transparent",
              color: active ? "var(--color-gold-strong)" : "var(--color-ink-muted)",
            }}
            data-active={active ? "true" : "false"}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
