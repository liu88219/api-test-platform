"""Built-in Demo Target E-Commerce API with Chaos Bug Injection for live QA demos."""

from __future__ import annotations

import json
import uuid
from typing import Any

# Global state for the Demo Target API
CHAOS_STATE: dict[str, Any] = {
    "mode": "none",  # Options: "none", "pricing_bug", "server_500_bug"
    "description": "正常運作中 (All services healthy)",
}

PRODUCTS_DB: dict[str, dict[str, Any]] = {
    "PROD-101": {
        "id": "PROD-101",
        "name": "Mechanical Keyboard Pro",
        "price": 1299,
        "stock": 42,
        "category": "Peripherals",
    },
    "PROD-102": {
        "id": "PROD-102",
        "name": "4K UltraWide Monitor",
        "price": 8999,
        "stock": 15,
        "category": "Displays",
    },
}

CARTS_DB: dict[str, dict[str, Any]] = {}
VALID_TOKENS: dict[str, dict[str, Any]] = {}


def get_chaos_state() -> dict[str, Any]:
    return dict(CHAOS_STATE)


def set_chaos_mode(mode: str) -> dict[str, Any]:
    descriptions = {
        "none": "正常運作中 (All services healthy)",
        "pricing_bug": "💥 [Bug 已注入] 結帳折扣計算異常（應收 2598 元，卻多扣 500 元變成 3098 元）",
        "server_500_bug": "💥 [Bug 已注入] 金流微服務連線中斷（/mock/orders/checkout 回傳 500 Internal Server Error）",
    }
    clean_mode = mode if mode in descriptions else "none"
    CHAOS_STATE["mode"] = clean_mode
    CHAOS_STATE["description"] = descriptions[clean_mode]
    return get_chaos_state()


def handle_mock_request(
    method: str,
    path: str,
    headers: dict[str, str],
    body: Any,
) -> tuple[int, dict[str, str], str]:
    """Process requests targeting /mock/* endpoints."""
    resp_headers = {"Content-Type": "application/json", "X-Mock-Service": "Demo-ECommerce-v1"}
    norm_headers = {k.lower(): v for k, v in (headers or {}).items()}

    if isinstance(body, str) and body.strip():
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}
    elif isinstance(body, dict):
        payload = body
    else:
        payload = {}

    # 1. GET /mock/health
    if method == "GET" and path == "/mock/health":
        return (
            200,
            resp_headers,
            json.dumps(
                {
                    "status": "healthy",
                    "service": "demo-ecommerce-api",
                    "chaos_mode": CHAOS_STATE["mode"],
                }
            ),
        )

    # 2. POST /mock/auth/login
    if method == "POST" and path == "/mock/auth/login":
        username = payload.get("username", "")
        password = payload.get("password", "")
        if not username or password != "qa_secret_2026":
            return (
                401,
                resp_headers,
                json.dumps(
                    {
                        "success": False,
                        "error": {"code": "INVALID_CREDENTIALS", "message": "Invalid username or password"},
                    }
                ),
            )
        token = f"tok_{uuid.uuid4().hex[:16]}"
        user_obj = {"id": "USR-8801", "username": username, "role": "VIP_BUYER"}
        VALID_TOKENS[token] = user_obj
        return (
            200,
            resp_headers,
            json.dumps(
                {
                    "success": True,
                    "data": {
                        "token": token,
                        "user": user_obj,
                    },
                }
            ),
        )

    # 3. GET /mock/products
    if method == "GET" and path == "/mock/products":
        return (
            200,
            resp_headers,
            json.dumps({"success": True, "data": {"products": list(PRODUCTS_DB.values())}}),
        )

    # 4. GET /mock/products/<id>
    if method == "GET" and path.startswith("/mock/products/"):
        prod_id = path.split("/mock/products/", 1)[1].strip("/")
        if prod_id not in PRODUCTS_DB:
            return (
                404,
                resp_headers,
                json.dumps(
                    {
                        "success": False,
                        "error": {
                            "code": "PRODUCT_NOT_FOUND",
                            "message": f"Product {prod_id} does not exist",
                        },
                    }
                ),
            )
        return (
            200,
            resp_headers,
            json.dumps({"success": True, "data": PRODUCTS_DB[prod_id]}),
        )

    # Helper to verify Bearer token for protected endpoints
    def _check_auth() -> tuple[bool, dict[str, Any] | None]:
        auth_val = norm_headers.get("authorization", "")
        if not auth_val.startswith("Bearer "):
            return False, None
        tok = auth_val.replace("Bearer ", "", 1).strip()
        if tok in VALID_TOKENS or tok.startswith("tok_"):
            return True, VALID_TOKENS.get(tok, {"id": "USR-8801", "username": "qa_engineer"})
        return False, None

    # 5. POST /mock/cart/items
    if method == "POST" and path == "/mock/cart/items":
        authed, _ = _check_auth()
        if not authed:
            return (
                401,
                resp_headers,
                json.dumps(
                    {
                        "success": False,
                        "error": {"code": "UNAUTHORIZED", "message": "Missing or invalid Bearer token"},
                    }
                ),
            )

        product_id = payload.get("product_id", "PROD-101")
        try:
            quantity = int(payload.get("quantity", 1))
        except (TypeError, ValueError):
            quantity = -1

        if quantity <= 0 or quantity > 99:
            return (
                400,
                resp_headers,
                json.dumps(
                    {
                        "success": False,
                        "error": {
                            "code": "INVALID_QUANTITY",
                            "message": "Quantity must be between 1 and 99",
                        },
                    }
                ),
            )

        product = PRODUCTS_DB.get(product_id)
        if not product:
            return (
                404,
                resp_headers,
                json.dumps(
                    {
                        "success": False,
                        "error": {"code": "PRODUCT_NOT_FOUND", "message": "Product not found"},
                    }
                ),
            )

        cart_id = f"CART-{uuid.uuid4().hex[:8].upper()}"
        cart_total = product["price"] * quantity
        CARTS_DB[cart_id] = {
            "cart_id": cart_id,
            "product_id": product_id,
            "quantity": quantity,
            "unit_price": product["price"],
            "cart_total": cart_total,
        }
        return (
            200,
            resp_headers,
            json.dumps(
                {
                    "success": True,
                    "data": CARTS_DB[cart_id],
                }
            ),
        )

    # 6. POST /mock/orders/checkout
    if method == "POST" and path == "/mock/orders/checkout":
        authed, user = _check_auth()
        if not authed:
            return (
                401,
                resp_headers,
                json.dumps(
                    {
                        "success": False,
                        "error": {"code": "UNAUTHORIZED", "message": "Missing or invalid Bearer token"},
                    }
                ),
            )

        if CHAOS_STATE["mode"] == "server_500_bug":
            return (
                500,
                resp_headers,
                json.dumps(
                    {
                        "success": False,
                        "error": {
                            "code": "PAYMENT_GATEWAY_CRASH",
                            "message": "Database connection pool exhausted during payment settlement",
                        },
                    }
                ),
            )

        cart_id = payload.get("cart_id", "")
        cart = CARTS_DB.get(cart_id, {"cart_total": 2598, "product_id": "PROD-101", "quantity": 2})
        charged_amount = cart["cart_total"]

        # Inject pricing bug when chaos mode == "pricing_bug"
        if CHAOS_STATE["mode"] == "pricing_bug":
            charged_amount = charged_amount + 500  # Deliberate overcharge bug!

        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        return (
            201,
            resp_headers,
            json.dumps(
                {
                    "success": True,
                    "data": {
                        "order": {
                            "order_id": order_id,
                            "cart_id": cart_id,
                            "buyer_id": user["id"] if user else "USR-8801",
                            "status": "PAID",
                            "charged_amount": charged_amount,
                            "currency": "TWD",
                        }
                    },
                }
            ),
        )

    return (
        404,
        resp_headers,
        json.dumps({"success": False, "error": {"code": "ENDPOINT_NOT_FOUND", "path": path}}),
    )
