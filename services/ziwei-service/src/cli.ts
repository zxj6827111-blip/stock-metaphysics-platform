/**
 * 批量排盘 CLI —— Python Adapter 的默认 transport。
 *
 * 输入（stdin，UTF-8 JSON）：`{ "requests": [ZiweiRequest, ...] }`
 * 或直接 `[ZiweiRequest, ...]` 或单个 `ZiweiRequest`。
 * 输出（stdout，UTF-8 JSON）：`{ "results": [...], "errors": [{index,message}], "iztroVersion": "..." }`
 *
 * 为什么用 stdin/stdout 而不是 HTTP 作为默认：
 * 研究流水线需要批量排盘（数十只股票 × 多个 as_of × 2 个 variant）。
 * 子进程 + 单次批量调用既避免常驻服务，也避免 N 次进程启动开销；
 * HTTP 服务（`server.ts`）保留给 Docker / 生产部署。
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { buildZiweiChart, IZTRO_VERSION } from './chart.js';
import type { ZiweiRequest } from './types.js';

function readStdin(): string {
  try {
    // 同步读取 fd 0：CLI 是一次性进程，无需异步。
    return readFileSync(0, 'utf8');
  } catch {
    return '';
  }
}

function parseRequests(raw: string): ZiweiRequest[] {
  const trimmed = raw.trim();
  if (!trimmed) {
    return [];
  }
  const parsed = JSON.parse(trimmed);
  if (Array.isArray(parsed)) {
    return parsed as ZiweiRequest[];
  }
  if (parsed && Array.isArray((parsed as { requests?: unknown }).requests)) {
    return (parsed as { requests: ZiweiRequest[] }).requests;
  }
  return [parsed as ZiweiRequest];
}

export function runBatch(rawInput: string): string {
  let requests: ZiweiRequest[];
  try {
    requests = parseRequests(rawInput);
  } catch (err) {
    return JSON.stringify({
      results: [],
      errors: [{ index: -1, message: `无法解析输入 JSON: ${(err as Error).message}` }],
      iztroVersion: IZTRO_VERSION,
    });
  }

  const results: unknown[] = [];
  const errors: { index: number; message: string }[] = [];
  requests.forEach((req, index) => {
    try {
      results.push(buildZiweiChart(req));
    } catch (err) {
      errors.push({ index, message: (err as Error).message });
    }
  });
  return JSON.stringify({ results, errors, iztroVersion: IZTRO_VERSION });
}

function main(): void {
  const args = process.argv.slice(2);
  if (args.includes('--smoke')) {
    const out = runBatch(
      JSON.stringify([
        {
          solarDate: '2001-08-27',
          timeIndex: 5,
          variantMode: 'variant_forward',
          asOfDate: '2024-11-15',
          asOfTimeIndex: 5,
        },
      ]),
    );
    const parsed = JSON.parse(out);
    const first = parsed.results?.[0];
    process.stdout.write(
      `iztro=${parsed.iztroVersion} errors=${parsed.errors.length} ` +
        `palaces=${first?.palaces?.length ?? 0} fiveElements=${first?.fiveElementsClass ?? '-'} ` +
        `soul=${first?.soul ?? '-'}\n`,
    );
    process.exit(parsed.errors.length === 0 && first ? 0 : 1);
  }
  if (args.includes('--version')) {
    process.stdout.write(`${IZTRO_VERSION}\n`);
    process.exit(0);
  }
  process.stdout.write(runBatch(readStdin()));
}

// 仅在被直接执行时跑 main（被 server.ts / 测试 import 时不执行）。
const thisFile = fileURLToPath(import.meta.url);
if (process.argv[1] && resolve(process.argv[1]) === resolve(thisFile)) {
  main();
}

export { dirname };
