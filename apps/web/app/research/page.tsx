"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ResearchIndexPage() {
  const router = useRouter();
  useEffect(() => { router.replace("/research/date-scan"); }, [router]);
  return (
    <main className="p-6 text-[13px]" style={{ color: "var(--color-ink-muted)" }}>
      正在进入研究实验室… <Link href="/research/date-scan" style={{ color: "var(--color-gold)" }}>择日关系扫描</Link>
    </main>
  );
}
