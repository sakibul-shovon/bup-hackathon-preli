#!/usr/bin/env python
"""POST all 10 public sample cases to a running instance, independently replay
the response, and print a summary table (plan Section 15/17 Phase 4 smoke test).

Usage: python scripts/run_public_cases.py [base_url]   (default http://localhost:8000)
"""
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.directives import NormalizedDirective  # noqa: E402
from app.schemas import OptimizeRequest  # noqa: E402
from app.validator import replay  # noqa: E402


def to_normalized(entry: dict) -> NormalizedDirective:
    sa = entry.get("structured_adjustment") or {}
    return NormalizedDirective(
        note_index=entry["note_index"], directive_type=entry["directive_type"],
        hours=list(sa.get("hours", [])), factor=sa.get("factor"),
        minimum_energy_kwh=sa.get("minimum_energy_kwh"), max_grid_kwh=sa.get("max_grid_kwh"),
        explanation=entry.get("explanation", ""),
    )


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    cases = json.loads((ROOT / "tests" / "data" / "public_cases.json").read_text(encoding="utf-8"))["cases"]

    print(f"{'ID':12s} {'HTTP':>5s} {'cost':>10s} {'reference':>10s} {'diff':>8s} {'replay':10s} {'status':6s}")
    all_ok = True
    with httpx.Client(timeout=35.0) as client:
        for case in cases:
            reference = case["expected_output"]["total_cost_bdt"]
            try:
                r = client.post(f"{base_url}/optimize-energy", json=case["input"])
            except httpx.HTTPError as exc:
                print(f"{case['id']:12s} {'ERR':>5s} {'':>10s} {reference:>10.2f} {'':>8s} {'N/A':10s} FAIL  ({exc})")
                all_ok = False
                continue

            if r.status_code != 200:
                print(f"{case['id']:12s} {r.status_code:>5d} {'':>10s} {reference:>10.2f} {'':>8s} {'N/A':10s} FAIL")
                all_ok = False
                continue

            body = r.json()
            cost = body["total_cost_bdt"]
            diff = abs(cost - reference)

            request = OptimizeRequest(**case["input"])
            directives = [to_normalized(e) for e in body["directive_interpretation"]]
            plan = {"hourly_plan": body["hourly_plan"], "total_grid_kwh": body["total_grid_kwh"],
                    "total_cost_bdt": body["total_cost_bdt"], "peak_grid_kwh": body["peak_grid_kwh"]}
            violations = replay(request, directives, plan)

            cost_ok = diff <= 0.01
            status = "OK" if (cost_ok and not violations) else "FAIL"
            if status == "FAIL":
                all_ok = False
            replay_label = "clean" if not violations else f"{len(violations)} viol"
            print(f"{case['id']:12s} {r.status_code:>5d} {cost:>10.2f} {reference:>10.2f} {diff:>8.4f} "
                  f"{replay_label:10s} {status:6s}")
            for v in violations[:3]:
                print(f"    - {v}")

    print()
    if all_ok:
        print("10/10 replay-clean and within 0.01 BDT of reference.")
        sys.exit(0)
    print("FAILURES ABOVE.")
    sys.exit(1)


if __name__ == "__main__":
    main()
