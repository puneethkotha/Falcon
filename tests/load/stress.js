/**
 * Stress Load Test
 * 
 * Purpose: Test system behavior under heavy load
 * VUs: Ramp up to 500 concurrent users
 * Duration: 10 minutes
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const successRate = new Rate('success');

// Test configuration
export const options = {
  stages: [
    { duration: '2m', target: 100 },   // Ramp to 100
    { duration: '3m', target: 300 },   // Ramp to 300
    { duration: '2m', target: 500 },   // Ramp to 500
    { duration: '2m', target: 500 },   // Stay at 500
    { duration: '1m', target: 0 },     // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<5000'],   // 95% under 5s (relaxed for stress)
    http_req_failed: ['rate<0.10'],      // Error rate under 10%
    errors: ['rate<0.10'],
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
  
  const success = check(response, {
    'status is 200': (r) => r.status === 200,
    'has prediction': (r) => {
      try {
        return JSON.parse(r.body).prediction !== undefined;
      } catch (e) {
        return false;
      }
    },
  });
  
  successRate.add(success);
  errorRate.add(!success);
  
  sleep(0.1 + Math.random() * 0.5);  // Shorter sleep for stress
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data),
    'tests/load/results/stress-summary.json': JSON.stringify(data),
  };
}

function textSummary(data) {
  const metrics = data.metrics;
  let summary = '\n✓ Stress Load Test Complete\n\n';
  
  if (metrics.http_reqs) {
    summary += `Total Requests: ${metrics.http_reqs.values.count}\n`;
  }
  
  if (metrics.http_req_duration) {
    summary += `Request Duration:\n`;
    summary += `  avg: ${metrics.http_req_duration.values.avg.toFixed(2)}ms\n`;
    summary += `  p95: ${metrics.http_req_duration.values['p(95)'].toFixed(2)}ms\n`;
    summary += `  p99: ${metrics.http_req_duration.values['p(99)'].toFixed(2)}ms\n`;
    summary += `  max: ${metrics.http_req_duration.values.max.toFixed(2)}ms\n`;
  }
  
  if (metrics.http_req_failed) {
    summary += `Error Rate: ${(metrics.http_req_failed.values.rate * 100).toFixed(2)}%\n`;
  }
  
  return summary + '\n';
}
