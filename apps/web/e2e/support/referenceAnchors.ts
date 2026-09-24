import { readFile } from "node:fs/promises";
import path from "node:path";

/**
 * 读取 `e2e/fixtures/reference-anchors.json` 里**人工核对并冻结**的参考矩形。
 *
 * 为什么测试要读它而不是再抄一遍数字：几何门禁一旦把 742 这类值写死，
 * 就和 anchor 测量脚本各持一份真相，参考图重测时只会有一边跟着变
 * （R1 的侧栏 231px 就是这么把错误值带进实现里的）。
 */

const FIXTURE_FILE = path.resolve(process.cwd(), "e2e", "fixtures", "reference-anchors.json");

export interface AnchorRect {
  x: number | null;
  y: number | null;
  width: number | null;
  height: number | null;
  confidence?: string | null;
}

let cached: Record<string, { anchors?: Record<string, AnchorRect | null> }> | null = null;

async function loadFixture() {
  if (!cached) {
    cached = JSON.parse(await readFile(FIXTURE_FILE, "utf8")) as Record<
      string,
      { anchors?: Record<string, AnchorRect | null> }
    >;
  }
  return cached;
}

/** 取某个 anchor 的参考矩形；缺失时抛错，避免测试静默拿到 undefined 当 0。 */
export async function referenceAnchor(page: string, anchor: string): Promise<AnchorRect> {
  const fixture = await loadFixture();
  const rect = fixture[page]?.anchors?.[anchor];
  if (!rect) {
    throw new Error(`参考矩形缺失：${page}.${anchor}（fixture 里为 null 表示不可导出，测试不得臆造阈值）`);
  }
  return rect;
}

/** 取某个 anchor 的参考顶边 y；不可导出时抛错。 */
export async function referenceTop(page: string, anchor: string): Promise<number> {
  const rect = await referenceAnchor(page, anchor);
  if (typeof rect.y !== "number") {
    throw new Error(`参考顶边不可导出：${page}.${anchor}.y = ${String(rect.y)}`);
  }
  return rect.y;
}
