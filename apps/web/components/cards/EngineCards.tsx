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
import { Medallion } from "./Medallion";

const ENGINE_ICON: Record<string, React.ComponentType<{ size?: number }>> = {
  bazi: IconTaiji,
  ziwei: IconStar4,
  huangli: IconGrid,
  backtest: IconGauge,
};

// 三张首行卡（EngineScoreCard / ConsensusCard / ConflictCard）的 min-h 取 140px：
// 参考图 02 首行整排高 197px，本轮卡片头 + 内边距固定后，148px 会让整排到 206.4px（+9.4），
// 而这 9.4px 会把第二行整体下推、使历史验证摘要卡顶超出参考的 742±12。
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
    <Card className="flex min-h-[140px] flex-col p-2" testId={`engine-card-${engine.engine}`}>
      {/* 引擎徽记用 Medallion（44px 圆章）而不是 24px 小圆点：
          参考图 02 的三张引擎卡靠这三枚大圆章区分引擎身份，
          24px 的点在 1672px 宽的终端里既看不清也撑不住卡片的视觉重量。 */}
      <div className="flex items-center gap-2.5">
        <Medallion
          icon={<Icon size={20} />}
          tone={
            engine.engine === "ziwei"
              ? "conflict"
              : engine.engine === "huangli"
                ? "down"
                : engine.engine === "backtest"
                  ? "info"
                  : "gold"
          }
          size={34}
          title={`${engine.displayName}引擎`}
          testId={`engine-medallion-${engine.engine}`}
        />
        <span
          className="text-[14.5px] font-semibold"
          style={{ color: "var(--color-ink)", fontFamily: "var(--font-serif-cn)" }}
        >
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
          <div className="mt-1 flex items-end gap-1">
            <span
              className="smp-num smp-key-number leading-none"
              style={{ color: engine.direction > 0 ? "var(--color-up)" : engine.direction < 0 ? "var(--color-down)" : "var(--color-ink)" }}
              data-testid={`engine-score-${engine.engine}`}
            >
              {engine.score.toFixed(0)}
            </span>
            <span className="pb-[2px] text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
              /100
            </span>
          </div>

          <div className="mt-0.5">
            <div className="flex items-center gap-1.5">
              <span className="smp-metric-label">信心</span>
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

          <p className="mt-0.5 text-[11.5px] leading-[16px] line-clamp-1" style={{ color: "var(--color-ink-muted)" }}>
            {engine.summary}
          </p>

          <div className="mt-auto flex items-center gap-2 whitespace-nowrap pt-1 text-[11.5px]">
            <span className="flex items-center gap-0.5">
              <span style={{ color: "var(--color-ink-muted)" }}>正向</span>
              <span className="smp-num" style={{ color: "var(--color-up)" }}>
                {engine.positiveCount}
              </span>
            </span>
            <span className="flex items-center gap-0.5">
              <span style={{ color: "var(--color-ink-muted)" }}>负向</span>
              <span className="smp-num" style={{ color: "var(--color-down)" }}>
                {engine.negativeCount}
              </span>
            </span>
            <Link
              href={engine.detailHref}
              className="ml-auto"
              style={{ color: "var(--color-ink-muted)" }}
              data-testid={`engine-detail-${engine.engine}`}
            >
              详情→
            </Link>
          </div>
        </>
      ) : (
        <div className="mt-2 flex-1">
          <div className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
            该引擎当前不可用
          </div>
          <p className="mt-1 text-[11px] leading-[16px]" style={{ color: "var(--color-ink-faint)" }}>
            {engine.unavailableReason ??
              "引擎未启用或计算失败。本卡片不会以 0 分参与任何聚合。"}
          </p>
        </div>
      )}
    </Card>
  );
}

export function ConsensusCard({ consensus }: { consensus: ConsensusView | null }) {
  if (!consensus) {
    return (
      <Card className="flex min-h-[140px] flex-col p-2.5" testId="consensus-card">
        <div className="flex items-center gap-1.5">
          <span className="smp-card-title-icon">
            <IconTarget size={14} />
          </span>
          <span className="text-[13px] font-medium">多模型共识</span>
        </div>
        <div className="my-auto py-2 text-center">
          <div className="text-[12px] font-medium" style={{ color: "var(--color-ink-muted)" }}>
            共识服务未产生结论
          </div>
          <p className="mt-1 text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
            模型输入存在缺失或计算降级，系统不提供虚构共识。
          </p>
        </div>
      </Card>
    );
  }

  const tone =
    consensus.label.includes("POSITIVE")
      ? "up"
      : consensus.label.includes("NEGATIVE")
        ? "down"
        : consensus.label === "MIXED"
          ? "conflict"
          : "flat";

  return (
    <Card className="flex min-h-[140px] flex-col p-2.5" testId="consensus-card">
      <div className="flex items-center gap-1.5">
        <span className="smp-card-title-icon">
          <IconTarget size={14} />
        </span>
        <span className="text-[13px] font-medium">多模型共识</span>
        {consensus.displayOnly ? (
          <span
            className="ml-auto text-[10px]"
            style={{ color: "var(--color-ink-faint)" }}
            title="Phase 1 未实现正式 ConsensusEngine，此处仅为展示层聚合"
          >
            展示层
          </span>
        ) : null}
      </div>

      <div className="mt-1.5 flex gap-2.5">
        {/* 共识徽记 */}
        <div className="flex w-[88px] shrink-0 items-center justify-center">
          <div
            className="flex h-[82px] w-[82px] flex-col items-center justify-center rounded-full text-center"
            style={{
              border: `1px solid ${tone === "up" ? "var(--color-up-dim)" : tone === "down" ? "var(--color-down-dim)" : "var(--color-border-strong)"}`,
              background:
                tone === "up"
                  ? "radial-gradient(circle, rgba(232,88,90,0.22), rgba(232,88,90,0.03) 70%)"
                  : tone === "down"
                    ? "radial-gradient(circle, rgba(79,211,155,0.22), rgba(79,211,155,0.03) 70%)"
                    : "radial-gradient(circle, rgba(124,143,163,0.2), rgba(124,143,163,0.03) 70%)",
              boxShadow: "0 0 20px rgba(232,88,90,0.10)",
            }}
            data-testid="consensus-badge"
          >
            <span
              className="text-[15px] font-semibold leading-tight"
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
          <div className="space-y-1">
            {consensus.directions.map((d) => (
              <div key={d.engine} className="flex items-center gap-1.5 text-[11px]">
                <span className="w-[56px]" style={{ color: "var(--color-ink-sub)" }}>
                  {d.displayName}
                </span>
                <DirectionMark direction={d.direction} size={11} />
                <span className="smp-num" style={{ color: "var(--color-ink-muted)" }}>
                  {d.direction > 0 ? "+" : d.direction < 0 ? "−" : "0"}
                </span>
              </div>
            ))}
            {consensus.unavailableEngines.map((e) => (
              <div key={e} className="flex items-center gap-1.5 text-[11px]">
                <span className="w-[56px]" style={{ color: "var(--color-ink-faint)" }}>
                  {e}
                </span>
                <span className="text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
                  未启用
                </span>
              </div>
            ))}
          </div>

          <div className="mt-1.5 space-y-0.5 border-t pt-1 text-[10.5px]" style={{ borderColor: "var(--color-border)" }}>
            <MetaRow label="一致性" value={consensus.agreement} />
            <MetaRow label="历史验证" value={consensus.historicalValidity} />
            <MetaRow label="数据质量" value={consensus.dataQuality} />
          </div>
        </div>
      </div>

      <p
        className="mt-auto pt-1 text-center text-[10.5px] tracking-[0.06em]"
        style={{ color: "var(--color-ink-muted)" }}
      >
        {consensus.note}
      </p>
    </Card>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span style={{ color: "var(--color-ink-muted)" }}>{label}：</span>
      <span style={{ color: "var(--color-ink)" }}>{value}</span>
    </div>
  );
}

export function ConflictCard({ conflict }: { conflict: ConflictView | null }) {
  if (!conflict) {
    return (
      <Card className="flex min-h-[140px] flex-col p-2.5" testId="conflict-card">
        <div className="flex items-center gap-1.5">
          <span className="smp-card-title-icon">
            <IconWarning size={14} />
          </span>
          <span className="text-[13px] font-medium">模型分歧监测</span>
        </div>
        <div className="my-auto py-2 text-center">
          <div className="text-[12px] font-medium" style={{ color: "var(--color-ink-muted)" }}>
            分歧检测未产生结果
          </div>
          <p className="mt-1 text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
            冲突检测服务未返回，系统不假定一致或冲突。
          </p>
        </div>
      </Card>
    );
  }

  if (!conflict.hasConflict) {
    return (
      <Card className="flex min-h-[140px] flex-col p-2.5" testId="conflict-card">
        <div className="flex items-center gap-1.5">
          <span className="smp-card-title-icon">
            <IconWarning size={14} />
          </span>
          <span className="text-[13px] font-medium">模型分歧监测</span>
        </div>
        <div className="mt-3 flex flex-col items-center justify-center">
          <span
            className="flex h-10 w-10 items-center justify-center rounded-full"
            style={{
              color: "var(--color-down)",
              border: "1px solid rgba(79,211,155,0.5)",
              background: "rgba(79,211,155,0.1)",
            }}
          >
            <IconCheck size={20} />
          </span>
          <div className="mt-1.5 text-[13px]" style={{ color: "var(--color-ink)" }}>
            {conflict.headline}
          </div>
        </div>
        <p
          className="mt-auto pt-2 text-center text-[10.5px] leading-[15px]"
          style={{ color: "var(--color-ink-muted)" }}
        >
          各模型结论趋于一致，未发现显著冲突。
        </p>
      </Card>
    );
  }

  return (
    <Card className="flex min-h-[140px] flex-col p-2.5" testId="conflict-card">
      <div className="flex items-center gap-1.5">
        <span style={{ color: "var(--color-conflict)" }}>
          <IconWarning size={14} />
        </span>
        <span className="text-[13px] font-medium">⚠ 模型存在明显分歧</span>
      </div>
      <div className="mt-2 space-y-1">
        {conflict.reasons.map((r, i) => (
          <div key={i} className="text-[11px] leading-[16px]">
            <span style={{ color: "var(--color-ink)" }}>{r.engine}：{r.direction}</span>
            <br />
            <span style={{ color: "var(--color-ink-muted)" }}>{r.text}</span>
          </div>
        ))}
      </div>
      <p className="mt-auto pt-1 text-[10.5px]" style={{ color: "var(--color-ink-muted)" }}>
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
    <Card testId="data-quality-card" anchor="data-quality">
      {/* 这里此前挂着一个「查看详情」按钮，但它既没有 onClick 也没有跳转目标，
          点下去没有任何反应 —— 研究终端里的假按钮等于虚报能力，故直接不渲染。
          本卡的可核对信息（评级依据 / 引擎版本 / 风险提示）已全部在卡内展示。 */}
      <CardHeader icon={<IconCheck size={14} />} title="数据质量与风险" />
      {/* 风险摘要前置：风险必须比"质量指标"更早被读到（复核任务书 §P2） */}
      <div
        className="mx-3.5 mb-2 flex items-start gap-2 rounded-[6px] border px-3 py-2 text-[11px]"
        style={{
          borderColor: "rgba(224,164,88,0.36)",
          background: "rgba(224,164,88,0.08)",
          color: "var(--color-warn)",
        }}
        data-testid="risk-summary"
      >
        <span className="mt-[1px]">
          <IconWarning size={13} />
        </span>
        <span>
          <span className="font-semibold">风险提示：</span>
          {quality.riskNote}
          {/* 后端登记的质量说明不止一条时，其余必须可展开 —— 
              只渲染 notes[0] 会把真实风险静默丢掉。 */}
          {(quality.riskNotes?.length ?? 0) > 1 ? (
            <details className="mt-1" data-testid="risk-notes-more">
              <summary className="cursor-pointer text-[11px] underline decoration-dotted">
                其它 {quality.riskNotes!.length - 1} 条数据质量说明
              </summary>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {quality.riskNotes!.slice(1).map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </span>
      </div>
      <div className="flex gap-3.5 px-3.5 pb-3">
        <div className="flex w-[104px] shrink-0 flex-col items-center justify-center">
          <div
            className="flex h-[76px] w-[76px] flex-col items-center justify-center rounded-full"
            style={{
              border: `2px solid ${gradeTone}`,
              boxShadow: `0 0 22px ${gradeTone}33`,
              background: "radial-gradient(circle, rgba(79,211,155,0.10), transparent 70%)",
            }}
          >
            <span className="smp-num text-[30px] font-semibold leading-none" style={{ color: gradeTone }}>
              {quality.grade}
            </span>
          </div>
          <div className="mt-1.5 text-center">
            <div className="text-[12.5px]" style={{ color: "var(--color-ink)" }}>
              {quality.title}
            </div>
            <div className="text-[12.5px]" style={{ color: gradeTone }}>
              {quality.subtitle}
            </div>
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
            {quality.items.map((it) => (
              <div
                key={it.label}
                className="flex items-center gap-1.5 text-[11.5px]"
                data-testid={`data-quality-item-${it.label}`}
              >
                {/* 勾只属于"已核对"。warn / bad 挂绿勾 = 把没证明的事画成证明过。 */}
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
                  {it.state === "ok" ? <IconCheck size={12} /> : <IconWarning size={12} />}
                </span>
                <span style={{ color: "var(--color-ink-sub)" }}>{it.label}</span>
                <span className="ml-auto" style={{ color: "var(--color-ink)" }}>
                  {it.value}
                </span>
              </div>
            ))}
          </div>
          <div className="smp-divider my-2" />
          {/* 这里原来固定写着「数据完整 · 来源可靠 · 计算一致」——
              一句与上面四项无关的总括性保证，任何一项是 warn 时它都是假话，故删除。
              改为如实说明这些结论各自的来源。 */}
          <p className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
            以上四项分别来自本次分析的出生档案、版本戳与古籍检索结果；未回传的字段显示「未提供 / 未验证」。
          </p>
        </div>
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
      <div className="smp-num smp-key-number--sm mt-1 leading-none" style={{ color }}>
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
      className="rounded-[7px] border px-2.5 py-1"
      style={{ borderColor: "var(--color-border)", background: "rgba(0,0,0,0.14)" }}
      data-testid={`evidence-${item.id}`}
    >
      <div className="flex items-start gap-2.5">
        <Chip tone={tone}>{item.stance}</Chip>
        <div className="min-w-0 flex-1">
          <div className="text-[12px] leading-[16px]" style={{ color: "var(--color-ink)" }}>
            {item.title}
          </div>
          <p className="mt-0 text-[11px] leading-[15px]" style={{ color: "var(--color-ink-muted)" }}>
            {item.detail}
          </p>
        </div>
        {/* 来源列必须**两行放完**：版本+日期一旦折行，行高就被右列顶到 45px，
            五条证据会把右卡撑到 365px（参考 278px），整列第三行整体下移。
            所以这里用 9px + nowrap 把 "v1.2.0 2024-11-14" 压回一行。 */}
        <div className="w-[92px] shrink-0 text-right">
          <div className="text-[10px] leading-[15px]" style={{ color: "var(--color-ink-faint)" }}>
            {item.source}
          </div>
          <div
            className="smp-num whitespace-nowrap text-[9px] leading-[13px]"
            style={{ color: "var(--color-ink-faint)" }}
          >
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

/**
 * 古籍书影缩略图（纯 SVG，无外部图片资源）。
 *
 * 为什么画而不是放图：AGENTS.md §9.13 禁止把参考图当图片贴上去，
 * 而 book_artifact 里也没有封面文件位。颜色由书名做确定性散列得出
 * （同一本书每次渲染同色，不同书不同色），只承担"这是哪一本"的视觉区分，
 * **不承载任何吉凶/强弱语义**。
 */
export function BookCover({ title, size = 44 }: { title: string; size?: number }) {
  let h = 0;
  for (let i = 0; i < title.length; i += 1) h = (h * 31 + title.charCodeAt(i)) % 360;
  const hue = h;
  const h2 = (hue + 26) % 360;
  const w = Math.round(size * 0.72);
  return (
    <svg
      width={w}
      height={size}
      viewBox="0 0 30 42"
      aria-hidden="true"
      style={{ flexShrink: 0, borderRadius: 2 }}
      data-testid="book-cover"
    >
      <defs>
        <linearGradient id={`bc-${hue}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={`hsl(${hue} 34% 26%)`} />
          <stop offset="100%" stopColor={`hsl(${h2} 30% 15%)`} />
        </linearGradient>
      </defs>
      <rect x="0.5" y="0.5" width="29" height="41" rx="1.5" fill={`url(#bc-${hue})`} stroke={`hsl(${hue} 40% 52%)`} strokeWidth="0.8" />
      {/* 书脊 */}
      <rect x="0.5" y="0.5" width="3.4" height="41" fill={`hsl(${hue} 30% 20%)`} opacity="0.85" />
      {/* 题签框（古籍线描的"竖排书名框"） */}
      <rect x="9" y="6" width="15" height="30" rx="1" fill="none" stroke={`hsl(${hue} 45% 62%)`} strokeWidth="0.9" opacity="0.9" />
      {[12, 17.5, 23, 28.5].map((y) => (
        <line
          key={y}
          x1="12.5"
          y1={y}
          x2="20.5"
          y2={y}
          stroke={`hsl(${hue} 45% 66%)`}
          strokeWidth="1.1"
          strokeLinecap="round"
          opacity="0.85"
        />
      ))}
    </svg>
  );
}

export function BookRow({ title, detail, tag }: { title: string; detail: string; tag: string }) {
  return (
    <div className="flex items-start gap-2.5" data-testid="book-row">
      <BookCover title={title} />
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
