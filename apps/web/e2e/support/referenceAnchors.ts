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

type FixtureFile = Record<
  string,
  {
    anchors?: Record<string, AnchorRect | null>;
    controlColumns?: { columns: ReferenceGridColumn[] };
  }
>;

let cached: FixtureFile | null = null;

/** 对照行的一列参考边界（V3-A.1 从已冻结的 controlRow note 改写而来）。 */
export interface ReferenceGridColumn {
  index: number;
  title: string;
  x: number;
  width: number;
}

async function loadFixture(): Promise<FixtureFile> {
  if (!cached) {
    cached = JSON.parse(await readFile(FIXTURE_FILE, "utf8")) as FixtureFile;
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

/**
 * 取对照行的**逐列**参考边界。
 *
 * 为什么单独一个读取口：整行外框对齐了不代表内部结构对齐 ——
 * V3-A 就是两张 50/50 的卡把 controlRow 的宽高做到了 ±12，
 * 而参考图是四张近似等宽的对照卡。缺这一份数据，测试就只能测外框。
 */
export async function referenceControlColumns(page: string): Promise<ReferenceGridColumn[]> {
  const fixture = await loadFixture();
  const cols = fixture[page]?.controlColumns?.columns;
  if (!cols?.length) {
    throw new Error(`对照行列边界缺失：${page}.controlColumns（不得臆造阈值）`);
  }
  return cols;
}
