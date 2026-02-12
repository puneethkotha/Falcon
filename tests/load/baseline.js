/**
 * Baseline Load Test
 * 
 * Purpose: Establish baseline performance metrics
 * VUs: 50 concurrent users
 * Duration: 5 minutes
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const cacheHitRate = new Rate('cache_hits');
const successRate = new Rate('success');

// Test configuration
export const options = {
  stages: [
    { duration: '1m', target: 50 },   // Ramp up to 50 users
    { duration: '3m', target: 50 },   // Stay at 50 users
    { duration: '1m', target: 0 },    // Ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<1000'],  // 95% of requests should be below 1s
    http_req_failed: ['rate<0.05'],      // Error rate should be below 5%
    errors: ['rate<0.05'],
    success: ['rate>0.95'],
  },
};

// Test data
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
  
  const payload = JSON.stringify({
    text: text,
  });
  
  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
    timeout: '30s',
  };
  
  const response = http.post('http://localhost/infer', payload, params);
  
  // Check response
  const success = check(response, {
    'status is 200': (r) => r.status === 200,
    'has prediction': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.prediction !== undefined;
      } catch (e) {
        return false;
      }
    },
    'has confidence': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.confidence !== undefined && body.confidence >= 0 && body.confidence <= 1;
      } catch (e) {
        return false;
      }
    },
    'response time < 2s': (r) => r.timings.duration < 2000,
  });
  
  // Track metrics
  successRate.add(success);
  errorRate.add(!success);
  
  if (response.status === 200) {
    try {
      const body = JSON.parse(response.body);
      cacheHitRate.add(body.cache_hit);
    } catch (e) {
      // Ignore parse errors
    }
  }
  
  // Think time between requests
  sleep(0.5 + Math.random() * 1.5);  // Random sleep between 0.5-2s
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'tests/load/results/baseline-summary.json': JSON.stringify(data),
  };
}

function textSummary(data, options) {
  const indent = options.indent || '';
  const enableColors = options.enableColors !== false;
  
  let summary = '\n';
  summary += `${indent}✓ Baseline Load Test Complete\n\n`;
  
  const metrics = data.metrics;
  
  if (metrics.http_reqs) {
    summary += `${indent}Total Requests: ${metrics.http_reqs.values.count}\n`;
  }
  
  if (metrics.http_req_duration) {
    summary += `${indent}Request Duration:\n`;
    summary += `${indent}  avg: ${metrics.http_req_duration.values.avg.toFixed(2)}ms\n`;
    summary += `${indent}  p50: ${metrics.http_req_duration.values['p(50)'].toFixed(2)}ms\n`;
    summary += `${indent}  p95: ${metrics.http_req_duration.values['p(95)'].toFixed(2)}ms\n`;
    summary += `${indent}  p99: ${metrics.http_req_duration.values['p(99)'].toFixed(2)}ms\n`;
  }
  
  if (metrics.http_req_failed) {
    const failRate = metrics.http_req_failed.values.rate * 100;
    summary += `${indent}Error Rate: ${failRate.toFixed(2)}%\n`;
  }
  
  if (metrics.cache_hits) {
    const hitRate = metrics.cache_hits.values.rate * 100;
    summary += `${indent}Cache Hit Rate: ${hitRate.toFixed(2)}%\n`;
  }
  
  summary += '\n';
  
  return summary;
}
