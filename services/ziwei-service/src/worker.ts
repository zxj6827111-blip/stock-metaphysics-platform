import { parentPort } from 'node:worker_threads';

import { buildZiweiChart } from './chart.js';
import type { ZiweiRequest } from './types.js';

interface WorkerJob {
  index: number;
  request: ZiweiRequest;
}

const port = parentPort;
if (port === null) {
  throw new Error('紫微计算 worker 缺少 parentPort');
}

port.on('message', ({ index, request }: WorkerJob) => {
  try {
    port.postMessage({ index, result: buildZiweiChart(request) });
  } catch (error) {
    port.postMessage({
      index,
      error: error instanceof Error ? error.message : String(error),
    });
  }
});
