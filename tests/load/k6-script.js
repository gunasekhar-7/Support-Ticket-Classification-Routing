import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const classifyLatency = new Trend('classify_latency');
const batchLatency = new Trend('batch_latency');
const loginCounter = new Counter('logins');

// Test configuration
export const options = {
  stages: [
    { duration: '30s', target: 10 },   // Ramp up
    { duration: '1m', target: 50 },    // Sustained load
    { duration: '30s', target: 100 },  // Stress test
    { duration: '30s', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],  // 95th percentile < 2000ms under 100 VU CI load
    http_req_failed: ['rate<0.01'],    // Error rate < 1%
    errors: ['rate<0.05'],             // Custom error rate < 5%
  },
};

// Base URL (override with -e BASE_URL=http://host:port)
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_PREFIX = '/api/v1';

// Test data
const TICKETS = [
  { subject: 'Login issue', body: 'Cannot login to my account', customer_id: 'cust-001' },
  { subject: 'Bug report', body: 'API returns 500 error on /users endpoint', customer_id: 'cust-002' },
  { subject: 'Billing question', body: 'Invoice amount is incorrect', customer_id: 'cust-003' },
  { subject: 'Feature request', body: 'Add dark mode support', customer_id: 'cust-004' },
  { subject: 'Security concern', body: 'Potential data breach detected', customer_id: 'cust-005' },
  { subject: 'Account access', body: 'Need to reset password', customer_id: 'cust-006' },
  { subject: 'Technical issue', body: 'Integration with Salesforce failing', customer_id: 'cust-007' },
  { subject: 'General question', body: 'What are your business hours?', customer_id: 'cust-008' },
];

let authToken = null;

export function setup() {
  // Login once and share token across VUs
  const loginRes = http.post(`${BASE_URL}${API_PREFIX}/auth/login`, JSON.stringify({
    username: 'service',
    password: 'any',
  }), {
    headers: { 'Content-Type': 'application/json' },
  });

  if (loginRes.status === 200) {
    const body = JSON.parse(loginRes.body);
    return { token: body.access_token };
  }
  return { token: null };
}

export default function (data) {
  if (!data.token) {
    console.log('Failed to get auth token');
    return;
  }

  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${data.token}`,
  };

  // 70% single classify
  if (Math.random() < 0.7) {
    classifyTicket(headers);
  }
  // 20% batch classify
  else if (Math.random() < 0.9) {
    batchClassify(headers);
  }
  // 10% health checks
  else {
    healthCheck(headers);
  }

  sleep(Math.random() * 2 + 1); // 1-3 seconds
}

function classifyTicket(headers) {
  const ticket = TICKETS[Math.floor(Math.random() * TICKETS.length)];
  const startTime = new Date();

  const res = http.post(`${BASE_URL}${API_PREFIX}/classify`, JSON.stringify(ticket), {
    headers,
  });

  const latency = new Date() - startTime;
  classifyLatency.add(latency);

  const success = check(res, {
    'classify status 200': (r) => r.status === 200,
    'has ticket_id': (r) => {
      try {
        return JSON.parse(r.body).ticket_id !== undefined;
      } catch {
        return false;
      }
    },
    'has classification': (r) => {
      try {
        return JSON.parse(r.body).classification !== undefined;
      } catch {
        return false;
      }
    },
    'confidence in range': (r) => {
      try {
        const conf = JSON.parse(r.body).classification.confidence;
        return conf >= 0 && conf <= 1;
      } catch {
        return false;
      }
    },
  });

  errorRate.add(!success);
}

function batchClassify(headers) {
  const batchSize = Math.floor(Math.random() * 15) + 5; // 5-20 tickets
  const tickets = [];
  for (let i = 0; i < batchSize; i++) {
    tickets.push({
      subject: `Batch ticket ${i}`,
      body: `Description for batch ticket ${i}`,
      customer_id: `cust-batch-${i}`,
    });
  }

  const startTime = new Date();
  const res = http.post(`${BASE_URL}${API_PREFIX}/classify/batch`, JSON.stringify({ tickets }), {
    headers,
  });

  const latency = new Date() - startTime;
  batchLatency.add(latency);

  const success = check(res, {
    'batch status 200': (r) => r.status === 200,
    'has results': (r) => {
      try {
        return Array.isArray(JSON.parse(r.body).results);
      } catch {
        return false;
      }
    },
    'correct batch size': (r) => {
      try {
        return JSON.parse(r.body).results.length === batchSize;
      } catch {
        return false;
      }
    },
  });

  errorRate.add(!success);
}

function healthCheck(headers) {
  const endpoints = ['/health/live', '/health/ready', '/metrics'];
  const endpoint = endpoints[Math.floor(Math.random() * endpoints.length)];

  const res = http.get(`${BASE_URL}${API_PREFIX}${endpoint}`, { headers });

  check(res, {
    [`${endpoint} status 200`]: (r) => r.status === 200,
  });

  errorRate.add(res.status !== 200);
}

export function teardown(data) {
  // Cleanup if needed
  console.log('Load test completed');
}