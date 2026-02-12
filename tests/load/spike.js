/**
 * Spike Load Test
 * 
 * Purpose: Test system resilience to sudden traffic spikes
 * Pattern: Sudden spike from 10 to 300 VUs and back
 * Duration: 6 minutes
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');
const successRate = new Rate('success');

export const options = {
  stages: [
    { duration: '1m', target: 10 },    // Low baseline
    { duration: '30s', target: 300 },  // Sudden spike!
    { duration: '2m', target: 300 },   // Sustain spike
    { duration: '30s', target: 10 },   // Drop back
    { duration: '1m', target: 10 },    // Recover
    { duration: '30s', target: 0 },    // End
  ],
  thresholds: {
    http_req_duration: ['p(95)<3000'],
    http_req_failed: ['rate<0.15'],
    errors: ['rate<0.15'],
  },
};

const texts = [
  'This product is absolutely amazing! Best purchase ever!',
  'Terrible quality, very disappointed with this',
  'It is okay, nothing special about it',
  'Fantastic service and great quality',
  'Worst experience I have ever had',
];

export default function () {
  const payload = JSON.stringify({
    text: texts[Math.floor(Math.random() * texts.length)],
  });
  
  const params = {
    headers: { 'Content-Type': 'application/json' },
    timeout: '60s',
  };
  
  const response = http.post('http://localhost/infer', payload, params);
  
  const success = check(response, {
    'status is 200': (r) => r.status === 200,
  });
  
  successRate.add(success);
  errorRate.add(!success);
  
  sleep(0.2);
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data),
    'tests/load/results/spike-summary.json': JSON.stringify(data),
  };
}

function textSummary(data) {
  const metrics = data.metrics;
  let summary = '\n✓ Spike Load Test Complete\n\n';
  
  if (metrics.http_reqs) {
    summary += `Total Requests: ${metrics.http_reqs.values.count}\n`;
  }
  
  if (metrics.http_req_duration) {
    summary += `Request Duration:\n`;
    summary += `  p95: ${metrics.http_req_duration.values['p(95)'].toFixed(2)}ms\n`;
    summary += `  p99: ${metrics.http_req_duration.values['p(99)'].toFixed(2)}ms\n`;
    summary += `  max: ${metrics.http_req_duration.values.max.toFixed(2)}ms\n`;
  }
  
  if (metrics.http_req_failed) {
    summary += `Error Rate: ${(metrics.http_req_failed.values.rate * 100).toFixed(2)}%\n`;
  }
  
  return summary + '\n';
}
