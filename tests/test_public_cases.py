"""THE ANCHOR (plan Section 12.1 / Section 17 Phase 1).

Mocks the LLM by using each public case's ground-truth directive_interpretation
directly (converted to NormalizedDirective), then runs the deterministic spine
(directives -> optimizer -> canonicalize -> replay -> response assembly) exactly
as main.py's orchestration will. Per Section 17 Phase 1, this phase's mocked
pipeline does NOT include guardrails.py (that is Phase 2 / Track A, built in L6) --
the ground-truth IR here is already fully normalized, unit-converted data, which
is exactly guardrails.py's *output* shape.

app/summary.py (Dev B, not yet built) is not wired in here; plan_summary is a
placeholder string for the purpose of checking the response's top-level shape.
"""
import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest

from app import config
from app.directives import NormalizedDirective, build_interpretation_array
from app.llm_interpreter import create_key_pool, interpret_notes
from app.optimizer import optimize
from app.schemas import OptimizeRequest
from app.validator import replay

CASES_PATH = Path(__file__).parent / "data" / "public_cases.json"

RESPONSE_TOP_LEVEL_KEYS = {
    "scenario_id",
    "directive_interpretation",
    "hourly_plan",
    "total_grid_kwh",
    "total_cost_bdt",
    "peak_grid_kwh",
    "plan_summary",
}
INTERPRETATION_ENTRY_KEYS = {"note_index", "applies", "directive_type", "structured_adjustment", "explanation"}
HOURLY_ENTRY_KEYS = {"hour", "grid_kwh", "solar_used_kwh", "battery_action", "battery_kwh", "battery_energy_after_kwh"}

STRUCTURED_ADJUSTMENT_KEYS = {
    "solar_reduction": {"hours", "factor"},
    "minimum_battery_reserve": {"hours", "minimum_energy_kwh"},
    "no_charge_window": {"hours"},
    "no_discharge_window": {"hours"},
    "max_grid_window": {"hours", "max_grid_kwh"},
}


def _load_cases() -> list[dict]:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return data["cases"]


def _to_normalized(entry: dict) -> NormalizedDirective:
    sa = entry["structured_adjustment"] or {}
    return NormalizedDirective(
        note_index=entry["note_index"],
        directive_type=entry["directive_type"],
        hours=list(sa.get("hours", [])),
        factor=sa.get("factor"),
        minimum_energy_kwh=sa.get("minimum_energy_kwh"),
        max_grid_kwh=sa.get("max_grid_kwh"),
        explanation=entry["explanation"],
    )


def _by_hour(request: OptimizeRequest) -> list:
    idx = {h.hour: h for h in request.hours}
    return [idx[i] for i in range(24)]


def run_pipeline(case: dict):
    """Mocked-LLM deterministic pipeline: directives -> optimizer -> canonicalize -> response."""
    request = OptimizeRequest(**case["input"])
    directives = [_to_normalized(e) for e in case["expected_output"]["directive_interpretation"]]

    ordered = _by_hour(request)
    solar = [float(h.solar_kwh) for h in ordered]
    demand = [float(h.demand_kwh) for h in ordered]
    tariff = [float(h.tariff_bdt_per_kwh) for h in ordered]

    hourly_plan, totals, kept, dropped = optimize(
        directives=directives,
        base_solar=solar,
        base_minimum=request.battery.minimum_energy_kwh,
        base_max_charge=request.battery.max_charge_kwh_per_hour,
        base_max_discharge=request.battery.max_discharge_kwh_per_hour,
        demand=demand,
        tariff=tariff,
        e0=request.battery.initial_energy_kwh,
        cap=request.battery.capacity_kwh,
    )
    assert dropped == [], f"{case['id']}: guaranteed-feasible public case dropped directives {dropped}"

    response = {
        "scenario_id": request.scenario_id,
        # F6/I5a: report ALL extracted directives, not just the ones the optimizer kept.
        "directive_interpretation": build_interpretation_array(directives),
        "hourly_plan": hourly_plan,
        "total_grid_kwh": totals["total_grid_kwh"],
        "total_cost_bdt": totals["total_cost_bdt"],
        "peak_grid_kwh": totals["peak_grid_kwh"],
        "plan_summary": "placeholder summary (app/summary.py wired in at L7)",
    }
    return request, directives, response


@pytest.fixture(scope="module")
def cases():
    return _load_cases()


def case_ids():
    return [c["id"] for c in _load_cases()]


@pytest.mark.parametrize("case", _load_cases(), ids=case_ids())
def test_response_schema_exact(case):
    _, _, response = run_pipeline(case)

    assert set(response.keys()) == RESPONSE_TOP_LEVEL_KEYS

    interpretation = response["directive_interpretation"]
    assert [e["note_index"] for e in interpretation] == list(range(len(interpretation)))
    for entry in interpretation:
        assert set(entry.keys()) == INTERPRETATION_ENTRY_KEYS
        dtype = entry["directive_type"]
        if dtype == "no_op":
            assert entry["applies"] is False
            assert entry["structured_adjustment"] is None
        else:
            assert entry["applies"] is True
            sa = entry["structured_adjustment"]
            assert set(sa.keys()) == STRUCTURED_ADJUSTMENT_KEYS[dtype]

    hourly_plan = response["hourly_plan"]
    assert len(hourly_plan) == 24
    assert [h["hour"] for h in hourly_plan] == list(range(24))
    for h in hourly_plan:
        assert set(h.keys()) == HOURLY_ENTRY_KEYS
        assert h["battery_action"] in ("charge", "discharge", "idle")
        if h["battery_action"] == "idle":
            assert h["battery_kwh"] == 0


@pytest.mark.parametrize("case", _load_cases(), ids=case_ids())
def test_replay_zero_violations(case):
    request, directives, response = run_pipeline(case)
    violations = replay(request, directives, response)
    assert violations == [], f"{case['id']}: replay violations {violations}"


@pytest.mark.parametrize("case", _load_cases(), ids=case_ids())
def test_totals_self_consistent(case):
    _, _, response = run_pipeline(case)
    hourly_plan = response["hourly_plan"]

    recomputed_grid = sum(h["grid_kwh"] for h in hourly_plan)
    assert response["total_grid_kwh"] == pytest.approx(recomputed_grid, abs=1e-6)

    recomputed_peak = max(h["grid_kwh"] for h in hourly_plan)
    assert response["peak_grid_kwh"] == pytest.approx(recomputed_peak, abs=1e-6)


@pytest.mark.parametrize("case", _load_cases(), ids=case_ids())
def test_cost_within_tolerance_of_reference(case):
    _, _, response = run_pipeline(case)
    reference_cost = case["expected_output"]["total_cost_bdt"]
    assert abs(response["total_cost_bdt"] - reference_cost) <= 0.01, (
        f"{case['id']}: got {response['total_cost_bdt']}, reference {reference_cost} "
        "(above = suboptimal bug, below = constraint bug)"
    )


@pytest.mark.live
@pytest.mark.parametrize("case", _load_cases(), ids=case_ids())
def test_live_interpretation_matches_ground_truth(case):
    """Section 12.1's second half: the REAL Groq call, per case, must match
    ground truth (type, applies, hours, numerics within 0.01). Never runs in
    the default suite -- select explicitly with `pytest -m live` and a real
    GROQ_API_KEYS/GROQ_API_KEY set (conftest.py skips it otherwise)."""
    request = OptimizeRequest(**case["input"])
    battery = request.battery

    async def go():
        async with httpx.AsyncClient() as client:
            pool = create_key_pool()
            deadline = time.monotonic() + config.LLM_DEADLINE_SECONDS
            return await interpret_notes(request.operator_notes, battery, client, pool, deadline)

    result = asyncio.run(go())
    assert not result.degraded, f"{case['id']}: live interpretation degraded (provider/key issue?)"

    for expected in case["expected_output"]["directive_interpretation"]:
        got = result.directives[expected["note_index"]]
        assert got.directive_type == expected["directive_type"], (
            f"{case['id']} note {expected['note_index']}: got {got.directive_type}, "
            f"expected {expected['directive_type']}"
        )
        assert (got.directive_type != "no_op") == expected["applies"]

        sa = expected["structured_adjustment"] or {}
        if "hours" in sa:
            assert set(got.hours) == set(sa["hours"]), (
                f"{case['id']} note {expected['note_index']}: hours {got.hours} != {sa['hours']}"
            )
        if "factor" in sa:
            assert got.factor is not None and abs(got.factor - sa["factor"]) <= 0.01
        if "minimum_energy_kwh" in sa:
            assert got.minimum_energy_kwh is not None and abs(got.minimum_energy_kwh - sa["minimum_energy_kwh"]) <= 0.01
        if "max_grid_kwh" in sa:
            assert got.max_grid_kwh is not None and abs(got.max_grid_kwh - sa["max_grid_kwh"]) <= 0.01
