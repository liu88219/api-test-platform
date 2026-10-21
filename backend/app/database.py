"""SQLite persistence layer and initial seed data for the PulseAPI Test Platform."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "platform.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables and seed default environments and scenarios if empty."""
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS environments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            base_url TEXT NOT NULL,
            description TEXT DEFAULT '',
            variables_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            environment_id INTEGER NOT NULL,
            tags_json TEXT DEFAULT '[]',
            fail_fast INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scenario_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id INTEGER NOT NULL,
            step_order INTEGER NOT NULL,
            name TEXT NOT NULL,
            method TEXT NOT NULL,
            path TEXT NOT NULL,
            headers_json TEXT DEFAULT '{}',
            body_json TEXT DEFAULT '{}',
            extractions_json TEXT DEFAULT '[]',
            assertions_json TEXT DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS test_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id INTEGER NOT NULL,
            scenario_name TEXT NOT NULL,
            environment_name TEXT NOT NULL,
            base_url TEXT NOT NULL,
            status TEXT NOT NULL,
            passed_steps INTEGER NOT NULL,
            total_steps INTEGER NOT NULL,
            passed_assertions INTEGER NOT NULL,
            total_assertions INTEGER NOT NULL,
            duration_ms REAL NOT NULL,
            chaos_mode TEXT DEFAULT 'none',
            failure_diagnosis TEXT DEFAULT '',
            step_results_json TEXT NOT NULL,
            final_context_json TEXT DEFAULT '{}',
            triggered_by TEXT DEFAULT 'Manual UI',
            created_at TEXT NOT NULL
        );
        """
    )

    cur.execute("SELECT COUNT(*) AS cnt FROM environments")
    if cur.fetchone()["cnt"] == 0:
        _seed_default_data(conn)

    conn.commit()
    conn.close()


def _seed_default_data(conn: sqlite3.Connection) -> None:
    now = _utc_now()
    cur = conn.cursor()

    # 1. Seed Environments
    cur.execute(
        """
        INSERT INTO environments (name, base_url, description, variables_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "Built-in E-Commerce Target (Local)",
            "http://127.0.0.1:8080",
            "內建電商微服務靶機（支援登入、商品查詢、購物車、結帳與 Chaos Bug 模擬）",
            json.dumps(
                {
                    "test_user": "qa_lead_mona",
                    "test_pass": "qa_secret_2026",
                    "order_qty": 2,
                    "expected_total": 2598,
                }
            ),
            now,
        ),
    )
    env_local_id = cur.lastrowid

    cur.execute(
        """
        INSERT INTO environments (name, base_url, description, variables_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "Custom Staging / Localhost API",
            "http://localhost:3000",
            "可自由修改 Base URL 以對接你自己的後端專案或公開 API (如 ReqRes / JSONPlaceholder)",
            json.dumps({"api_version": "v1"}),
            now,
        ),
    )

    # 2. Seed Scenario 1: E2E E-Commerce Checkout Chain (4 chained steps)
    cur.execute(
        """
        INSERT INTO scenarios (name, description, environment_id, tags_json, fail_fast, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "🛒 電商金流完整下單鏈路 (E2E Checkout Flow)",
            "驗證「登入取 Token → 查詢商品庫存 → 加入購物車 → 結帳扣款」4 步驟跨 API 變數傳遞與金額斷言。",
            env_local_id,
            json.dumps(["E2E", "Checkout", "P0-Critical"]),
            1,
            now,
        ),
    )
    s1_id = cur.lastrowid

    s1_steps = [
        {
            "step_order": 1,
            "name": "Step 1: 會員登入並提取 Bearer Token",
            "method": "POST",
            "path": "/mock/auth/login",
            "headers": {"Content-Type": "application/json"},
            "body": {"username": "{{test_user}}", "password": "{{test_pass}}"},
            "extractions": [
                {"var_name": "auth_token", "jsonpath": "$.data.token"},
                {"var_name": "buyer_id", "jsonpath": "$.data.user.id"},
            ],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 200},
                {"type": "jsonpath", "path": "$.data.token", "operator": "not_empty", "expected": ""},
                {"type": "jsonpath", "path": "$.data.user.role", "operator": "eq", "expected": "VIP_BUYER"},
            ],
        },
        {
            "step_order": 2,
            "name": "Step 2: 取得商品列表並提取首筆商品 ID",
            "method": "GET",
            "path": "/mock/products",
            "headers": {},
            "body": {},
            "extractions": [
                {"var_name": "target_product_id", "jsonpath": "$.data.products[0].id"},
                {"var_name": "unit_price", "jsonpath": "$.data.products[0].price"},
            ],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 200},
                {"type": "jsonpath", "path": "$.data.products[0].stock", "operator": "gt", "expected": 0},
                {"type": "jsonpath", "path": "$.data.products[0].price", "operator": "eq", "expected": 1299},
            ],
        },
        {
            "step_order": 3,
            "name": "Step 3: 帶入 Token 與商品 ID 加入購物車",
            "method": "POST",
            "path": "/mock/cart/items",
            "headers": {"Authorization": "Bearer {{auth_token}}"},
            "body": {"product_id": "{{target_product_id}}", "quantity": "{{order_qty}}"},
            "extractions": [
                {"var_name": "active_cart_id", "jsonpath": "$.data.cart_id"},
            ],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 200},
                {"type": "jsonpath", "path": "$.data.cart_total", "operator": "eq", "expected": "{{expected_total}}"},
            ],
        },
        {
            "step_order": 4,
            "name": "Step 4: 建立結帳訂單並驗證實付金額與狀態",
            "method": "POST",
            "path": "/mock/orders/checkout",
            "headers": {"Authorization": "Bearer {{auth_token}}"},
            "body": {"cart_id": "{{active_cart_id}}", "payment_method": "CREDIT_CARD"},
            "extractions": [
                {"var_name": "final_order_id", "jsonpath": "$.data.order.order_id"},
            ],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 201},
                {"type": "jsonpath", "path": "$.data.order.status", "operator": "eq", "expected": "PAID"},
                {
                    "type": "jsonpath",
                    "path": "$.data.order.charged_amount",
                    "operator": "eq",
                    "expected": "{{expected_total}}",
                },
                {"type": "response_time_ms", "operator": "lt", "expected": 500},
            ],
        },
    ]

    for step in s1_steps:
        cur.execute(
            """
            INSERT INTO scenario_steps
            (scenario_id, step_order, name, method, path, headers_json, body_json, extractions_json, assertions_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s1_id,
                step["step_order"],
                step["name"],
                step["method"],
                step["path"],
                json.dumps(step["headers"]),
                json.dumps(step["body"]),
                json.dumps(step["extractions"]),
                json.dumps(step["assertions"]),
            ),
        )

    # 3. Seed Scenario 2: Security & Negative Boundary Testing (3 steps)
    cur.execute(
        """
        INSERT INTO scenarios (name, description, environment_id, tags_json, fail_fast, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "🔒 權限防護與邊界負向測試 (Auth & Negative Boundary Suite)",
            "驗證未授權攔截 (401)、非法負數購買量攔截 (400)、以及不存在商品的錯誤碼契約 (404)。",
            env_local_id,
            json.dumps(["Security", "Negative-Test", "Boundary"]),
            0,
            now,
        ),
    )
    s2_id = cur.lastrowid

    s2_steps = [
        {
            "step_order": 1,
            "name": "Step 1: 未帶 Token 直接呼叫結帳應攔截 (401 Unauthorized)",
            "method": "POST",
            "path": "/mock/orders/checkout",
            "headers": {},
            "body": {"cart_id": "CART-FAKE"},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 401},
                {"type": "jsonpath", "path": "$.error.code", "operator": "eq", "expected": "UNAUTHORIZED"},
            ],
        },
        {
            "step_order": 2,
            "name": "Step 2: 購買負數數量 (-5) 應觸發邊界值校驗 (400 Bad Request)",
            "method": "POST",
            "path": "/mock/cart/items",
            "headers": {"Authorization": "Bearer tok_boundary_test"},
            "body": {"product_id": "PROD-101", "quantity": -5},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 400},
                {"type": "jsonpath", "path": "$.error.code", "operator": "eq", "expected": "INVALID_QUANTITY"},
            ],
        },
        {
            "step_order": 3,
            "name": "Step 3: 查詢不存在的商品編號應回傳標準 404 結構",
            "method": "GET",
            "path": "/mock/products/PROD-99999",
            "headers": {},
            "body": {},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 404},
                {"type": "jsonpath", "path": "$.error.code", "operator": "eq", "expected": "PRODUCT_NOT_FOUND"},
            ],
        },
    ]

    for step in s2_steps:
        cur.execute(
            """
            INSERT INTO scenario_steps
            (scenario_id, step_order, name, method, path, headers_json, body_json, extractions_json, assertions_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s2_id,
                step["step_order"],
                step["name"],
                step["method"],
                step["path"],
                json.dumps(step["headers"]),
                json.dumps(step["body"]),
                json.dumps(step["extractions"]),
                json.dumps(step["assertions"]),
            ),
        )

    # 4. Seed Scenario 3: Health & Latency SLA Probe
    cur.execute(
        """
        INSERT INTO scenarios (name, description, environment_id, tags_json, fail_fast, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "⚡ 核心服務健康度與 SLA 耗時巡檢 (Health & Latency SLA Probe)",
            "監控微服務健康檢查端點與商品目錄回應時間是否低於 200ms SLO 門檻。",
            env_local_id,
            json.dumps(["Smoke", "SLA-Monitor"]),
            1,
            now,
        ),
    )
    s3_id = cur.lastrowid

    s3_steps = [
        {
            "step_order": 1,
            "name": "Step 1: 微服務 Health Check 端點檢查",
            "method": "GET",
            "path": "/mock/health",
            "headers": {},
            "body": {},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 200},
                {"type": "jsonpath", "path": "$.status", "operator": "eq", "expected": "healthy"},
                {"type": "response_time_ms", "operator": "lt", "expected": 200},
            ],
        },
        {
            "step_order": 2,
            "name": "Step 2: 商品目錄讀取效能 SLA (< 200ms)",
            "method": "GET",
            "path": "/mock/products",
            "headers": {},
            "body": {},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 200},
                {"type": "jsonpath", "path": "$.data.products.length", "operator": "gte", "expected": 2},
                {"type": "response_time_ms", "operator": "lt", "expected": 200},
            ],
        },
    ]

    for step in s3_steps:
        cur.execute(
            """
            INSERT INTO scenario_steps
            (scenario_id, step_order, name, method, path, headers_json, body_json, extractions_json, assertions_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s3_id,
                step["step_order"],
                step["name"],
                step["method"],
                step["path"],
                json.dumps(step["headers"]),
                json.dumps(step["body"]),
                json.dumps(step["extractions"]),
                json.dumps(step["assertions"]),
            ),
        )

    # 5. Seed Scenario 4: Payment Idempotency & Duplicate Checkout Guard
    cur.execute(
        """
        INSERT INTO scenarios (name, description, environment_id, tags_json, fail_fast, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "💳 金流冪等性與防重複扣款測試 (Idempotency & Duplicate Checkout Guard)",
            "模擬使用者連點兩次結帳按鈕，驗證首次結帳成功 (201) 後，同一購物車二次重複結帳必須攔截回傳 409 DUPLICATE_CHECKOUT。",
            env_local_id,
            json.dumps(["Idempotency", "Payment-Safety", "P0-Critical"]),
            1,
            now,
        ),
    )
    s4_id = cur.lastrowid

    s4_steps = [
        {
            "step_order": 1,
            "name": "Step 1: 登入取得合法 Bearer Token",
            "method": "POST",
            "path": "/mock/auth/login",
            "headers": {"Content-Type": "application/json"},
            "body": {"username": "{{test_user}}", "password": "{{test_pass}}"},
            "extractions": [{"var_name": "idem_token", "jsonpath": "$.data.token"}],
            "assertions": [{"type": "status_code", "operator": "eq", "expected": 200}],
        },
        {
            "step_order": 2,
            "name": "Step 2: 建立待結帳購物車並提取 Cart ID",
            "method": "POST",
            "path": "/mock/cart/items",
            "headers": {"Authorization": "Bearer {{idem_token}}"},
            "body": {"product_id": "PROD-101", "quantity": 1},
            "extractions": [{"var_name": "idem_cart_id", "jsonpath": "$.data.cart_id"}],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 200},
                {"type": "jsonpath", "path": "$.data.cart_id", "operator": "not_empty", "expected": ""},
            ],
        },
        {
            "step_order": 3,
            "name": "Step 3: 首次提交結帳請求應成功扣款 (201 Created)",
            "method": "POST",
            "path": "/mock/orders/checkout",
            "headers": {"Authorization": "Bearer {{idem_token}}"},
            "body": {"cart_id": "{{idem_cart_id}}", "payment_method": "CREDIT_CARD"},
            "extractions": [{"var_name": "first_order_id", "jsonpath": "$.data.order.order_id"}],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 201},
                {"type": "jsonpath", "path": "$.data.order.status", "operator": "eq", "expected": "PAID"},
            ],
        },
        {
            "step_order": 4,
            "name": "Step 4: 重複提交同一購物車結帳應觸發冪等攔截 (409 Conflict)",
            "method": "POST",
            "path": "/mock/orders/checkout",
            "headers": {"Authorization": "Bearer {{idem_token}}"},
            "body": {"cart_id": "{{idem_cart_id}}", "payment_method": "CREDIT_CARD"},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 409},
                {"type": "jsonpath", "path": "$.error.code", "operator": "eq", "expected": "DUPLICATE_CHECKOUT"},
            ],
        },
    ]

    for step in s4_steps:
        cur.execute(
            """
            INSERT INTO scenario_steps
            (scenario_id, step_order, name, method, path, headers_json, body_json, extractions_json, assertions_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s4_id,
                step["step_order"],
                step["name"],
                step["method"],
                step["path"],
                json.dumps(step["headers"]),
                json.dumps(step["body"]),
                json.dumps(step["extractions"]),
                json.dumps(step["assertions"]),
            ),
        )

    # 6. Seed Scenario 5: Inventory Overselling & Full Boundary Value Analysis (BVA)
    cur.execute(
        """
        INSERT INTO scenarios (name, description, environment_id, tags_json, fail_fast, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "📦 庫存超賣防護與完整邊界值分析 (Inventory Overselling & Full BVA)",
            "依據邊界值分析法 (BVA) 驗證零值 (0)、超出單筆上限 (100)、以及超過商品實際庫存量 (50 > 42) 的防超賣攔截。",
            env_local_id,
            json.dumps(["Boundary-BVA", "Inventory-Guard", "P1"]),
            0,
            now,
        ),
    )
    s5_id = cur.lastrowid

    s5_steps = [
        {
            "step_order": 1,
            "name": "Step 1: 零值邊界測試 (quantity = 0) 應攔截回傳 400",
            "method": "POST",
            "path": "/mock/cart/items",
            "headers": {"Authorization": "Bearer tok_bva_tester"},
            "body": {"product_id": "PROD-101", "quantity": 0},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 400},
                {"type": "jsonpath", "path": "$.error.code", "operator": "eq", "expected": "INVALID_QUANTITY"},
            ],
        },
        {
            "step_order": 2,
            "name": "Step 2: 單筆上限邊界測試 (quantity = 100 > 99) 應攔截回傳 400",
            "method": "POST",
            "path": "/mock/cart/items",
            "headers": {"Authorization": "Bearer tok_bva_tester"},
            "body": {"product_id": "PROD-101", "quantity": 100},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 400},
                {"type": "jsonpath", "path": "$.error.code", "operator": "eq", "expected": "INVALID_QUANTITY"},
            ],
        },
        {
            "step_order": 3,
            "name": "Step 3: 庫存超賣防護測試 (購買 50 件 > 現貨 42 件) 應回傳 409",
            "method": "POST",
            "path": "/mock/cart/items",
            "headers": {"Authorization": "Bearer tok_bva_tester"},
            "body": {"product_id": "PROD-101", "quantity": 50},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 409},
                {"type": "jsonpath", "path": "$.error.code", "operator": "eq", "expected": "INSUFFICIENT_STOCK"},
                {"type": "jsonpath", "path": "$.error.available_stock", "operator": "eq", "expected": 42},
            ],
        },
    ]

    for step in s5_steps:
        cur.execute(
            """
            INSERT INTO scenario_steps
            (scenario_id, step_order, name, method, path, headers_json, body_json, extractions_json, assertions_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s5_id,
                step["step_order"],
                step["name"],
                step["method"],
                step["path"],
                json.dumps(step["headers"]),
                json.dumps(step["body"]),
                json.dumps(step["extractions"]),
                json.dumps(step["assertions"]),
            ),
        )

    # 7. Seed Scenario 6: Coupon & Pricing Decision Matrix
    cur.execute(
        """
        INSERT INTO scenarios (name, description, environment_id, tags_json, fail_fast, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "🎟️ 優惠券折抵與計價邏輯決策表 (Coupon & Pricing Decision Matrix)",
            "運用決策表測試法驗證有效折扣碼 (VIP200 折抵 200 元)、過期折扣碼 (EXPIRED2020) 與偽造折扣碼 (FAKE999)。",
            env_local_id,
            json.dumps(["Decision-Table", "Pricing", "P1"]),
            0,
            now,
        ),
    )
    s6_id = cur.lastrowid

    s6_steps = [
        {
            "step_order": 1,
            "name": "Step 1: 建立購物車 (原價 2598 元)",
            "method": "POST",
            "path": "/mock/cart/items",
            "headers": {"Authorization": "Bearer tok_coupon_tester"},
            "body": {"product_id": "PROD-101", "quantity": 2},
            "extractions": [{"var_name": "coupon_cart_id", "jsonpath": "$.data.cart_id"}],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 200},
                {"type": "jsonpath", "path": "$.data.cart_total", "operator": "eq", "expected": 2598},
            ],
        },
        {
            "step_order": 2,
            "name": "Step 2: 套用有效優惠碼 VIP200 應折抵 200 元 (實付 2398 元)",
            "method": "POST",
            "path": "/mock/orders/checkout",
            "headers": {"Authorization": "Bearer tok_coupon_tester"},
            "body": {"cart_id": "{{coupon_cart_id}}", "coupon_code": "VIP200"},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 201},
                {"type": "jsonpath", "path": "$.data.order.discount_amount", "operator": "eq", "expected": 200},
                {"type": "jsonpath", "path": "$.data.order.charged_amount", "operator": "eq", "expected": 2398},
            ],
        },
        {
            "step_order": 3,
            "name": "Step 3: 套用過期優惠碼 EXPIRED2020 應攔截回傳 400",
            "method": "POST",
            "path": "/mock/orders/checkout",
            "headers": {"Authorization": "Bearer tok_coupon_tester"},
            "body": {"cart_id": "{{coupon_cart_id}}", "coupon_code": "EXPIRED2020"},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 400},
                {"type": "jsonpath", "path": "$.error.code", "operator": "eq", "expected": "COUPON_EXPIRED"},
            ],
        },
        {
            "step_order": 4,
            "name": "Step 4: 套用不存在的偽造優惠碼 FAKE999 應攔截回傳 400",
            "method": "POST",
            "path": "/mock/orders/checkout",
            "headers": {"Authorization": "Bearer tok_coupon_tester"},
            "body": {"cart_id": "{{coupon_cart_id}}", "coupon_code": "FAKE999"},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 400},
                {"type": "jsonpath", "path": "$.error.code", "operator": "eq", "expected": "INVALID_COUPON"},
            ],
        },
    ]

    for step in s6_steps:
        cur.execute(
            """
            INSERT INTO scenario_steps
            (scenario_id, step_order, name, method, path, headers_json, body_json, extractions_json, assertions_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s6_id,
                step["step_order"],
                step["name"],
                step["method"],
                step["path"],
                json.dumps(step["headers"]),
                json.dumps(step["body"]),
                json.dumps(step["extractions"]),
                json.dumps(step["assertions"]),
            ),
        )

    # 8. Seed Scenario 7: OWASP API Security (BOLA & RBAC Authorization Guard)
    cur.execute(
        """
        INSERT INTO scenarios (name, description, environment_id, tags_json, fail_fast, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "🔐 越權存取與角色權限防護 (OWASP API Security: BOLA & RBAC)",
            "驗證錯誤密碼登入攔截 (401)、買家垂直越權呼叫管理員刪商品 API (403 ADMIN_ONLY)、以及水平越權偷看他人訂單 (403 BOLA)。",
            env_local_id,
            json.dumps(["OWASP-Security", "BOLA-RBAC", "P0-Critical"]),
            0,
            now,
        ),
    )
    s7_id = cur.lastrowid

    s7_steps = [
        {
            "step_order": 1,
            "name": "Step 1: 輸入錯誤密碼登入應拒絕發放 Token (401 Unauthorized)",
            "method": "POST",
            "path": "/mock/auth/login",
            "headers": {"Content-Type": "application/json"},
            "body": {"username": "{{test_user}}", "password": "wrong_password_123"},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 401},
                {"type": "jsonpath", "path": "$.error.code", "operator": "eq", "expected": "INVALID_CREDENTIALS"},
            ],
        },
        {
            "step_order": 2,
            "name": "Step 2: 垂直越權測試 (RBAC) — 一般買家呼叫管理員刪除商品 API 應回傳 403",
            "method": "DELETE",
            "path": "/mock/admin/products/PROD-101",
            "headers": {"Authorization": "Bearer tok_buyer_role"},
            "body": {},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 403},
                {"type": "jsonpath", "path": "$.error.code", "operator": "eq", "expected": "ADMIN_ONLY"},
            ],
        },
        {
            "step_order": 3,
            "name": "Step 3: 水平越權測試 (BOLA) — 嘗試讀取其他買家的私密訂單應回傳 403",
            "method": "GET",
            "path": "/mock/orders/ORD-OTHER-999",
            "headers": {"Authorization": "Bearer tok_buyer_role"},
            "body": {},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 403},
                {"type": "jsonpath", "path": "$.error.code", "operator": "eq", "expected": "FORBIDDEN_ORDER_ACCESS"},
            ],
        },
    ]

    for step in s7_steps:
        cur.execute(
            """
            INSERT INTO scenario_steps
            (scenario_id, step_order, name, method, path, headers_json, body_json, extractions_json, assertions_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s7_id,
                step["step_order"],
                step["name"],
                step["method"],
                step["path"],
                json.dumps(step["headers"]),
                json.dumps(step["body"]),
                json.dumps(step["extractions"]),
                json.dumps(step["assertions"]),
            ),
        )

    # 9. Seed Scenario 8: Order State Machine Lifecycle Transition
    cur.execute(
        """
        INSERT INTO scenarios (name, description, environment_id, tags_json, fail_fast, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "🔄 訂單狀態機生命週期測試 (Order State Machine Transition)",
            "依據狀態轉換測試法驗證訂單由「已付款 (PAID) → 申請退款 (REFUNDED) → 禁止二次重複退款 (409 ORDER_ALREADY_REFUNDED)」。",
            env_local_id,
            json.dumps(["State-Machine", "Order-Lifecycle", "P1"]),
            1,
            now,
        ),
    )
    s8_id = cur.lastrowid

    s8_steps = [
        {
            "step_order": 1,
            "name": "Step 1: 建立待測試購物車",
            "method": "POST",
            "path": "/mock/cart/items",
            "headers": {"Authorization": "Bearer tok_state_tester"},
            "body": {"product_id": "PROD-101", "quantity": 1},
            "extractions": [{"var_name": "state_cart_id", "jsonpath": "$.data.cart_id"}],
            "assertions": [{"type": "status_code", "operator": "eq", "expected": 200}],
        },
        {
            "step_order": 2,
            "name": "Step 2: 結帳建立新訂單 (初始狀態 PAID)",
            "method": "POST",
            "path": "/mock/orders/checkout",
            "headers": {"Authorization": "Bearer tok_state_tester"},
            "body": {"cart_id": "{{state_cart_id}}"},
            "extractions": [{"var_name": "state_order_id", "jsonpath": "$.data.order.order_id"}],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 201},
                {"type": "jsonpath", "path": "$.data.order.status", "operator": "eq", "expected": "PAID"},
            ],
        },
        {
            "step_order": 3,
            "name": "Step 3: 首次申請取消退款，狀態應轉換為 REFUNDED (200 OK)",
            "method": "POST",
            "path": "/mock/orders/{{state_order_id}}/refund",
            "headers": {"Authorization": "Bearer tok_state_tester"},
            "body": {"reason": "Customer requested cancellation"},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 200},
                {"type": "jsonpath", "path": "$.data.order.status", "operator": "eq", "expected": "REFUNDED"},
            ],
        },
        {
            "step_order": 4,
            "name": "Step 4: 對已退款訂單再次呼叫退款，應攔截非法狀態轉換 (409 Conflict)",
            "method": "POST",
            "path": "/mock/orders/{{state_order_id}}/refund",
            "headers": {"Authorization": "Bearer tok_state_tester"},
            "body": {"reason": "Duplicate refund attempt"},
            "extractions": [],
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 409},
                {"type": "jsonpath", "path": "$.error.code", "operator": "eq", "expected": "ORDER_ALREADY_REFUNDED"},
            ],
        },
    ]

    for step in s8_steps:
        cur.execute(
            """
            INSERT INTO scenario_steps
            (scenario_id, step_order, name, method, path, headers_json, body_json, extractions_json, assertions_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s8_id,
                step["step_order"],
                step["name"],
                step["method"],
                step["path"],
                json.dumps(step["headers"]),
                json.dumps(step["body"]),
                json.dumps(step["extractions"]),
                json.dumps(step["assertions"]),
            ),
        )


def list_environments() -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM environments ORDER BY id ASC").fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "base_url": r["base_url"],
            "description": r["description"],
            "variables": json.loads(r["variables_json"] or "{}"),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def create_or_update_environment(data: dict[str, Any]) -> dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    env_id = data.get("id")
    name = (data.get("name") or "New Environment").strip()
    base_url = (data.get("base_url") or "http://localhost:8080").strip()
    description = data.get("description") or ""
    variables = data.get("variables") or {}

    if env_id:
        cur.execute(
            """
            UPDATE environments
            SET name = ?, base_url = ?, description = ?, variables_json = ?
            WHERE id = ?
            """,
            (name, base_url, description, json.dumps(variables), env_id),
        )
    else:
        cur.execute(
            """
            INSERT INTO environments (name, base_url, description, variables_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, base_url, description, json.dumps(variables), _utc_now()),
        )
        env_id = cur.lastrowid

    conn.commit()
    conn.close()
    envs = [e for e in list_environments() if e["id"] == env_id]
    return envs[0] if envs else {}


def get_scenario(scenario_id: int) -> dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()
    if not row:
        conn.close()
        return None

    env_row = conn.execute(
        "SELECT * FROM environments WHERE id = ?", (row["environment_id"],)
    ).fetchone()
    step_rows = conn.execute(
        "SELECT * FROM scenario_steps WHERE scenario_id = ? ORDER BY step_order ASC, id ASC",
        (scenario_id,),
    ).fetchall()
    last_run = conn.execute(
        "SELECT id, status, duration_ms, created_at, passed_assertions, total_assertions "
        "FROM test_runs WHERE scenario_id = ? ORDER BY id DESC LIMIT 1",
        (scenario_id,),
    ).fetchone()
    conn.close()

    steps = [
        {
            "id": s["id"],
            "step_order": s["step_order"],
            "name": s["name"],
            "method": s["method"],
            "path": s["path"],
            "headers": json.loads(s["headers_json"] or "{}"),
            "body": json.loads(s["body_json"] or "{}"),
            "extractions": json.loads(s["extractions_json"] or "[]"),
            "assertions": json.loads(s["assertions_json"] or "[]"),
        }
        for s in step_rows
    ]

    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "environment_id": row["environment_id"],
        "environment_name": env_row["name"] if env_row else "Default",
        "base_url": env_row["base_url"] if env_row else "http://127.0.0.1:8080",
        "environment_variables": json.loads(env_row["variables_json"] or "{}") if env_row else {},
        "tags": json.loads(row["tags_json"] or "[]"),
        "fail_fast": bool(row["fail_fast"]),
        "steps": steps,
        "last_run": dict(last_run) if last_run else None,
        "created_at": row["created_at"],
    }


def list_scenarios() -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT id FROM scenarios ORDER BY id ASC").fetchall()
    conn.close()
    result = []
    for r in rows:
        sc = get_scenario(r["id"])
        if sc:
            result.append(sc)
    return result


def save_scenario(data: dict[str, Any]) -> dict[str, Any]:
    """Create or update a Scenario along with its steps."""
    conn = get_connection()
    cur = conn.cursor()
    scenario_id = data.get("id")
    name = (data.get("name") or "Untitled Scenario").strip()
    description = data.get("description") or ""
    environment_id = int(data.get("environment_id") or 1)
    tags = data.get("tags") if isinstance(data.get("tags"), list) else ["API"]
    fail_fast = 1 if data.get("fail_fast", True) else 0
    steps = data.get("steps") or []

    if scenario_id:
        cur.execute(
            """
            UPDATE scenarios
            SET name = ?, description = ?, environment_id = ?, tags_json = ?, fail_fast = ?
            WHERE id = ?
            """,
            (name, description, environment_id, json.dumps(tags), fail_fast, scenario_id),
        )
        cur.execute("DELETE FROM scenario_steps WHERE scenario_id = ?", (scenario_id,))
    else:
        cur.execute(
            """
            INSERT INTO scenarios (name, description, environment_id, tags_json, fail_fast, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, description, environment_id, json.dumps(tags), fail_fast, _utc_now()),
        )
        scenario_id = cur.lastrowid

    for idx, step in enumerate(steps, start=1):
        cur.execute(
            """
            INSERT INTO scenario_steps
            (scenario_id, step_order, name, method, path, headers_json, body_json, extractions_json, assertions_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scenario_id,
                int(step.get("step_order") or idx),
                step.get("name") or f"Step {idx}",
                (step.get("method") or "GET").upper(),
                step.get("path") or "/",
                json.dumps(step.get("headers") or {}),
                json.dumps(step.get("body") if step.get("body") is not None else {}),
                json.dumps(step.get("extractions") or []),
                json.dumps(step.get("assertions") or []),
            ),
        )

    conn.commit()
    conn.close()
    return get_scenario(int(scenario_id)) or {}


def delete_scenario(scenario_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM scenario_steps WHERE scenario_id = ?", (scenario_id,))
    cur.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def record_test_run(
    scenario: dict[str, Any],
    run_output: dict[str, Any],
    chaos_mode: str = "none",
    triggered_by: str = "Manual UI",
) -> dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    now = _utc_now()

    cur.execute(
        """
        INSERT INTO test_runs
        (scenario_id, scenario_name, environment_name, base_url, status,
         passed_steps, total_steps, passed_assertions, total_assertions,
         duration_ms, chaos_mode, failure_diagnosis, step_results_json,
         final_context_json, triggered_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scenario["id"],
            scenario["name"],
            scenario["environment_name"],
            scenario["base_url"],
            run_output["status"],
            run_output["passed_steps"],
            run_output["total_steps"],
            run_output["passed_assertions"],
            run_output["total_assertions"],
            run_output["duration_ms"],
            chaos_mode,
            run_output.get("failure_diagnosis") or "",
            json.dumps(run_output["step_results"]),
            json.dumps(run_output.get("final_context") or {}),
            triggered_by,
            now,
        ),
    )
    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return get_test_run(int(run_id)) or {}


def get_test_run(run_id: int) -> dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM test_runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "scenario_id": row["scenario_id"],
        "scenario_name": row["scenario_name"],
        "environment_name": row["environment_name"],
        "base_url": row["base_url"],
        "status": row["status"],
        "passed_steps": row["passed_steps"],
        "total_steps": row["total_steps"],
        "passed_assertions": row["passed_assertions"],
        "total_assertions": row["total_assertions"],
        "duration_ms": row["duration_ms"],
        "chaos_mode": row["chaos_mode"],
        "failure_diagnosis": row["failure_diagnosis"],
        "step_results": json.loads(row["step_results_json"] or "[]"),
        "final_context": json.loads(row["final_context_json"] or "{}"),
        "triggered_by": row["triggered_by"],
        "created_at": row["created_at"],
    }


def list_test_runs(limit: int = 30) -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM test_runs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "scenario_id": r["scenario_id"],
            "scenario_name": r["scenario_name"],
            "environment_name": r["environment_name"],
            "base_url": r["base_url"],
            "status": r["status"],
            "passed_steps": r["passed_steps"],
            "total_steps": r["total_steps"],
            "passed_assertions": r["passed_assertions"],
            "total_assertions": r["total_assertions"],
            "duration_ms": r["duration_ms"],
            "chaos_mode": r["chaos_mode"],
            "failure_diagnosis": r["failure_diagnosis"],
            "triggered_by": r["triggered_by"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def get_dashboard_stats() -> dict[str, Any]:
    conn = get_connection()
    total_scenarios = conn.execute("SELECT COUNT(*) AS c FROM scenarios").fetchone()["c"]
    total_steps = conn.execute("SELECT COUNT(*) AS c FROM scenario_steps").fetchone()["c"]
    runs = conn.execute(
        "SELECT id, scenario_name, status, duration_ms, passed_assertions, total_assertions, created_at "
        "FROM test_runs ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()

    total_runs = len(runs)
    passed_runs = sum(1 for r in runs if r["status"] == "PASSED")
    failed_runs = total_runs - passed_runs
    pass_rate = round((passed_runs / total_runs) * 100, 1) if total_runs > 0 else 100.0
    avg_duration = (
        round(sum(r["duration_ms"] for r in runs) / total_runs, 2) if total_runs > 0 else 0.0
    )

    recent_trend = [
        {
            "id": r["id"],
            "scenario_name": r["scenario_name"],
            "status": r["status"],
            "duration_ms": r["duration_ms"],
            "passed_assertions": r["passed_assertions"],
            "total_assertions": r["total_assertions"],
            "created_at": r["created_at"],
        }
        for r in reversed(runs[:15])
    ]

    return {
        "total_scenarios": total_scenarios,
        "total_steps": total_steps,
        "total_runs": total_runs,
        "passed_runs": passed_runs,
        "failed_runs": failed_runs,
        "pass_rate": pass_rate,
        "avg_duration_ms": avg_duration,
        "recent_trend": recent_trend,
    }
