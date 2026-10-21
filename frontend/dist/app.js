/**
 * PulseAPI Frontend Controller (Dual-Mode: Python FastAPI Backend + GitHub Pages Standalone Engine)
 * Works seamlessly both with the local Python server and when hosted statically on GitHub Pages!
 */

const state = {
  isStaticMode: false,
  stats: null,
  environments: [],
  scenarios: [],
  selectedScenarioId: null,
  runs: [],
  selectedRunId: null,
  selectedRunDetail: null,
};

/* ============================================================================
 * Browser Fallback Engine (Used automatically when hosted on GitHub Pages)
 * ============================================================================ */
const DEFAULT_STATIC_DB = {
  chaos: { mode: "none", description: "正常運作中 (All services healthy)" },
  environments: [
    {
      id: 1,
      name: "Built-in E-Commerce Target (Simulator)",
      base_url: "http://127.0.0.1:8765",
      description: "內建電商微服務靶機（支援登入、商品查詢、購物車、結帳與 Chaos Bug 模擬）",
      variables: { test_user: "qa_lead_mona", test_pass: "qa_secret_2026", order_qty: 2, expected_total: 2598 },
    },
    {
      id: 2,
      name: "JSONPlaceholder Public REST API",
      base_url: "https://jsonplaceholder.typicode.com",
      description: "公開真實 REST API，可在瀏覽器直接發送真實 HTTPS 請求驗證",
      variables: { target_user_id: 1 },
    },
  ],
  scenarios: [
    {
      id: 1,
      name: "🛒 電商金流完整下單鏈路 (E2E Checkout Flow)",
      description: "驗證「登入取 Token → 查詢商品庫存 → 加入購物車 → 結帳扣款」4 步驟跨 API 變數傳遞與金額斷言。",
      environment_id: 1,
      tags: ["E2E", "Checkout", "P0-Critical"],
      fail_fast: true,
      steps: [
        {
          step_order: 1,
          name: "Step 1: 會員登入並提取 Bearer Token",
          method: "POST",
          path: "/mock/auth/login",
          headers: { "Content-Type": "application/json" },
          body: { username: "{{test_user}}", password: "{{test_pass}}" },
          extractions: [
            { var_name: "auth_token", jsonpath: "$.data.token" },
            { var_name: "buyer_id", jsonpath: "$.data.user.id" },
          ],
          assertions: [
            { type: "status_code", operator: "eq", expected: 200 },
            { type: "jsonpath", path: "$.data.token", operator: "not_empty", expected: "" },
            { type: "jsonpath", path: "$.data.user.role", operator: "eq", expected: "VIP_BUYER" },
          ],
        },
        {
          step_order: 2,
          name: "Step 2: 取得商品列表並提取首筆商品 ID",
          method: "GET",
          path: "/mock/products",
          headers: {},
          body: {},
          extractions: [
            { var_name: "target_product_id", jsonpath: "$.data.products[0].id" },
            { var_name: "unit_price", jsonpath: "$.data.products[0].price" },
          ],
          assertions: [
            { type: "status_code", operator: "eq", expected: 200 },
            { type: "jsonpath", path: "$.data.products[0].stock", operator: "gt", expected: 0 },
            { type: "jsonpath", path: "$.data.products[0].price", operator: "eq", expected: 1299 },
          ],
        },
        {
          step_order: 3,
          name: "Step 3: 帶入 Token 與商品 ID 加入購物車",
          method: "POST",
          path: "/mock/cart/items",
          headers: { Authorization: "Bearer {{auth_token}}" },
          body: { product_id: "{{target_product_id}}", quantity: "{{order_qty}}" },
          extractions: [{ var_name: "active_cart_id", jsonpath: "$.data.cart_id" }],
          assertions: [
            { type: "status_code", operator: "eq", expected: 200 },
            { type: "jsonpath", path: "$.data.cart_total", operator: "eq", expected: "{{expected_total}}" },
          ],
        },
        {
          step_order: 4,
          name: "Step 4: 建立結帳訂單並驗證實付金額與狀態",
          method: "POST",
          path: "/mock/orders/checkout",
          headers: { Authorization: "Bearer {{auth_token}}" },
          body: { cart_id: "{{active_cart_id}}", payment_method: "CREDIT_CARD" },
          extractions: [{ var_name: "final_order_id", jsonpath: "$.data.order.order_id" }],
          assertions: [
            { type: "status_code", operator: "eq", expected: 201 },
            { type: "jsonpath", path: "$.data.order.status", operator: "eq", expected: "PAID" },
            { type: "jsonpath", path: "$.data.order.charged_amount", operator: "eq", expected: "{{expected_total}}" },
            { type: "response_time_ms", operator: "lt", expected: 500 },
          ],
        },
      ],
    },
    {
      id: 2,
      name: "🔒 權限防護與邊界負向測試 (Auth & Negative Boundary Suite)",
      description: "驗證未授權攔截 (401)、非法負數購買量攔截 (400)、以及不存在商品的錯誤碼契約 (404)。",
      environment_id: 1,
      tags: ["Security", "Negative-Test", "Boundary"],
      fail_fast: false,
      steps: [
        {
          step_order: 1,
          name: "Step 1: 未帶 Token 直接呼叫結帳應攔截 (401 Unauthorized)",
          method: "POST",
          path: "/mock/orders/checkout",
          headers: {},
          body: { cart_id: "CART-FAKE" },
          extractions: [],
          assertions: [
            { type: "status_code", operator: "eq", expected: 401 },
            { type: "jsonpath", path: "$.error.code", operator: "eq", expected: "UNAUTHORIZED" },
          ],
        },
        {
          step_order: 2,
          name: "Step 2: 購買負數數量 (-5) 應觸發邊界值校驗 (400 Bad Request)",
          method: "POST",
          path: "/mock/cart/items",
          headers: { Authorization: "Bearer tok_boundary_test" },
          body: { product_id: "PROD-101", quantity: -5 },
          extractions: [],
          assertions: [
            { type: "status_code", operator: "eq", expected: 400 },
            { type: "jsonpath", path: "$.error.code", operator: "eq", expected: "INVALID_QUANTITY" },
          ],
        },
        {
          step_order: 3,
          name: "Step 3: 查詢不存在的商品編號應回傳標準 404 結構",
          method: "GET",
          path: "/mock/products/PROD-99999",
          headers: {},
          body: {},
          extractions: [],
          assertions: [
            { type: "status_code", operator: "eq", expected: 404 },
            { type: "jsonpath", path: "$.error.code", operator: "eq", expected: "PRODUCT_NOT_FOUND" },
          ],
        },
      ],
    },
    {
      id: 3,
      name: "⚡ 核心服務健康度與 SLA 耗時巡檢 (Health & Latency SLA Probe)",
      description: "監控微服務健康檢查端點與商品目錄回應時間是否低於 200ms SLO 門檻。",
      environment_id: 1,
      tags: ["Smoke", "SLA-Monitor"],
      fail_fast: true,
      steps: [
        {
          step_order: 1,
          name: "Step 1: 微服務 Health Check 端點檢查",
          method: "GET",
          path: "/mock/health",
          headers: {},
          body: {},
          extractions: [],
          assertions: [
            { type: "status_code", operator: "eq", expected: 200 },
            { type: "jsonpath", path: "$.status", operator: "eq", expected: "healthy" },
            { type: "response_time_ms", operator: "lt", expected: 200 },
          ],
        },
        {
          step_order: 2,
          name: "Step 2: 商品目錄讀取效能 SLA (< 200ms)",
          method: "GET",
          path: "/mock/products",
          headers: {},
          body: {},
          extractions: [],
          assertions: [
            { type: "status_code", operator: "eq", expected: 200 },
            { type: "jsonpath", path: "$.data.products.length", operator: "gte", expected: 2 },
            { type: "response_time_ms", operator: "lt", expected: 200 },
          ],
        },
      ],
    },
  ],
  runs: [],
};

function getStaticStore() {
  const raw = localStorage.getItem("pulseapi_store_v1");
  if (raw) {
    try {
      return JSON.parse(raw);
    } catch (_) {}
  }
  const copy = JSON.parse(JSON.stringify(DEFAULT_STATIC_DB));
  localStorage.setItem("pulseapi_store_v1", JSON.stringify(copy));
  return copy;
}

function saveStaticStore(store) {
  localStorage.setItem("pulseapi_store_v1", JSON.stringify(store));
}

function renderTemplateJS(val, ctx) {
  if (typeof val === "string") {
    const exact = val.match(/^\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}$/);
    if (exact && exact[1] in ctx) return ctx[exact[1]];
    return val.replace(/\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}/g, (m, k) => (k in ctx ? String(ctx[k]) : m));
  }
  if (Array.isArray(val)) return val.map((item) => renderTemplateJS(item, ctx));
  if (val && typeof val === "object") {
    const out = {};
    for (const [k, v] of Object.entries(val)) out[k] = renderTemplateJS(v, ctx);
    return out;
  }
  return val;
}

function extractJsonPathJS(data, expr) {
  if (!expr || !data) return [false, undefined];
  let clean = expr.trim().replace(/^\$\.?/, "");
  if (!clean) return [true, data];
  const parts = clean.split(".");
  let cur = data;
  for (const part of parts) {
    const m = part.match(/^([^\[\]]+)?(?:\[(\d+)\])?$/);
    if (!m) return [false, undefined];
    const [, key, idx] = m;
    if (key) {
      if (key === "length" && (Array.isArray(cur) || typeof cur === "string")) {
        cur = cur.length;
      } else if (cur && typeof cur === "object" && key in cur) {
        cur = cur[key];
      } else {
        return [false, undefined];
      }
    }
    if (idx !== undefined) {
      if (!Array.isArray(cur) || Number(idx) >= cur.length) return [false, undefined];
      cur = cur[Number(idx)];
    }
  }
  return [true, cur];
}

async function runScenarioInBrowser(store, sc) {
  const env = store.environments.find((e) => e.id === sc.environment_id) || store.environments[0];
  const ctx = { ...(env.variables || {}) };
  const stepResults = [];
  let overallPassed = true;
  let passedSteps = 0;
  let totalAssertions = 0;
  let passedAssertions = 0;
  let totalMs = 0;
  let diagnosis = "";

  for (let i = 0; i < sc.steps.length; i++) {
    const step = sc.steps[i];
    const method = (step.method || "GET").toUpperCase();
    const path = String(renderTemplateJS(step.path || "/", ctx));
    const headers = renderTemplateJS(step.headers || {}, ctx);
    const body = renderTemplateJS(step.body || {}, ctx);
    const fullUrl = path.startsWith("http") ? path : `${env.base_url.replace(/\/$/, "")}${path}`;

    let statusCode = 200;
    let respJson = {};
    let elapsedMs = 0.05;

    if (path.startsWith("/mock/")) {
      // Built-in browser mock target
      const t0 = performance.now();
      const authHeader = headers.Authorization || headers.authorization || "";
      if (path === "/mock/health") {
        statusCode = 200;
        respJson = { status: "healthy", chaos_mode: store.chaos.mode };
      } else if (path === "/mock/auth/login") {
        statusCode = 200;
        respJson = {
          success: true,
          data: { token: "tok_ghpages_98a1f", user: { id: "USR-8801", role: "VIP_BUYER" } },
        };
      } else if (path === "/mock/products") {
        statusCode = 200;
        respJson = {
          success: true,
          data: {
            products: [
              { id: "PROD-101", name: "Mechanical Keyboard Pro", price: 1299, stock: 42 },
              { id: "PROD-102", name: "4K UltraWide Monitor", price: 8999, stock: 15 },
            ],
          },
        };
      } else if (path.startsWith("/mock/products/")) {
        statusCode = 404;
        respJson = { success: false, error: { code: "PRODUCT_NOT_FOUND" } };
      } else if (path === "/mock/cart/items") {
        if (!authHeader.startsWith("Bearer ")) {
          statusCode = 401;
          respJson = { success: false, error: { code: "UNAUTHORIZED" } };
        } else if (Number(body.quantity) <= 0) {
          statusCode = 400;
          respJson = { success: false, error: { code: "INVALID_QUANTITY" } };
        } else {
          statusCode = 200;
          respJson = {
            success: true,
            data: { cart_id: "CART-88A1", product_id: body.product_id, quantity: body.quantity, cart_total: 2598 },
          };
        }
      } else if (path === "/mock/orders/checkout") {
        if (!authHeader.startsWith("Bearer ")) {
          statusCode = 401;
          respJson = { success: false, error: { code: "UNAUTHORIZED" } };
        } else if (store.chaos.mode === "server_500_bug") {
          statusCode = 500;
          respJson = {
            success: false,
            error: { code: "PAYMENT_GATEWAY_CRASH", message: "Database connection pool exhausted" },
          };
        } else {
          statusCode = 201;
          const amount = store.chaos.mode === "pricing_bug" ? 3098 : 2598;
          respJson = {
            success: true,
            data: { order: { order_id: "ORD-99201", status: "PAID", charged_amount: amount } },
          };
        }
      }
      elapsedMs = Math.max(0.04, Number((performance.now() - t0).toFixed(2)));
    } else {
      // Real browser HTTP fetch for external APIs
      const t0 = performance.now();
      try {
        const res = await fetch(fullUrl, {
          method,
          headers,
          body: method !== "GET" && method !== "HEAD" ? JSON.stringify(body) : undefined,
        });
        statusCode = res.status;
        respJson = await res.json().catch(() => ({}));
      } catch (e) {
        statusCode = 0;
        respJson = { error: e.message };
      }
      elapsedMs = Number((performance.now() - t0).toFixed(2));
    }

    totalMs += elapsedMs;
    const assertResults = [];
    let stepPassed = true;

    for (const rule of step.assertions || []) {
      const exp = renderTemplateJS(rule.expected, ctx);
      let actual = null;
      let found = true;
      let target = rule.type;

      if (rule.type === "status_code") {
        actual = statusCode;
        target = "HTTP Status Code";
      } else if (rule.type === "response_time_ms") {
        actual = elapsedMs;
        target = "Response Time (ms)";
      } else {
        [found, actual] = extractJsonPathJS(respJson, rule.path);
        target = `JSONPath (${rule.path})`;
      }

      let passed = false;
      if (rule.operator === "not_empty") passed = found && actual !== null && String(actual).length > 0;
      else if (rule.operator === "gt") passed = Number(actual) > Number(exp);
      else if (rule.operator === "gte") passed = Number(actual) >= Number(exp);
      else if (rule.operator === "lt") passed = Number(actual) < Number(exp);
      else passed = String(actual) === String(exp);

      if (!passed) stepPassed = false;
      totalAssertions++;
      if (passed) passedAssertions++;
      assertResults.push({
        type: rule.type,
        path: rule.path || "",
        target,
        operator: rule.operator,
        expected: exp,
        actual: found ? actual : "<NOT_FOUND>",
        passed,
      });
    }

    const extracted = {};
    for (const ext of step.extractions || []) {
      const [found, val] = extractJsonPathJS(respJson, ext.jsonpath);
      if (found) {
        ctx[ext.var_name] = val;
        extracted[ext.var_name] = val;
      }
    }

    if (!stepPassed) {
      overallPassed = false;
      if (!diagnosis) {
        if (statusCode >= 500) {
          diagnosis = `💥 [後端服務異常 5xx] 步驟「${step.name}」回傳 HTTP ${statusCode}。屬伺服器端異常，非測試腳本問題。`;
        } else {
          const failedRule = assertResults.find((a) => !a.passed);
          diagnosis = `🔍 [資料斷言不符] 步驟「${step.name}」驗證 ${failedRule?.target} 預期為 ${failedRule?.expected}，但實際收到 ${failedRule?.actual}。`;
        }
      }
    } else {
      passedSteps++;
    }

    stepResults.push({
      step_order: i + 1,
      step_name: step.name,
      method,
      url: fullUrl,
      request_headers: headers,
      request_body: body,
      status_code: statusCode,
      elapsed_ms: elapsedMs,
      passed: stepPassed,
      assertions: assertResults,
      extracted_variables: extracted,
      response_body: respJson,
    });
  }

  const runRecord = {
    id: (store.runs[0]?.id || 0) + 1,
    scenario_id: sc.id,
    scenario_name: sc.name,
    environment_name: env.name,
    base_url: env.base_url,
    status: overallPassed ? "PASSED" : "FAILED",
    passed_steps: passedSteps,
    total_steps: sc.steps.length,
    passed_assertions: passedAssertions,
    total_assertions: totalAssertions,
    duration_ms: Number(totalMs.toFixed(2)),
    chaos_mode: store.chaos.mode,
    failure_diagnosis: diagnosis,
    step_results: stepResults,
    final_context: ctx,
    triggered_by: "GitHub Pages Live Runner",
    created_at: new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC",
  };

  store.runs.unshift(runRecord);
  saveStaticStore(store);
  return runRecord;
}

/* ============================================================================
 * Unified API Adapter (Talks to Python Server OR Browser Engine on GitHub Pages)
 * ============================================================================ */
async function apiFetch(path, options = {}) {
  const cleanUrl = path.startsWith("/") ? `.${path}` : path;
  if (!state.isStaticMode) {
    try {
      const res = await fetch(cleanUrl, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      if (res.ok && res.headers.get("content-type")?.includes("application/json")) {
        return await res.json();
      }
      state.isStaticMode = true;
    } catch (_) {
      state.isStaticMode = true;
    }
  }

  // Static / GitHub Pages Mode Handler
  const store = getStaticStore();
  if (store.runs.length === 0) {
    for (const sc of store.scenarios) {
      await runScenarioInBrowser(store, sc);
    }
  }

  const method = (options.method || "GET").toUpperCase();
  const body = options.body ? JSON.parse(options.body) : {};

  if (path === "/api/stats") {
    const totalRuns = store.runs.length;
    const passedRuns = store.runs.filter((r) => r.status === "PASSED").length;
    return {
      total_scenarios: store.scenarios.length,
      total_steps: store.scenarios.reduce((acc, s) => acc + s.steps.length, 0),
      total_runs: totalRuns,
      passed_runs: passedRuns,
      failed_runs: totalRuns - passedRuns,
      pass_rate: totalRuns ? Number(((passedRuns / totalRuns) * 100).toFixed(1)) : 100.0,
      avg_duration_ms: totalRuns
        ? Number((store.runs.reduce((a, r) => a + r.duration_ms, 0) / totalRuns).toFixed(2))
        : 0.15,
      chaos: store.chaos,
    };
  }
  if (path === "/api/environments") {
    if (method === "GET") return store.environments;
    if (method === "POST") {
      if (body.id) {
        const idx = store.environments.findIndex((e) => e.id === body.id);
        if (idx >= 0) store.environments[idx] = { ...store.environments[idx], ...body };
      } else {
        body.id = store.environments.length + 1;
        store.environments.push(body);
      }
      saveStaticStore(store);
      return body;
    }
  }
  if (path === "/api/scenarios") {
    if (method === "GET") {
      return store.scenarios.map((sc) => {
        const env = store.environments.find((e) => e.id === sc.environment_id) || store.environments[0];
        const lastRun = store.runs.find((r) => r.scenario_id === sc.id) || null;
        return {
          ...sc,
          environment_name: env.name,
          base_url: env.base_url,
          environment_variables: env.variables,
          last_run: lastRun,
        };
      });
    }
    if (method === "POST") {
      if (body.id) {
        const idx = store.scenarios.findIndex((s) => s.id === body.id);
        if (idx >= 0) store.scenarios[idx] = { ...store.scenarios[idx], ...body };
      } else {
        body.id = store.scenarios.length + 1;
        store.scenarios.push(body);
      }
      saveStaticStore(store);
      return body;
    }
  }
  const mRunSingle = path.match(/^\/api\/scenarios\/(\d+)\/run$/);
  if (mRunSingle && method === "POST") {
    const sc = store.scenarios.find((s) => s.id === Number(mRunSingle[1]));
    return await runScenarioInBrowser(store, sc);
  }
  if (path === "/api/runs/batch" && method === "POST") {
    const runs = [];
    for (const sc of store.scenarios) {
      runs.push(await runScenarioInBrowser(store, sc));
    }
    const passedCount = runs.filter((r) => r.status === "PASSED").length;
    return {
      suite_status: passedCount === runs.length ? "PASSED" : "FAILED",
      total_scenarios: runs.length,
      passed_scenarios: passedCount,
      failed_scenarios: runs.length - passedCount,
      runs,
    };
  }
  if (path === "/api/runs") return store.runs;
  const mRunDetail = path.match(/^\/api\/runs\/(\d+)$/);
  if (mRunDetail) return store.runs.find((r) => r.id === Number(mRunDetail[1])) || store.runs[0];
  if (path === "/api/chaos" && method === "POST") {
    const descriptions = {
      none: "正常運作中 (All services healthy)",
      pricing_bug: "💥 [Bug 已注入] 結帳折扣計算異常（應收 2598 元，卻多扣 500 元變成 3098 元）",
      server_500_bug: "💥 [Bug 已注入] 金流微服務連線中斷（/mock/orders/checkout 回傳 500）",
    };
    store.chaos = { mode: body.mode || "none", description: descriptions[body.mode] || descriptions.none };
    saveStaticStore(store);
    return store.chaos;
  }
  return {};
}

function showToast(message) {
  const container = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3600);
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function switchTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `panel-${tabName}`);
  });
}

async function refreshAllData() {
  const [stats, envs, scenarios, runs] = await Promise.all([
    apiFetch("/api/stats"),
    apiFetch("/api/environments"),
    apiFetch("/api/scenarios"),
    apiFetch("/api/runs"),
  ]);

  state.stats = stats;
  state.environments = envs;
  state.scenarios = scenarios;
  state.runs = runs;

  if (!state.selectedScenarioId && scenarios.length > 0) {
    state.selectedScenarioId = scenarios[0].id;
  }
  if (!state.selectedRunId && runs.length > 0) {
    state.selectedRunId = runs[0].id;
    state.selectedRunDetail = await apiFetch(`/api/runs/${state.selectedRunId}`);
  }

  renderMetrics();
  renderScenarioList();
  renderScenarioDetail();
  renderRunsHistory();
  renderRunReport();
  renderEnvironments();
}

function renderMetrics() {
  const s = state.stats;
  if (!s) return;

  document.getElementById("kpi-scenarios").textContent = s.total_scenarios;
  document.getElementById("kpi-steps").textContent = `${s.total_steps} API Steps`;

  const passRateEl = document.getElementById("kpi-pass-rate");
  passRateEl.textContent = `${s.pass_rate}%`;
  passRateEl.className = `metric-value ${s.pass_rate >= 90 ? "metric-pass" : "metric-fail"}`;

  document.getElementById("kpi-runs-summary").textContent = `${s.passed_runs} Passed / ${s.total_runs} Runs`;
  document.getElementById("kpi-latency").textContent = `${s.avg_duration_ms} ms`;

  const chaosMode = s.chaos?.mode || "none";
  const chaosSelect = document.getElementById("chaos-select");
  const chaosBox = document.getElementById("chaos-box");
  const chaosStatusEl = document.getElementById("kpi-chaos-status");
  const chaosDescEl = document.getElementById("kpi-chaos-desc");

  chaosSelect.value = chaosMode;
  if (chaosMode === "none") {
    chaosBox.classList.remove("chaos-active");
    chaosStatusEl.textContent = "Healthy";
    chaosStatusEl.className = "metric-value metric-pass";
    chaosDescEl.textContent = "內建電商靶機正常";
  } else {
    chaosBox.classList.add("chaos-active");
    chaosStatusEl.textContent = "Bug Injected";
    chaosStatusEl.className = "metric-value metric-fail";
    chaosDescEl.textContent = s.chaos?.description || "已注入異常";
  }
}

function renderScenarioList() {
  const container = document.getElementById("scenario-list");
  container.innerHTML = state.scenarios
    .map((sc) => {
      const selected = sc.id === state.selectedScenarioId ? "selected" : "";
      const lastStatus = sc.last_run ? sc.last_run.status : "READY";
      const pillClass = lastStatus === "PASSED" ? "pass" : lastStatus === "FAILED" ? "fail" : "";
      const tagsHtml = (sc.tags || [])
        .map((t) => `<span class="tag-badge">${escapeHtml(t)}</span>`)
        .join("");

      return `
        <div class="scenario-item ${selected}" data-scenario-id="${sc.id}">
          <div class="scenario-item-top">
            <span class="scenario-item-title">${escapeHtml(sc.name)}</span>
            ${
              sc.last_run
                ? `<span class="status-pill ${pillClass}">${lastStatus}</span>`
                : `<span class="tag-badge">NEW</span>`
            }
          </div>
          <div class="scenario-item-meta">
            <div class="tag-row">${tagsHtml}</div>
            <span class="mono">${sc.steps.length} steps</span>
          </div>
        </div>
      `;
    })
    .join("");

  container.querySelectorAll(".scenario-item").forEach((el) => {
    el.addEventListener("click", () => {
      state.selectedScenarioId = Number(el.dataset.scenarioId);
      renderScenarioList();
      renderScenarioDetail();
    });
  });
}

function renderScenarioDetail() {
  const container = document.getElementById("scenario-detail-content");
  const sc = state.scenarios.find((x) => x.id === state.selectedScenarioId);
  if (!sc) {
    container.innerHTML = `<p class="text-muted">請從左側選擇或新增一個 API 測試場景。</p>`;
    return;
  }

  const envVarsEntries = Object.entries(sc.environment_variables || {});
  const envVarsHtml =
    envVarsEntries.length > 0
      ? envVarsEntries
          .map(
            ([k, v]) =>
              `<span class="var-chip" title="Environment Variable">{{${escapeHtml(k)}}} = ${escapeHtml(JSON.stringify(v))}</span>`
          )
          .join(" ")
      : `<span class="text-muted">無預設變數</span>`;

  const stepsHtml = sc.steps
    .map((step) => {
      const extractionsHtml =
        step.extractions && step.extractions.length > 0
          ? step.extractions
              .map(
                (ext) =>
                  `<li>📤 提取 <code>${escapeHtml(ext.jsonpath)}</code> ➔ 存入變數 <strong>{{${escapeHtml(ext.var_name)}}}</strong></li>`
              )
              .join("")
          : `<li class="text-muted">此步驟無提取變數</li>`;

      const assertionsHtml =
        step.assertions && step.assertions.length > 0
          ? step.assertions
              .map(
                (a) =>
                  `<li>✅ 驗證 <code>${escapeHtml(a.type === "jsonpath" ? a.path : a.type)}</code> <strong>${escapeHtml(a.operator)}</strong> <code>${escapeHtml(a.expected)}</code></li>`
              )
              .join("")
          : `<li class="text-muted">無斷言規則</li>`;

      const hasBody = step.body && Object.keys(step.body).length > 0;
      const hasHeaders = step.headers && Object.keys(step.headers).length > 0;

      return `
        <div class="step-card">
          <div class="step-card-header">
            <div class="step-title-group">
              <span class="step-num">#${step.step_order}</span>
              <span class="method-badge method-${escapeHtml(step.method)}">${escapeHtml(step.method)}</span>
              <span class="step-path">${escapeHtml(step.path)}</span>
              <strong>${escapeHtml(step.name)}</strong>
            </div>
          </div>

          ${
            hasHeaders || hasBody
              ? `<div class="step-grid-2" style="margin-bottom: 10px;">
                  <div class="spec-box">
                    <div class="spec-box-title">Request Headers</div>
                    <pre class="mono" style="font-size:12px;">${escapeHtml(JSON.stringify(step.headers || {}, null, 2))}</pre>
                  </div>
                  <div class="spec-box">
                    <div class="spec-box-title">Request Body Payload</div>
                    <pre class="mono" style="font-size:12px;">${escapeHtml(JSON.stringify(step.body || {}, null, 2))}</pre>
                  </div>
                </div>`
              : ""
          }

          <div class="step-grid-2">
            <div class="spec-box">
              <div class="spec-box-title">變數提取 (Variable Extractions)</div>
              <ul class="rule-list">${extractionsHtml}</ul>
            </div>
            <div class="spec-box">
              <div class="spec-box-title">自動化斷言規則 (Assertions)</div>
              <ul class="rule-list">${assertionsHtml}</ul>
            </div>
          </div>
        </div>
      `;
    })
    .join("");

  container.innerHTML = `
    <div class="detail-header">
      <div>
        <h2 class="detail-title">${escapeHtml(sc.name)}</h2>
        <p class="detail-desc">${escapeHtml(sc.description)}</p>
      </div>
      <div class="detail-actions">
        <button id="btn-edit-scenario" class="btn btn-ghost btn-sm" type="button">✎ 編輯場景 JSON</button>
        <button id="btn-run-single" class="btn btn-primary" type="button">
          ▶ 立即執行驗證 (Run Scenario)
        </button>
      </div>
    </div>

    <div class="env-context-bar">
      <div>
        <strong>目標環境：</strong> <span>${escapeHtml(sc.environment_name)}</span>
        <code style="margin-left:8px; color:#0284c7;">${escapeHtml(sc.base_url)}</code>
      </div>
      <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
        <span class="text-muted">初始環境變數：</span>
        ${envVarsHtml}
      </div>
    </div>

    <div class="steps-pipeline">
      ${stepsHtml}
    </div>
  `;

  document.getElementById("btn-run-single").addEventListener("click", () => triggerSingleRun(sc.id));
  document.getElementById("btn-edit-scenario").addEventListener("click", () => openScenarioModal(sc));
}

async function triggerSingleRun(scenarioId) {
  const btn = document.getElementById("btn-run-single");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ 執行驗證中...";
  }
  try {
    const runRecord = await apiFetch(`/api/scenarios/${scenarioId}/run`, {
      method: "POST",
      body: JSON.stringify({ triggered_by: "Manual Studio Run" }),
    });
    state.selectedRunId = runRecord.id;
    state.selectedRunDetail = runRecord;
    await refreshAllData();
    switchTab("inspector");
    showToast(
      runRecord.status === "PASSED"
        ? `✅ 測試通過！(${runRecord.passed_assertions}/${runRecord.total_assertions} 條斷言全數通過)`
        : `❌ 測試發現異常！已自動生成 QA 根因診斷報告`
    );
  } catch (err) {
    showToast(`執行失敗: ${err.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "▶ 立即執行驗證 (Run Scenario)";
    }
  }
}

async function triggerBatchRuns() {
  const btn = document.getElementById("btn-run-all");
  btn.disabled = true;
  btn.textContent = "⏳ 全量回歸執行中...";
  try {
    const batch = await apiFetch("/api/runs/batch", {
      method: "POST",
      body: JSON.stringify({ triggered_by: "Batch Quality Gate" }),
    });
    if (batch.runs && batch.runs.length > 0) {
      const failedRun = batch.runs.find((r) => r.status === "FAILED");
      const targetRun = failedRun || batch.runs[0];
      state.selectedRunId = targetRun.id;
      state.selectedRunDetail = targetRun;
    }
    await refreshAllData();
    switchTab("inspector");
    showToast(
      batch.suite_status === "PASSED"
        ? `🎉 全量回歸完成：${batch.passed_scenarios}/${batch.total_scenarios} 個場景全數 PASS！`
        : `⚠️ 全量回歸攔截到異常：${batch.failed_scenarios} 個場景失敗！`
    );
  } catch (err) {
    showToast(`批次執行錯誤: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "▶ 全量回歸驗證 (Run All Suites)";
  }
}

function renderRunsHistory() {
  const container = document.getElementById("runs-history-list");
  container.innerHTML = state.runs
    .map((r) => {
      const selected = r.id === state.selectedRunId ? "selected" : "";
      const pillClass = r.status === "PASSED" ? "pass" : "fail";
      return `
        <div class="run-history-item ${selected}" data-run-id="${r.id}">
          <div class="scenario-item-top">
            <span class="scenario-item-title">#${r.id} ${escapeHtml(r.scenario_name)}</span>
            <span class="status-pill ${pillClass}">${r.status}</span>
          </div>
          <div class="scenario-item-meta">
            <span>斷言: ${r.passed_assertions}/${r.total_assertions}</span>
            <span class="mono">${r.duration_ms} ms</span>
          </div>
          <div class="scenario-item-meta" style="margin-top:4px;">
            <span>${escapeHtml(r.triggered_by)}</span>
            <span>${escapeHtml(r.created_at)}</span>
          </div>
        </div>
      `;
    })
    .join("");

  container.querySelectorAll(".run-history-item").forEach((el) => {
    el.addEventListener("click", async () => {
      const runId = Number(el.dataset.runId);
      state.selectedRunId = runId;
      state.selectedRunDetail = await apiFetch(`/api/runs/${runId}`);
      renderRunsHistory();
      renderRunReport();
    });
  });
}

function renderRunReport() {
  const container = document.getElementById("run-report-content");
  const run = state.selectedRunDetail;
  if (!run) {
    container.innerHTML = `<p class="text-muted">請選擇左側任一筆測試執行紀錄以檢視詳細報告。</p>`;
    return;
  }

  const pillClass = run.status === "PASSED" ? "pass" : "fail";
  const diagHtml = run.failure_diagnosis
    ? `<div class="diagnosis-banner">
        <strong>🤖 自動化 QA 根因診斷 (Failure Triage)：</strong><br/>
        ${escapeHtml(run.failure_diagnosis)}
      </div>`
    : "";

  const finalVarsEntries = Object.entries(run.final_context || {});
  const finalVarsHtml = finalVarsEntries
    .map(([k, v]) => `<span class="var-chip">{{${escapeHtml(k)}}} = ${escapeHtml(JSON.stringify(v))}</span>`)
    .join(" ");

  const stepResultsHtml = (run.step_results || [])
    .map((sr) => {
      const stepPill = sr.passed ? "pass" : "fail";
      const assertionsRows = (sr.assertions || [])
        .map((a) => {
          const icon = a.passed ? "✔" : "✖";
          const color = a.passed ? "color: var(--pass-color);" : "color: var(--fail-color); font-weight:700;";
          return `<li style="${color}">${icon} [${escapeHtml(a.target)}] 預期 ${escapeHtml(a.operator)} <code>${escapeHtml(a.expected)}</code> ｜ 實際值: <code>${escapeHtml(JSON.stringify(a.actual))}</code></li>`;
        })
        .join("");

      const extractedEntries = Object.entries(sr.extracted_variables || {});
      const extractedHtml =
        extractedEntries.length > 0
          ? extractedEntries
              .map(([k, v]) => `<li>📤 <code>{{${escapeHtml(k)}}}</code> = <code>${escapeHtml(JSON.stringify(v))}</code></li>`)
              .join("")
          : `<li class="text-muted">無提取變數</li>`;

      return `
        <div class="step-card" style="border-left: 4px solid ${sr.passed ? "var(--pass-color)" : "var(--fail-color)"};">
          <div class="step-card-header">
            <div class="step-title-group">
              <span class="step-num">Step ${sr.step_order}</span>
              <span class="method-badge method-${escapeHtml(sr.method)}">${escapeHtml(sr.method)}</span>
              <span class="step-path">${escapeHtml(sr.url)}</span>
              <strong>${escapeHtml(sr.step_name)}</strong>
            </div>
            <div style="display:flex; align-items:center; gap:10px;">
              <span class="mono" style="font-size:12px;">HTTP ${sr.status_code} · ${sr.elapsed_ms} ms</span>
              <span class="status-pill ${stepPill}">${sr.passed ? "PASS" : "FAIL"}</span>
            </div>
          </div>

          <div class="step-grid-2">
            <div class="spec-box">
              <div class="spec-box-title">斷言驗證結果 (Assertion Checklist)</div>
              <ul class="rule-list">${assertionsRows}</ul>
            </div>
            <div class="spec-box">
              <div class="spec-box-title">動態提取變數 (Extracted Variables)</div>
              <ul class="rule-list">${extractedHtml}</ul>
            </div>
          </div>

          <div class="step-grid-2" style="margin-top:10px;">
            <div>
              <div class="spec-box-title">實際發送 Request Payload</div>
              <pre class="code-block">${escapeHtml(JSON.stringify({ headers: sr.request_headers, body: sr.request_body }, null, 2))}</pre>
            </div>
            <div>
              <div class="spec-box-title">實際收到 Response JSON</div>
              <pre class="code-block">${escapeHtml(JSON.stringify(sr.response_body, null, 2))}</pre>
            </div>
          </div>
        </div>
      `;
    })
    .join("");

  container.innerHTML = `
    <div class="detail-header">
      <div>
        <div style="display:flex; align-items:center; gap:10px;">
          <h2 class="detail-title">Run #${run.id} — ${escapeHtml(run.scenario_name)}</h2>
          <span class="status-pill ${pillClass}">${run.status}</span>
        </div>
        <p class="detail-desc">
          執行時間：${escapeHtml(run.created_at)} ｜ 總耗時：<strong>${run.duration_ms} ms</strong> ｜
          步驟通過：<strong>${run.passed_steps}/${run.total_steps}</strong> ｜
          斷言通過：<strong>${run.passed_assertions}/${run.total_assertions}</strong> ｜
          靶機狀態：<code>${escapeHtml(run.chaos_mode)}</code>
        </p>
      </div>
    </div>

    ${diagHtml}

    <div class="env-context-bar">
      <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
        <strong>執行結束時變數池 (Runtime Context Pool)：</strong>
        ${finalVarsHtml}
      </div>
    </div>

    <div class="steps-pipeline">
      ${stepResultsHtml}
    </div>
  `;
}

function renderEnvironments() {
  const container = document.getElementById("environments-list");
  container.innerHTML = state.environments
    .map(
      (env) => `
      <div class="env-card">
        <h3>${escapeHtml(env.name)}</h3>
        <p class="detail-desc">${escapeHtml(env.description)}</p>
        <div class="env-input-group">
          <label>Target Base URL (可改為你自己的真實服務網址)</label>
          <input type="text" id="env-url-${env.id}" value="${escapeHtml(env.base_url)}" />
        </div>
        <div class="env-input-group">
          <label>全域環境變數 (Variables JSON)</label>
          <textarea rows="4" id="env-vars-${env.id}">${escapeHtml(JSON.stringify(env.variables || {}, null, 2))}</textarea>
        </div>
        <div style="margin-top:12px; display:flex; justify-content:flex-end;">
          <button class="btn btn-secondary btn-sm btn-save-env" data-env-id="${env.id}" type="button">
            💾 儲存環境設定
          </button>
        </div>
      </div>
    `
    )
    .join("");

  container.querySelectorAll(".btn-save-env").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const envId = Number(btn.dataset.envId);
      const envObj = state.environments.find((e) => e.id === envId);
      const newUrl = document.getElementById(`env-url-${envId}`).value.trim();
      const rawVars = document.getElementById(`env-vars-${envId}`).value;
      try {
        const parsedVars = JSON.parse(rawVars || "{}");
        await apiFetch("/api/environments", {
          method: "POST",
          body: JSON.stringify({
            id: envId,
            name: envObj.name,
            description: envObj.description,
            base_url: newUrl,
            variables: parsedVars,
          }),
        });
        await refreshAllData();
        showToast("✅ 測試環境與全域變數已更新！");
      } catch (err) {
        showToast(`JSON 格式錯誤或儲存失敗: ${err.message}`);
      }
    });
  });
}

function openScenarioModal(scenario = null) {
  const modal = document.getElementById("scenario-modal");
  const envSelect = document.getElementById("form-scenario-env");
  envSelect.innerHTML = state.environments
    .map((e) => `<option value="${e.id}">${escapeHtml(e.name)} (${escapeHtml(e.base_url)})</option>`)
    .join("");

  if (scenario) {
    document.getElementById("form-scenario-id").value = scenario.id;
    document.getElementById("form-scenario-name").value = scenario.name;
    document.getElementById("form-scenario-env").value = scenario.environment_id;
    document.getElementById("form-scenario-desc").value = scenario.description;
    document.getElementById("form-scenario-tags").value = (scenario.tags || []).join(", ");
    document.getElementById("form-scenario-steps").value = JSON.stringify(scenario.steps, null, 2);
  } else {
    document.getElementById("form-scenario-id").value = "";
    document.getElementById("form-scenario-name").value = "";
    document.getElementById("form-scenario-desc").value = "";
    document.getElementById("form-scenario-tags").value = "API, Custom";
    loadSampleStepsIntoModal();
  }

  modal.classList.remove("hidden");
}

function loadSampleStepsIntoModal() {
  const sampleSteps = [
    {
      step_order: 1,
      name: "Step 1: 登入取得認證 Token",
      method: "POST",
      path: "/mock/auth/login",
      headers: { "Content-Type": "application/json" },
      body: { username: "qa_tester", password: "qa_secret_2026" },
      extractions: [{ var_name: "auth_token", jsonpath: "$.data.token" }],
      assertions: [
        { type: "status_code", operator: "eq", expected: 200 },
        { type: "jsonpath", path: "$.data.token", operator: "not_empty", expected: "" },
      ],
    },
    {
      step_order: 2,
      name: "Step 2: 查詢商品目錄並驗證回應時間",
      method: "GET",
      path: "/mock/products",
      headers: { Authorization: "Bearer {{auth_token}}" },
      body: {},
      extractions: [],
      assertions: [
        { type: "status_code", operator: "eq", expected: 200 },
        { type: "response_time_ms", operator: "lt", expected: 300 },
      ],
    },
  ];
  document.getElementById("form-scenario-steps").value = JSON.stringify(sampleSteps, null, 2);
}

function bindEvents() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  document.getElementById("chaos-select").addEventListener("change", async (e) => {
    const mode = e.target.value;
    await apiFetch("/api/chaos", {
      method: "POST",
      body: JSON.stringify({ mode }),
    });
    await refreshAllData();
    showToast(
      mode === "none"
        ? "🟢 已恢復靶機正常狀態"
        : "💥 已向靶機注入故障！現在點擊「執行驗證」即可觀察平台如何攔截 Bug"
    );
  });

  document.getElementById("btn-run-all").addEventListener("click", triggerBatchRuns);
  document.getElementById("btn-refresh-runs").addEventListener("click", refreshAllData);
  document.getElementById("btn-new-scenario").addEventListener("click", () => openScenarioModal(null));
  document.getElementById("btn-load-sample-steps").addEventListener("click", loadSampleStepsIntoModal);

  const closeModal = () => document.getElementById("scenario-modal").classList.add("hidden");
  document.getElementById("btn-close-modal").addEventListener("click", closeModal);
  document.getElementById("btn-cancel-modal").addEventListener("click", closeModal);

  document.getElementById("scenario-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const idVal = document.getElementById("form-scenario-id").value;
      const stepsParsed = JSON.parse(document.getElementById("form-scenario-steps").value);
      const tags = document
        .getElementById("form-scenario-tags")
        .value.split(",")
        .map((s) => s.trim())
        .filter(Boolean);

      const saved = await apiFetch("/api/scenarios", {
        method: "POST",
        body: JSON.stringify({
          id: idVal ? Number(idVal) : undefined,
          name: document.getElementById("form-scenario-name").value,
          environment_id: Number(document.getElementById("form-scenario-env").value),
          description: document.getElementById("form-scenario-desc").value,
          tags,
          steps: stepsParsed,
        }),
      });
      state.selectedScenarioId = saved.id;
      closeModal();
      await refreshAllData();
      showToast("✅ 測試場景已儲存！");
    } catch (err) {
      showToast(`儲存失敗 (請檢查 Steps JSON 語法): ${err.message}`);
    }
  });

  document.getElementById("btn-new-env").addEventListener("click", async () => {
    await apiFetch("/api/environments", {
      method: "POST",
      body: JSON.stringify({
        name: "External Public API (JSONPlaceholder)",
        base_url: "https://jsonplaceholder.typicode.com",
        description: "外部公開 REST API 測試環境",
        variables: { sample_user_id: 1 },
      }),
    });
    await refreshAllData();
    showToast("✅ 已新增外部測試環境！");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  refreshAllData();
});
