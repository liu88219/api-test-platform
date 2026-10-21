#!/usr/bin/env python3
"""CLI Test Runner & Periodic Report Generator for CI/CD Pipelines (GitHub Actions / Terminal)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import database, service  # pylint: disable=wrong-import-position
from app.mock_ecommerce import set_chaos_mode  # pylint: disable=wrong-import-position


def generate_markdown_report(runs: list[dict[str, Any]], chaos_mode: str) -> str:
    """Generate a structured Markdown report for GitHub Actions Summary & Periodic Records."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total_sc = len(runs)
    passed_sc = sum(1 for r in runs if r["status"] == "PASSED")
    total_steps = sum(r["total_steps"] for r in runs)
    passed_steps = sum(r["passed_steps"] for r in runs)
    total_asserts = sum(r["total_assertions"] for r in runs)
    passed_asserts = sum(r["passed_assertions"] for r in runs)
    total_ms = round(sum(r["duration_ms"] for r in runs), 2)
    pass_rate = round((passed_sc / total_sc) * 100, 1) if total_sc else 100.0
    overall_badge = "✅ PASSED" if passed_sc == total_sc else "❌ FAILED"

    lines = [
        f"## ⚡ PulseAPI 每日自動化測試巡檢報告 ({now_str})",
        "",
        f"- **總體狀態 (Quality Gate)**：**{overall_badge}** (通過率 `{pass_rate}%`)",
        f"- **執行統計**：`{passed_sc}/{total_sc}` 測試場景 ｜ `{passed_steps}/{total_steps}` API 步驟 ｜ `{passed_asserts}/{total_asserts}` 斷言驗證",
        f"- **總執行耗時**：`{total_ms} ms` ｜ **靶機模式**：`{chaos_mode}`",
        "",
        "| # | 測試場景名稱 | 狀態 | 步驟數 | 斷言通過 | 耗時 (ms) | 診斷與備註 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for r in runs:
        st_icon = "✅ PASS" if r["status"] == "PASSED" else "❌ FAIL"
        diag = r.get("failure_diagnosis") or "全數斷言通過"
        lines.append(
            f"| #{r['scenario_id']} | {r['scenario_name']} | {st_icon} | "
            f"`{r['passed_steps']}/{r['total_steps']}` | "
            f"`{r['passed_assertions']}/{r['total_assertions']}` | "
            f"`{r['duration_ms']}` | {diag} |"
        )

    lines.append("")
    return "\n".join(lines)


def update_periodic_ledger(ledger_path: Path, runs: list[dict[str, Any]], chaos_mode: str) -> None:
    """Update reports/DAILY_TEST_LEDGER.md with the latest periodic execution record."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_sc = len(runs)
    passed_sc = sum(1 for r in runs if r["status"] == "PASSED")
    total_steps = sum(r["total_steps"] for r in runs)
    total_asserts = sum(r["total_assertions"] for r in runs)
    passed_asserts = sum(r["passed_assertions"] for r in runs)
    total_ms = round(sum(r["duration_ms"] for r in runs), 2)
    status_str = "✅ PASS (100%)" if passed_sc == total_sc else f"❌ FAIL ({passed_sc}/{total_sc})"

    new_row = (
        f"| `{now_str}` | {status_str} | `{passed_sc}/{total_sc}` 場景 | "
        f"`{total_steps}` 步 | `{passed_asserts}/{total_asserts}` 斷言 | `{total_ms} ms` | `CI Scheduled / Gate` |"
    )

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    latest_detail_md = generate_markdown_report(runs, chaos_mode)

    existing_rows: list[str] = []
    if ledger_path.exists():
        content = ledger_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("| `20"):
                existing_rows.append(line)

    # Keep latest 60 periodic entries
    all_rows = [new_row] + existing_rows[:59]

    full_ledger = "\n".join(
        [
            "# 📊 PulseAPI 自動化測試週期紀錄總表 (Periodic QA Execution Ledger)",
            "",
            "> 本檔案由 GitHub Actions 排程（每日定時巡檢與 CI Quality Gate）自動執行 [`backend/cli_runner.py`](../backend/cli_runner.py) 後更新，完整留存每次自動化回歸測試的週期紀錄。",
            "",
            "## 🗓️ 歷史週期巡檢紀錄 (Chronological Run History)",
            "",
            "| 執行時間 (UTC) | 總體結果 | 場景通過數 | API 步驟數 | 斷言驗證數 | 總耗時 | 觸發來源 |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            *all_rows,
            "",
            "---",
            "",
            "## 🔍 最新一次執行明細報告 (Latest Run Breakdown)",
            "",
            latest_detail_md,
        ]
    )
    ledger_path.write_text(full_ledger, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PulseAPI CLI Runner - Execute Automated API Scenarios in CI/CD"
    )
    parser.add_argument(
        "--scenario-id",
        type=int,
        default=None,
        help="Run a specific Scenario ID (omit to run all scenarios)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Override target environment Base URL",
    )
    parser.add_argument(
        "--chaos",
        type=str,
        choices=["none", "pricing_bug", "server_500_bug"],
        default="none",
        help="Inject a demo bug into the built-in target API to verify failure detection",
    )
    parser.add_argument(
        "--report-md",
        type=str,
        default=None,
        help="Write a Markdown summary report to the specified file path (e.g. $GITHUB_STEP_SUMMARY)",
    )
    parser.add_argument(
        "--update-ledger",
        type=str,
        default=None,
        help="Update the periodic ledger Markdown file (e.g. reports/DAILY_TEST_LEDGER.md)",
    )
    args = parser.parse_args()

    database.init_db()
    set_chaos_mode(args.chaos)

    print("=" * 78)
    print("🚀 PulseAPI Automated API Verification Suite")
    print(f"🔧 Target Chaos Mode: {args.chaos}")
    print("=" * 78)

    if args.scenario_id is not None:
        run_res = service.run_single_scenario(
            args.scenario_id,
            override_base_url=args.base_url,
            triggered_by="CLI Runner",
        )
        if not run_res:
            print(f"❌ Scenario ID {args.scenario_id} not found.")
            return 1
        runs = [run_res]
    else:
        suite = service.run_all_scenarios(triggered_by="CLI CI/CD Gate")
        runs = suite["runs"]

    any_failed = False
    for r in runs:
        badge = "✅ PASS" if r["status"] == "PASSED" else "❌ FAIL"
        print(
            f"\n{badge} | Scenario #{r['scenario_id']}: {r['scenario_name']} "
            f"({r['duration_ms']} ms | Assertions: {r['passed_assertions']}/{r['total_assertions']})"
        )
        for step in r["step_results"]:
            s_icon = "  ✔" if step["passed"] else "  ✖"
            print(
                f"{s_icon} [{step['method']}] {step['url']} -> HTTP {step['status_code']} ({step['elapsed_ms']} ms)"
            )
            if step["extracted_variables"]:
                print(f"      ↳ Extracted: {step['extracted_variables']}")
            for a in step["assertions"]:
                if not a["passed"]:
                    print(
                        f"      ↳ ⚠️ Assertion Failed: {a['target']} {a['operator']} {a['expected']} "
                        f"(Actual: {a['actual']})"
                    )
        if r["status"] != "PASSED":
            any_failed = True
            if r["failure_diagnosis"]:
                print(f"  💡 QA Root-Cause Diagnosis: {r['failure_diagnosis']}")

    if args.report_md:
        md_text = generate_markdown_report(runs, args.chaos)
        Path(args.report_md).write_text(md_text, encoding="utf-8")

    if args.update_ledger:
        update_periodic_ledger(Path(args.update_ledger), runs, args.chaos)
        print(f"\n📝 Updated periodic test ledger at: {args.update_ledger}")

    print("\n" + "=" * 78)
    if any_failed:
        print("❌ Quality Gate FAILED: One or more API verification scenarios failed.")
        return 1

    print("✅ Quality Gate PASSED: All API scenarios and assertions verified successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
