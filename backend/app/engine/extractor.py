"""JSONPath variable extractor and {{variable}} template renderer."""

from __future__ import annotations

import json
import re
from typing import Any

TEMPLATE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")
EXACT_TEMPLATE_PATTERN = re.compile(r"^\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}$")


def render_template(value: Any, context: dict[str, Any]) -> Any:
    """Recursively replace {{var_name}} placeholders using values from context.

    If a string value is an exact placeholder like "{{quantity}}" and the context
    holds an int/float/bool/list/dict, the native Python type is preserved.
    """
    if isinstance(value, str):
        exact_match = EXACT_TEMPLATE_PATTERN.match(value)
        if exact_match:
            var_name = exact_match.group(1)
            if var_name in context:
                return context[var_name]
            return value

        def _replacer(match: re.Match[str]) -> str:
            key = match.group(1)
            if key in context and context[key] is not None:
                return str(context[key])
            return match.group(0)

        return TEMPLATE_PATTERN.sub(_replacer, value)

    if isinstance(value, dict):
        return {str(k): render_template(v, context) for k, v in value.items()}

    if isinstance(value, list):
        return [render_template(item, context) for item in value]

    return value


def extract_jsonpath(data: Any, path_expr: str) -> tuple[bool, Any]:
    """Extract a value from parsed JSON data using a JSONPath expression.

    Supports expressions such as:
      - $.data.token
      - $.data.products[0].id
      - $.data.products[-1].price
      - $.items[*].id
      - $.data.products.length

    Returns:
      (found: bool, extracted_value: Any)
    """
    if not path_expr:
        return False, None

    expr = path_expr.strip()
    if expr == "$":
        return True, data

    if expr.startswith("$."):
        expr = expr[2:]
    elif expr.startswith("$"):
        expr = expr[1:]

    # Tokenize segments like products[0], items[*], or regular keys
    tokens: list[str] = [seg for seg in expr.split(".") if seg]
    current: Any = data

    for token in tokens:
        # Check for array index syntax: key[0] or [0] or key[*]
        bracket_match = re.match(r"^([^\[\]]+)?(?:\[(\*|-?\d+)\])?$", token)
        if not bracket_match:
            return False, None

        key_part, index_part = bracket_match.group(1), bracket_match.group(2)

        if key_part:
            if key_part == "length" and isinstance(current, (list, dict, str)):
                current = len(current)
            elif isinstance(current, dict) and key_part in current:
                current = current[key_part]
            else:
                return False, None

        if index_part is not None:
            if not isinstance(current, list):
                return False, None
            if index_part == "*":
                # Keep list for wildcard projection
                continue
            idx = int(index_part)
            try:
                current = current[idx]
            except IndexError:
                return False, None

    return True, current


def run_extractions(
    extractions: list[dict[str, Any]],
    response_json: Any,
    response_headers: dict[str, str],
    status_code: int,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Run extraction rules on an HTTP response and update the shared context."""
    extracted_this_step: dict[str, Any] = {}

    for rule in extractions or []:
        var_name = (rule.get("var_name") or "").strip()
        source = rule.get("source", "jsonpath")
        expr = (rule.get("jsonpath") or rule.get("path") or "").strip()
        if not var_name:
            continue

        found = False
        val: Any = None

        if source == "status_code":
            found, val = True, status_code
        elif source == "header":
            header_lookup = {k.lower(): v for k, v in response_headers.items()}
            if expr.lower() in header_lookup:
                found, val = True, header_lookup[expr.lower()]
        else:
            found, val = extract_jsonpath(response_json, expr)

        if found:
            context[var_name] = val
            extracted_this_step[var_name] = val

    return extracted_this_step
