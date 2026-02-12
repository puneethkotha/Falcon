/**
 * Soak Load Test
 * 
 * Purpose: Test system stability over extended period
 * VUs: 100 concurrent users
 * Duration: 10 minutes
 * 
 * Looks for: memory leaks, connection pool exhaustion, degradation
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

const errorRate = new Rate('errors');
const successRate = new Rate('success');
const latencyTrend = new Trend('latency_trend');
const timeouts = new Counter('timeouts');

export const options = {
  stages: [
    { duration: '1m', target: 100 },    // Ramp up
    { duration: '8m', target: 100 },    // Sustain for 8 minutes
    { duration: '1m', target: 0 },      // Ramp down
  ],
  thresholds: {
    http_req_duration: [
      'p(95)<2000',                     // p95 should stay under 2s
      'p(99)<5000',                     // p99 should stay under 5s
    ],
    http_req_failed: ['rate<0.05'],
    errors: ['rate<0.05'],
    latency_trend: ['p(95)<2000'],      // Track latency degradation
  },
};

const texts = [
  'This product is absolutely amazing! Best purchase ever!',
  'Terrible quality, very disappointed with this',
  'It is okay, nothing special about it',
  'Fantastic service and great quality',
  'Worst experience I have ever had',
  'Pretty good, meets expectations',
  'Outstanding performance, highly recommended',
  'Poor quality, not worth the money',
  'Average product, nothing to complain about',
  'Excellent value for money',
];

export default function () {
  const text = texts[Math.floor(Math.random() * texts.length)];
  
  const payload = JSON.stringify({ text });
  const params = {
    headers: { 'Content-Type': 'application/json' },
    timeout: '60s',
  };
  
  const response = http.post('http://localhost/infer', payload, params);
  
  // Track latency over time
  if (response.timings && response.timings.duration) {
    latencyTrend.add(response.timings.duration);
  }
  
  // Track timeouts
  if (response.status === 0) {
    timeouts.add(1);
  }
  
  const success = check(response, {
    'status is 200': (r) => r.status === 200,
    'has prediction': (r) => {
      try {
        return JSON.parse(r.body).prediction !== undefined;
      } catch (e) {
        return false;
      }
    },
    'no timeout': (r) => r.status !== 0,
    'latency stable': (r) => r.timings.duration < 5000,
  });
  
  successRate.add(success);
  errorRate.add(!success);
  
  sleep(0.5 + Math.random() * 1);
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data),
    'tests/load/results/soak-summary.json': JSON.stringify(data),
  };
}

function textSummary(data) {
  const metrics = data.metrics;
  let summary = '\n✓ Soak Load Test Complete\n\n';
  
  if (metrics.http_reqs) {
    summary += `Total Requests: ${metrics.http_reqs.values.count}\n`;
  }
  
  if (metrics.http_req_duration) {
    summary += `Request Duration:\n`;
    summary += `  avg: ${metrics.http_req_duration.values.avg.toFixed(2)}ms\n`;
    summary += `  min: ${metrics.http_req_duration.values.min.toFixed(2)}ms\n`;
    summary += `  max: ${metrics.http_req_duration.values.max.toFixed(2)}ms\n`;
    summary += `  p95: ${metrics.http_req_duration.values['p(95)'].toFixed(2)}ms\n`;
    summary += `  p99: ${metrics.http_req_duration.values['p(99)'].toFixed(2)}ms\n`;
  }
  
  if (metrics.http_req_failed) {
    summary += `Error Rate: ${(metrics.http_req_failed.values.rate * 100).toFixed(2)}%\n`;
  }
  
  if (metrics.timeouts) {
    summary += `Timeouts: ${metrics.timeouts.values.count}\n`;
  }
  
  if (metrics.latency_trend) {
    summary += `\nLatency Stability:\n`;
    summary += `  p50: ${metrics.latency_trend.values['p(50)'].toFixed(2)}ms\n`;
    summary += `  p95: ${metrics.latency_trend.values['p(95)'].toFixed(2)}ms\n`;
    summary += `  p99: ${metrics.latency_trend.values['p(99)'].toFixed(2)}ms\n`;
  }
  
  summary += '\n⚠️  Check for:\n';
  summary += '  - Latency degradation over time\n';
  summary += '  - Memory growth in worker containers\n';
  summary += '  - Connection pool exhaustion\n';
  summary += '  - Error rate increases\n\n';
  
  return summary;
}
