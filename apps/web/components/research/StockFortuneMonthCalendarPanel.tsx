"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Card, CardBody, CardHeader, Chip } from "@/components/cards/Card";
import { SectionError, SectionLoading, SectionUnavailable } from "@/components/shell/SectionState";
import { api, endpoints } from "@/lib/api";
import type {
  ApiFortuneMonthCalendarRequest,
  ApiFortuneMonthCalendarResponse,
  ApiFortuneRelationEvent,
  ApiSystemVersions,
} from "@/lib/researchV2";
import { isFixtureActive } from "@/lib/fixture";

type BirthBasis = ApiFortuneMonthCalendarRequest["birth_basis"];
type DisplayMode = "all" | "trading";
type DateMode = "month" | "custom";

export function StockFortuneMonthCalendarPanel({ stockCode }: { stockCode: string }) {
  const fixture = isFixtureActive();
  const [today] = useState(() => new Date());
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [dateMode, setDateMode] = useState<DateMode>("month");
  const [rangeStart, setRangeStart] = useState(monthBounds(today.getFullYear(), today.getMonth() + 1).start);
  const [rangeEnd, setRangeEnd] = useState(monthBounds(today.getFullYear(), today.getMonth() + 1).end);
  const [birthBasis, setBirthBasis] = useState<BirthBasis>("listing_open");
  const [displayMode, setDisplayMode] = useState<DisplayMode>("all");
  const [data, setData] = useState<ApiFortuneMonthCalendarResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSequence = useRef(0);

  const loadRange = useCallback(async (startDate: string, endDate: string, basis: BirthBasis) => {
    const rangeError = validateRange(startDate, endDate);
    if (rangeError) {
      setData(null);
      setError(rangeError);
      return;
    }
    const sequence = ++requestSequence.current;
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const versions = await api.get<ApiSystemVersions>(endpoints.systemVersions());
      const request: ApiFortuneMonthCalendarRequest = {
        stock_code: stockCode,
        start_date: startDate,
        end_date: endDate,
        birth_basis: basis,
        birth_profile_version: basis === "listing_open" ? "v2-phase4b-listing_open" : "stock-fortune-birth-v2",
        evaluation_time: "12:00:00",
        timezone: "Asia/Shanghai",
        market_session_version: "a-share-session-v1",
        config_version: versions.config_version,
      };
      const response = await api.post<ApiFortuneMonthCalendarResponse>(
        endpoints.fortuneMonthCalendarV2(), request,
      );
      if (sequence === requestSequence.current) setData(response);
    } catch (value) {
      if (sequence === requestSequence.current) {
        setError(value instanceof Error ? value.message : String(value));
      }
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, [stockCode]);

  useEffect(() => {
    const initial = monthBounds(today.getFullYear(), today.getMonth() + 1);
    setYear(today.getFullYear());
    setMonth(today.getMonth() + 1);
    setDateMode("month");
    setRangeStart(initial.start);
    setRangeEnd(initial.end);
    setBirthBasis("listing_open");
    setDisplayMode("all");
    setData(null);
    setError(null);
    if (!fixture && stockCode) void loadRange(initial.start, initial.end, "listing_open");
  }, [fixture, loadRange, stockCode, today]);

  const selectedRange = useMemo(
    () => dateMode === "month" ? monthBounds(year, month) : { start: rangeStart, end: rangeEnd },
    [dateMode, year, month, rangeStart, rangeEnd],
  );
  const activeCalendar = data?.calendar;
  const dayRows = activeCalendar?.days ?? [];
  const shownDays = displayMode === "trading"
    ? dayRows.filter((row) => row.is_trading_day === true)
    : dayRows;
  const timeline = data?.timeline;
  const pointByDate = new Map((timeline?.points ?? []).map((point) => [point.date, point]));
  const monthInfoByStart = new Map((data?.month_interpretations ?? []).map((item) => [item.segment.start_at, item]));
  const monthSegments = (activeCalendar?.months ?? []).filter((segment) => (
    segment.kind === "month" && overlaps(segment.start_at, segment.end_at, selectedRange.start, selectedRange.end)
  ));
  const currentRangeError = validateRange(selectedRange.start, selectedRange.end);
  const luck = timeline?.stable_context?.luck_cycle_context;
  const titleName = data?.stock_identity.name || activeCalendar?.stock.name || stockCode;

  const invalidateResult = () => {
    requestSequence.current += 1;
    setData(null);
    setError(null);
    setLoading(false);
  };
  const updateMonth = (nextYear: number, nextMonth: number) => {
    const bounds = monthBounds(nextYear, nextMonth);
    setYear(nextYear);
    setMonth(nextMonth);
    setRangeStart(bounds.start);
    setRangeEnd(bounds.end);
    invalidateResult();
  };
  const runQuery = () => void loadRange(selectedRange.start, selectedRange.end, birthBasis);

  return (
    <Card className="mt-3" testId="fortune-month-calendar-v2">
      <CardHeader
        title="股票月份与每日十神 · v2"
        dense
        right={<Chip tone={activeCalendar && timeline ? "gold" : loading ? "info" : "warn"}>{loading ? "查询中" : activeCalendar && timeline ? "部分结果可追溯" : data ? "部分不可用" : "待查询"}</Chip>}
      />
      <CardBody>
        <div className="mb-2 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
          {titleName}（{stockCode}）· 每日按 12:00 Asia/Shanghai 取样；CalendarEngine 原有 23:00 日界保持不变。十神、喜忌与合冲只作传统结构分类，不表示收益或交易方向。
        </div>
        {fixture ? <SectionUnavailable what="真实股票月历" reason="此页面当前处于 UI fixture 模式；移除 ?fixture=ui-reference 后才会读取本地股票档案与 v2 API，不用演示数据代替真实验收。" testId="fortune-month-fixture-unavailable" /> : null}
        <div className="grid gap-2 rounded border p-3 sm:grid-cols-2 xl:grid-cols-5" style={{ borderColor: "var(--color-border)" }} data-testid="fortune-month-controls">
          <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>日期选择
            <select className="smp-input mt-1 w-full" value={dateMode} onChange={(event) => { setDateMode(event.target.value as DateMode); invalidateResult(); }} data-testid="fortune-month-date-mode">
              <option value="month">公历月份</option><option value="custom">自定义日期范围</option>
            </select>
          </label>
          {dateMode === "month" ? <>
            <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>年份
              <select className="smp-input mt-1 w-full" value={year} onChange={(event) => updateMonth(Number(event.target.value), month)} data-testid="fortune-month-year">
                {Array.from({ length: 81 }, (_, index) => today.getFullYear() - 40 + index).map((value) => <option key={value} value={value}>{value} 年</option>)}
              </select>
            </label>
            <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>月份
              <select className="smp-input mt-1 w-full" value={month} onChange={(event) => updateMonth(year, Number(event.target.value))} data-testid="fortune-month-month">
                {Array.from({ length: 12 }, (_, index) => index + 1).map((value) => <option key={value} value={value}>{value} 月</option>)}
              </select>
            </label>
          </> : <>
            <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>开始日期
              <input className="smp-input mt-1 w-full" type="date" value={rangeStart} onChange={(event) => { setRangeStart(event.target.value); invalidateResult(); }} data-testid="fortune-month-range-start" />
            </label>
            <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>结束日期
              <input className="smp-input mt-1 w-full" type="date" value={rangeEnd} onChange={(event) => { setRangeEnd(event.target.value); invalidateResult(); }} data-testid="fortune-month-range-end" />
            </label>
          </>}
          <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>出生口径
            <select className="smp-input mt-1 w-full" value={birthBasis} onChange={(event) => { setBirthBasis(event.target.value as BirthBasis); invalidateResult(); }} data-testid="fortune-month-birth-basis">
              <option value="listing_open">上市日开盘（研究假设）</option>
              <option value="MARKET_FIRST_TRADE">行情首笔/最早观测</option>
            </select>
          </label>
          <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>明细显示
            <select className="smp-input mt-1 w-full" value={displayMode} onChange={(event) => setDisplayMode(event.target.value as DisplayMode)} data-testid="fortune-month-display-filter">
              <option value="all">全部自然日</option><option value="trading">仅已确认交易日</option>
            </select>
          </label>
          <div className="flex items-end gap-2">
            <button type="button" className="smp-btn smp-btn--primary px-4" onClick={runQuery} disabled={fixture || loading || Boolean(currentRangeError) || !stockCode} data-testid="fortune-month-run">{loading ? "查询中…" : "查询月份与日期"}</button>
          </div>
          <div className="text-[11px] sm:col-span-2 xl:col-span-4" style={{ color: "var(--color-ink-muted)" }}>
            {dateMode === "month" ? `实际查询公历范围：${selectedRange.start} ～ ${selectedRange.end}` : `自定义查询范围：${selectedRange.start} ～ ${selectedRange.end}`} · 服务端按精确节气切流月，默认返回完整自然日；“仅已确认交易日”只过滤显示。
            {currentRangeError ? <span className="ml-2" role="alert" data-testid="fortune-month-range-error">{currentRangeError}</span> : null}
          </div>
        </div>

        {loading ? <SectionLoading label="正在复用所选出生档案，计算精确节气月段、自然日十神与来源证据…" rows={4} /> : null}
        {error ? <SectionError what="股票月份与每日十神" message={error} onRetry={runQuery} testId="fortune-month-error" /> : null}

        {data ? <>
          <div className="mt-2 rounded border px-3 py-2 text-[11.5px]" style={{ borderColor: "var(--color-border)" }} data-testid="fortune-month-executed-query">
            实际执行：{data.stock_identity.name}（{data.stock_identity.symbol}）· {data.request.start_date} ～ {data.request.end_date} · 出生口径 {birthBasisLabel(data.birth_profile.birth_basis)} · 日采样 {data.request.evaluation_time} {data.request.timezone} · 显示条件 {displayMode === "all" ? "全部自然日" : "仅已确认交易日"} · 十神/关系条件：无筛选
          </div>
          <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-3" data-testid="fortune-month-birth-profile">
            <ProfileValue label="出生研究档案" value={`${birthBasisLabel(data.birth_profile.birth_basis)} · ${data.birth_profile.birth_time_precision}`} detail={`${data.birth_profile.listing_date ?? "上市日不可用"} · ${data.birth_profile.birth_datetime ?? "计算时刻不可用"} ${data.birth_profile.timezone}`} />
            <ProfileValue label="档案来源与版本" value={data.birth_profile.source.source} detail={`${data.birth_profile.source_version} · 档案 ${data.birth_profile.birth_profile_version} · 规则 ${data.birth_profile.rule_version}`} />
            <ProfileValue label="出生口径边界" value={data.birth_profile.first_trade_datetime ?? "首笔成交时刻未核实"} detail={data.birth_profile.assumptions.map((item) => item.reason).join("；") || "无额外假设"} />
          </div>
          {data.birth_profile.assumptions.length ? <div className="mt-2 rounded border p-2 text-[11.5px]" style={{ borderColor: "var(--color-border)" }} data-testid="fortune-month-birth-assumptions">{data.birth_profile.assumptions.map((item) => <div key={`${item.key}-${item.value}`}>· {item.key}：{item.value}。{item.reason} {item.impact}</div>)}</div> : null}

          <section className="mt-3 rounded border p-3" style={{ borderColor: "var(--color-border)" }} data-testid="fortune-first-day-polarity">
            <div className="flex items-center justify-between gap-2"><h3 className="text-[13px] font-semibold" style={{ color: "var(--color-ink)" }}>首日阴阳与运限 · 研究兼容假设</h3><Chip tone={data.first_day_polarity.status === "available" && luck?.availability === "available" ? "gold" : "warn"}>{data.first_day_polarity.status} / 运限 {luck?.availability ?? "不可用"}</Chip></div>
            <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              <ProfileValue label="首日阴阳与涨跌幅" value={`${data.first_day_polarity.first_day_yinyang ?? "缺失"} · 开盘至收盘 ${data.first_day_polarity.first_day_pct_chg === null ? "不可用" : `${(data.first_day_polarity.first_day_pct_chg * 100).toFixed(2)}%`}`} detail={`${data.first_day_polarity.observation_date ?? "观测日期未知"} · ${data.first_day_polarity.price_basis || "价格基准不可用"} · 交易日证据 ${data.first_day_polarity.is_trading_day === true ? "已确认" : data.first_day_polarity.is_trading_day === false ? "冲突/非交易日" : "不可用"}`} />
              <ProfileValue label="字段来源" value={data.first_day_polarity.source || "不可用"} detail={data.first_day_polarity.source_version || "来源版本缺失"} />
              <ProfileValue label="收盘后可见" value={data.first_day_polarity.visible_at ?? "时点不可用"} detail={`${data.first_day_polarity.trading_day_source || "交易日来源缺失"} · ${data.first_day_polarity.market_session_version || "市场时段版本缺失"}`} />
              <ProfileValue label="实际顺逆" value={directionLabel(luck?.direction)} detail={`兼容输入：${compatibilityLabel(luck?.compatibility_gender)}；不是股票的真实性别`} />
            </div>
            <div className="mt-2 text-[11.5px]" style={{ color: data.first_day_polarity.status === "available" ? "var(--color-ink-muted)" : "var(--color-warn)" }} data-testid="fortune-polarity-reason">{data.first_day_polarity.reason}{luck?.unavailability_reason ? ` 运限状态：${luck.unavailability_reason}` : ""}</div>
            {luck?.assumptions?.length ? <div className="mt-1 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>{luck.assumptions.map((item) => `· ${item.key}：${item.value}。${item.reason}`).join("\n")}</div> : null}
            {luck?.cycle_periods?.length ? <div className="mt-2 overflow-x-auto"><table className="smp-table min-w-[520px]" data-testid="fortune-luck-cycle-periods"><thead><tr><th>序</th><th>大运</th><th>起止年龄</th><th>起止年份</th><th>起止时刻</th></tr></thead><tbody>{luck.cycle_periods.map((period) => <tr key={`${period.cycle_index}-${period.start_at}`}><td>{period.cycle_index}</td><td>{period.ganzhi.stem}{period.ganzhi.branch}</td><td>{period.start_age} ～ {period.end_age}</td><td>{period.start_year} ～ {period.end_year}</td><td>{formatDateTime(period.start_at)} ～ {formatDateTime(period.end_at)}</td></tr>)}</tbody></table></div> : null}
          </section>

          <section className="mt-3" data-testid="fortune-month-segments">
            <div className="mb-1 flex items-center justify-between gap-2"><h3 className="text-[13px] font-semibold" style={{ color: "var(--color-ink)" }}>节气流月段与结构解释</h3><Chip tone={activeCalendar ? "gold" : "warn"}>{activeCalendar ? `${monthSegments.length} 段` : "不可用"}</Chip></div>
            {activeCalendar ? <>
              <div className="mb-1 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>月柱按十二节精确换月，不按公历每月 1 日切换。财星类别相对当前股票日主计算；这里只描述月柱天干与地支藏干。</div>
              <div className="mb-2 rounded border p-2 text-[11.5px]" style={{ borderColor: "var(--color-border)" }} data-testid="fortune-month-yongshen">
                <strong>原局喜忌依据</strong> · 日主 {activeCalendar.natal.day_master || "不可用"} · 用神 {activeCalendar.yong_shen.available ? activeCalendar.yong_shen.yong_shen.join("、") || "未列出" : "不可用"} · 喜神 {activeCalendar.yong_shen.available ? activeCalendar.yong_shen.xi_shen.join("、") || "未列出" : "不可用"} · 忌神 {activeCalendar.yong_shen.available ? activeCalendar.yong_shen.ji_shen.join("、") || "未列出" : "不可用"}。按服务端原局结果展示，不推导价格方向。
              </div>
              <div className="overflow-x-auto"><table className="smp-table min-w-[1050px]" data-testid="fortune-month-segment-table"><thead><tr><th>实际节气区间</th><th>边界</th><th>月柱</th><th>月干十神</th><th>地支藏干十神</th><th>喜忌</th><th>倾向与含义</th></tr></thead><tbody>{monthSegments.map((segment) => {
                const interpretation = monthInfoByStart.get(segment.start_at);
                return <tr key={segment.start_at} data-testid="fortune-month-segment-row"><td>{formatDateTime(segment.start_at)} ～ {formatDateTime(segment.end_at)}</td><td>{segment.boundary_jieqi} → {segment.next_boundary_jieqi}</td><td>{ganzhi(segment.ganzhi)}</td><td>{segment.stem} · {segment.stem_ten_god}</td><td>{hiddenGods(segment.branch_hidden_stems)}</td><td>{segment.verdict}</td><td className="max-w-[520px] whitespace-normal">{interpretation?.explanation ?? segment.reason}{interpretation?.wealth_star_locations.length ? <div className="mt-1">财星位置：{interpretation.wealth_star_locations.join("；")}</div> : null}{interpretation?.related_events.length ? <div className="mt-1">{interpretation.related_events.map(formatRelationEvent).join("；")}</div> : null}</td></tr>;
              })}</tbody></table></div>
            </> : <SectionUnavailable what="股票日主月段解释" reason={data.calendar_unavailability_reason || "出生档案、原局或十神服务不可用；Fortune 时间轴与首日阴阳区块仍独立显示。"} testId="fortune-month-calendar-unavailable" />}
          </section>

          <section className="mt-3" data-testid="fortune-day-details">
            <div className="mb-1 flex items-center justify-between gap-2"><h3 className="text-[13px] font-semibold" style={{ color: "var(--color-ink)" }}>每日流日十神与结构</h3><Chip tone={dayRows.length ? "gold" : "warn"}>{displayMode === "all" ? `${shownDays.length}/${activeCalendar?.natural_day_count ?? 0} 个自然日` : `${shownDays.length} 个已确认交易日 / ${dayRows.length} 个自然日`}</Chip></div>
            {activeCalendar ? dayRows.length > 0 && shownDays.length > 0 ? <div className="overflow-x-auto"><table className="smp-table min-w-[1100px]" data-testid="fortune-day-table"><thead><tr><th>日期</th><th>日柱</th><th>流日十神</th><th>藏干十神</th><th>喜忌</th><th>合冲刑害结构说明</th><th>交易日状态</th></tr></thead><tbody>{shownDays.map((row) => {
              const point = pointByDate.get(row.date);
              const events = point?.relation_events ?? [];
              const relationContextAvailable = timeline?.stable_context?.natal_context.availability === "available";
              return <tr key={row.date} data-testid="fortune-day-row" data-date={row.date}><td>{row.date} · 12:00</td><td>{ganzhi(row.ganzhi)}</td><td>{row.stem} · {row.stem_ten_god}</td><td>{hiddenGods(row.branch_hidden_stems)}</td><td>{row.verdict}</td><td className="max-w-[560px] whitespace-normal">{row.reason}{events.length ? <div className="mt-1">{events.filter((event) => event.source.context === "day").map(formatRelationEvent).join("；") || "无流日与原局关系事件"}</div> : relationContextAvailable ? "未检测到流日与原局的合冲刑害事件" : "原局关系上下文不可用，不能判定有无相关事件"}</td><td>{tradingLabel(row.is_trading_day, row.trading_calendar_source)}</td></tr>;
            })}</tbody></table></div> : <div data-testid="fortune-day-empty" className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>{dayRows.length === 0 ? "该日期范围没有可显示的每日记录。" : "所选条件下没有已确认交易日；切换到全部自然日可查看完整日期。"}</div> : <SectionUnavailable what="每日股票十神" reason={data.calendar_unavailability_reason || "日主/出生档案不可用；服务端返回的日期干支与运限状态仍独立保留。"} testId="fortune-day-calendar-unavailable" />}
          </section>
          {!timeline ? <SectionUnavailable what="Fortune 时间轴" reason={data.timeline_unavailability_reason || "时间轴服务不可用；已计算的股票十神日历继续显示。"} testId="fortune-timeline-unavailable" /> : null}
          <details className="mt-2 text-[11px]" data-testid="fortune-month-versions"><summary style={{ color: "var(--color-ink-muted)" }}>数据、规则与计算版本</summary><pre className="mt-1 max-h-[200px] overflow-auto rounded p-2" style={{ background: "rgba(255,255,255,0.03)" }}>{JSON.stringify({ resolved_versions: data.resolved_versions, calendar_versions: activeCalendar?.versions, fortune_rule_versions: timeline?.rule_versions, provenance: timeline?.provenance }, null, 2)}</pre></details>
        </> : null}
      </CardBody>
    </Card>
  );
}

function ProfileValue({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="rounded border px-2.5 py-2" style={{ borderColor: "var(--color-border)" }}><div className="smp-metric-label">{label}</div><div className="mt-1 break-all text-[12px]" style={{ color: "var(--color-ink)" }}>{value}</div><div className="mt-1 break-all text-[10.5px]" style={{ color: "var(--color-ink-muted)" }}>{detail}</div></div>;
}

function monthBounds(year: number, month: number): { start: string; end: string } {
  return { start: `${year}-${String(month).padStart(2, "0")}-01`, end: `${year}-${String(month).padStart(2, "0")}-${new Date(year, month, 0).getDate()}` };
}

function validateRange(start: string, end: string): string | null {
  if (!start || !end) return "请选择完整的开始和结束日期。";
  const first = Date.parse(`${start}T00:00:00Z`);
  const last = Date.parse(`${end}T00:00:00Z`);
  if (!Number.isFinite(first) || !Number.isFinite(last)) return "日期格式无效。";
  if (last < first) return "结束日期不得早于开始日期。";
  if ((last - first) / 86_400_000 + 1 > 730) return "一次最多查询 730 个自然日。";
  return null;
}

function overlaps(startAt: string, endAt: string, startDate: string, endDate: string): boolean {
  return endAt.slice(0, 10) >= startDate && startAt.slice(0, 10) <= endDate;
}

function formatDateTime(value: string): string {
  return value.replace("T", " ");
}

function ganzhi(value: { text?: string; stem: string; branch: string } | null | undefined): string {
  return value ? value.text || `${value.stem}${value.branch}` : "不可用";
}

function hiddenGods(items: { stem: string; ten_god: string; rank: string }[]): string {
  return items.length ? items.map((item) => `${item.stem}·${item.ten_god}${item.rank ? `（${item.rank}）` : ""}`).join("；") : "无藏干数据";
}

function tradingLabel(value: boolean | null, source: string): string {
  if (value === true) return `已确认交易日（${source}）`;
  if (value === false) return `已确认非交易日（${source}）`;
  return `未知（${source || "交易日历未覆盖"}）`;
}

function formatRelationEvent(event: ApiFortuneRelationEvent): string {
  return `${event.relation_type}：${event.source.context}/${event.source.pillar}/${event.source.component}${event.source.value} → ${event.target.context}/${event.target.pillar}/${event.target.component}${event.target.value}${event.explanation ? `（${event.explanation}）` : ""}`;
}

function birthBasisLabel(value: string): string {
  if (value === "LISTING_OPEN" || value === "listing_open") return "上市日开盘研究假设";
  if (value === "MARKET_FIRST_TRADE") return "行情首笔/最早观测";
  return value || "不可用";
}

function directionLabel(value?: string | null): string {
  if (value === "FORWARD") return "顺行";
  if (value === "REVERSE") return "逆行";
  return "不可用";
}

function compatibilityLabel(value?: string | null): string {
  const normalized = value?.toLowerCase();
  if (normalized === "male") return "男命兼容参数（研究假设）";
  if (normalized === "female") return "女命兼容参数（研究假设）";
  return "未提供兼容参数";
}
