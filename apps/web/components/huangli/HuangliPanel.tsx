"use client";

/**
 * HuangliPanel —— 黄历 / 日课展示。
 *
 * 必须把「传统黄历数据」与「股票研究映射」分开展示（uiux_spec §19）：
 *  - 上层：公历/农历/干支/节气/生肖/纳音/建除/十二神/黄黑道/冲煞/彭祖百忌
 *  - 下层：与股票原局的关系（由后端 H_DAY_* 因子给出，不在前端计算）
 */

import type { FactorRowView } from "@/lib/types";
import { Card, CardHeader, Chip } from "../cards/Card";
import { IconCalendar, IconDiamond } from "../shell/Icons";

export interface HuangliField {
  label: string;
  value: string;
  tone?: "gold" | "up" | "down" | "flat";
}

export function HuangliPanel({
  primary,
  fields,
  relationFactors,
}: {
  primary: { solar: string; lunar: string; ganzhi: string; jieqi: string };
  fields: HuangliField[];
  relationFactors: FactorRowView[];
}) {
  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
      <Card testId="huangli-primary">
        <CardHeader icon={<IconCalendar size={14} />} title="当日日课" />
        <div className="p-4">
          <div
            className="rounded-[8px] border px-4 py-3"
            style={{
              borderColor: "var(--color-gold-dim)",
              background: "linear-gradient(180deg, rgba(212,184,122,0.10), rgba(212,184,122,0.02))",
            }}
          >
            <div className="text-[22px] font-semibold tracking-[0.12em]" style={{ color: "var(--color-gold-strong)" }}>
              {primary.ganzhi}
            </div>
            <div className="mt-1 text-[12.5px]" style={{ color: "var(--color-ink-sub)" }}>
              {primary.solar}
            </div>
            <div className="text-[12.5px]" style={{ color: "var(--color-ink-sub)" }}>
              {primary.lunar}
            </div>
            <div className="mt-2">
              <Chip tone="gold">节气：{primary.jieqi || "—"}</Chip>
            </div>
          </div>
        </div>
      </Card>

      <Card className="xl:col-span-2" testId="huangli-fields">
        <CardHeader icon={<IconDiamond size={14} />} title="传统黄历字段" />
        <div className="grid grid-cols-2 gap-x-6 gap-y-0 px-4 py-2 md:grid-cols-3">
          {fields.map((f) => (
            <div
              key={f.label}
              className="flex items-center justify-between border-b py-2"
              style={{ borderColor: "rgba(30,52,68,0.55)" }}
            >
              <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                {f.label}
              </span>
              <span
                className="text-[12.5px]"
                style={{
                  color:
                    f.tone === "gold"
                      ? "var(--color-gold)"
                      : f.tone === "up"
                        ? "var(--color-up)"
                        : f.tone === "down"
                          ? "var(--color-down)"
                          : "var(--color-ink)",
                }}
              >
                {f.value}
              </span>
            </div>
          ))}
        </div>
      </Card>

      <Card className="xl:col-span-3" testId="huangli-relations">
        <CardHeader
          icon={<IconDiamond size={14} />}
          title="与股票原局的关系（研究映射）"
          right={
            <span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
              以下为 H_DAY_* 因子，属于研究映射，不是传统黄历的说法
            </span>
          }
        />
        <div className="grid grid-cols-1 gap-x-6 px-4 py-2 md:grid-cols-2">
          {relationFactors.length === 0 ? (
            <div className="py-4 text-center text-[12px]" style={{ color: "var(--color-ink-faint)" }}>
              暂无与原局的显著关系（或该股尚未完成分析）
            </div>
          ) : (
            relationFactors.map((f) => (
              <div
                key={f.factorId}
                className="flex items-start gap-2.5 border-b py-2"
                style={{ borderColor: "rgba(30,52,68,0.55)" }}
              >
                <span
                  className="smp-num mt-[2px] w-[104px] shrink-0 text-[11.5px]"
                  style={{ color: "var(--color-ink-sub)" }}
                >
                  {f.factorId}
                </span>
                <span className="min-w-0 flex-1 text-[12px] leading-[18px]" style={{ color: "var(--color-ink)" }}>
                  {f.explanation}
                </span>
                <Chip tone={f.direction > 0 ? "up" : f.direction < 0 ? "down" : "flat"}>
                  {f.direction > 0 ? "+1" : f.direction < 0 ? "-1" : "0"}
                </Chip>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}
