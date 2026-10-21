"""Assertion evaluation engine and automated QA failure triage diagnostics."""

from __future__ import annotations

from typing import Any
from .extractor import extract_jsonpath, render_template


def _compare_values(actual: Any, operator: str, expected: Any, found: bool = True) -> bool:
    """Compare actual vs expected value using the specified operator."""
    op = (operator or "eq").lower().strip()

    if op == "exists":
        return bool(found and actual is not None)

    if op == "not_empty":
        if not found or actual is None:
            return False
        if isinstance(actual, (str, list, dict)):
            return len(actual) > 0
        return True

    if not found:
        return False

    # Try numeric coercion for numeric comparisons or matching numeric strings
    if op in ("gt", "gte", "lt", "lte"):
        try:
            num_actual = float(actual)
            num_expected = float(expected)
            if op == "gt":
                return num_actual > num_expected
            if op == "gte":
                return num_actual >= num_expected
            if op == "lt":
                return num_actual < num_expected
            if op == "lte":
                return num_actual <= num_expected
        except (TypeError, ValueError):
            return False

    if op == "eq":
        if str(actual).isdigit() and str(expected).isdigit():
            return int(actual) == int(expected)
        try:
            if isinstance(actual, (int, float)) or isinstance(expected, (int, float)):
                return float(actual) == float(expected)
        except (TypeError, ValueError):
            pass
        return actual == expected or str(actual) == str(expected)

    if op == "neq":
        return not _compare_values(actual, "eq", expected, found)

    if op == "contains":
        if actual is None:
            return False
        if isinstance(actual, (list, dict)):
            return expected in actual or str(expected) in [str(x) for x in actual]
        return str(expected) in str(actual)

    return False


def evaluate_assertions(
    assertions: list[dict[str, Any]],
    status_code: int,
    response_json: Any,
    response_text: str,
    response_headers: dict[str, str],
    elapsed_ms: float,
    context: dict[str, Any],
) -> tuple[bool, list[dict[str, Any]]]:
    """Evaluate all assertion rules for a single API step."""
    results: list[dict[str, Any]] = []
    all_passed = True

    for rule in assertions or []:
        rule_type = (rule.get("type") or "status_code").lower().strip()
        operator = (rule.get("operator") or "eq").lower().strip()
        path = (rule.get("path") or "").strip()
        raw_expected = rule.get("expected")
        expected = render_template(raw_expected, context)

        found = True
        actual: Any = None
        target_label = rule_type

        if rule_type == "status_code":
            actual = status_code
            target_label = "HTTP Status Code"
        elif rule_type == "response_time_ms":
            actual = elapsed_ms
            target_label = "Response Time (ms)"
        elif rule_type == "header":
            header_map = {k.lower(): v for k, v in response_headers.items()}
            found = path.lower() in header_map
            actual = header_map.get(path.lower())
            target_label = f"Header [{path}]"
        elif rule_type == "body_contains":
            actual = response_text
            operator = "contains"
            target_label = "Response Body"
        else:
            # Default: jsonpath
            found, actual = extract_jsonpath(response_json, path)
            target_label = f"JSONPath ({path})"

        passed = _compare_values(actual, operator, expected, found)
        if not passed:
            all_passed = False

        results.append(
            {
                "type": rule_type,
                "path": path,
                "target": target_label,
                "operator": operator,
                "expected": expected,
                "actual": actual if found else "<NOT_FOUND>",
                "passed": passed,
            }
        )

    return all_passed, results


def diagnose_step_failure(
    step_name: str,
    status_code: int,
    assertion_results: list[dict[str, Any]],
    response_json: Any,
    error_message: str | None = None,
) -> str:
    """Generate an intelligent QA root-cause diagnostic summary when a step fails."""
    if error_message:
        return (
            f"🚨 [網路/連線異常] 步驟「{step_name}」無法完成請求：{error_message}。"
            "請確認目標環境 Base URL 是否啟動且網路可達。"
        )

    failed_rules = [r for r in assertion_results if not r["passed"]]
    if not failed_rules:
        return ""

    if status_code >= 500:
        server_err = ""
        if isinstance(response_json, dict):
            err_obj = response_json.get("error") or response_json.get("detail") or response_json.get("message")
            if err_obj:
                server_err = f"（後端錯誤訊息：{err_obj}）"
        return (
            f"💥 [後端服務異常 5xx] 步驟「{step_name}」回傳 HTTP {status_code}{server_err}。"
            "屬於伺服器端 Crash 或資料庫/第三方依賴異常，非測試腳本問題。"
        )

    if status_code in (401, 403):
        first_fail = failed_rules[0]
        if first_fail["type"] == "status_code" and int(first_fail["expected"]) < 400:
            return (
                f"🔒 [權限驗證失敗 {status_code}] 步驟「{step_name}」被拒絕存取。"
                "請檢查前置登入步驟是否成功提取 {{auth_token}}，或 Header Authorization 格式是否正確。"
            )

    for rule in failed_rules:
        if rule["type"] == "jsonpath":
            return (
                f"🔍 [資料斷言不符] 步驟「{step_name}」中欄位 `{rule['path']}` "
                f"預期為 `{rule['expected']}` ({rule['operator']})，但實際收到 `{rule['actual']}`。"
                "疑似後端商業邏輯計算錯誤（如金額/狀態異常）或 API 契約結構變更。"
            )
        if rule["type"] == "response_time_ms":
            return (
                f"🐢 [效能 SLA 超標] 步驟「{step_name}」耗時 {rule['actual']} ms，"
                f"超過門檻 {rule['expected']} ms。建議排查後端慢查詢 (Slow Query)。"
            )

    first = failed_rules[0]
    return (
        f"⚠️ [斷言失敗] 步驟「{step_name}」驗證 `{first['target']}` 失敗："
        f"預期 `{first['expected']}` ({first['operator']})，實際為 `{first['actual']}`。"
    )
