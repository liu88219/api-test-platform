"""HTTP & REST API Server for PulseAPI Test Platform (Zero-dependency + FastAPI compatible)."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
from typing import Any
import urllib.parse

from . import database, service
from .mock_ecommerce import get_chaos_state, handle_mock_request, set_chaos_mode

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def route_api_request(
    method: str,
    path: str,
    headers: dict[str, str],
    body_text: str,
) -> tuple[int, dict[str, str], str]:
    """Central router for /api/* and /mock/* endpoints."""
    resp_headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }

    if method == "OPTIONS":
        return 204, resp_headers, ""

    parsed = urllib.parse.urlparse(path)
    clean_path = parsed.path.rstrip("/") or "/"

    # Route /mock/* to built-in Demo E-Commerce Target API
    if clean_path.startswith("/mock/"):
        status, mock_headers, mock_body = handle_mock_request(method, clean_path, headers, body_text)
        merged_headers = {**resp_headers, **mock_headers}
        return status, merged_headers, mock_body

    payload: dict[str, Any] = {}
    if body_text.strip():
        try:
            payload = json.loads(body_text)
        except json.JSONDecodeError:
            payload = {}

    # 1. GET /api/stats (Dashboard Overview + Chaos State)
    if method == "GET" and clean_path == "/api/stats":
        stats = database.get_dashboard_stats()
        stats["chaos"] = get_chaos_state()
        return 200, resp_headers, json.dumps(stats)

    # 2. GET / POST /api/chaos
    if clean_path == "/api/chaos":
        if method == "GET":
            return 200, resp_headers, json.dumps(get_chaos_state())
        if method == "POST":
            mode = payload.get("mode", "none")
            new_state = set_chaos_mode(mode)
            return 200, resp_headers, json.dumps(new_state)

    # 3. GET / POST /api/environments
    if clean_path == "/api/environments":
        if method == "GET":
            return 200, resp_headers, json.dumps(database.list_environments())
        if method == "POST":
            saved = database.create_or_update_environment(payload)
            return 200, resp_headers, json.dumps(saved)

    # 4. GET / POST /api/scenarios
    if clean_path == "/api/scenarios":
        if method == "GET":
            return 200, resp_headers, json.dumps(database.list_scenarios())
        if method == "POST":
            saved = database.save_scenario(payload)
            return 200, resp_headers, json.dumps(saved)

    # 5. GET / DELETE /api/scenarios/{id}
    m_sc = re.match(r"^/api/scenarios/(\d+)$", clean_path)
    if m_sc:
        sc_id = int(m_sc.group(1))
        if method == "GET":
            sc = database.get_scenario(sc_id)
            if not sc:
                return 404, resp_headers, json.dumps({"error": "Scenario not found"})
            return 200, resp_headers, json.dumps(sc)
        if method == "DELETE":
            ok = database.delete_scenario(sc_id)
            return 200, resp_headers, json.dumps({"deleted": ok})

    # 6. POST /api/scenarios/{id}/run (Trigger Single Scenario)
    m_run_sc = re.match(r"^/api/scenarios/(\d+)/run$", clean_path)
    if m_run_sc and method == "POST":
        sc_id = int(m_run_sc.group(1))
        override_url = payload.get("base_url")
        override_vars = payload.get("variables")
        triggered_by = payload.get("triggered_by", "Manual UI")
        run_record = service.run_single_scenario(
            sc_id,
            override_base_url=override_url,
            override_variables=override_vars,
            triggered_by=triggered_by,
        )
        if not run_record:
            return 404, resp_headers, json.dumps({"error": "Scenario not found"})
        return 200, resp_headers, json.dumps(run_record)

    # 7. POST /api/runs/batch (Run All Scenarios)
    if method == "POST" and clean_path == "/api/runs/batch":
        triggered_by = payload.get("triggered_by", "Batch Suite UI")
        batch_result = service.run_all_scenarios(triggered_by=triggered_by)
        return 200, resp_headers, json.dumps(batch_result)

    # 8. GET /api/runs & GET /api/runs/{id}
    if method == "GET" and clean_path == "/api/runs":
        return 200, resp_headers, json.dumps(database.list_test_runs(limit=40))

    m_run_id = re.match(r"^/api/runs/(\d+)$", clean_path)
    if m_run_id and method == "GET":
        run_id = int(m_run_id.group(1))
        run_detail = database.get_test_run(run_id)
        if not run_detail:
            return 404, resp_headers, json.dumps({"error": "TestRun not found"})
        return 200, resp_headers, json.dumps(run_detail)

    return 404, resp_headers, json.dumps({"error": f"API route {clean_path} not found"})


class PlatformHTTPHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler serving both REST APIs and Frontend static assets."""

    def log_message(self, format: str, *args: Any) -> None:  # pylint: disable=redefined-builtin
        # Keep console logs concise
        pass

    def _handle_all(self, method: str) -> None:
        content_len = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(content_len).decode("utf-8", errors="replace") if content_len > 0 else ""
        req_headers = {k: v for k, v in self.headers.items()}

        if self.path.startswith("/api/") or self.path.startswith("/mock/"):
            status, resp_headers, resp_body = route_api_request(
                method, self.path, req_headers, raw_body
            )
            body_bytes = resp_body.encode("utf-8")
            self.send_response(status)
            for k, v in resp_headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)
            return

        # Serve static frontend files from frontend/dist
        clean_rel = urllib.parse.urlparse(self.path).path.lstrip("/")
        if not clean_rel:
            clean_rel = "index.html"
        target_file = (FRONTEND_DIST / clean_rel).resolve()
        if not str(target_file).startswith(str(FRONTEND_DIST.resolve())) or not target_file.is_file():
            target_file = FRONTEND_DIST / "index.html"

        if target_file.is_file():
            mime_type, _ = mimetypes.guess_type(str(target_file))
            content_bytes = target_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime_type or "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content_bytes)))
            self.end_headers()
            self.wfile.write(content_bytes)
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        self._handle_all("GET")

    def do_POST(self) -> None:  # pylint: disable=invalid-name
        self._handle_all("POST")

    def do_PUT(self) -> None:  # pylint: disable=invalid-name
        self._handle_all("PUT")

    def do_DELETE(self) -> None:  # pylint: disable=invalid-name
        self._handle_all("DELETE")

    def do_OPTIONS(self) -> None:  # pylint: disable=invalid-name
        self._handle_all("OPTIONS")


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def run_server(host: str = "0.0.0.0", port: int = 8765) -> None:
    import os
    actual_port = int(os.environ.get("PORT", str(port)))
    database.init_db()
    service.ensure_initial_runs()
    server = ReusableThreadingHTTPServer((host, actual_port), PlatformHTTPHandler)
    print(f"🚀 PulseAPI Automated Testing Platform running at http://localhost:{actual_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    run_server()
