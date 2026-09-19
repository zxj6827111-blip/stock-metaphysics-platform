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

import { buildZiweiChart, ENGINE_VERSION, IZTRO_VERSION } from './chart.js';
import type { ZiweiRequest } from './types.js';

const PORT = Number(process.env.ZIWEI_PORT ?? 8100);
const HOST = process.env.ZIWEI_HOST ?? '127.0.0.1';
const MAX_BODY_BYTES = 2 * 1024 * 1024;

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

    const results: unknown[] = [];
    const errors: { index: number; message: string }[] = [];
    requests.forEach((r, index) => {
      try {
        results.push(buildZiweiChart(r));
      } catch (err) {
        errors.push({ index, message: (err as Error).message });
      }
    });
    send(res, 200, { results, errors, iztroVersion: IZTRO_VERSION });
    return;
  }

  send(res, 404, { error: { code: 'NOT_FOUND', message: `未知路径: ${req.method} ${url}` } });
});

server.listen(PORT, HOST, () => {
  process.stdout.write(
    `ziwei-service listening on http://${HOST}:${PORT} (iztro ${IZTRO_VERSION})\n`,
  );
});
