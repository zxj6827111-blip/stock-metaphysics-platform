"use client";

/**
 * 因子字典页（复刻 doc/ui-reference/06_factor_dictionary.png）。
 *
 * 展示 **Phase 1 的因子 + Phase 2 的紫微因子**，每个都能看到：
 * definition / computation / requires / tags / version / rule_score 语义。
 *
 * 布局（复核任务书 §R2 / 06 参考图）
 * --------------------------------
 * 左侧 2/5（40%）为因子列表，右侧 3/5（60%）为分区详情
 * （定义 → 计算 → 依赖字段 → 证据 → 历史验证）。筛选走**后端真实支持的**
 * `category` / `engine` 查询参数，文本检索在返回结果内进行并如实说明范围。
 *
 * 三条纪律
 * --------
 * 1. **每个因子必须显示 rule_score 语义声明** —— "不代表预期收益率，也不代表上涨概率"；
 * 2. **没有跑过的统计数字不能出现**：逐因子激活率/IC/胜率需要真实快照上的审计产物，
 *    本页只给**准确空态**并指向脚本与产物路径，绝不生成虚构走势图或有效性指标；
 * 3. 源码路径、脚本名收进「来源与方法」，不铺在正文里。
 */

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { Card, CardBody, CardHeader, Chip } from "@/components/cards/Card";
import { AppShell } from "@/components/shell/AppShell";
import { PageHero } from "@/components/shell/TopBar";
import { PageError, PageLoading } from "@/components/shell/PageState";
import { RawField, SourceMethod } from "@/components/shell/SourceMethod";
import { IconGrid, IconSearch } from "@/components/shell/Icons";
import { api, endpoints } from "@/lib/api";
import { engineCn } from "@/lib/dataSource";
import { isFixtureActive, factorsDictionaryFixture } from "@/lib/fixture";

interface FactorDef {
  factor_id: string;
  name: string;
  engine: string;
  category: string;
  definition: string;
  computation: string;
  raw_unit: string;
  normalized_hint: string;
  default_direction: string | number;
  rule_score_meaning: string;
  rule_version: string;
  requires: string[];
  tags: string[];
}

interface DictResponse {
  total: number;
  total_all: number;
  by_category: Record<string, number>;
  items: FactorDef[];
  disclaimer: string;
  rule_version: string;
}

const DIR_CN: Record<string, string> = { "1": "正向", "0": "中性", "-1": "负向" };
const PAGE_SIZE = 25;

function FactorsInner() {
  const [data, setData] = useState<DictResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [engine, setEngine] = useState<string>("");
  const [category, setCategory] = useState<string>("");
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  // engine / category 是后端真实支持的查询参数 —— 用它而不是前端自筛，
  // 页面看到的分组数与“全部因子”的口径才与接口一致。
  const load = useCallback(async (eng: string, cat: string) => {
    if (isFixtureActive()) {
      setData(factorsDictionaryFixture as unknown as DictResponse);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams();
      if (eng) qs.set("engine", eng);
      if (cat) qs.set("category", cat);
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      setData(await api.get<DictResponse>(endpoints.factorDictionary() + suffix));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(engine, category);
  }, [load, engine, category]);

  useEffect(() => {
    setPage(1);
  }, [engine, category, q]);

  const filtered = useMemo(() => {
    let list = data?.items ?? [];
    if (q.trim()) {
      const needle = q.trim();
      list = list.filter(
        (d) =>
          d.factor_id.includes(needle) ||
          d.name.includes(needle) ||
          d.definition.includes(needle) ||
          d.tags.some((t) => t.includes(needle)),
      );
    }
    return list;
  }, [data, q]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const rows = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const current = filtered.find((d) => d.factor_id === selectedId) ?? filtered[0] ?? null;

  const categories = useMemo(
    () => Array.from(new Set((data?.items ?? []).map((d) => d.category))).sort(),
    [data],
  );
  const engines = ["bazi", "ziwei", "huangli", "quant", "calendar", "consensus"];

  return (
    <AppShell
      activeNav="factors"
      dataStatus={error ? "bad" : "ok"}
      statusText={error ? "后端未连接" : isFixtureActive() ? "演示数据（固定样本）" : "数据正常"}
    >
      <PageHero
        title="因子字典"
        subtitle="统一管理八字、紫微、黄历与量化辅助因子，沉淀可复用研究资产"
        seal="典"
      />

      {loading ? <PageLoading label="正在读取因子字典…" /> : null}
      {error ? <PageError message={error} onRetry={() => load(engine, category)} /> : null}

      {!loading && !error && data ? (
        <>
          {/* ---------- 筛选区 ---------- */}
          <Card testId="factor-filters">
            <CardHeader
              icon={<IconSearch size={15} />}
              title="筛选"
              dense
              right={
                <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                  共 {data.total_all} 个 · 当前命中 {filtered.length} 个
                </span>
              }
            />
            <CardBody className="!py-2">
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="搜索因子 ID / 名称 / 定义 / 标签"
                  className="min-w-[240px] flex-1 rounded border px-3 py-1.5 text-[12.5px] outline-none"
                  style={{ borderColor: "var(--color-border)", background: "transparent", color: "var(--color-ink)" }}
                  data-testid="factor-search"
                />
                <Select value={engine} onChange={setEngine} options={engines} placeholder="全部术数" label="来源模型" renderOption={engineCn} />
                <Select value={category} onChange={setCategory} options={categories} placeholder="全部层级" label="层级" />
                <button
                  type="button"
                  className="smp-btn px-2.5 py-1 text-[11.5px]"
                  onClick={() => {
                    setEngine("");
                    setCategory("");
                    setQ("");
                  }}
                  data-testid="factor-reset"
                >
                  重置
                </button>
              </div>
              <p className="mt-1.5 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
                来源模型 / 层级为<strong>后端查询参数</strong>（全量口径）；文本检索在返回结果内进行，
                即“先按筛选条件取回，再在结果内搜索”，不冒充全库语义检索。
              </p>
            </CardBody>
          </Card>

          {/* ---------- 列表 40% / 详情 60% ---------- */}
          <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <Card testId="factor-list">
              <CardHeader
                icon={<IconGrid size={15} />}
                title={`因子列表（${filtered.length} 个）`}
                dense
                right={
                  <span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
                    rule_version {data.rule_version}
                  </span>
                }
              />
              <div className="max-h-[560px] overflow-y-auto px-2 pb-2">
                <table className="w-full text-[11.5px]" data-testid="factor-table">
                  <thead className="sticky top-0" style={{ background: "var(--color-bg, #0d1117)" }}>
                    <tr style={{ color: "var(--color-ink-muted)" }}>
                      <th className="text-left font-medium">ID</th>
                      <th className="text-left font-medium">名称</th>
                      <th className="text-left font-medium">来源</th>
                      <th className="text-left font-medium">方向</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((d) => {
                      const active = current?.factor_id === d.factor_id;
                      return (
                        <tr
                          key={d.factor_id}
                          onClick={() => setSelectedId(d.factor_id)}
                          style={{
                            borderTop: "1px solid var(--color-border)",
                            background: active ? "rgba(212,160,74,0.10)" : undefined,
                            cursor: "pointer",
                          }}
                          data-testid={`factor-row-${d.factor_id}`}
                          aria-selected={active}
                        >
                          <td className="py-[3px]">
                            <code className="text-[11px]">{d.factor_id}</code>
                          </td>
                          <td className="truncate">{d.name}</td>
                          <td style={{ color: "var(--color-ink-muted)" }}>{engineCn(d.engine)}</td>
                          <td>{DIR_CN[String(d.default_direction)] ?? "中性"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {!filtered.length ? (
                  <div className="py-4 text-center text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
                    没有匹配的因子。清空筛选或搜索词再试。
                  </div>
                ) : null}
              </div>
              {pageCount > 1 ? (
                <div
                  className="flex items-center justify-between border-t px-2 py-1 text-[11.5px]"
                  style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
                  data-testid="factor-pagination"
                >
                  <span>
                    第 {currentPage} / {pageCount} 页 · 每页 {PAGE_SIZE}（前端分页，列表已全部取回）
                  </span>
                  <span className="flex gap-1">
                    <button
                      type="button"
                      className="smp-btn px-2 py-[2px] text-[11px]"
                      disabled={currentPage <= 1}
                      onClick={() => setPage(currentPage - 1)}
                    >
                      上一页
                    </button>
                    <button
                      type="button"
                      className="smp-btn px-2 py-[2px] text-[11px]"
                      disabled={currentPage >= pageCount}
                      onClick={() => setPage(currentPage + 1)}
                    >
                      下一页
                    </button>
                  </span>
                </div>
              ) : null}
            </Card>

            <Card testId="factor-detail">
              <CardHeader
                icon={<IconGrid size={15} />}
                title={current ? `因子详情 ${current.factor_id}` : "因子详情"}
                dense
                right={
                  current ? (
                    <div className="flex items-center gap-1">
                      <Chip tone="flat">{engineCn(current.engine)}</Chip>
                      <Chip tone="flat">{current.category}</Chip>
                      <Chip tone={current.default_direction === 0 ? "flat" : "gold"}>
                        {DIR_CN[String(current.default_direction)] ?? "中性"}
                      </Chip>
                    </div>
                  ) : null
                }
              />
              {current ? (
                <CardBody className="space-y-2.5">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="text-[15px] font-semibold" data-testid="factor-detail-name">
                      {current.name}
                    </span>
                    <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                      规则版本 {current.rule_version}
                    </span>
                  </div>

                  <Section title="因子定义">{current.definition}</Section>

                  <Section title="计算">
                    <code
                      className="block rounded border px-2 py-1 text-[11.5px] leading-relaxed"
                      style={{ borderColor: "var(--color-border)", color: "var(--color-ink-sub)" }}
                    >
                      {current.computation || "（定义中未给出显式算式）"}
                    </code>
                    <div className="mt-1 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                      原始值：{current.raw_unit || "—"}｜归一化：{current.normalized_hint || "—"}
                    </div>
                  </Section>

                  <Section title="依赖字段">
                    {current.requires.length ? (
                      <div className="flex flex-wrap gap-1">
                        {current.requires.map((r) => (
                          <span
                            key={r}
                            className="rounded-[3px] border px-1.5 py-[1px] text-[11px]"
                            style={{ borderColor: "var(--color-border)", color: "var(--color-ink-sub)" }}
                          >
                            {r}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span style={{ color: "var(--color-ink-muted)" }}>（未声明依赖字段）</span>
                    )}
                  </Section>

                  <Section title="证据">
                    {current.tags.length ? (
                      <div className="flex flex-wrap gap-1">
                        {current.tags.map((t) => (
                          <Chip key={t} tone="flat">
                            {t}
                          </Chip>
                        ))}
                      </div>
                    ) : (
                      <span style={{ color: "var(--color-ink-muted)" }}>（未标注主题标签）</span>
                    )}
                    <div className="mt-1.5 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                      古籍依据的检索入口在「古籍证据」页；本页只列出该因子的主题标签，
                      不在这里复制条文（避免出现未经核实的引文）。
                    </div>
                  </Section>

                  <Section title="历史验证">
                    <div
                      className="rounded border px-2.5 py-2 text-[11.5px] leading-relaxed"
                      style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
                      data-testid="factor-history-empty"
                    >
                      <b style={{ color: "var(--color-ink-sub)" }}>
                        本页不显示逐因子的胜率 / 平均收益 / IC。
                      </b>
                      <br />
                      这些数字必须在<strong>真实快照</strong>上由审计脚本算出后才可信；当前页面的数据源
                      （因子字典接口）<strong>不包含</strong>历史统计字段，因此这里给空态而不是占位图。
                      逐因子有效性请以已生成的研究产物为准。
                    </div>
                  </Section>

                  <div
                    className="rounded border px-2.5 py-2 text-[11.5px] leading-relaxed"
                    style={{ borderColor: "rgba(212,160,74,0.45)", color: "var(--color-ink-muted)" }}
                    data-testid="rule-score-meaning"
                  >
                    <b style={{ color: "var(--color-gold)" }}>规则分语义：</b>
                    {current.rule_score_meaning}
                  </div>

                  <SourceMethod label="来源与方法" testId="factor-source-method">
                    <RawField label="接口" value="GET /api/v1/factor-dictionary?engine=&category=" />
                    <RawField label="因子规则版本" value={data.rule_version} />
                    <RawField label="因子总数（全量）" value={String(data.total_all)} />
                    <RawField
                      label="质量审计脚本"
                      value="scripts/factor_quality_audit.py、scripts/ziwei_factor_quality_audit.py"
                    />
                    <RawField
                      label="审计产物"
                      value="docs/factor_quality_report.md、docs/ziwei-factor-dictionary.md"
                    />
                    <div>{data.disclaimer}</div>
                  </SourceMethod>
                </CardBody>
              ) : (
                <CardBody>
                  <div className="py-4 text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
                    请选择一个因子。
                  </div>
                </CardBody>
              )}
            </Card>
          </div>
        </>
      ) : null}
    </AppShell>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div data-testid={`factor-section-${title}`}>
      <div className="text-[11.5px] font-semibold" style={{ color: "var(--color-ink-sub)" }}>
        {title}
      </div>
      <div className="mt-0.5 text-[12px] leading-relaxed" style={{ color: "var(--color-ink)" }}>
        {children}
      </div>
    </div>
  );
}

function Select({
  value,
  onChange,
  options,
  placeholder,
  label,
  renderOption,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  placeholder: string;
  label: string;
  renderOption?: (v: string) => string;
}) {
  return (
    <label className="flex items-center gap-1 text-[11.5px]">
      <span style={{ color: "var(--color-ink-muted)" }}>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border px-2 py-1 text-[11.5px] outline-none"
        style={{ borderColor: "var(--color-border)", background: "transparent", color: "var(--color-ink)" }}
        data-testid={`factor-filter-${label}`}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {renderOption ? renderOption(o) : o}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function FactorsPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <FactorsInner />
    </Suspense>
  );
}
