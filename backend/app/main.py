"""FastAPI Application Entry Point (with zero-dependency fallback runner)."""

from __future__ import annotations

from typing import Any
from . import database, service
from .mock_ecommerce import get_chaos_state, set_chaos_mode
from .server import run_server

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="PulseAPI - Automated API Testing & Scenario Orchestration Platform",
        version="1.0.0",
        description="Multi-step API test runner with JSONPath variable chaining, assertion engine, and QA failure triage.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def on_startup() -> None:
        database.init_db()
        service.ensure_initial_runs()

    @app.get("/api/stats")
    def api_get_stats() -> dict[str, Any]:
        stats = database.get_dashboard_stats()
        stats["chaos"] = get_chaos_state()
        return stats

    @app.get("/api/environments")
    def api_list_environments() -> list[dict[str, Any]]:
        return database.list_environments()

    @app.post("/api/environments")
    def api_save_environment(payload: dict[str, Any]) -> dict[str, Any]:
        return database.create_or_update_environment(payload)

    @app.get("/api/scenarios")
    def api_list_scenarios() -> list[dict[str, Any]]:
        return database.list_scenarios()

    @app.get("/api/scenarios/{scenario_id}")
    def api_get_scenario(scenario_id: int) -> dict[str, Any]:
        sc = database.get_scenario(scenario_id)
        if not sc:
            raise HTTPException(status_code=404, detail="Scenario not found")
        return sc

    @app.post("/api/scenarios")
    def api_save_scenario(payload: dict[str, Any]) -> dict[str, Any]:
        return database.save_scenario(payload)

    @app.delete("/api/scenarios/{scenario_id}")
    def api_delete_scenario(scenario_id: int) -> dict[str, Any]:
        return {"deleted": database.delete_scenario(scenario_id)}

    @app.post("/api/scenarios/{scenario_id}/run")
    def api_run_scenario(scenario_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = payload or {}
        res = service.run_single_scenario(
            scenario_id,
            override_base_url=body.get("base_url"),
            override_variables=body.get("variables"),
            triggered_by=body.get("triggered_by", "FastAPI REST"),
        )
        if not res:
            raise HTTPException(status_code=404, detail="Scenario not found")
        return res

    @app.post("/api/runs/batch")
    def api_run_batch(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = payload or {}
        return service.run_all_scenarios(triggered_by=body.get("triggered_by", "Batch API"))

    @app.get("/api/runs")
    def api_list_runs() -> list[dict[str, Any]]:
        return database.list_test_runs(limit=40)

    @app.get("/api/runs/{run_id}")
    def api_get_run(run_id: int) -> dict[str, Any]:
        run_obj = database.get_test_run(run_id)
        if not run_obj:
            raise HTTPException(status_code=404, detail="Run not found")
        return run_obj

    @app.post("/api/chaos")
    def api_set_chaos(payload: dict[str, Any]) -> dict[str, Any]:
        return set_chaos_mode(payload.get("mode", "none"))

except ImportError:
    app = None


if __name__ == "__main__":
    run_server()
