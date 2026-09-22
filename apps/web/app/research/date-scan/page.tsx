"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { Card, CardHeader, Chip } from "@/components/cards/Card";
import { AppShell } from "@/components/shell/AppShell";
import { PageHero } from "@/components/shell/TopBar";
import { PageError, PageLoading, UnavailableBlock } from "@/components/shell/PageState";
import { SourceMethod, RawField } from "@/components/shell/SourceMethod";
import { ResearchNav } from "@/components/research/ResearchNav";
import { DateRelationFingerprint } from "@/components/research/DateRelationFingerprint";
import { MarketRelationSummary } from "@/components/research/MarketRelationSummary";
import { RelationMatrix } from "@/components/research/RelationMatrix";
import { RelationScatter } from "@/components/research/RelationScatter";
import { RelationStockTable } from "@/components/research/RelationStockTable";
import { api, endpoints, type ApiDateScanDetail, type ApiDateScanResponse, type ApiRelationStockResult } from "@/lib/api";

const DEFAULT_DATE = "2026-09-22";
const RELATIONS = ["", "六合", "六冲", "三合", "半合", "三会", "相刑", "相害", "六破", "伏吟", "反吟", "天合地合", "天克地冲"];

function DateScanInner() {
  const search = useSearchParams();
  const fixture = search?.get("fixture") === "ui-reference";
  const [date, setDate] = useState(search?.get("date") || DEFAULT_DATE);
  const [relationType, setRelationType] = useState("");
  const [sort, setSort] = useState("stock_code");
  const [page, setPage] = useState(0);
  const [data, setData] = useState<ApiDateScanResponse | null>(null);
  const [selected, setSelected] = useState<ApiRelationStockResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const pageSize = 100;

  const load = useCallback(async (targetDate: string, targetPage: number, targetSort: string, targetRelation: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.post<ApiDateScanResponse>(endpoints.dateScan(), {
        date: targetDate,
        universe: "v4-full",
        birth_basis: "listing_open",
        birth_profile_version: "v2-phase4b-listing_open",
        relation_rule_version: "bazi-relation-v2",
        limit: pageSize,
        offset: targetPage * pageSize,
        sort: targetSort,
        relation_type: targetRelation || null,
      });
      setData(response);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (fixture) {
      setLoading(false);
      setData(null);
      return;
    }
    void load(date, page, sort, relationType);
  }, [date, page, sort, relationType, load, fixture]);

  const onSelect = useCallback(async (row: ApiRelationStockResult) => {
    if (!data) return;
    setDetailError(null);
    setDetailLoading(true);
    try {
      const detail = await api.get<ApiDateScanDetail>(endpoints.dateScanDetail(data.scan_id, row.stock_code, {
        date: data.target_date,
        universe: data.versions.universe_version,
        birthBasis: data.versions.birth_basis,
        birthProfileVersion: data.versions.birth_profile_version,
        relationRuleVersion: data.versions.relation_rule_version,
      }));
      setSelected(detail.row);
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : String(e));
    } finally {
      setDetailLoading(false);
    }
  }, [data]);

  const pageCount = Math.max(1, Math.ceil((data?.filtered_count ?? 0) / pageSize));
  const dateLabel = useMemo(() => data?.fingerprint ? `${data.fingerprint.year} · ${data.fingerprint.month} · ${data.fingerprint.day}` : "日期干支读取中…", [data]);

  return (
    <AppShell activeNav="research" dataStatus={error ? "bad" : loading ? "warn" : "ok"} statusText={error ? "扫描失败" : loading ? "关系扫描中" : "研究数据就绪"}>
      <PageHero title="择日关系扫描" subtitle="指定日期 × 全市场股票八字关系矩阵" seal="研" couplet={["择日", "观局", "察势", "验真"]} motto={["先看结构", "再问统计"]} />
      <ResearchNav />
      {fixture ? <Card><UnavailableBlock what="择日关系扫描" reason="当前为 UI 复刻 fixture 模式；本页没有冻结的全市场扫描样本，因此不会请求真实 API 或伪造扫描结果。移除 ?fixture=ui-reference 后可使用真实研究数据。" /></Card> : null}
      <Card className="mb-2" testId="date-scan-controls">
        <CardHeader title="研究控制区" dense right={<Chip tone="gold">跨股票研究工具</Chip>} />
        <div className="grid gap-3 p-3 md:grid-cols-[190px_1fr_auto] md:items-end">
          <label className="block text-[12px]" style={{ color: "var(--color-ink-muted)" }}>研究日期<input type="date" className="smp-input mt-1 w-full" value={date} onChange={(event) => { setPage(0); setDate(event.target.value); }} data-testid="date-scan-date" /></label>
          <div>
            <div className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>日期干支</div>
            <div className="mt-1 text-[19px]" style={{ color: "var(--color-gold-strong)" }}>{dateLabel}</div>
          </div>
          <div className="flex flex-wrap gap-2 text-[11.5px]"><Chip tone="flat">股票池：全A · v4-full</Chip><Chip tone="flat">出生基准：上市首日开盘</Chip><Chip tone="flat">规则：relation-v2</Chip></div>
        </div>
      </Card>

      {loading && !data ? <PageLoading label="正在读取日期指纹并扫描全市场关系…" /> : null}
      {error ? <PageError title="择日关系扫描失败" message={error} onRetry={() => void load(date, page, sort, relationType)} /> : null}
      {data ? (
        <div className="space-y-2">
          <DateRelationFingerprint fingerprint={data.fingerprint} />
          <MarketRelationSummary data={data} />
          <div className="grid gap-2 lg:grid-cols-[1.05fr_0.95fr]">
            <RelationScatter rows={data.rows} />
            <Card testId="relation-filter-bar">
              <CardHeader title="关系筛选与排序" dense />
              <div className="flex flex-wrap gap-2 p-3">
                {RELATIONS.map((relation) => <button key={relation || "all"} type="button" className={`smp-btn ${relationType === relation ? "smp-btn--primary" : ""}`} onClick={() => { setPage(0); setRelationType(relation); }}>{relation || "全部关系"}</button>)}
                <label className="flex items-center gap-2 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>排序<select className="smp-input" value={sort} onChange={(event) => { setPage(0); setSort(event.target.value); }}><option value="stock_code">代码</option><option value="s">协同 S</option><option value="v">扰动 V</option><option value="u">混合 U</option></select></label>
              </div>
              <div className="px-3 pb-3 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>筛选作用于后端已计算的 RelationEvent；前端不重新计算术数关系。</div>
            </Card>
          </div>
          <Card>
            <CardHeader title={`全市场股票结果（${data.returned_count} / ${data.filtered_count}，原始 ${data.stock_total}）`} dense right={<span className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>点击股票查看完整 3×4 矩阵</span>} />
            <RelationStockTable rows={data.rows} onSelect={onSelect} />
            <div className="flex items-center justify-between border-t px-3 py-2 text-[11.5px]" style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}><span>第 {page + 1} / {pageCount} 页 · {data.cache.hit ? "缓存命中" : "刚刚计算"}</span><span className="flex gap-2"><button type="button" className="smp-btn px-2 py-1" disabled={page <= 0} onClick={() => setPage((value) => Math.max(0, value - 1))}>上一页</button><button type="button" className="smp-btn px-2 py-1" disabled={page + 1 >= pageCount} onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}>下一页</button></span></div>
          </Card>
          <Card>
            <CardHeader title="方法与研究边界" dense />
            <div className="grid gap-2 p-3 md:grid-cols-2"><div className="smp-disclaimer">{data.disclaimer}</div><SourceMethod label="版本与来源" testId="date-scan-source"><RawField label="scan_id" value={data.scan_id} /><RawField label="universe_digest" value={data.versions.universe_digest} /><RawField label="fingerprint_version" value={data.versions.fingerprint_version} /><RawField label="bazi_engine_version" value={data.versions.bazi_engine_version} /></SourceMethod></div>
            {data.warnings.length ? <div className="border-t px-3 py-2 text-[11.5px]" style={{ borderColor: "var(--color-border)", color: "var(--color-warn)" }}>{data.warnings.slice(0, 3).map((warning) => <div key={warning.code}>· {warning.message}</div>)}</div> : null}
          </Card>
        </div>
      ) : null}
      {detailLoading ? <PageLoading label="正在读取股票关系矩阵…" /> : null}
      {detailError ? <Card><UnavailableBlock what="股票详情" reason={detailError} /></Card> : null}
      {selected ? <RelationMatrix row={selected} onClose={() => setSelected(null)} /> : null}
    </AppShell>
  );
}

export default function DateScanPage() {
  return <Suspense fallback={<PageLoading />}><DateScanInner /></Suspense>;
}
