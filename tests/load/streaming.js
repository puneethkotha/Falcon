/**
 * Streaming TTFT Load Test (chassis-level)
 *
 * guidellm owns the throughput-vs-latency frontier (see benchmarks/). k6 owns the
 * HTTP-level behavior of the Falcon chassis under load. For streaming responses,
 * http_req_waiting is the time to the first byte, which for SSE is the first token
 * frame -- i.e. TTFT as seen through Nginx and the worker. This script trends that
 * under a ramp so failover / rate-limit / breaker behavior can be observed without a
 * fixed-classification latency assumption.
 *
 * Run:  k6 run tests/load/streaming.js
 */
import http from 'k6/http';
import { check } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const ttft = new Trend('ttft_ms', true);
const successRate = new Rate('success');

export const options = {
  stages: [
    { duration: '1m', target: 20 },
    { duration: '3m', target: 20 },
    { duration: '1m', target: 0 },
  ],
  thresholds: {
    // TTFB == TTFT for a streamed response. Defended SLO on the GPU path: p95 < 500ms.
    // Loosened here because CPU/mock hosts are slower; tighten on the GPU host.
    'ttft_ms': ['p(95)<2000'],
    'http_req_failed': ['rate<0.05'],
    'success': ['rate>0.95'],
  },
};

const prompts = [
  'Summarize what a circuit breaker does in one sentence.',
  'Explain continuous batching briefly.',
  'What is time to first token?',
  'Describe PagedAttention in one line.',
];

export default function () {
  const payload = JSON.stringify({
    prompt: prompts[Math.floor(Math.random() * prompts.length)],
    max_tokens: 64,
    temperature: 0.7,
    stream: true,
  });
  const res = http.post('http://localhost/generate', payload, {
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    timeout: '120s',
  });

  const ok = check(res, {
    'status is 200': (r) => r.status === 200,
    'is event-stream': (r) => (r.headers['Content-Type'] || '').includes('text/event-stream'),
    'has data frames': (r) => typeof r.body === 'string' && r.body.includes('data:'),
  });

  // http_req_waiting is time-to-first-byte == TTFT for SSE.
  ttft.add(res.timings.waiting);
  successRate.add(ok);
}
