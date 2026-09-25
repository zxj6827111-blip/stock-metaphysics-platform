"use client";

/**
 * 古籍证据检索页（复刻 doc/ui-reference/09_classics_evidence_search.png）。
 *
 * 一条硬约束：**生产页面只能展示真实 KnowledgeProvider 返回的数据。**
 * 参考图上那些书名/条文是设计示意；本页面不内置任何古籍文本，
 * 全部来自 `/api/v1/analysis/{id}/evidence` 的检索结果。
 * 演示模式（`?fixture=ui-reference`）用的是**真实语料检索后冻结**的样本，
 * entry_id / 版本 / provenance 与真实模式同源，不是手写编造的条目。
 *
 * 布局（复核任务书 §R2 / 09 参考图）
 * --------------------------------
 * 左侧 55% 检索结果、右侧 45% 分类摘要与选中证据详情；
 * **支持 / 反证 / 中性计数固定在首屏**（右栏第一张卡），且列表在「全部」模式下
 * 按 **反证优先** 排序 —— 反证不会被支持条目挤到页面末尾。
 * 每条证据形成 `原文 → 项目解释 → 关联主题` 的可追溯结构。
 *
 * 另外两条纪律：
 * 1. **支持与反证必须并列**：三类计数永远同时渲染，即使某一类为空也要说明"为空意味着什么"；
 * 2. 每条证据必须显示 `source / edition / provenance / license_status` —— 没有这些的文本
 *    不应该出现在研究系统里；语料自带的"未校勘"限制也必须显示。
 */

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { Card, CardBody, CardHeader, Chip } from "@/components/cards/Card";
import { ResearchPage, SectionNote } from "@/components/shell/ResearchPage";
import { PageLoading, UnavailableBlock } from "@/components/shell/PageState";
import { RawField, SourceMethod } from "@/components/shell/SourceMethod";
import { IconBook, IconSearch } from "@/components/shell/Icons";
import { api, endpoints, type ApiEvidence, type ApiEvidenceItem } from "@/lib/api";
import { useAnalysis } from "@/lib/analysisStore";
import { useBirthBasisParam } from "@/lib/useBirthBasisParam";
import { useHorizonParam } from "@/lib/useHorizonParam";
import { FIXTURE_QUERY_VALUE, isFixtureActive, evidenceFixture } from "@/lib/fixture";

/** 三类证据的展示顺序 —— 「全部」模式下也按这个顺序分段，反证永远在最前。 */
const STANCES = [
  { key: "counter", label: "反证", tone: "var(--color-warn)" },
  { key: "support", label: "支持", tone: "var(--color-up)" },
  { key: "neutral", label: "中性", tone: "var(--color-flat)" },
] as const;

type StanceKey = (typeof STANCES)[number]["key"];

type Buckets = Record<StanceKey, ApiEvidenceItem[]>;

function EvidenceInner() {
  const params = useParams<{ code: string }>();
  const code = params?.code ?? "600519";
  const searchParams = useSearchParams();
  // 用查询参数（而不是 window.location）判定演示模式：服务端与客户端一致，
  // 避免"服务端渲染真实证据 / 客户端渲染演示语料"的 hydration 不一致。
  const isFixtureDemo = searchParams.get("fixture") === FIXTURE_QUERY_VALUE;
  const birthBasis = useBirthBasisParam();
  const horizon = useHorizonParam();
  const { analysis, loading, error, reload } = useAnalysis(code, "forward", undefined, birthBasis, horizon);

  const [bundle, setBundle] = useState<ApiEvidence | null>(null);
  const [evLoading, setEvLoading] = useState(false);
  const [evError, setEvError] = useState<string | null>(null);
  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [stance, setStance] = useState<StanceKey | "all">("all");
  const [activeId, setActiveId] = useState<string | null>(null);

  const load = useCallback(
    async (analysisId: string) => {
      if (isFixtureActive() && code === "600519") {
        setBundle(evidenceFixture);
        setEvLoading(false);
        return;
      }
      setEvLoading(true);
      setEvError(null);
      try {
        const data = await api.get<ApiEvidence>(endpoints.evidence(analysisId));
        setBundle(data);
      } catch (e) {
        setEvError(e instanceof Error ? e.message : String(e));
      } finally {
        setEvLoading(false);
      }
    },
    [code],
  );

  useEffect(() => {
    if (analysis?.analysis_id) void load(analysis.analysis_id);
  }, [analysis?.analysis_id, load]);

  const ev = bundle?.evidence;

  const allBuckets: Buckets = useMemo(
    () => ({
      counter: (ev?.counter_evidence as ApiEvidenceItem[] | undefined) ?? [],
      support: (ev?.supporting_evidence as ApiEvidenceItem[] | undefined) ?? [],
      neutral: (ev?.neutral_evidence as ApiEvidenceItem[] | undefined) ?? [],
    }),
    [ev],
  );

  const matches = useCallback(
    (it: ApiEvidenceItem) => {
      const needle = q.trim();
      if (!needle) return true;
      return (
        it.original_text.includes(needle) ||
        (it.modern_note ?? "").includes(needle) ||
        it.book.includes(needle) ||
        (it.topic ?? []).some((t) => t.includes(needle))
      );
    },
    [q],
  );

  const buckets: Buckets = useMemo(
    () => ({
      counter: allBuckets.counter.filter(matches),
      support: allBuckets.support.filter(matches),
      neutral: allBuckets.neutral.filter(matches),
    }),
    [allBuckets, matches],
  );

  // 列表顺序：反证 → 支持 → 中性（每类内部按后端 score 降序）
  const ordered = useMemo(() => {
    const keys: StanceKey[] = stance === "all" ? ["counter", "support", "neutral"] : [stance];
    return keys.flatMap((k) =>
      [...buckets[k]].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)),
    );
  }, [buckets, stance]);

  const active = ordered.find((it) => it.entry_id === activeId) ?? ordered[0] ?? null;
  const total = buckets.counter.length + buckets.support.length + buckets.neutral.length;
  const totalAll =
    allBuckets.counter.length + allBuckets.support.length + allBuckets.neutral.length;

  return (
    <ResearchPage
      activeNav="evidence"
      title="古籍证据检索"
      subtitle="连通经典古籍与现代研究，把结论落到原典证据与历史样本"
      seal="典"
      // 参考图 09 的 Hero 高 102px（104-20+16+2）。
      heroMinHeight={84}
      code={code}
      analysis={analysis}
      loading={loading}
      error={error}
      onReload={reload}
      loadingLabel="正在检索古籍证据（同时返回支持与反证）…"
    >
      {/* ---------- 检索与范围 ---------- */}
      <Card testId="evidence-search">
        <CardHeader
          icon={<IconSearch size={15} />}
          title="证据检索"
          dense
          right={
            <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              {isFixtureDemo ? "演示语料（真实语料冻结样本）" : "知识库检索"}
            </span>
          }
        />
        <CardBody className="!py-2">
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="在本次检索结果内筛选：书名 / 原文 / 解释 / 主题"
              className="min-w-[260px] flex-1 rounded border px-3 py-1.5 text-[12.5px] outline-none"
              style={{
                borderColor: "var(--color-border)",
                background: "transparent",
                color: "var(--color-ink)",
              }}
              data-testid="evidence-filter"
            />
            <span className="flex items-center gap-1" data-testid="evidence-stance-tabs">
              {(["all", "counter", "support", "neutral"] as const).map((k) => {
                const label = k === "all" ? "全部" : STANCES.find((s) => s.key === k)!.label;
                const count = k === "all" ? total : buckets[k].length;
                const on = stance === k;
                return (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setStance(k)}
                    aria-pressed={on}
                    className="rounded-[4px] border px-2 py-[3px] text-[11.5px]"
                    style={{
                      borderColor: on ? "var(--color-gold)" : "var(--color-border)",
                      color: on ? "var(--color-gold)" : "var(--color-ink-sub)",
                    }}
                    data-testid={`evidence-tab-${k}`}
                  >
                    {label} {count}
                  </button>
                );
              })}
            </span>
          </div>
          <p className="mt-1.5 text-[11px]" style={{ color: "var(--color-ink-muted)" }} data-testid="evidence-scope">
            检索范围：<b>本次分析触发的检索结果</b>（由驱动因子构造检索词，后端 BM25 + 主题匹配），
            不是全库语义检索；输入框只在这个结果集内筛选。
            {q.trim() ? ` 当前筛选后 ${total} / ${totalAll} 条。` : ""}
          </p>
          <div className="mt-1.5">
            <SourceMethod testId="evidence-source-method">
              <RawField
                label="语料来源"
                value={
                  isFixtureDemo
                    ? "演示语料：真实公版语料检索后冻结的固定样本（entry_id / 版本与真实模式同源）"
                    : "项目自持公版语料库（KnowledgeProvider 检索）"
                }
              />
              <RawField label="检索方法" value={ev?.retrieval_method ?? "—"} />
              <RawField label="知识库版本" value={ev?.knowledge_version ?? "—"} />
              <RawField
                label="驱动因子"
                value={
                  bundle?.driver_factors?.length
                    ? bundle.driver_factors.map((f) => `${f.factor_id}(${f.name})`).join("、")
                    : "（无）"
                }
              />
              <RawField label="检索主题" value={ev?.query?.topics?.join("、") ?? "—"} />
              <RawField label="候选条目数" value={String(ev?.total_candidates ?? "—")} />
              <RawField label="检索接口" value="GET /api/v1/analysis/{analysis_id}/evidence" />
            </SourceMethod>
          </div>
        </CardBody>
      </Card>

      {evError ? (
        <Card testId="evidence-error">
          <CardBody>
            <div className="text-[13px]" style={{ color: "var(--color-warn)" }}>
              古籍检索失败：{evError}
            </div>
          </CardBody>
        </Card>
      ) : null}

      {evLoading ? (
        <Card>
          <CardBody>
            <div className="text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
              正在检索…
            </div>
          </CardBody>
        </Card>
      ) : null}

      {!evLoading && !ev ? (
        <Card>
          <CardBody>
            <UnavailableBlock
              what="古籍证据包"
              reason="后端未返回证据包（可能尚无因子观测，或知识库不可用）。"
            />
          </CardBody>
        </Card>
      ) : null}

      {/* ---------- 左 55% 结果 / 右 45% 摘要与详情 ---------- */}
      {ev ? (
        <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,11fr)_minmax(0,9fr)]">
          <Card testId="evidence-list">
            <CardHeader
              icon={<IconBook size={15} />}
              title={`证据列表（${
                stance === "all" ? total : `${buckets[stance].length} / ${allBuckets[stance].length}`
              } 条）`}
              dense
              right={
                <span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
                  {stance === "all" ? "排序：反证 → 支持 → 中性" : STANCES.find((s) => s.key === stance)!.label}
                </span>
              }
            />
            <CardBody className="!py-1.5">
              {ordered.length ? (
                <ol className="space-y-1.5" data-testid="evidence-items">
                  {ordered.map((it, i) => {
                    const key = stanceKeyOf(it, buckets);
                    const meta = STANCES.find((s) => s.key === key)!;
                    const on = active?.entry_id === it.entry_id;
                    return (
                      <li key={it.entry_id}>
                        <button
                          type="button"
                          onClick={() => setActiveId(it.entry_id)}
                          className="w-full rounded border px-2.5 py-1.5 text-left"
                          style={{
                            borderColor: on ? "var(--color-gold)" : "var(--color-border)",
                            background: on ? "rgba(212,160,74,0.08)" : undefined,
                          }}
                          data-testid={`evidence-item-${it.entry_id}`}
                          data-stance={key}
                        >
                          <div className="flex items-baseline justify-between gap-2">
                            <span className="text-[12px] font-semibold" style={{ color: meta.tone }}>
                              {i + 1}. 《{it.book}》{it.chapter ? ` · ${it.chapter}` : ""}
                            </span>
                            <span
                              className="shrink-0 text-[10.5px]"
                              style={{ color: "var(--color-ink-muted)" }}
                            >
                              {meta.label} · 检索得分 {Number(it.score ?? 0).toFixed(2)}（BM25）
                            </span>
                          </div>
                          <blockquote
                            className="mt-0.5 line-clamp-2 border-l-2 pl-2 text-[12px] leading-[17px]"
                            style={{ borderColor: meta.tone }}
                          >
                            {it.original_text}
                          </blockquote>
                        </button>
                      </li>
                    );
                  })}
                </ol>
              ) : (
                <div className="py-4 text-center text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
                  {q.trim() ? "当前筛选词在本次结果内没有命中。" : "后端未返回该类目证据条目。"}
                </div>
              )}
            </CardBody>
          </Card>

          <div className="space-y-3">
            {/* 三栏计数：首屏固定可见，反证与支持并列 */}
            <Card testId="evidence-counts">
              <CardHeader icon={<IconBook size={15} />} title="证据聚合（支持 / 反证 / 中性）" dense />
              <CardBody className="!py-2">
                <div className="grid grid-cols-3 gap-2" data-testid="evidence-stance-counts">
                  {STANCES.map((s) => (
                    <div
                      key={s.key}
                      className="rounded border px-2 py-1.5"
                      style={{ borderColor: "var(--color-border)" }}
                      data-testid={`stance-count-${s.key}`}
                    >
                      <div className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
                        {s.label}
                      </div>
                      <div className="text-[20px] font-bold leading-tight" style={{ color: s.tone }}>
                        {buckets[s.key].length}
                      </div>
                      <div className="text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
                        占 {total ? Math.round((buckets[s.key].length / total) * 100) : 0}%
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-1.5 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
                  比例只描述<b>本次检索结果</b>的构成，不是"古籍整体倾向"；
                  展示层不做倾向性结论（那属于研究结论，需要专门方法）。
                </div>
              </CardBody>
            </Card>

            <Card testId="evidence-detail">
              <CardHeader
                icon={<IconBook size={15} />}
                title="选中证据详情（原文 → 解释 → 主题）"
                dense
              />
              <CardBody className="!py-2">
                {active ? (
                  <div className="space-y-2 text-[12px]" data-testid="evidence-detail-body">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="text-[13px] font-semibold" style={{ color: "var(--color-gold)" }}>
                        《{active.book}》{active.chapter ? ` · ${active.chapter}` : ""}
                      </span>
                      {active.school ? <Chip tone="flat">{active.school}</Chip> : null}
                      <span className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
                        检索得分 {Number(active.score ?? 0).toFixed(2)}（BM25，非 0–1 相似度）
                        {active.authority_weight == null
                          ? ""
                          : ` · 权威权重 ${active.authority_weight.toFixed(2)}`}
                      </span>
                    </div>

                    <Field label="① 原典原文">
                      <blockquote
                        className="border-l-2 pl-2 text-[12.5px] leading-relaxed"
                        style={{ borderColor: "var(--color-gold-dim)" }}
                      >
                        {active.original_text}
                      </blockquote>
                    </Field>

                    <Field label="② 项目解释（本项目自撰，不是古籍原文）">
                      {active.modern_note || (
                        <span style={{ color: "var(--color-ink-muted)" }}>（该条未附项目解释）</span>
                      )}
                    </Field>

                    <Field label="③ 关联主题与因子">
                      <div className="flex flex-wrap gap-1">
                        {(active.topic ?? []).map((t) => (
                          <Chip key={t} tone="flat">
                            {t}
                          </Chip>
                        ))}
                        {(active.matched_query_terms ?? []).map((t) => (
                          <Chip key={`m-${t}`} tone="gold">
                            命中 {t}
                          </Chip>
                        ))}
                      </div>
                      <div className="mt-1 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
                        本次检索由这些因子触发：
                        {bundle?.driver_factors?.length
                          ? bundle.driver_factors.map((f) => `${f.factor_id}(${f.name})`).join("、")
                          : "（无）"}
                        。主题标签同时用于因子定义与语料条目，因此可以顺着
                        「因子 → 主题 → 原文」逐跳核对。
                      </div>
                    </Field>

                    <div
                      className="rounded border px-2.5 py-1.5 text-[11px] leading-relaxed"
                      style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
                      data-testid="evidence-provenance"
                    >
                      <div>来源：{active.source || "—"}</div>
                      <div>版本：{active.edition || "—"}</div>
                      <div>出处：{active.provenance || "—"}</div>
                      <div>
                        版权：
                        {active.license_status === "public_domain"
                          ? "公版（public_domain）"
                          : active.license_status || "—"}
                      </div>
                      <div>
                        条目 ID：<code>{active.entry_id}</code>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="py-4 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
                    选择左侧任一条证据查看原文、解释与来源。
                  </div>
                )}
              </CardBody>
            </Card>

            <Card testId="evidence-caveat">
              <CardHeader icon={<IconBook size={15} />} title="使用前必须知道的限制" dense />
              <CardBody className="!py-2 space-y-1.5">
                <SectionNote>{ev.note ?? "（无说明）"}</SectionNote>
                <SectionNote>
                  语料声明：<strong>未逐字对照权威刊本校勘</strong>（紫微语料的
                  <code>verification_status</code> 为 <code>unverified_offline</code>）。
                  因此这里的原文只能用于流程演示与检索核对，正式引用前必须完成校勘，
                  不得声称已校勘。
                </SectionNote>
                <SectionNote>
                  反证为空时不能读成"古籍一致支持"：那更可能是检索词覆盖不足。
                  系统不会把"没有反证"渲染成利好。
                </SectionNote>
              </CardBody>
            </Card>
          </div>
        </div>
      ) : null}
    </ResearchPage>
  );
}

/** 从三个桶里反查某条证据属于哪一类（后端 stance 字段优先）。 */
function stanceKeyOf(it: ApiEvidenceItem, buckets: Buckets): StanceKey {
  if (it.stance === "supporting" || it.stance === "support") return "support";
  if (it.stance === "counter") return "counter";
  if (it.stance === "neutral") return "neutral";
  for (const k of ["counter", "support", "neutral"] as StanceKey[]) {
    if (buckets[k].some((x) => x.entry_id === it.entry_id)) return k;
  }
  return "neutral";
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] font-semibold" style={{ color: "var(--color-ink-sub)" }}>
        {label}
      </div>
      <div className="mt-0.5" style={{ color: "var(--color-ink)" }}>
        {children}
      </div>
    </div>
  );
}

export default function EvidencePage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <EvidenceInner />
    </Suspense>
  );
}
