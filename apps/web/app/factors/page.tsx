"use client";

/**
 * 因子字典页（复刻 doc/ui-reference/06_factor_dictionary.png）。
 *
 * 展示 **Phase 1 的 65 个因子 + Phase 2 的 49 个紫微因子 = 114 个**，
 * 每个都能看到：definition / computation / version / activation rate /
 * 历史统计 / 关联证据入口。
 *
 * 两条纪律：
 * 1. **每个因子必须显示 rule_score 语义声明** —— "不代表预期收益率，也不代表上涨概率"；
 * 2. **质量标记必须可见**（LOW_DISCRIMINATION / CONSTANT / POTENTIAL_DUPLICATE）——
 *    研究系统不能把"这个因子在样本上没有区分度"藏起来。
 */

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { Card, CardHeader } from "@/components/cards/Card";
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

function FactorsInner() {
  const [data, setData] = useState<DictResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [engine, setEngine] = useState<string>("");
  const [category, setCategory] = useState<string>("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<FactorDef | null>(null);

  const load = useCallback(async () => {
    if (isFixtureActive()) {
      setData(factorsDictionaryFixture as unknown as DictResponse);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setData(await api.get<DictResponse>(endpoints.factorDictionary()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const items = useMemo(() => {
    let list = data?.items ?? [];
    if (engine) list = list.filter((d) => d.engine === engine);
    if (category) list = list.filter((d) => d.category === category);
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
  }, [data, engine, category, q]);

  const engines = useMemo(
    () => Array.from(new Set((data?.items ?? []).map((d) => d.engine))).sort(),
    [data],
  );
  const categories = useMemo(
    () => Array.from(new Set((data?.items ?? []).map((d) => d.category))).sort(),
    [data],
  );

  const current = selected ?? items[0] ?? null;

  return (
    <AppShell
      activeNav="factors"
      dataStatus={error ? "bad" : "ok"}
      statusText={error ? "后端未连接" : "数据正常"}
    >
      <PageHero
        title="因子字典"
        subtitle="统一管理八字、紫微、黄历与量化辅助因子，沉淀可复用研究资产"
        seal="典"
      />

      {loading ? <PageLoading label="正在读取因子字典…" /> : null}
      {error ? <PageError message={error} onRetry={load} /> : null}

      {!loading && !error && data ? (
        <>
          <Card>
            <CardHeader
              icon={<IconSearch size={15} />}
              title={`因子列表（${items.length} / ${data.total_all} 个）`}
              right={
                <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                  rule_version {data.rule_version}
                </span>
              }
              dense
            />
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="搜索因子 ID / 名称 / 定义 / 标签"
                className="min-w-[240px] flex-1 rounded border px-3 py-1.5 text-[12.5px] outline-none"
                style={{ borderColor: "var(--color-border)", background: "transparent", color: "var(--color-ink)" }}
                data-testid="factor-search"
              />
              <Select value={engine} onChange={setEngine} options={engines} placeholder="全部术数" label="术数" />
              <Select
                value={category}
                onChange={setCategory}
                options={categories}
                placeholder="全部层级"
                label="层级"
              />
            </div>
            <div className="mt-2">
              <p
                className="rounded border px-3 py-2 text-[12px]"
                style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
              >
                {data.disclaimer}
              </p>
            </div>
          </Card>

          <div className="grid grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] gap-3">
            <Card>
              <CardHeader icon={<IconGrid size={15} />} title="因子表" dense />
              <div className="max-h-[620px] overflow-y-auto">
                <table className="w-full text-[12px]" data-testid="factor-table">
                  <thead className="sticky top-0" style={{ background: "var(--color-bg, #0d1117)" }}>
                    <tr style={{ color: "var(--color-ink-muted)" }}>
                      <th className="text-left">ID</th>
                      <th className="text-left">名称</th>
                      <th className="text-left">术数</th>
                      <th className="text-left">方向</th>
                      <th className="text-left">版本</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((d) => {
                      const active = current?.factor_id === d.factor_id;
                      return (
                        <tr
                          key={d.factor_id}
                          onClick={() => setSelected(d)}
                          style={{
                            borderTop: "1px solid var(--color-border)",
                            background: active ? "rgba(212,160,74,0.10)" : undefined,
                            cursor: "pointer",
                          }}
                          data-testid={`factor-row-${d.factor_id}`}
                        >
                          <td className="py-1">
                            <code>{d.factor_id}</code>
                          </td>
                          <td>{d.name}</td>
                          <td>{engineCn(d.engine)}</td>
                          <td>{DIR_CN[String(d.default_direction)] ?? "中性"}</td>
                          <td style={{ color: "var(--color-ink-muted)" }}>{d.rule_version}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {!items.length ? (
                  <div className="py-4 text-center text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
                    没有匹配的因子。
                  </div>
                ) : null}
              </div>
            </Card>

            <Card testId="factor-detail">
              <CardHeader icon={<IconGrid size={15} />} title="因子详情" dense />
              {current ? (
                <div className="space-y-2 text-[12.5px]">
                  <div className="flex items-baseline gap-2">
                    <code className="text-[14px]" style={{ color: "var(--color-gold)" }}>
                      {current.factor_id}
                    </code>
                    <span className="text-[14px] font-semibold">{current.name}</span>
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1" style={{ color: "var(--color-ink-muted)" }}>
                    <span>术数：{engineCn(current.engine)}</span>
                    <span>层级：{current.category}</span>
                    <span>方向（传统规则）：{DIR_CN[String(current.default_direction)] ?? "中性"}</span>
                    <span>规则版本：{current.rule_version}</span>
                  </div>

                  <Block title="定义">{current.definition}</Block>
                  <Block title="计算">
                    <code>{current.computation || "—"}</code>
                  </Block>
                  <Block title="原始值 / 归一化">
                    {current.raw_unit || "—"}｜{current.normalized_hint || "—"}
                  </Block>
                  <Block title="依赖盘面字段">
                    {current.requires.length ? current.requires.join("、") : "—"}
                  </Block>
                  <Block title="标签">{current.tags.length ? current.tags.join("、") : "—"}</Block>

                  <div
                    className="rounded border px-3 py-2 text-[12px]"
                    style={{ borderColor: "rgba(212,160,74,0.45)", color: "var(--color-ink-muted)" }}
                    data-testid="rule-score-meaning"
                  >
                    <b style={{ color: "var(--color-gold)" }}>规则分语义：</b>
                    {current.rule_score_meaning}
                  </div>

                  <div
                    className="rounded border px-3 py-2 text-[12px]"
                    style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
                  >
                    <b>质量审计与历史统计</b>
                    <br />
                    逐因子审计（激活率 / 空值率 / 唯一取值数 / 相关系数）在<strong>真实快照</strong>上生成；
                    本页刻意<strong>不显示未运行的统计数字</strong> —— 没有跑过的数字不能出现在研究终端里。
                    <div className="mt-1.5">
                      <SourceMethod label="审计脚本与产物路径">
                        <RawField label="审计脚本" value="scripts/factor_quality_audit.py、scripts/ziwei_factor_quality_audit.py" />
                        <RawField label="审计产物" value="docs/factor_quality_report.md、docs/ziwei-factor-dictionary.md" />
                      </SourceMethod>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="py-4 text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
                  请选择一个因子。
                </div>
              )}
            </Card>
          </div>
        </>
      ) : null}
    </AppShell>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11.5px] font-semibold" style={{ color: "var(--color-ink-muted)" }}>
        {title}
      </div>
      <div className="mt-0.5 leading-relaxed">{children}</div>
    </div>
  );
}

function Select({
  value,
  onChange,
  options,
  placeholder,
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  placeholder: string;
  label: string;
}) {
  return (
    <label className="flex items-center gap-1 text-[12px]">
      <span style={{ color: "var(--color-ink-muted)" }}>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border px-2 py-1 text-[12px] outline-none"
        style={{ borderColor: "var(--color-border)", background: "transparent", color: "var(--color-ink)" }}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
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
