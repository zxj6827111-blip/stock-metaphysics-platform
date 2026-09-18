"use client";

/**
 * EngineScoreCard / ConsensusCard / ConflictCard / DataQualityBadge / BacktestMetricCard
 *
 * 这些是 uiux_spec §29 里要求抽象出的通用组件，三个页面复用同一套实现。
 *
 * 关键约束：
 *  - score 为 null（引擎未启用/失败）时显示「未启用 / 不可用」，
 *    **绝不显示 0 分**，也绝不参与任何平均值计算。
 *  - 分数只是摘要，盘面与解释必须在详情页可见。
 */

import Link from "next/link";

import type {
  BacktestMetric,
  ConsensusView,
  ConflictView,
  DataQualityView,
  EngineCardView,
  EvidenceCardView,
} from "@/lib/types";
import { Card, CardHeader, Chip, DirectionMark } from "./Card";
import {
  IconBook,
  IconCheck,
  IconFlame,
  IconGauge,
  IconGrid,
  IconStar4,
  IconTaiji,
  IconTarget,
  IconWarning,
} from "../shell/Icons";

const ENGINE_ICON: Record<string, React.ComponentType<{ size?: number }>> = {
  bazi: IconTaiji,
  ziwei: IconStar4,
  huangli: IconGrid,
  backtest: IconGauge,
};

const ENGINE_ACCENT: Record<string, string> = {
  bazi: "var(--color-gold)",
  ziwei: "#b07cd6",
  huangli: "#4fd39b",
  backtest: "#6b8fd4",
};

export function EngineScoreCard({ engine }: { engine: EngineCardView }) {
  const Icon = ENGINE_ICON[engine.engine] ?? IconTaiji;
  const accent = ENGINE_ACCENT[engine.engine] ?? "var(--color-gold)";
  const dirTone = engine.direction > 0 ? "up" : engine.direction < 0 ? "down" : "flat";

  return (
    <Card className="flex min-h-[186px] flex-col p-4" testId={`engine-card-${engine.engine}`}>
      <div className="flex items-center gap-2">
        <span
          className="flex h-7 w-7 items-center justify-center rounded-full"
          style={{ color: accent, border: `1px solid ${accent}55`, background: `${accent}18` }}
        >
          <Icon size={15} />
        </span>
        <span className="text-[14px] font-medium" style={{ color: "var(--color-ink)" }}>
          {engine.displayName}
        </span>
        {engine.available && engine.score !== null ? (
          <Chip tone={dirTone as "up" | "down" | "flat"} testId={`engine-dir-${engine.engine}`}>
            {engine.directionLabel}
          </Chip>
        ) : (
          <Chip tone="flat">未启用</Chip>
        )}
      </div>

      {engine.available && engine.score !== null ? (
        <>
          <div className="mt-3 flex items-end gap-1.5">
            <span
              className="smp-num text-[32px] font-semibold leading-none"
              style={{ color: engine.direction > 0 ? "var(--color-up)" : engine.direction < 0 ? "var(--color-down)" : "var(--color-ink)" }}
              data-testid={`engine-score-${engine.engine}`}
            >
              {engine.score.toFixed(0)}
            </span>
            <span className="pb-[3px] text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
              /100
            </span>
          </div>

          <div className="mt-2.5">
            <div className="smp-metric-label">信心指数</div>
            <div className="mt-1 flex items-center gap-2">
              <div className="h-[3px] flex-1 rounded-full" style={{ background: "var(--color-surface-4)" }}>
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.round((engine.confidence ?? 0) * 100)}%`,
                    background: accent,
                  }}
                />
              </div>
              <span className="smp-num text-[11.5px]" style={{ color: "var(--color-ink-sub)" }}>
                {Math.round((engine.confidence ?? 0) * 100)}%
              </span>
            </div>
          </div>

          <p className="mt-2.5 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
            {engine.summary}
          </p>

          <div className="mt-auto flex items-center gap-3 whitespace-nowrap pt-3 text-[11px]">
            <span className="flex items-center gap-1">
              <span style={{ color: "var(--color-ink-muted)" }}>正向因素</span>
              <span className="smp-num" style={{ color: "var(--color-up)" }}>
                {engine.positiveCount}
              </span>
            </span>
            <span className="flex items-center gap-1">
              <span style={{ color: "var(--color-ink-muted)" }}>负向因素</span>
              <span className="smp-num" style={{ color: "var(--color-down)" }}>
                {engine.negativeCount}
              </span>
            </span>
            <Link
              href={engine.detailHref}
              className="ml-auto"
              style={{ color: "var(--color-ink-muted)" }}
            >
              查看详情→
            </Link>
          </div>
        </>
      ) : (
        <div className="mt-4 flex-1">
          <div className="text-[13px]" style={{ color: "var(--color-ink-muted)" }}>
            该引擎当前不可用
          </div>
          <p className="mt-2 text-[11.5px] leading-[18px]" style={{ color: "var(--color-ink-faint)" }}>
            {engine.unavailableReason ??
              "引擎未启用或计算失败。本卡片不会以 0 分参与任何聚合，其他模型结果不受影响。"}
          </p>
        </div>
      )}
    </Card>
  );
}

export function ConsensusCard({ consensus }: { consensus: ConsensusView }) {
  const tone =
    consensus.label.includes("POSITIVE")
      ? "up"
      : consensus.label.includes("NEGATIVE")
        ? "down"
        : consensus.label === "MIXED"
          ? "conflict"
          : "flat";

  return (
    <Card className="flex min-h-[186px] flex-col p-4" testId="consensus-card">
      <div className="flex items-center gap-2">
        <span className="smp-card-title-icon">
          <IconTarget size={15} />
        </span>
        <span className="text-[14px] font-medium">多模型共识</span>
        {consensus.displayOnly ? (
          <span
            className="ml-auto text-[10.5px]"
            style={{ color: "var(--color-ink-faint)" }}
            title="Phase 1 未实现正式 ConsensusEngine，此处仅为展示层聚合"
          >
            展示层
          </span>
        ) : null}
      </div>

      <div className="mt-3 flex gap-4">
        {/* 共识徽记 */}
        <div className="flex w-[118px] shrink-0 items-center justify-center">
          <div
            className="flex h-[104px] w-[104px] flex-col items-center justify-center rounded-full text-center"
            style={{
              border: `1px solid ${tone === "up" ? "var(--color-up-dim)" : tone === "down" ? "var(--color-down-dim)" : "var(--color-border-strong)"}`,
              background:
                tone === "up"
                  ? "radial-gradient(circle, rgba(232,88,90,0.22), rgba(232,88,90,0.03) 70%)"
                  : tone === "down"
                    ? "radial-gradient(circle, rgba(79,211,155,0.22), rgba(79,211,155,0.03) 70%)"
                    : "radial-gradient(circle, rgba(124,143,163,0.2), rgba(124,143,163,0.03) 70%)",
              boxShadow: "0 0 26px rgba(232,88,90,0.12)",
            }}
            data-testid="consensus-badge"
          >
            <span
              className="text-[17px] font-semibold leading-tight"
              style={{
                color:
                  tone === "up" ? "var(--color-up)" : tone === "down" ? "var(--color-down)" : "var(--color-ink)",
              }}
            >
              {consensus.labelCn}
            </span>
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="space-y-1.5">
            {consensus.directions.map((d) => (
              <div key={d.engine} className="flex items-center gap-2">
                <span className="w-[68px] text-[12px]" style={{ color: "var(--color-ink-sub)" }}>
                  {d.displayName}
                </span>
                <DirectionMark direction={d.direction} size={13} />
                <span className="smp-num text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
                  {d.direction > 0 ? "+" : d.direction < 0 ? "−" : "0"}
                </span>
              </div>
            ))}
            {consensus.unavailableEngines.map((e) => (
              <div key={e} className="flex items-center gap-2">
                <span className="w-[68px] text-[12px]" style={{ color: "var(--color-ink-faint)" }}>
                  {e}
                </span>
                <span className="text-[11.5px]" style={{ color: "var(--color-ink-faint)" }}>
                  未启用（不计入）
                </span>
              </div>
            ))}
          </div>

          <div className="mt-3 space-y-1 border-t pt-2.5" style={{ borderColor: "var(--color-border)" }}>
            <MetaRow label="一致性" value={consensus.agreement} />
            <MetaRow label="历史验证" value={consensus.historicalValidity} />
            <MetaRow label="数据质量" value={consensus.dataQuality} />
          </div>
        </div>
      </div>

      <p
        className="mt-auto pt-3 text-center text-[11.5px] tracking-[0.1em]"
        style={{ color: "var(--color-ink-muted)" }}
      >
        {consensus.note}
      </p>
    </Card>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-[11.5px]">
      <span style={{ color: "var(--color-ink-muted)" }}>{label}：</span>
      <span style={{ color: "var(--color-ink)" }}>{value}</span>
    </div>
  );
}

export function ConflictCard({ conflict }: { conflict: ConflictView }) {
  if (!conflict.hasConflict) {
    return (
      <Card className="flex min-h-[186px] flex-col p-4" testId="conflict-card">
        <div className="flex items-center gap-2">
          <span className="smp-card-title-icon">
            <IconWarning size={15} />
          </span>
          <span className="text-[14px] font-medium">模型分歧监测</span>
        </div>
        <div className="mt-6 flex flex-col items-center justify-center">
          <span
            className="flex h-14 w-14 items-center justify-center rounded-full"
            style={{
              color: "var(--color-down)",
              border: "1px solid rgba(79,211,155,0.5)",
              background: "rgba(79,211,155,0.1)",
            }}
          >
            <IconCheck size={26} />
          </span>
          <div className="mt-3 text-[14px]" style={{ color: "var(--color-ink)" }}>
            {conflict.headline}
          </div>
        </div>
        <p
          className="mt-auto pt-4 text-center text-[11.5px] leading-[18px]"
          style={{ color: "var(--color-ink-muted)" }}
        >
          各模型结论趋于一致，
          <br />
          未发现需要重点关注的分类。
        </p>
      </Card>
    );
  }

  return (
    <Card className="flex min-h-[186px] flex-col p-4" testId="conflict-card">
      <div className="flex items-center gap-2">
        <span style={{ color: "var(--color-conflict)" }}>
          <IconWarning size={15} />
        </span>
        <span className="text-[14px] font-medium">⚠ 模型存在明显分歧</span>
      </div>
      <div className="mt-3 space-y-2">
        {conflict.reasons.map((r, i) => (
          <div key={i} className="text-[11.5px] leading-[18px]">
            <span style={{ color: "var(--color-ink)" }}>{r.engine}：{r.direction}</span>
            <br />
            <span style={{ color: "var(--color-ink-muted)" }}>{r.text}</span>
          </div>
        ))}
      </div>
      <p className="mt-auto pt-3 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
        系统禁止用平均分掩盖分歧，以上方向并列展示。
      </p>
    </Card>
  );
}

export function DataQualityBadge({ quality }: { quality: DataQualityView }) {
  const gradeTone =
    quality.grade === "A"
      ? "var(--color-down)"
      : quality.grade === "B"
        ? "var(--color-gold)"
        : quality.grade === "C"
          ? "var(--color-warn)"
          : "var(--color-up)";

  return (
    <Card testId="data-quality-card">
      <CardHeader icon={<IconCheck size={14} />} title="数据质量与风险" action={{ label: "查看详情" }} />
      <div className="flex gap-4 p-4">
        <div className="flex w-[128px] shrink-0 flex-col items-center justify-center">
          <div
            className="flex h-[92px] w-[92px] flex-col items-center justify-center rounded-full"
            style={{
              border: `2px solid ${gradeTone}`,
              boxShadow: `0 0 22px ${gradeTone}33`,
              background: "radial-gradient(circle, rgba(79,211,155,0.10), transparent 70%)",
            }}
          >
            <span className="smp-num text-[34px] font-semibold leading-none" style={{ color: gradeTone }}>
              {quality.grade}
            </span>
          </div>
          <div className="mt-2 text-center">
            <div className="text-[13px]" style={{ color: "var(--color-ink)" }}>
              {quality.title}
            </div>
            <div className="text-[13px]" style={{ color: gradeTone }}>
              {quality.subtitle}
            </div>
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            {quality.items.map((it) => (
              <div key={it.label} className="flex items-center gap-1.5 text-[11.5px]">
                <span
                  style={{
                    color:
                      it.state === "ok"
                        ? "var(--color-down)"
                        : it.state === "warn"
                          ? "var(--color-warn)"
                          : "var(--color-up)",
                  }}
                >
                  <IconCheck size={12} />
                </span>
                <span style={{ color: "var(--color-ink-sub)" }}>{it.label}</span>
                <span className="ml-auto" style={{ color: "var(--color-ink)" }}>
                  {it.value}
                </span>
              </div>
            ))}
          </div>
          <div className="smp-divider my-2.5" />
          <p className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
            数据完整 · 来源可靠 · 计算一致
          </p>
        </div>
      </div>
      <div
        className="mx-4 mb-3 flex items-start gap-2 rounded-[6px] border px-3 py-2 text-[11px]"
        style={{
          borderColor: "rgba(224,164,88,0.36)",
          background: "rgba(224,164,88,0.08)",
          color: "var(--color-warn)",
        }}
      >
        <span className="mt-[1px]">
          <IconWarning size={13} />
        </span>
        <span>
          <span className="font-semibold">风险提示：</span>
          {quality.riskNote}
        </span>
      </div>
    </Card>
  );
}

export function BacktestMetricCard({ metric }: { metric: BacktestMetric }) {
  const color =
    metric.tone === "up"
      ? "var(--color-up)"
      : metric.tone === "down"
        ? "var(--color-down)"
        : metric.tone === "gold"
          ? "var(--color-gold)"
          : "var(--color-ink)";
  return (
    <div
      className="rounded-[8px] border px-3 py-2.5"
      style={{ borderColor: "var(--color-border)", background: "var(--color-surface-1)" }}
      data-testid={`metric-${metric.key}`}
      title={metric.hint}
    >
      <div className="flex items-center gap-1.5">
        <span className="smp-metric-label">{metric.label}</span>
      </div>
      <div className="smp-num mt-1 text-[20px] font-semibold leading-none" style={{ color }}>
        {metric.value}
      </div>
    </div>
  );
}

const STANCE_TONE: Record<string, "up" | "down" | "flat"> = {
  利多: "up",
  利空: "down",
  中性: "flat",
};

export function EvidenceRow({ item }: { item: EvidenceCardView }) {
  const tone = STANCE_TONE[item.stance] ?? "flat";
  return (
    <div
      className="rounded-[7px] border px-3 py-2"
      style={{ borderColor: "var(--color-border)", background: "rgba(0,0,0,0.14)" }}
      data-testid={`evidence-${item.id}`}
    >
      <div className="flex items-start gap-2.5">
        <Chip tone={tone}>{item.stance}</Chip>
        <div className="min-w-0 flex-1">
          <div className="text-[12.5px]" style={{ color: "var(--color-ink)" }}>
            {item.title}
          </div>
          <p className="mt-1 text-[11.5px] leading-[17px]" style={{ color: "var(--color-ink-muted)" }}>
            {item.detail}
          </p>
        </div>
        <div className="w-[92px] shrink-0 text-right">
          <div className="text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
            {item.source}
          </div>
          <div className="smp-num text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
            {item.version} {item.date}
          </div>
        </div>
      </div>
    </div>
  );
}

export function FlameRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-[11.5px]">
      <span className="flex items-center gap-1.5" style={{ color: "var(--color-ink-sub)" }}>
        <IconFlame size={12} />
        {label}
      </span>
      <span className="smp-num" style={{ color: "var(--color-ink)" }}>
        {value}
      </span>
    </div>
  );
}

export function BookRow({ title, detail, tag }: { title: string; detail: string; tag: string }) {
  return (
    <div className="flex items-start gap-2">
      <span style={{ color: "var(--color-gold-dim)" }}>
        <IconBook size={14} />
      </span>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-[12.5px]" style={{ color: "var(--color-ink)" }}>
            {title}
          </span>
          <Chip tone="gold">{tag}</Chip>
        </div>
        <p className="mt-0.5 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
          {detail}
        </p>
      </div>
    </div>
  );
}
