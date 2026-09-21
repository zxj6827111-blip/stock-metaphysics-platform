/**
 * 文本格式化小工具。
 *
 * 为什么需要它：后端的**面向研究者的说明字段**（methodology / explanation_cn /
 * key_findings / 免责声明）里用 `**强调**` 标出限定词（例如
 * "**不是净值、不是累计投资收益**"）。这些字段是给 Markdown 报告与
 * 终端日志用的，直接放进 JSX 会渲染成裸星号 —— 读起来像排版错误，
 * 而且会削弱那句限定语的作用。
 *
 * 这里统一把它们转成纯文本（由调用方决定用不用 <strong> 包裹），
 * **不做 HTML 注入**（AGENTS.md §13：不把后端字符串当 HTML 渲染）。
 */

export function stripMdEmphasis(text: string | null | undefined): string {
  if (!text) return "";
  return text.replace(/\*\*(.+?)\*\*/g, "$1");
}

export function stripMdEmphasisDeep(value: unknown): unknown {
  if (typeof value === "string") return stripMdEmphasis(value);
  if (Array.isArray(value)) return value.map(stripMdEmphasisDeep);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, stripMdEmphasisDeep(v)]),
    );
  }
  return value;
}
