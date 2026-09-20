"use client";

/**
 * 古籍证据检索页（复刻 doc/ui-reference/09_classics_evidence_search.png）。
 *
 * 一条硬约束：**生产页面只能展示真实 KnowledgeProvider 返回的数据。**
 * 参考图上那些书名/条文是设计示意；本页面不内置任何古籍文本，
 * 全部来自 `/api/v1/analysis/{id}/evidence-bundle` 的 `classical` 字段。
 *
 * 另外两条纪律：
 * 1. **支持与反证必须并列**：三栏（支持 / 反证 / 中性）永远同时渲染，
 *    即使某一栏为空也要显示并说明"为空意味着什么"；
 * 2. 每条证据必须显示 `source / edition / provenance / license_status` —— 没有这些的文本
 *    不应该出现在研究系统里。
 */

import { useParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { Card, CardHeader } from "@/components/cards/Card";
import { ResearchPage, SectionNote } from "@/components/shell/ResearchPage";
import { PageLoading, UnavailableBlock } from "@/components/shell/PageState";
import { IconBook, IconSearch } from "@/components/shell/Icons";
import { api, endpoints, type ApiEvidence } from "@/lib/api";
import { useAnalysis } from "@/lib/analysisStore";
import { isFixtureActive, evidenceFixture } from "@/lib/fixture";

interface Item {
  entry_id: string;
  book: string;
  chapter?: string;
  original_text: string;
  modern_note?: string;
  score?: number;
  stance?: string;
  source?: string;
  edition?: string;
  provenance?: string;
  license_status?: string;
}

function EvidenceInner() {
  const params = useParams<{ code: string }>();
  const code = params?.code ?? "600519";
  const { analysis, loading, error, reload } = useAnalysis(code);

  const [bundle, setBundle] = useState<ApiEvidence | null>(null);
  const [evLoading, setEvLoading] = useState(false);
  const [evError, setEvError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  const load = useCallback(async (analysisId: string) => {
    if (isFixtureActive() && code === "600519") {
      setBundle(evidenceFixture);
      setEvLoading(false);
      return;
    }
    setEvLoading(true);
    setEvError(null);
    try {
      const data = await api.get<ApiEvidence & { classical?: unknown }>(
        endpoints.evidence(analysisId),
      );
      setBundle(data);
    } catch (e) {
      setEvError(e instanceof Error ? e.message : String(e));
    } finally {
      setEvLoading(false);
    }
  }, []);

  useEffect(() => {
    if (analysis?.analysis_id) void load(analysis.analysis_id);
  }, [analysis?.analysis_id, load]);

  const ev = bundle?.evidence as unknown as {
    supporting_evidence?: Item[];
    counter_evidence?: Item[];
    neutral_evidence?: Item[];
    retrieval_method?: string;
    note?: string;
  } | undefined;

  const filter = useCallback(
    (items: Item[] | undefined) => {
      const list = items ?? [];
      if (!q.trim()) return list;
      const needle = q.trim();
      return list.filter(
        (it) =>
          it.original_text.includes(needle) ||
          (it.modern_note ?? "").includes(needle) ||
          it.book.includes(needle),
      );
    },
    [q],
  );

  const supporting = useMemo(() => filter(ev?.supporting_evidence), [ev, filter]);
  const counter = useMemo(() => filter(ev?.counter_evidence), [ev, filter]);
  const neutral = useMemo(() => filter(ev?.neutral_evidence), [ev, filter]);

  return (
    <ResearchPage
      activeNav="evidence"
      title="古籍证据检索"
      subtitle="连通经典古籍与现代研究，把结论落到原典证据与历史样本"
      seal="典"
      code={code}
      analysis={analysis}
      loading={loading}
      error={error}
      onReload={reload}
      loadingLabel="正在检索古籍证据（同时返回支持与反证）…"
    >
      <Card>
        <CardHeader
          icon={<IconSearch size={15} />}
          title="检索"
          right={
            <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              {ev?.retrieval_method ?? "bm25+topic_match+authority_weight"}
            </span>
          }
          dense
        />
        <div className="flex items-center gap-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="在当前结果内筛选关键词，如：财帛宫 / 四化 / 庙旺"
            className="w-full rounded border px-3 py-1.5 text-[12.5px] outline-none"
            style={{
              borderColor: "var(--color-border)",
              background: "transparent",
              color: "var(--color-ink)",
            }}
            data-testid="evidence-filter"
          />
          <span className="shrink-0 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
            支持 {supporting.length} · 反证 {counter.length} · 中性 {neutral.length}
          </span>
        </div>
        <div className="mt-2">
          <SectionNote>
            语料只收录<strong>清代及以前</strong>的公版原文；每条都带 source / edition / provenance /
            license_status。检索<strong>必须同时返回支持与反证</strong>，以避免「先有结论后找古籍」。
          </SectionNote>
        </div>
      </Card>

      {evError ? (
        <Card testId="evidence-error">
          <div className="py-3 text-[13px]" style={{ color: "var(--color-warn)" }}>
            古籍检索失败：{evError}
          </div>
        </Card>
      ) : null}

      {evLoading ? (
        <Card>
          <div className="py-3 text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
            正在检索…
          </div>
        </Card>
      ) : null}

      {!evLoading && !ev ? (
        <UnavailableBlock
          what="古籍证据包"
          reason="后端未返回证据包（可能尚无因子观测，或知识库不可用）。"
        />
      ) : null}

      {ev ? (
        <>
          <Card testId="evidence-supporting">
            <CardHeader
              icon={<IconBook size={15} />}
              title={`支持性证据（真实 KnowledgeProvider 返回，${supporting.length} 条）`}
              dense
            />
            <EvidenceList items={supporting} tone="support" />
          </Card>

          <Card testId="evidence-counter">
            <CardHeader
              icon={<IconBook size={15} />}
              title={`反证 / 不同流派解释（${counter.length} 条）`}
              dense
            />
            <EvidenceList items={counter} tone="counter" />
            {!counter.length ? (
              <div className="mt-2">
                <SectionNote>
                  未检索到反证 —— 这本身需要警惕：反证为空可能意味着检索词覆盖不足，
                  <strong>不得</strong>据此认为「古籍一致支持」。系统不会把"没有反证"渲染成利好。
                </SectionNote>
              </div>
            ) : null}
          </Card>

          <Card testId="evidence-neutral">
            <CardHeader
              icon={<IconBook size={15} />}
              title={`中性 / 背景条目（${neutral.length} 条）`}
              dense
            />
            <EvidenceList items={neutral} tone="neutral" />
          </Card>

          <Card>
            <CardHeader icon={<IconBook size={15} />} title="检索说明" dense />
            <SectionNote>{ev.note ?? "（无说明）"}</SectionNote>
            <SectionNote>
              古籍条文只说明传统术数的说法，<strong>不构成对股票收益的任何判断</strong>。
              本页所有文本均来自项目自持的公有领域语料，未逐字校勘，
              正式引用前必须完成校勘（见 knowledge/*/classical_seed.json 的 _meta）。
            </SectionNote>
          </Card>
        </>
      ) : null}
    </ResearchPage>
  );
}

function EvidenceList({
  items,
  tone,
}: {
  items: Item[];
  tone: "support" | "counter" | "neutral";
}) {
  const accent =
    tone === "support"
      ? "var(--color-up)"
      : tone === "counter"
        ? "var(--color-down)"
        : "var(--color-flat)";

  if (!items.length) {
    return (
      <div className="py-4 text-center text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
        暂无该类目证据条目
      </div>
    );
  }
  return (
    <ol className="space-y-2">
      {items.map((it, i) => (
        <li
          key={it.entry_id}
          className="rounded border p-3"
          style={{ borderColor: "var(--color-border)" }}
          data-testid={`evidence-item-${it.entry_id}`}
        >
          <div className="flex items-baseline justify-between gap-3">
            <div className="text-[12.5px] font-semibold" style={{ color: accent }}>
              {i + 1}. 《{it.book}》{it.chapter ? ` · ${it.chapter}` : ""}
            </div>
            <div className="shrink-0 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
              {it.score !== undefined ? `相似度 ${Number(it.score).toFixed(2)}` : ""}
            </div>
          </div>
          <blockquote
            className="mt-1 border-l-2 pl-3 text-[13px] leading-relaxed"
            style={{ borderColor: accent }}
          >
            {it.original_text}
          </blockquote>
          {it.modern_note ? (
            <p className="mt-1 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
              现代说明（本项目自撰）：{it.modern_note}
            </p>
          ) : null}
          <div
            className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px]"
            style={{ color: "var(--color-ink-muted)" }}
          >
            <span>ID：<code>{it.entry_id}</code></span>
            {it.edition ? <span>版本：{it.edition}</span> : null}
            {it.license_status ? <span>版权：{it.license_status}</span> : null}
            {it.source ? <span>来源：{it.source}</span> : null}
          </div>
          {it.provenance ? (
            <div className="mt-0.5 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
              出处：{it.provenance}
            </div>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

export default function EvidencePage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <EvidenceInner />
    </Suspense>
  );
}
