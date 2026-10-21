"""Multi-step API Scenario Execution Engine."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from .asserter import diagnose_step_failure, evaluate_assertions
from .extractor import render_template, run_extractions


def _send_http_request(
    method: str,
    full_url: str,
    headers: dict[str, str],
    body_obj: Any,
    timeout_sec: float = 10.0,
    local_dispatcher: Callable[[str, str, dict[str, str], Any], tuple[int, dict[str, str], str]] | None = None,
) -> tuple[int, dict[str, str], str, Any, float, str | None]:
    """Send a real HTTP request (or dispatch locally if matching local mock prefix).

    Returns:
      (status_code, response_headers, response_text, response_json, elapsed_ms, error_message)
    """
    method_upper = (method or "GET").upper().strip()
    req_headers = {"Accept": "application/json", "User-Agent": "PulseAPI-TestRunner/1.0"}
    for k, v in (headers or {}).items():
        if k and v is not None:
            req_headers[str(k)] = str(v)

    # Check if local_dispatcher handles this path directly (e.g., /mock/...)
    parsed = urllib.parse.urlparse(full_url)
    if local_dispatcher and parsed.path.startswith("/mock/"):
        start_t = time.perf_counter()
        path_with_query = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        status, resp_headers, resp_text = local_dispatcher(
            method_upper, path_with_query, req_headers, body_obj
        )
        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
        try:
            resp_json = json.loads(resp_text) if resp_text else {}
        except json.JSONDecodeError:
            resp_json = None
        return status, resp_headers, resp_text, resp_json, elapsed_ms, None

    data_bytes: bytes | None = None
    if method_upper not in ("GET", "HEAD") and body_obj is not None and body_obj != "":
        if isinstance(body_obj, (dict, list)):
            data_bytes = json.dumps(body_obj).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        elif isinstance(body_obj, str):
            data_bytes = body_obj.encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(
        url=full_url,
        data=data_bytes,
        headers=req_headers,
        method=method_upper,
    )

    start_t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
            status_code = resp.getcode()
            resp_headers = {k: v for k, v in resp.info().items()}
            raw_bytes = resp.read()
            resp_text = raw_bytes.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as http_err:
        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
        status_code = http_err.code
        resp_headers = {k: v for k, v in http_err.headers.items()} if http_err.headers else {}
        raw_bytes = http_err.read() if http_err.fp else b""
        resp_text = raw_bytes.decode("utf-8", errors="replace")
    except Exception as exc:  # pylint: disable=broad-except
        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
        return 0, {}, "", None, elapsed_ms, str(exc)

    try:
        resp_json = json.loads(resp_text) if resp_text else {}
    except json.JSONDecodeError:
        resp_json = None

    return status_code, resp_headers, resp_text, resp_json, elapsed_ms, None


def execute_scenario(
    scenario: dict[str, Any],
    base_url: str,
    initial_variables: dict[str, Any] | None = None,
    local_dispatcher: Callable[[str, str, dict[str, str], Any], tuple[int, dict[str, str], str]] | None = None,
) -> dict[str, Any]:
    """Execute a multi-step API test scenario with variable chaining and assertions."""
    context: dict[str, Any] = dict(initial_variables or {})
    steps = sorted(scenario.get("steps", []), key=lambda s: s.get("step_order", 1))
    fail_fast = bool(scenario.get("fail_fast", True))

    step_results: list[dict[str, Any]] = []
    overall_passed = True
    total_duration_ms = 0.0
    passed_steps = 0
    total_assertions = 0
    passed_assertions = 0
    failure_diagnosis = ""

    clean_base = (base_url or "").rstrip("/")

    for idx, step in enumerate(steps, start=1):
        step_name = step.get("name") or f"Step {idx}"
        method = (step.get("method") or "GET").upper()
        raw_path = step.get("path") or "/"
        rendered_path = str(render_template(raw_path, context))

        if rendered_path.startswith("http://") or rendered_path.startswith("https://"):
            full_url = rendered_path
        else:
            slash_path = rendered_path if rendered_path.startswith("/") else f"/{rendered_path}"
            full_url = f"{clean_base}{slash_path}"

        rendered_headers = render_template(step.get("headers") or {}, context)
        rendered_body = render_template(step.get("body"), context)

        status_code, resp_headers, resp_text, resp_json, elapsed_ms, error_msg = _send_http_request(
            method=method,
            full_url=full_url,
            headers=rendered_headers if isinstance(rendered_headers, dict) else {},
            body_obj=rendered_body,
            local_dispatcher=local_dispatcher,
        )
        total_duration_ms += elapsed_ms

        if error_msg:
            step_passed = False
            assertion_results: list[dict[str, Any]] = []
            extracted_vars: dict[str, Any] = {}
        else:
            step_passed, assertion_results = evaluate_assertions(
                assertions=step.get("assertions") or [],
                status_code=status_code,
                response_json=resp_json,
                response_text=resp_text,
                response_headers=resp_headers,
                elapsed_ms=elapsed_ms,
                context=context,
            )
            extracted_vars = run_extractions(
                extractions=step.get("extractions") or [],
                response_json=resp_json,
                response_headers=resp_headers,
                status_code=status_code,
                context=context,
            )

        step_total_asserts = len(assertion_results)
        step_passed_asserts = sum(1 for a in assertion_results if a["passed"])
        total_assertions += step_total_asserts
        passed_assertions += step_passed_asserts

        step_diag = ""
        if not step_passed:
            overall_passed = False
            step_diag = diagnose_step_failure(
                step_name=step_name,
                status_code=status_code,
                assertion_results=assertion_results,
                response_json=resp_json,
                error_message=error_msg,
            )
            if not failure_diagnosis:
                failure_diagnosis = step_diag
        else:
            passed_steps += 1

        step_results.append(
            {
                "step_order": idx,
                "step_name": step_name,
                "method": method,
                "url": full_url,
                "request_headers": rendered_headers,
                "request_body": rendered_body,
                "status_code": status_code,
                "elapsed_ms": elapsed_ms,
                "passed": step_passed,
                "error_message": error_msg,
                "diagnosis": step_diag,
                "assertions": assertion_results,
                "extracted_variables": extracted_vars,
                "response_body": resp_json if resp_json is not None else resp_text[:2000],
            }
        )

        if not step_passed and fail_fast:
            break

    return {
        "status": "PASSED" if overall_passed else "FAILED",
        "passed": overall_passed,
        "passed_steps": passed_steps,
        "total_steps": len(steps),
        "passed_assertions": passed_assertions,
        "total_assertions": total_assertions,
        "duration_ms": round(total_duration_ms, 2),
        "failure_diagnosis": failure_diagnosis,
        "step_results": step_results,
        "final_context": context,
    }
