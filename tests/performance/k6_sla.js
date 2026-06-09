import crypto from "k6/crypto";
import encoding from "k6/encoding";
import http from "k6/http";
import ws from "k6/ws";
import { check, sleep } from "k6";

const API_BASE = (__ENV.AEOS_API_BASE || "http://localhost:8000/api/v1").replace(/\/$/, "");
const PLANNER_URL = (__ENV.AEOS_PLANNER_URL || "http://localhost:8010").replace(/\/$/, "");
const GOVERNANCE_URL = (__ENV.AEOS_GOVERNANCE_URL || "http://localhost:8020").replace(/\/$/, "");
const MEMORY_URL = (__ENV.AEOS_MEMORY_URL || "http://localhost:8017").replace(/\/$/, "");
const WS_URL = __ENV.AEOS_WS_URL || "ws://localhost:8040/ws/events";
const JWT_SECRET = __ENV.JWT_SECRET || "test-jwt-secret-key-for-aeos-123456789";

export const options = {
  scenarios: {
    incident_ingest: {
      executor: "constant-vus",
      vus: Number(__ENV.AEOS_K6_VUS || 10),
      duration: __ENV.AEOS_K6_DURATION || "30s",
      exec: "incidentIngest",
    },
    governance_validate: {
      executor: "constant-vus",
      vus: Number(__ENV.AEOS_K6_VUS || 10),
      duration: __ENV.AEOS_K6_DURATION || "30s",
      exec: "governanceValidate",
    },
    planner_generate: {
      executor: "constant-vus",
      vus: Number(__ENV.AEOS_K6_VUS || 10),
      duration: __ENV.AEOS_K6_DURATION || "30s",
      exec: "plannerGenerate",
    },
    audit_query: {
      executor: "constant-vus",
      vus: Number(__ENV.AEOS_K6_VUS || 10),
      duration: __ENV.AEOS_K6_DURATION || "30s",
      exec: "auditQuery",
    },
    memory_context: {
      executor: "constant-vus",
      vus: Number(__ENV.AEOS_K6_VUS || 10),
      duration: __ENV.AEOS_K6_DURATION || "30s",
      exec: "memoryContextQuery",
    },
    websocket_connect: {
      executor: "constant-vus",
      vus: Number(__ENV.AEOS_K6_WS_VUS || 5),
      duration: __ENV.AEOS_K6_DURATION || "30s",
      exec: "websocketConnect",
    },
  },
  thresholds: {
    "http_req_duration{endpoint:incident_ingest}": ["p(95)<5000"],
    "http_req_duration{endpoint:planner_generate}": ["p(95)<10000"],
    "http_req_duration{endpoint:governance_validate}": ["p(95)<1000"],
    "http_req_duration{endpoint:audit_query}": ["p(95)<3000"],
    "http_req_duration{endpoint:memory_context}": ["p(95)<500"],
    checks: ["rate>0.95"],
  },
};

function base64url(value) {
  return encoding.b64encode(JSON.stringify(value), "rawurl");
}

function token(role = "admin") {
  if (__ENV.AEOS_JWT_TOKEN) return __ENV.AEOS_JWT_TOKEN;
  const now = Math.floor(Date.now() / 1000);
  const header = base64url({ alg: "HS256", typ: "JWT" });
  const payload = base64url({ sub: "k6-load-user", role, iat: now, exp: now + 3600 });
  const signingInput = `${header}.${payload}`;
  const signature = crypto.hmac("sha256", JWT_SECRET, signingInput, "base64rawurl");
  return `${signingInput}.${signature}`;
}

function authHeaders(role = "admin") {
  return { Authorization: `Bearer ${token(role)}` };
}

function socketIoUrl(role = "admin") {
  const separator = WS_URL.includes("?") ? "&" : "?";
  return `${WS_URL}${separator}token=${token(role)}&EIO=4&transport=websocket`;
}

function uuidv4() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = Math.floor(Math.random() * 16);
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function incidentIngest() {
  const payload = {
    format: "text",
    metadata: JSON.stringify({ source: "k6", run: __VU }),
    file: http.file(`critical load test ${Date.now()} ${__VU}`.repeat(8), "incident.txt", "text/plain"),
  };
  const res = http.post(`${API_BASE}/incidents/ingest`, payload, {
    headers: authHeaders("admin"),
    tags: { endpoint: "incident_ingest" },
  });
  check(res, {
    "incident ingest accepted": (r) => r.status === 200,
    "incident ingest has id": (r) => Boolean(r.json("incident_id")),
  });
  sleep(1);
}

export function plannerGenerate() {
  const workflowId = uuidv4();
  const res = http.post(
    `${PLANNER_URL}/planner/generate`,
    JSON.stringify({
      incident_id: uuidv4(),
      severity: "high",
      root_signature: "K6_LOAD",
      workflow_id: workflowId,
    }),
    { headers: { "Content-Type": "application/json" }, tags: { endpoint: "planner_generate" } }
  );
  check(res, { "planner responded": (r) => [200, 422, 500].includes(r.status) });
  sleep(1);
}

export function governanceValidate() {
  const res = http.post(
    `${GOVERNANCE_URL}/governance/validate-action`,
    JSON.stringify({
      agent_type: "operations",
      action: { tool: "gather_logs", params: { service: "db" }, timeout_seconds: 30 },
    }),
    { headers: { "Content-Type": "application/json" }, tags: { endpoint: "governance_validate" } }
  );
  check(res, {
    "governance responded": (r) => r.status === 200,
    "governance risk score present": (r) => r.json("risk_score") !== undefined,
  });
  sleep(1);
}

export function auditQuery() {
  const res = http.get(`${API_BASE}/audit?limit=100`, {
    headers: authHeaders("admin"),
    tags: { endpoint: "audit_query" },
  });
  check(res, {
    "audit query ok": (r) => r.status === 200,
    "audit query returns list": (r) => Array.isArray(r.json()),
  });
  sleep(1);
}

export function memoryContextQuery() {
  const res = http.post(
    `${MEMORY_URL}/memory/context/query`,
    JSON.stringify({ context_type: "incident_resolution", query_text: "load", limit: 10 }),
    { headers: { "Content-Type": "application/json" }, tags: { endpoint: "memory_context" } }
  );
  check(res, {
    "memory context query ok": (r) => r.status === 200,
    "memory context returns list": (r) => Array.isArray(r.json()),
  });
  sleep(1);
}

export function websocketConnect() {
  const res = ws.connect(socketIoUrl("admin"), null, (socket) => {
    socket.on("open", () => socket.setTimeout(() => socket.close(), 1000));
  });
  check(res, { "websocket connected": (r) => r && r.status === 101 });
  sleep(1);
}
