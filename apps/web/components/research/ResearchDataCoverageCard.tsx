"use client";

import { useEffect, useState } from "react";

import { Card, CardBody, CardHeader, Chip } from "@/components/cards/Card";
import { SectionError, SectionLoading, SectionUnavailable } from "@/components/shell/SectionState";
import { api, endpoints } from "@/lib/api";
import type { ApiHistoricalDatasetV2, ApiSystemVersions } from "@/lib/researchV2";
import { DEFAULT_RESEARCH_DATASET_ID } from "@/lib/researchV2";

export function ResearchDataCoverageCard({ fixture }: { fixture: boolean }) {
  const [versions, setVersions] = useState<ApiSystemVersions | null>(null);
  const [dataset, setDataset] = useState<ApiHistoricalDatasetV2 | null>(null);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (fixture) return;
    let cancelled = false;
    setLoading(true);
    void Promise.allSettled([
      api.get<ApiSystemVersions>(endpoints.systemVersions()),
      api.get<ApiHistoricalDatasetV2>(endpoints.historicalDatasetV2(DEFAULT_RESEARCH_DATASET_ID)),
    ]).then(([versionResult, datasetResult]) => {
      if (cancelled) return;
      if (versionResult.status === "fulfilled") {
        setVersions(versionResult.value);
        setVersionsError(null);
      } else {
        setVersionsError(errorText(versionResult.reason));
      }
      if (datasetResult.status === "fulfilled") {
        setDataset(datasetResult.value);
        setDatasetError(null);
      } else {
        setDatasetError(errorText(datasetResult.reason));
      }
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [fixture, nonce]);

  if (fixture) return null;
  const dates = dataset?.metadata.scope?.research_dates ?? [];
  const orderedDates = [...dates].sort();
  const dateRange = orderedDates.length
    ? `${orderedDates[0]} ～ ${orderedDates[orderedDates.length - 1]}`
    : "不可用";

  return (
    <Card className="mt-3" testId="research-data-coverage">
      <CardHeader
        title="行情截止日与研究可用范围"
        dense
        right={<Chip tone={dataset?.research_eligible ? "gold" : "warn"}>{dataset?.research_eligible ? "数据集可用于研究" : "数据集未认证"}</Chip>}
      />
      <CardBody>
        {loading ? <SectionLoading label="正在读取实例版本与历史数据集清单…" rows={2} /> : null}
        {versionsError ? <SectionError what="行情截止信息" message={versionsError} onRetry={() => setNonce((value) => value + 1)} /> : null}
        {datasetError ? <SectionError what="研究数据集" message={datasetError} onRetry={() => setNonce((value) => value + 1)} /> : null}
        {!loading && !versionsError && !datasetError && !dataset ? (
          <SectionUnavailable what="研究范围" reason="实例没有返回所选数据集；请核对数据集 ID 与 API 数据根配置。" />
        ) : null}
        <div className="grid gap-2 text-[11.5px] sm:grid-cols-2 lg:grid-cols-4" data-testid="research-data-coverage-values">
          <CoverageValue label="行情快照截止日" value={versions?.market_data_cutoff_date ?? "不可用"} detail={`${versions?.market_data_source ?? "来源不可用"} · ${versions?.market_data_version ?? "版本不可用"}`} />
          <CoverageValue label="历史数据集范围" value={dateRange} detail={`${dataset?.dataset_id ?? DEFAULT_RESEARCH_DATASET_ID} · ${dataset?.metadata.scope?.sample_kind ?? "范围不可用"}`} />
          <CoverageValue label="样本覆盖" value={dataset ? `${dataset.row_count} 行 · ${dataset.complete_shard_count}/${dataset.expected_shard_count} 分片` : "不可用"} detail={`${dataset?.metadata.scope?.stock_code ?? "证券范围未提供"} · ${dataset?.metadata.scope?.exchange ?? "交易所未提供"}`} />
          <CoverageValue label="研究 / 确认性资格" value={dataset ? `${dataset.research_eligible ? "可用于研究" : "未认证"} / ${dataset.confirmatory_research_eligible ? "具确认性资格" : "不具确认性资格"}` : "不可用"} detail={`manifest=${dataset?.status ?? "不可用"} · schema=${dataset?.schema_version ?? "不可用"}`} />
        </div>
        {dataset?.metadata.known_limitations?.length ? (
          <div className="mt-2 text-[11.5px]" style={{ color: "var(--color-warn)" }} data-testid="research-data-limitations">
            {dataset.metadata.known_limitations.slice(0, 3).map((limitation) => <div key={limitation}>· {limitation}</div>)}
          </div>
        ) : null}
        <div className="mt-2 text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
          行情快照截止日与历史数据集范围是两个独立口径；展示数据集范围不代表该范围已认证。
        </div>
      </CardBody>
    </Card>
  );
}

function CoverageValue({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded border px-2.5 py-2" style={{ borderColor: "var(--color-border)" }}>
      <div className="smp-metric-label">{label}</div>
      <div className="mt-1 break-all text-[12px]" style={{ color: "var(--color-ink)" }}>{value}</div>
      <div className="mt-1 break-all text-[10.5px]" style={{ color: "var(--color-ink-muted)" }}>{detail}</div>
    </div>
  );
}

function errorText(value: unknown): string {
  return value instanceof Error ? value.message : String(value);
}
