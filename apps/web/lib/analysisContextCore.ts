/**
 * 分析上下文查询串的**纯函数核心**（跨页面导航与跳转链接的唯一来源）。
 *
 * 为什么单独一个文件
 * ------------------
 * `lib/analysisContext.ts` 里的客户端 hook 需要 `next/navigation`；
 * 而 e2e 测试（`e2e/ui-parity-r1.spec.ts`）需要在 **Node 进程**里验证
 * 下面这组纯函数 —— 若从带 `next/navigation` 的模块导入，等于把整个
 * Next 客户端运行时拖进 Playwright 的 Node 侧，跨平台行为不可控。
 * 纯逻辑因此独立成这个**零依赖**模块：页面侧经 `lib/analysisContext.ts`
 * 再导出使用，测试直接导入本文件，两侧测的是同一份实现。
 *
 * 为什么这组规则只写一份：一次分析由 `code + variant + birthBasis + horizon + asOf`
 * 共同确定（见 `lib/analysisStore.ts` 的 `keyOf`）。跳转链接如果只带 fixture，
 * 落地页就会静默回落到默认假设 —— 用户在两页看到的是**两次不同的分析**。
 * 把"哪些参数属于分析身份"写在一处，页面与侧栏才不会各记一份、各漏几个。
 */

/** 属于分析身份的 URL 参数（顺序固定，保证同一上下文生成同一串）。 */
export const ANALYSIS_CONTEXT_PARAMS = ["fixture", "birthBasis", "horizon", "asOf"] as const;

/** 由查询参数得到 `?a=b` 形式的后缀；无参数时返回空串。 */
export function analysisContextSuffix(
  params: Pick<URLSearchParams, "get"> | null | undefined,
): string {
  if (!params) return "";
  const q = new URLSearchParams();
  for (const name of ANALYSIS_CONTEXT_PARAMS) {
    const value = params.get(name);
    if (value) q.set(name, value);
  }
  return q.size ? `?${q.toString()}` : "";
}

/**
 * 给一个已有链接补齐分析上下文。
 *
 * 演示夹具里的 `detailHref` 是**冻结时**拼好的，只带当时那份样本的上下文；
 * 直接拿来渲染，就会出现"URL 选了 60d，点进详情却回到默认窗口"。
 *
 * 优先级（不可反过来）：**当前 URL 上的上下文覆盖链接里的旧值**。
 * 链接里的值是"上一次点进来时"的快照，当前 URL 才是用户此刻的选择；
 * 若让链接优先，用户在 URL 上改的假设就会在跳转那一刻被静默撤销。
 * 当前 URL 上不存在该参数时，链接自己带的值原样保留。
 * 与分析上下文无关的查询参数（如 `?date=`）一律不动。
 */
export function withAnalysisContext(href: string, params: URLSearchParams | null): string {
  if (!params || !href) return href;
  const [path, query = ""] = href.split("?");
  const q = new URLSearchParams(query);
  for (const name of ANALYSIS_CONTEXT_PARAMS) {
    const value = params.get(name);
    if (value) q.set(name, value);
  }
  const s = q.toString();
  return s ? `${path}?${s}` : path;
}
