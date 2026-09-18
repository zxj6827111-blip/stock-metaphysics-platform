"use client";

/**
 * EvidenceDrawer —— 古籍证据抽屉（uiux_spec §21）。
 *
 * 三条硬性要求：
 *  1. 必须同时展示 supporting_evidence 与 counter_evidence；
 *  2. 每条必须显示 book / chapter / edition / provenance / license_status；
 *  3. 不按吉凶染色，只区分「支持当前规则 / 与当前规则相反 / 中性背景」。
 */

import { useEffect } from "react";

import type { ApiEvidenceItem } from "@/lib/api";
import { Chip } from "../cards/Card";
import { IconBook, IconClose } from "../shell/Icons";

export function EvidenceDrawer({
  open,
  onClose,
  supporting,
  counter,
  neutral,
  note,
  retrievalMethod,
}: {
  open: boolean;
  onClose: () => void;
  supporting: ApiEvidenceItem[];
  counter: ApiEvidenceItem[];
  neutral: ApiEvidenceItem[];
  note?: string;
  retrievalMethod?: string;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (open) document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" data-testid="evidence-drawer">
      <button
        type="button"
        aria-label="关闭"
        className="flex-1 cursor-default bg-black/55"
        onClick={onClose}
      />
      <div
        className="smp-scroll flex h-full w-[720px] max-w-[92vw] flex-col overflow-y-auto border-l"
        style={{ borderColor: "var(--color-border-strong)", background: "var(--color-canvas)" }}
      >
        <header
          className="sticky top-0 z-10 flex items-center gap-2 border-b px-4 py-3"
          style={{ borderColor: "var(--color-border)", background: "var(--color-canvas)" }}
        >
          <span className="smp-card-title-icon">
            <IconBook size={15} />
          </span>
          <span className="text-[14px] font-medium">古籍证据</span>
          {retrievalMethod ? (
            <span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
              {retrievalMethod}
            </span>
          ) : null}
          <button type="button" className="ml-auto" onClick={onClose} aria-label="关闭证据抽屉">
            <IconClose size={16} />
          </button>
        </header>

        {note ? (
          <p
            className="border-b px-4 py-2.5 text-[11.5px] leading-[18px]"
            style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
          >
            {note}
          </p>
        ) : null}

        <Section title="支持当前规则" tone="supporting" items={supporting} />
        <Section title="与当前规则相反（反证）" tone="counter" items={counter} />
        <Section title="中性背景" tone="neutral" items={neutral} />

        <div className="mt-auto px-4 py-4">
          <div className="smp-disclaimer">
            古籍只说明传统术数的说法，<strong>不构成对股票收益的任何判断</strong>。
            本系统同时检索支持与相反观点，以避免「先有结论后找古籍」。
            语料只收录清代及以前的公版原文；Phase 1 未逐字校勘，正式发布前需完成校勘。
          </div>
        </div>
      </div>
    </div>
  );
}

function Section({
  title,
  tone,
  items,
}: {
  title: string;
  tone: "supporting" | "counter" | "neutral";
  items: ApiEvidenceItem[];
}) {
  const chipTone = tone === "supporting" ? "up" : tone === "counter" ? "down" : "flat";
  const border = tone === "counter" ? "rgba(79,211,155,0.28)" : "var(--color-border)";

  return (
    <section className="px-4 py-3">
      <div className="mb-2 flex items-center gap-2">
        <Chip tone={chipTone as "up" | "down" | "flat"}>
          {tone === "supporting" ? "支持" : tone === "counter" ? "反证" : "中性"}
        </Chip>
        <span className="text-[12.5px]" style={{ color: "var(--color-ink)" }}>
          {title}
        </span>
        <span className="smp-num text-[11.5px]" style={{ color: "var(--color-ink-faint)" }}>
          {items.length} 条
        </span>
      </div>

      {items.length === 0 ? (
        <div className="py-2 text-[11.5px]" style={{ color: "var(--color-ink-faint)" }}>
          本次检索未命中该类条目。
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((it) => (
            <article
              key={it.entry_id}
              className="rounded-[7px] border px-3 py-2.5"
              style={{ borderColor: border, background: "rgba(0,0,0,0.16)" }}
            >
              <div className="flex items-center gap-2">
                <span className="text-[12.5px]" style={{ color: "var(--color-gold)" }}>
                  《{it.book}》
                </span>
                {it.chapter ? (
                  <span className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
                    {it.chapter}
                  </span>
                ) : null}
                <span className="smp-num ml-auto text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
                  {it.entry_id} · score {it.score.toFixed(2)}
                </span>
              </div>

              <blockquote
                className="mt-1.5 border-l-2 pl-2.5 text-[13px] leading-[22px]"
                style={{ borderColor: "var(--color-gold-dim)", color: "var(--color-ink)", fontFamily: "var(--font-serif-cn)" }}
              >
                {it.original_text}
              </blockquote>

              {it.modern_note ? (
                <p className="mt-1.5 text-[11.5px] leading-[18px]" style={{ color: "var(--color-ink-sub)" }}>
                  <span style={{ color: "var(--color-ink-faint)" }}>现代说明：</span>
                  {it.modern_note}
                </p>
              ) : null}

              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px]">
                <Meta k="版本" v={it.edition || "—"} />
                <Meta k="来源" v={it.provenance ? it.provenance.slice(0, 28) + (it.provenance.length > 28 ? "…" : "") : "—"} />
                <Meta
                  k="版权"
                  v={it.license_status === "public_domain" ? "公版原文" : it.license_status}
                />
                <Meta k="权威权重" v={it.authority_weight.toFixed(2)} />
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function Meta({ k, v }: { k: string; v: string }) {
  return (
    <span title={v} style={{ color: "var(--color-ink-faint)" }}>
      {k}：<span style={{ color: "var(--color-ink-muted)" }}>{v}</span>
    </span>
  );
}
