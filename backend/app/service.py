"""High-level orchestration service connecting DB, Scenario Runner, and Target Mock API."""

from __future__ import annotations

from typing import Any
from . import database
from .engine.runner import execute_scenario
from .mock_ecommerce import get_chaos_state, handle_mock_request


def run_single_scenario(
    scenario_id: int,
    override_base_url: str | None = None,
    override_variables: dict[str, Any] | None = None,
    triggered_by: str = "Manual UI",
) -> dict[str, Any] | None:
    """Load a scenario from SQLite, execute all its API steps, and save the TestRun report."""
    scenario = database.get_scenario(scenario_id)
    if not scenario:
        return None

    base_url = (override_base_url or scenario["base_url"]).strip()
    initial_vars = dict(scenario.get("environment_variables") or {})
    if override_variables:
        initial_vars.update(override_variables)

    # If the target is our built-in local mock API, pass handle_mock_request
    # so it works both in-process and over localhost HTTP without deadlocking.
    is_local_mock = any(
        host in base_url
        for host in (
            "127.0.0.1:8765",
            "localhost:8765",
            "127.0.0.1:8080",
            "localhost:8080",
            "0.0.0.0:8765",
        )
    )
    dispatcher = handle_mock_request if is_local_mock else None

    run_output = execute_scenario(
        scenario=scenario,
        base_url=base_url,
        initial_variables=initial_vars,
        local_dispatcher=dispatcher,
    )

    chaos_mode = get_chaos_state()["mode"]
    saved_run = database.record_test_run(
        scenario=scenario,
        run_output=run_output,
        chaos_mode=chaos_mode,
        triggered_by=triggered_by,
    )
    return saved_run


def run_all_scenarios(triggered_by: str = "Batch Regression") -> dict[str, Any]:
    """Execute all registered scenarios sequentially as a regression suite."""
    scenarios = database.list_scenarios()
    results: list[dict[str, Any]] = []
    passed_count = 0

    for sc in scenarios:
        run_record = run_single_scenario(sc["id"], triggered_by=triggered_by)
        if run_record:
            results.append(run_record)
            if run_record["status"] == "PASSED":
                passed_count += 1

    total = len(results)
    return {
        "suite_status": "PASSED" if passed_count == total else "FAILED",
        "total_scenarios": total,
        "passed_scenarios": passed_count,
        "failed_scenarios": total - passed_count,
        "runs": results,
    }


def ensure_initial_runs() -> None:
    """If no test runs exist yet, execute the default scenarios once so the dashboard has live data."""
    stats = database.get_dashboard_stats()
    if stats["total_runs"] == 0:
        run_all_scenarios(triggered_by="Initial Seed Boot")
