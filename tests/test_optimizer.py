"""Optimizer edge scenarios (plan Section 12.3). Validator negative tests (one
per replay check) already live in tests/test_validator.py -- not duplicated here.
"""
import pytest
from fastapi.testclient import TestClient

from app.directives import NormalizedDirective
from app.main import app
from app.optimizer import optimize, solve_full
from app.schemas import InfeasibleError
from app.validator import replay


def base_scenario(**overrides):
    scenario = dict(
        directives=[],
        base_solar=[0.0] * 24,
        base_minimum=20.0,
        base_max_charge=50.0,
        base_max_discharge=50.0,
        demand=[100.0] * 24,
        tariff=[10.0] * 24,
        e0=100.0,
        cap=300.0,
    )
    scenario.update(overrides)
    return scenario


def solve(scenario):
    return optimize(
        scenario["directives"], scenario["base_solar"], scenario["base_minimum"],
        scenario["base_max_charge"], scenario["base_max_discharge"], scenario["demand"],
        scenario["tariff"], scenario["e0"], scenario["cap"],
    )


class TestEdgeScenarios:
    def test_capacity_zero(self):
        s = base_scenario(cap=0.0, e0=0.0, base_minimum=0.0)
        plan, totals, kept, dropped = solve(s)
        assert dropped == []
        assert all(p["battery_action"] == "idle" for p in plan)
        assert totals["total_grid_kwh"] == pytest.approx(sum(s["demand"]))

    def test_rates_zero(self):
        s = base_scenario(base_max_charge=0.0, base_max_discharge=0.0)
        plan, totals, kept, dropped = solve(s)
        assert all(p["battery_action"] == "idle" for p in plan)

    def test_initial_equals_capacity(self):
        s = base_scenario(e0=300.0, cap=300.0)
        plan, totals, kept, dropped = solve(s)
        assert plan[-1]["battery_energy_after_kwh"] == pytest.approx(300.0, abs=1e-6)

    def test_initial_equals_minimum(self):
        s = base_scenario(e0=20.0, base_minimum=20.0)
        plan, totals, kept, dropped = solve(s)
        assert all(p["battery_energy_after_kwh"] >= 20.0 - 1e-6 for p in plan)

    def test_initial_less_than_minimum_is_422_via_api(self):
        """F4/I7a: unconditionally infeasible (neutrality forces E_after[23]=initial
        while the reserve floor forces E_after[23]>=minimum). Must be ACCEPTED at
        the API layer (400 would be wrong -- I7) and THEN return 422."""
        payload = {
            "scenario_id": "EDGE-INITIAL-LT-MIN",
            "operator_notes": ["no directive here"],
            "hours": [{"hour": h, "demand_kwh": 50.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 10.0}
                      for h in range(24)],
            "battery": {
                "capacity_kwh": 300.0, "initial_energy_kwh": 30.0, "minimum_energy_kwh": 50.0,
                "max_charge_kwh_per_hour": 50.0, "max_discharge_kwh_per_hour": 50.0,
            },
        }
        with TestClient(app) as client:
            r = client.post("/optimize-energy", json=payload)
        assert r.status_code == 422
        assert r.json() == {"error": "infeasible_scenario"}

    def test_initial_less_than_minimum_raises_at_optimizer_level_too(self):
        s = base_scenario(e0=30.0, base_minimum=50.0)
        with pytest.raises(InfeasibleError):
            solve(s)

    def test_zero_solar_everywhere(self):
        s = base_scenario(base_solar=[0.0] * 24)
        plan, totals, kept, dropped = solve(s)
        assert all(p["solar_used_kwh"] == 0 for p in plan)

    def test_solar_exceeds_demand_at_midday(self):
        solar = [0.0] * 24
        for h in range(10, 15):
            solar[h] = 300.0  # far above demand -- battery should charge from surplus
        s = base_scenario(base_solar=solar)
        plan, totals, kept, dropped = solve(s)
        assert any(p["battery_action"] == "charge" and 10 <= p["hour"] <= 14 for p in plan)

    def test_all_tariffs_zero(self):
        s = base_scenario(tariff=[0.0] * 24)
        plan, totals, kept, dropped = solve(s)
        assert totals["total_cost_bdt"] == 0.0

    def test_flat_tariffs_alternate_optima_still_replay_clean(self):
        s = base_scenario(tariff=[10.0] * 24)
        plan, totals, kept, dropped = solve(s)
        from app.schemas import OptimizeRequest

        request = OptimizeRequest(
            scenario_id="FLAT",
            operator_notes=["n/a"],
            hours=[{"hour": h, "demand_kwh": s["demand"][h], "solar_kwh": s["base_solar"][h],
                    "tariff_bdt_per_kwh": s["tariff"][h]} for h in range(24)],
            battery={"capacity_kwh": s["cap"], "initial_energy_kwh": s["e0"],
                     "minimum_energy_kwh": s["base_minimum"],
                     "max_charge_kwh_per_hour": s["base_max_charge"],
                     "max_discharge_kwh_per_hour": s["base_max_discharge"]},
        )
        plan_dict = {"hourly_plan": plan, **totals}
        assert replay(request, s["directives"], plan_dict) == []

    def test_tight_grid_cap_at_exact_feasibility_edge(self):
        demand = [100.0] * 24
        cap_note = NormalizedDirective(0, "max_grid_window", hours=[5], max_grid_kwh=demand[5])
        s = base_scenario(demand=demand, directives=[cap_note])
        plan, totals, kept, dropped = solve(s)
        assert dropped == []
        assert plan[5]["grid_kwh"] <= demand[5] + 1e-6

    def test_reserve_window_requires_precharging(self):
        reserve_note = NormalizedDirective(
            0, "minimum_battery_reserve", hours=[18, 19, 20], minimum_energy_kwh=250.0
        )
        s = base_scenario(e0=100.0, cap=300.0, directives=[reserve_note])
        plan, totals, kept, dropped = solve(s)
        assert dropped == []
        for h in (18, 19, 20):
            assert plan[h]["battery_energy_after_kwh"] >= 250.0 - 1e-6
        assert any(p["battery_action"] == "charge" and p["hour"] < 18 for p in plan)

    def test_contradiction_no_charge_all_day_plus_reserve_above_initial_is_lp_infeasible(self):
        """no_charge_window covering all 24h forces the battery to only ever
        discharge/idle, so SOC can never rise above `initial` -- a reserve
        directive demanding more than `initial` makes the FULL directive set
        infeasible at the raw LP level (optimize()'s own salvage recovers a
        valid schedule by dropping one of the two; this test asserts the raw
        LP correctly detects the conflict before any salvage runs)."""
        no_charge = NormalizedDirective(0, "no_charge_window", hours=list(range(24)))
        reserve = NormalizedDirective(1, "minimum_battery_reserve", hours=[12], minimum_energy_kwh=250.0)
        s = base_scenario(e0=100.0, cap=300.0, directives=[no_charge, reserve])

        res = solve_full(s["directives"], s["base_solar"], s["base_minimum"], s["base_max_charge"],
                          s["base_max_discharge"], s["demand"], s["tariff"], s["e0"], s["cap"])
        assert res.status == 2, "expected the raw LP to detect infeasibility"

        # optimize()'s salvage should still recover a valid (partial) schedule
        plan, totals, kept, dropped = solve(s)
        assert len(dropped) == 1
