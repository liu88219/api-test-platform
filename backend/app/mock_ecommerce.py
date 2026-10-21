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
CHECKED_OUT_CARTS: set[str] = set()
ORDERS_DB: dict[str, dict[str, Any]] = {}
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
    resp_headers = {"Content-Type": "application/json", "X-Mock-Service": "Demo-ECommerce-v2"}
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
            return True, VALID_TOKENS.get(tok, {"id": "USR-8801", "username": "qa_engineer", "role": "VIP_BUYER"})
        return False, None

    # 5. DELETE /mock/admin/products/<id> (RBAC Admin Endpoint)
    if method == "DELETE" and path.startswith("/mock/admin/products/"):
        authed, user = _check_auth()
        if not authed:
            return (
                401,
                resp_headers,
                json.dumps(
                    {"success": False, "error": {"code": "UNAUTHORIZED", "message": "Missing Bearer token"}}
                ),
            )
        if not user or user.get("role") != "ADMIN":
            return (
                403,
                resp_headers,
                json.dumps(
                    {
                        "success": False,
                        "error": {
                            "code": "ADMIN_ONLY",
                            "message": "Forbidden: Buyer role cannot access administrator endpoints",
                        },
                    }
                ),
            )
        return 200, resp_headers, json.dumps({"success": True})

    # 6. POST /mock/cart/items
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

        if quantity > product["stock"]:
            return (
                409,
                resp_headers,
                json.dumps(
                    {
                        "success": False,
                        "error": {
                            "code": "INSUFFICIENT_STOCK",
                            "message": f"Requested {quantity} exceeds available stock ({product['stock']})",
                            "available_stock": product["stock"],
                        },
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

    # 7. POST /mock/orders/checkout
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

        cart_id = str(payload.get("cart_id", ""))
        if cart_id and cart_id != "CART-DEMO" and cart_id in CHECKED_OUT_CARTS:
            return (
                409,
                resp_headers,
                json.dumps(
                    {
                        "success": False,
                        "error": {
                            "code": "DUPLICATE_CHECKOUT",
                            "message": f"Cart {cart_id} has already been settled (Idempotency Guard)",
                        },
                    }
                ),
            )

        cart = CARTS_DB.get(cart_id, {"cart_total": 2598, "product_id": "PROD-101", "quantity": 2})
        base_amount = cart["cart_total"]
        discount_amount = 0

        coupon_code = (payload.get("coupon_code") or "").strip()
        if coupon_code:
            if coupon_code == "VIP200":
                discount_amount = 200
            elif coupon_code == "EXPIRED2020":
                return (
                    400,
                    resp_headers,
                    json.dumps(
                        {
                            "success": False,
                            "error": {
                                "code": "COUPON_EXPIRED",
                                "message": "Coupon EXPIRED2020 has expired",
                            },
                        }
                    ),
                )
            else:
                return (
                    400,
                    resp_headers,
                    json.dumps(
                        {
                            "success": False,
                            "error": {
                                "code": "INVALID_COUPON",
                                "message": f"Coupon {coupon_code} is not valid",
                            },
                        }
                    ),
                )

        charged_amount = max(0, base_amount - discount_amount)

        # Inject pricing bug when chaos mode == "pricing_bug"
        if CHAOS_STATE["mode"] == "pricing_bug":
            charged_amount = charged_amount + 500  # Deliberate overcharge bug!

        if cart_id and cart_id != "CART-DEMO" and not coupon_code:
            CHECKED_OUT_CARTS.add(cart_id)

        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        order_obj = {
            "order_id": order_id,
            "cart_id": cart_id,
            "buyer_id": user["id"] if user else "USR-8801",
            "status": "PAID",
            "discount_amount": discount_amount,
            "charged_amount": charged_amount,
            "currency": "TWD",
        }
        ORDERS_DB[order_id] = order_obj

        return (
            201,
            resp_headers,
            json.dumps(
                {
                    "success": True,
                    "data": {"order": order_obj},
                }
            ),
        )

    # 8. POST /mock/orders/<order_id>/refund (Order State Machine Transition)
    if method == "POST" and path.startswith("/mock/orders/") and path.endswith("/refund"):
        authed, _ = _check_auth()
        if not authed:
            return (
                401,
                resp_headers,
                json.dumps(
                    {"success": False, "error": {"code": "UNAUTHORIZED", "message": "Missing Bearer token"}}
                ),
            )
        order_id = path.split("/mock/orders/", 1)[1].rsplit("/refund", 1)[0].strip("/")
        order = ORDERS_DB.get(order_id)
        if not order:
            return (
                404,
                resp_headers,
                json.dumps(
                    {"success": False, "error": {"code": "ORDER_NOT_FOUND", "message": "Order not found"}}
                ),
            )
        if order["status"] == "REFUNDED":
            return (
                409,
                resp_headers,
                json.dumps(
                    {
                        "success": False,
                        "error": {
                            "code": "ORDER_ALREADY_REFUNDED",
                            "message": f"Order {order_id} is already in REFUNDED state",
                        },
                    }
                ),
            )
        order["status"] = "REFUNDED"
        return (
            200,
            resp_headers,
            json.dumps({"success": True, "data": {"order": order}}),
        )

    # 9. GET /mock/orders/<order_id> (BOLA Horizontal Authorization Check)
    if method == "GET" and path.startswith("/mock/orders/"):
        authed, user = _check_auth()
        if not authed:
            return (
                401,
                resp_headers,
                json.dumps(
                    {"success": False, "error": {"code": "UNAUTHORIZED", "message": "Missing Bearer token"}}
                ),
            )
        order_id = path.split("/mock/orders/", 1)[1].strip("/")
        if order_id.startswith("ORD-OTHER"):
            return (
                403,
                resp_headers,
                json.dumps(
                    {
                        "success": False,
                        "error": {
                            "code": "FORBIDDEN_ORDER_ACCESS",
                            "message": "BOLA Guard: Cannot access another user's private order",
                        },
                    }
                ),
            )
        order = ORDERS_DB.get(
            order_id,
            {"order_id": order_id, "buyer_id": user["id"] if user else "USR-8801", "status": "PAID"},
        )
        return 200, resp_headers, json.dumps({"success": True, "data": {"order": order}})

    return (
        404,
        resp_headers,
        json.dumps({"success": False, "error": {"code": "ENDPOINT_NOT_FOUND", "path": path}}),
    )
