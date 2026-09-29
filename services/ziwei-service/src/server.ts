/**
 * 紫微排盘 HTTP 服务（部署 transport）。
 *
 * 端点
 * ----
 *   GET  /health               健康检查
 *   POST /internal/ziwei/chart 单个排盘
 *   POST /internal/ziwei/batch 批量排盘（研究流水线用）
 *
 * 只依赖 Node 内置 `http`，不引入 Web 框架：
 * 本服务的职责是**确定性排盘**，不是业务服务，减少依赖面即减少风险面。
 */

import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { Worker } from 'node:worker_threads';

import { buildZiweiChart, ENGINE_VERSION, IZTRO_VERSION } from './chart.js';
import type { ZiweiRequest } from './types.js';

const PORT = Number(process.env.ZIWEI_PORT ?? 8100);
const HOST = process.env.ZIWEI_HOST ?? '127.0.0.1';
const MAX_BODY_BYTES = 2 * 1024 * 1024;
const PARALLEL_BATCH_THRESHOLD = 16;
const MAX_BATCH_WORKERS = 4;

interface WorkerResult {
  index: number;
  result?: unknown;
  error?: string;
}

interface BatchOutput {
  results: unknown[];
  errors: { index: number; message: string }[];
}

function calculateBatchSequential(requests: ZiweiRequest[]): BatchOutput {
  const results: unknown[] = [];
  const errors: { index: number; message: string }[] = [];
  requests.forEach((request, index) => {
    try {
      results.push(buildZiweiChart(request));
    } catch (error) {
      errors.push({
        index,
        message: error instanceof Error ? error.message : String(error),
      });
    }
  });
  return { results, errors };
}

async function calculateBatch(requests: ZiweiRequest[]): Promise<BatchOutput> {
  if (requests.length < PARALLEL_BATCH_THRESHOLD) {
    return calculateBatchSequential(requests);
  }

  const workers: Worker[] = [];
  try {
    const workerCount = Math.min(MAX_BATCH_WORKERS, requests.length);
    for (let i = 0; i < workerCount; i += 1) {
      workers.push(new Worker(new URL('./worker.js', import.meta.url)));
    }

    const outputByIndex: unknown[] = new Array(requests.length);
    const errors: { index: number; message: string }[] = [];
    let nextIndex = 0;
    let completed = 0;

    await new Promise<void>((resolve, reject) => {
      const dispatch = (worker: Worker): void => {
        if (nextIndex >= requests.length) return;
        const index = nextIndex;
        nextIndex += 1;
        worker.postMessage({ index, request: requests[index] });
      };

      for (const worker of workers) {
        worker.on('error', reject);
        worker.on('message', (message: WorkerResult) => {
          if (message.error !== undefined) {
            errors.push({ index: message.index, message: message.error });
          } else {
            outputByIndex[message.index] = message.result;
          }
          completed += 1;
          if (completed === requests.length) {
            resolve();
          } else {
            dispatch(worker);
          }
        });
        dispatch(worker);
      }
    });

    // 与原先串行服务保持相同契约：成功结果按原始顺序排列，错误独立带原输入索引。
    return {
      results: outputByIndex.filter((result) => result !== undefined),
      errors: errors.sort((a, b) => a.index - b.index),
    };
  } finally {
    await Promise.all(workers.map((worker) => worker.terminate()));
  }
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks: Buffer[] = [];
    req.on('data', (chunk: Buffer) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error('请求体过大'));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

function send(res: ServerResponse, status: number, payload: unknown): void {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

const server = createServer(async (req, res) => {
  const url = req.url ?? '/';

  if (req.method === 'GET' && url.startsWith('/health')) {
    send(res, 200, { status: 'ok', engineVersion: ENGINE_VERSION, iztroVersion: IZTRO_VERSION });
    return;
  }

  if (req.method === 'POST' && (url.startsWith('/internal/ziwei/chart') ||
      url.startsWith('/internal/ziwei/batch'))) {
    let raw: string;
    try {
      raw = await readBody(req);
    } catch (err) {
      send(res, 413, { error: { code: 'PAYLOAD_TOO_LARGE', message: (err as Error).message } });
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch (err) {
      send(res, 400, { error: { code: 'INVALID_JSON', message: (err as Error).message } });
      return;
    }

    const requests: ZiweiRequest[] = Array.isArray(parsed)
      ? (parsed as ZiweiRequest[])
      : Array.isArray((parsed as { requests?: unknown })?.requests)
        ? ((parsed as { requests: ZiweiRequest[] }).requests)
        : [parsed as ZiweiRequest];

    try {
      const { results, errors } = await calculateBatch(requests);
      send(res, 200, { results, errors, iztroVersion: IZTRO_VERSION });
    } catch (error) {
      send(res, 500, {
        error: {
          code: 'WORKER_POOL_FAILED',
          message: error instanceof Error ? error.message : String(error),
        },
      });
    }
    return;
  }

  send(res, 404, { error: { code: 'NOT_FOUND', message: `未知路径: ${req.method} ${url}` } });
});

server.listen(PORT, HOST, () => {
  process.stdout.write(
    `ziwei-service listening on http://${HOST}:${PORT} (iztro ${IZTRO_VERSION})\n`,
  );
});
