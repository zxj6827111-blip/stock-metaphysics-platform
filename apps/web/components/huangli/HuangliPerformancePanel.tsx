"use client";

/**
 * 「黄历证据与历史表现」分区（复刻 doc/ui-reference/08_huangli_detail.png 下半部）。
 *
 * 口径声明（必须与参考图的差异一起读）
 * ----------------------------------
 * 参考图有「+12.6% / 72% / 仓位建议」这类数字，本组件**不复制**它们：
 *
 * 1. 本区是**描述性统计**，不是策略回测 —— 系统没有可复现的组合规则、
 *    没有仓位、没有交易成本与可执行性检验，因此**不画净值/累计收益曲线**，
 *    只画"各类别截至该日期的平均持有期收益"（扩展均值）；
 * 2. 样本只取标签在分析基准日之前**已可观测**的那些（标签结束日 ≤ 基准日），
 *    防未来信息泄漏；
 * 3. 多日持有期的日频样本彼此重叠，页面必须同时给出原始样本量与
 *    **互不重叠的有效样本量**，不用朴素显著性造"有效"结论；
 * 4. "关键发现"由后端从实际数字生成，不预设吉日优于凶日。
 */

import { useEffect, useState, type ReactNode } from "react";

import { Card, CardHeader } from "@/components/cards/Card";
import { CLASS_TONE, CLASS_TONE_CN, HuangliClassTrendChart } from "@/components/charts/Charts";
import { IconTrend } from "@/components/shell/Icons";
import { SectionNote } from "@/components/shell/ResearchPage";
import {
  SectionEmpty,
  SectionError,
  SectionLoading,
  SectionUnavailable,
} from "@/components/shell/SectionState";
import { api, endpoints, type ApiHuangliPerformance } from "@/lib/api";
import { isFixtureActive, huangliPerformanceFixture } from "@/lib/fixture";
import { stripMdEmphasis } from "@/lib/text";

const WINDOWS = [
  { key: "1y", label: "近1年" },
  { key: "3y", label: "近3年" },
  { key: "5y", label: "近5年" },
  { key: "custom", label: "自定义" },
] as const;

const HORIZONS = [
  { value: 1, label: "下一交易日" },
  { value: 5, label: "5 个交易日" },
  { value: 20, label: "20 个交易日" },
] as const;

export function HuangliPerformancePanel({
  analysisId,
  sectionTag,
}: {
  analysisId: string | null;
  /** 分区身份标签（③）：由页面传入，挂在卡头标题后。 */
  sectionTag?: ReactNode;
}) {
  const [windowKey, setWindowKey] = useState<string>("1y");
  const [horizon, setHorizon] = useState<number>(1);
  const [customStart, setCustomStart] = useState<string>("");
  const [customEnd, setCustomEnd] = useState<string>("");
  const [data, setData] = useState<ApiHuangliPerformance | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const isCustom = windowKey === "custom";

  useEffect(() => {
    let cancelled = false;
    // 演示模式：读固定样本，零真实请求。
    // 但**只有**固定样本对应的那一组参数（近 1 年 / 1 个交易日）可以直接命中 ——
    // 其它组合必须显式说明"演示样本里没有"，否则切到「5 个交易日」却看到 1 日结果，
    // 会让读者以为那就是 5 日的结论。
    if (isFixtureActive()) {
      const matchesFixture = !isCustom && windowKey === "1y" && horizon === 1;
      if (!matchesFixture) {
        setData(null);
        setError(null);
        setLoading(false);
        return () => {
          cancelled = true;
        };
      }
      setData(huangliPerformanceFixture as unknown as ApiHuangliPerformance);
      setError(null);
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    if (!analysisId) {
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    if (isCustom && !customStart) {
      // 等用户给出起止日再请求，避免用默认值假装算过
      setData(null);
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    setLoading(true);
    setError(null);
    api
      .get<ApiHuangliPerformance>(
        endpoints.huangliPerformance(analysisId, {
          window: windowKey,
          horizon,
          start: isCustom ? customStart : undefined,
          end: isCustom ? customEnd || undefined : undefined,
        }),
      )
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [analysisId, windowKey, horizon, customStart, customEnd, isCustom, nonce]);

  return (
    <Card testId="huangli-performance">
      <CardHeader
        icon={<IconTrend size={15} />}
        title="黄历证据与历史表现"
        tag={sectionTag}
        right={
          <div className="flex flex-wrap items-center gap-1.5" data-testid="huangli-perf-controls">
            <div className="flex items-center gap-1">
              {WINDOWS.map((w) => (
                <button
                  key={w.key}
                  type="button"
                  onClick={() => setWindowKey(w.key)}
                  className="rounded-[4px] px-2 py-[3px] text-[11.5px] transition-colors"
                  style={tabStyle(w.key === windowKey)}
                  data-testid={`huangli-perf-window-${w.key}`}
                  aria-pressed={w.key === windowKey}
                >
                  {w.label}
                </button>
              ))}
            </div>
            <span style={{ color: "var(--color-border-strong)" }}>|</span>
            <div className="flex items-center gap-1">
              {HORIZONS.map((h) => (
                <button
                  key={h.value}
                  type="button"
                  onClick={() => setHorizon(h.value)}
                  className="rounded-[4px] px-2 py-[3px] text-[11.5px] transition-colors"
                  style={tabStyle(h.value === horizon)}
                  data-testid={`huangli-perf-horizon-${h.value}`}
                  aria-pressed={h.value === horizon}
                >
                  {h.label}
                </button>
              ))}
            </div>
          </div>
        }
        dense
      />

      {isCustom ? (
        <div className="mb-2 flex flex-wrap items-center gap-2 text-[11.5px]" data-testid="huangli-perf-custom">
          <label style={{ color: "var(--color-ink-muted)" }}>自定义区间</label>
          <input
            type="date"
            value={customStart}
            onChange={(e) => setCustomStart(e.target.value)}
            className="smp-input px-2 py-1 text-[11.5px]"
            data-testid="huangli-perf-start"
          />
          <span style={{ color: "var(--color-ink-muted)" }}>~</span>
          <input
            type="date"
            value={customEnd}
            onChange={(e) => setCustomEnd(e.target.value)}
            className="smp-input px-2 py-1 text-[11.5px]"
            data-testid="huangli-perf-end"
          />
          <span style={{ color: "var(--color-ink-faint)" }}>
            结束日晚于分析基准日时按基准日截断
          </span>
        </div>
      ) : null}

      {loading ? <SectionLoading label="正在按分类统计历史样本…" rows={4} /> : null}

      {!loading && error ? (
        <SectionError
          what="黄历历史表现"
          message={error}
          onRetry={() => setNonce((n) => n + 1)}
          testId="huangli-perf-error"
        />
      ) : null}

      {!loading && !error && !data && isCustom && !customStart ? (
        <SectionEmpty what="自定义区间" hint="请选择起始日期（结束日可留空，默认取分析基准日）。" />
      ) : null}

      {!loading && !error && !data && isFixtureActive() && !(isCustom && !customStart) ? (
        <SectionEmpty
          what="该参数组合在演示模式中没有样本"
          hint={
            isCustom
              ? "演示模式只带一份固定的「近 1 年 / 1 个交易日」样本；自定义区间需要在真实模式下请求后端。"
              : "演示模式只带一份固定的「近 1 年 / 1 个交易日」样本；其它窗口或持有期需要在真实模式下请求后端。"
          }
          testId="huangli-perf-fixture-miss"
        />
      ) : null}

      {!loading && !error && data ? (
        data.unavailable_reason ? (
          <SectionUnavailable
            what="黄历历史表现"
            reason={data.unavailable_reason}
            testId="huangli-perf-unavailable"
          />
        ) : (
          <PerformanceBody data={data} />
        )
      ) : null}
    </Card>
  );
}

function tabStyle(active: boolean): React.CSSProperties {
  return active
    ? {
        color: "#241c0c",
        background: "linear-gradient(180deg, var(--color-gold-strong), var(--color-gold))",
        fontWeight: 600,
      }
    : { color: "var(--color-ink-sub)", border: "1px solid var(--color-border)" };
}

function PerformanceBody({ data }: { data: ApiHuangliPerformance }) {
  const classes = Object.keys(data.series.by_class);
  return (
    <div className="space-y-2.5">
      {/* 口径摘要条：区间 / 持有期 / 数据截止 / 复权 / 来源 */}
      <div
        className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded border px-2.5 py-1.5 text-[11.5px]"
        style={{ borderColor: "var(--color-border)", background: "rgba(0,0,0,0.16)" }}
        data-testid="huangli-perf-provenance"
      >
        <Prov label="研究区间" value={`${fmtDate(data.window.effective_start)} ~ ${fmtDate(data.window.effective_end)}`} />
        <Prov label="持有期" value={`${data.horizon} 个交易日`} />
        <Prov label="分类依据" value={`${data.class_rule.rule_id}（${data.class_rule.basis_source}）`} />
        <Prov label="复权口径" value={data.labels.return_basis_cn || "—"} />
        <Prov label="行情来源" value={data.labels.bar_source ?? "—"} />
        <Prov
          label="基准"
          value={
            data.labels.benchmark_available
              ? data.labels.benchmark_code
              : `${data.labels.benchmark_code}（不可用，不展示超额）`
          }
        />
        <Prov label="数据截止" value={fmtDate(data.labels.label_cutoff ?? data.labels.data_cutoff)} />
        <Prov label="口径版本" value={data.performance_version} />
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
        {/* 左：分类收益时间图 */}
        <div>
          <div className="mb-1 text-[12px]" style={{ color: "var(--color-ink-sub)" }}>
            分类收益时间图（{data.class_rule.categories.map((c) => c.label_cn).join(" / ")}）
          </div>
          {data.series.dates.length ? (
            <HuangliClassTrendChart
              dates={data.series.dates}
              byClass={data.series.by_class}
              countsByClass={data.series.counts_by_class}
            />
          ) : (
            <SectionEmpty what="分类收益时间图" hint="没有可用样本。" />
          )}
          <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--color-ink-faint)" }}>
            {stripMdEmphasis(data.series.metric_cn)}
          </p>
        </div>

        {/* 右：分类统计 + 重叠披露 */}
        <div className="space-y-2">
          <div className="text-[12px]" style={{ color: "var(--color-ink-sub)" }}>
            收益统计
          </div>
          <table className="smp-table" data-testid="huangli-perf-groups">
            <thead>
              <tr>
                <th>类别</th>
                <th className="whitespace-nowrap text-right">样本</th>
                <th className="whitespace-nowrap text-right">平均</th>
                <th className="whitespace-nowrap text-right">中位数</th>
                <th className="whitespace-nowrap text-right">上涨占比</th>
                {data.labels.benchmark_available ? (
                  <th className="whitespace-nowrap text-right">平均超额</th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {data.groups.map((g) => (
                <tr key={g.class_code ?? "unknown"} data-testid={`huangli-perf-group-${g.class_code ?? "unknown"}`}>
                  <td>
                    <span
                      className="mr-1.5 inline-block h-2.5 w-2.5 rounded-[2px] align-middle"
                      style={{ background: CLASS_TONE[g.class_code ?? "unknown"] }}
                    />
                    {g.class_label_cn || CLASS_TONE_CN[g.class_code ?? "unknown"] || "未给出分类"}
                  </td>
                  <td className="smp-num whitespace-nowrap text-right">{g.n}</td>
                  <td className="smp-num whitespace-nowrap text-right">{pct(g.mean)}</td>
                  <td className="smp-num whitespace-nowrap text-right">{pct(g.median)}</td>
                  <td className="smp-num whitespace-nowrap text-right">
                    {g.up_share === null ? "—" : `${(g.up_share * 100).toFixed(0)}%`}
                  </td>
                  {data.labels.benchmark_available ? (
                    <td className="smp-num whitespace-nowrap text-right">{pct(g.mean_excess)}</td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>

          <SectionNote>
            <b>重叠与有效样本：</b>
            {stripMdEmphasis(data.overlap.independent_note_cn)}
            {data.overlap.total_samples != null ? (
              <>
                <br />
                原始样本 {data.overlap.total_samples} 个；互不重叠有效样本{" "}
                {data.overlap.independent_samples} 个。
              </>
            ) : null}
          </SectionNote>
        </div>
      </div>

      {/* 关键发现（后端从实际数字生成，不预设吉凶优劣） */}
      <div>
        <div className="mb-1 text-[12px]" style={{ color: "var(--color-ink-sub)" }}>
          关键发现（客观摘要）
        </div>
        <ul className="space-y-1" data-testid="huangli-perf-findings">
          {data.key_findings.map((f, i) => (
            <li
              key={i}
              className="flex items-start gap-1.5 text-[12px] leading-relaxed"
              style={{ color: f.level === "warn" ? "var(--color-warn)" : "var(--color-ink-sub)" }}
            >
              <span style={{ color: "var(--color-ink-faint)" }}>·</span>
              <span>{stripMdEmphasis(f.text_cn)}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* 样本规则与限制 */}
      <details className="rounded border px-2.5 py-1.5" style={{ borderColor: "var(--color-border)" }}>
        <summary className="cursor-pointer text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
          样本规则、统计限制与口径来源（点击展开）
        </summary>
        <div className="mt-1.5 space-y-1 text-[11.5px] leading-relaxed" style={{ color: "var(--color-ink-muted)" }}>
          <div>
            <b style={{ color: "var(--color-ink-sub)" }}>样本规则：</b>
            {data.sample_rule_cn}
          </div>
          <div>
            <b style={{ color: "var(--color-ink-sub)" }}>标签口径：</b>
            {data.labels.label_version}（持有期 {data.labels.horizon_supported.join(" / ")} 个交易日）；
            因标签不完整被剔除的样本 {data.labels.n_dropped_incomplete_label} 个。
          </div>
          <div>
            <b style={{ color: "var(--color-ink-sub)" }}>分类口径：</b>
            {data.class_rule.difference_note_cn}
          </div>
          <ul className="space-y-0.5">
            {data.limitations_cn.map((t, i) => (
              <li key={i}>· {t}</li>
            ))}
          </ul>
          {data.warnings.length ? (
            <ul className="space-y-0.5" style={{ color: "var(--color-warn)" }}>
              {data.warnings.map((w, i) => (
                <li key={i}>
                  · [{w.severity}] {w.code}：{w.message}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </details>

      {classes.length < 2 ? (
        <div className="text-[11.5px]" style={{ color: "var(--color-warn)" }}>
          本窗口内只有 {classes.length} 个类别出现，缺少的类别没有统计结果（不以 0 填充）。
        </div>
      ) : null}
    </div>
  );
}

function Prov({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-baseline gap-1">
      <span style={{ color: "var(--color-ink-muted)" }}>{label}</span>
      <span className="smp-num" style={{ color: "var(--color-ink-sub)" }}>
        {value}
      </span>
    </span>
  );
}

function pct(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(2)}%`;
}

function fmtDate(v: string | null | undefined): string {
  return v ? v.slice(0, 10) : "—";
}

