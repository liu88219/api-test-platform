"""Automated Unit & Integration Tests for PulseAPI Core Test Engine."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.asserter import evaluate_assertions  # pylint: disable=wrong-import-position
from app.engine.extractor import extract_jsonpath, render_template  # pylint: disable=wrong-import-position
from app.engine.runner import execute_scenario  # pylint: disable=wrong-import-position
from app.mock_ecommerce import handle_mock_request, set_chaos_mode  # pylint: disable=wrong-import-position


class TestPulseAPIEngine(unittest.TestCase):
    """Verify template interpolation, JSONPath extraction, assertions, and scenario chaining."""

    def tearDown(self) -> None:
        set_chaos_mode("none")

    def test_template_rendering_preserves_types_and_interpolates_strings(self) -> None:
        ctx = {"auth_token": "tok_abc123", "qty": 3, "expected_price": 2598}
        headers = render_template({"Authorization": "Bearer {{auth_token}}"}, ctx)
        body = render_template({"quantity": "{{qty}}", "note": "User token={{auth_token}}"}, ctx)

        self.assertEqual(headers["Authorization"], "Bearer tok_abc123")
        self.assertEqual(body["quantity"], 3)
        self.assertIsInstance(body["quantity"], int)
        self.assertEqual(body["note"], "User token=tok_abc123")

    def test_jsonpath_extraction(self) -> None:
        sample = {
            "success": True,
            "data": {
                "token": "tok_xyz",
                "products": [
                    {"id": "PROD-101", "price": 1299},
                    {"id": "PROD-102", "price": 8999},
                ],
            },
        }
        found_tok, tok = extract_jsonpath(sample, "$.data.token")
        self.assertTrue(found_tok)
        self.assertEqual(tok, "tok_xyz")

        found_prod, prod_id = extract_jsonpath(sample, "$.data.products[0].id")
        self.assertTrue(found_prod)
        self.assertEqual(prod_id, "PROD-101")

        found_len, count = extract_jsonpath(sample, "$.data.products.length")
        self.assertTrue(found_len)
        self.assertEqual(count, 2)

    def test_assertion_evaluator(self) -> None:
        rules = [
            {"type": "status_code", "operator": "eq", "expected": 200},
            {"type": "jsonpath", "path": "$.data.total", "operator": "eq", "expected": "{{target_total}}"},
            {"type": "response_time_ms", "operator": "lt", "expected": 500},
        ]
        passed, report = evaluate_assertions(
            assertions=rules,
            status_code=200,
            response_json={"data": {"total": 2598}},
            response_text='{"data": {"total": 2598}}',
            response_headers={"Content-Type": "application/json"},
            elapsed_ms=12.4,
            context={"target_total": 2598},
        )
        self.assertTrue(passed)
        self.assertEqual(len(report), 3)

    def test_end_to_end_scenario_chaining_and_chaos_bug_detection(self) -> None:
        scenario = {
            "name": "Chained Login & Checkout",
            "fail_fast": True,
            "steps": [
                {
                    "step_order": 1,
                    "name": "Login",
                    "method": "POST",
                    "path": "/mock/auth/login",
                    "headers": {},
                    "body": {"username": "qa", "password": "qa_secret_2026"},
                    "extractions": [{"var_name": "token", "jsonpath": "$.data.token"}],
                    "assertions": [{"type": "status_code", "operator": "eq", "expected": 200}],
                },
                {
                    "step_order": 2,
                    "name": "Checkout",
                    "method": "POST",
                    "path": "/mock/orders/checkout",
                    "headers": {"Authorization": "Bearer {{token}}"},
                    "body": {"cart_id": "CART-DEMO"},
                    "extractions": [],
                    "assertions": [
                        {"type": "status_code", "operator": "eq", "expected": 201},
                        {"type": "jsonpath", "path": "$.data.order.charged_amount", "operator": "eq", "expected": 2598},
                    ],
                },
            ],
        }

        # 1. Normal mode -> should PASS
        set_chaos_mode("none")
        res_ok = execute_scenario(
            scenario,
            base_url="http://127.0.0.1:8080",
            initial_variables={},
            local_dispatcher=handle_mock_request,
        )
        self.assertEqual(res_ok["status"], "PASSED")
        self.assertIn("token", res_ok["final_context"])

        # 2. Pricing Bug Chaos mode -> should FAIL and diagnose data mismatch
        set_chaos_mode("pricing_bug")
        res_bug = execute_scenario(
            scenario,
            base_url="http://127.0.0.1:8080",
            initial_variables={},
            local_dispatcher=handle_mock_request,
        )
        self.assertEqual(res_bug["status"], "FAILED")
        self.assertIn("資料斷言不符", res_bug["failure_diagnosis"])


if __name__ == "__main__":
    unittest.main()
