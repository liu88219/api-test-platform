#!/usr/bin/env python3
"""CLI Test Runner for CI/CD Pipelines (GitHub Actions / Jenkins / Terminal)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import database, service  # pylint: disable=wrong-import-position
from app.mock_ecommerce import set_chaos_mode  # pylint: disable=wrong-import-position


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
        help="Override target environment Base URL (e.g. https://staging.example.com)",
    )
    parser.add_argument(
        "--chaos",
        type=str,
        choices=["none", "pricing_bug", "server_500_bug"],
        default="none",
        help="Inject a demo bug into the built-in target API to verify failure detection",
    )
    args = parser.parse_args()

    database.init_db()
    set_chaos_mode(args.chaos)

    print("=" * 74)
    print("🚀 PulseAPI Automated API Verification Suite")
    print(f"🔧 Target Chaos Mode: {args.chaos}")
    print("=" * 74)

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

    print("\n" + "=" * 74)
    if any_failed:
        print("❌ Quality Gate FAILED: One or more API verification scenarios failed.")
        return 1

    print("✅ Quality Gate PASSED: All API scenarios and assertions verified successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
