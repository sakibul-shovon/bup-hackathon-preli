"""Tests for the independent replay validator (plan Section 11).

Each of the 10 numbered replay checks gets at least one dedicated test that
hand-builds a plan violating exactly that check and asserts the violation is
caught and named. The three-tier runtime policy (ship / log-and-ship /
trivial-fallback / raise) is also covered.
"""
import copy
import logging

import pytest

from app.directives import NormalizedDirective
from app.schemas import Battery, HourEntry, OptimizeRequest
from app.validator import (
    ValidatorInternalError,
    build_trivial_plan,
    max_violation,
    replay,
    validate_and_ship,
)

DEMAND = 10.0
SOLAR = 5.0
TARIFF = 7.0
CAPACITY = 100.0
INITIAL = 50.0
MINIMUM = 20.0
MAX_CHARGE = 20.0
MAX_DISCHARGE = 20.0


def make_request(**battery_overrides) -> OptimizeRequest:
    hours = [
        HourEntry(hour=h, demand_kwh=DEMAND, solar_kwh=SOLAR, tariff_bdt_per_kwh=TARIFF)
        for h in range(24)
    ]
    battery = Battery(
        capacity_kwh=CAPACITY,
        initial_energy_kwh=INITIAL,
        minimum_energy_kwh=MINIMUM,
        max_charge_kwh_per_hour=MAX_CHARGE,
        max_discharge_kwh_per_hour=MAX_DISCHARGE,
        **battery_overrides,
    )
    return OptimizeRequest(scenario_id="TEST-1", operator_notes=["note"], hours=hours, battery=battery)


def make_valid_plan() -> dict:
    """grid=5, solar_used=5 (balances demand=10); battery idle all 24h at SOC=50."""
    hourly = [
        {
            "hour": h,
            "grid_kwh": 5.0,
            "solar_used_kwh": 5.0,
            "battery_action": "idle",
            "battery_kwh": 0.0,
            "battery_energy_after_kwh": INITIAL,
        }
        for h in range(24)
    ]
    return {
        "hourly_plan": hourly,
        "total_grid_kwh": 5.0 * 24,
        "total_cost_bdt": 5.0 * TARIFF * 24,
        "peak_grid_kwh": 5.0,
    }


def has_check(violations: list[str], prefix: str) -> bool:
    return any(v.startswith(prefix) for v in violations)


class TestValidBaseline:
    def test_valid_plan_has_no_violations(self):
        request = make_request()
        plan = make_valid_plan()
        assert replay(request, [], plan) == []
        assert max_violation(request, [], plan) == 0.0


class TestCheck1EntryCount:
    def test_wrong_entry_count_caught(self):
        request = make_request()
        plan = make_valid_plan()
        plan["hourly_plan"] = plan["hourly_plan"][:23]  # drop hour 23
        violations = replay(request, [], plan)
        assert violations
        assert has_check(violations, "check1_entries")


class TestCheck2FiniteNonNegative:
    def test_negative_grid_kwh_caught(self):
        request = make_request()
        plan = make_valid_plan()
        plan["hourly_plan"][0]["grid_kwh"] = -1.0
        violations = replay(request, [], plan)
        assert violations
        assert has_check(violations, "check2_nonneg")

    def test_non_finite_field_caught(self):
        request = make_request()
        plan = make_valid_plan()
        plan["hourly_plan"][3]["solar_used_kwh"] = float("nan")
        violations = replay(request, [], plan)
        assert violations
        assert has_check(violations, "check2_finite")


class TestCheck3ActionEnumAndIdle:
    def test_invalid_enum_caught(self):
        request = make_request()
        plan = make_valid_plan()
        plan["hourly_plan"][0]["battery_action"] = "standby"
        violations = replay(request, [], plan)
        assert violations
        assert has_check(violations, "check3_action_enum")

    def test_idle_nonzero_battery_kwh_caught(self):
        request = make_request()
        plan = make_valid_plan()
        plan["hourly_plan"][0]["battery_kwh"] = 3.0  # action stays "idle"
        violations = replay(request, [], plan)
        assert violations
        assert has_check(violations, "check3_idle_zero")


class TestCheck4EffectiveSolarBound:
    def test_solar_used_exceeds_recomputed_eff_solar(self):
        request = make_request()
        plan = make_valid_plan()
        # eff_solar[0] recomputed independently = 5 * 0.5 = 2.5; plan claims 5.0
        directives = [NormalizedDirective(note_index=0, directive_type="solar_reduction", hours=[0], factor=0.5)]
        violations = replay(request, directives, plan)
        assert violations
        assert has_check(violations, "check4_solar_bound")


class TestCheck5SocAndReserve:
    def test_soc_recompute_mismatch_caught(self):
        request = make_request()
        plan = make_valid_plan()
        plan["hourly_plan"][0]["battery_energy_after_kwh"] = 999.0  # idle => should stay 50
        violations = replay(request, [], plan)
        assert violations
        assert has_check(violations, "check5_soc_recompute")

    def test_reserve_floor_breach_caught(self):
        request = make_request()
        plan = make_valid_plan()
        # recomputed reserve directive requires 80 kWh at hour 0; SOC stays 50 (idle) -> breach
        directives = [
            NormalizedDirective(note_index=0, directive_type="minimum_battery_reserve", hours=[0], minimum_energy_kwh=80.0)
        ]
        violations = replay(request, directives, plan)
        assert violations
        assert has_check(violations, "check5_reserve_floor")


class TestCheck6ChargeDischargeBounds:
    def test_charge_exceeds_bound_in_prohibited_window(self):
        request = make_request()
        plan = make_valid_plan()
        plan["hourly_plan"][0]["battery_action"] = "charge"
        plan["hourly_plan"][0]["battery_kwh"] = 5.0
        directives = [NormalizedDirective(note_index=0, directive_type="no_charge_window", hours=[0])]
        violations = replay(request, directives, plan)
        assert violations
        assert has_check(violations, "check6_charge_ub")

    def test_discharge_exceeds_base_bound(self):
        request = make_request()
        plan = make_valid_plan()
        plan["hourly_plan"][0]["battery_action"] = "discharge"
        plan["hourly_plan"][0]["battery_kwh"] = MAX_DISCHARGE + 5.0  # exceeds base 20 kWh/h
        violations = replay(request, [], plan)
        assert violations
        assert has_check(violations, "check6_discharge_ub")


class TestCheck7EnergyBalance:
    def test_balance_broken_caught(self):
        request = make_request()
        plan = make_valid_plan()
        plan["hourly_plan"][0]["grid_kwh"] = 0.0  # was 5.0; balance now off by 5
        violations = replay(request, [], plan)
        assert violations
        assert has_check(violations, "check7_energy_balance")


class TestCheck8GridCap:
    def test_grid_exceeds_recomputed_cap(self):
        request = make_request()
        plan = make_valid_plan()  # hour 0 grid_kwh = 5.0
        directives = [NormalizedDirective(note_index=0, directive_type="max_grid_window", hours=[0], max_grid_kwh=2.0)]
        violations = replay(request, directives, plan)
        assert violations
        assert has_check(violations, "check8_grid_cap")


class TestCheck9EndOfDayNeutrality:
    def test_final_soc_diverges_from_initial(self):
        request = make_request()
        plan = make_valid_plan()
        plan["hourly_plan"][0]["battery_action"] = "charge"
        plan["hourly_plan"][0]["battery_kwh"] = 10.0  # never discharged back -> final SOC != initial
        violations = replay(request, [], plan)
        assert violations
        assert has_check(violations, "check9_neutrality")


class TestCheck10Totals:
    def test_total_grid_mismatch_caught(self):
        request = make_request()
        plan = make_valid_plan()
        plan["total_grid_kwh"] = 999.0
        violations = replay(request, [], plan)
        assert has_check(violations, "check10_total_grid")

    def test_total_cost_mismatch_caught(self):
        request = make_request()
        plan = make_valid_plan()
        plan["total_cost_bdt"] = 1.0
        violations = replay(request, [], plan)
        assert has_check(violations, "check10_total_cost")

    def test_peak_grid_mismatch_caught(self):
        request = make_request()
        plan = make_valid_plan()
        plan["peak_grid_kwh"] = 0.0
        violations = replay(request, [], plan)
        assert has_check(violations, "check10_peak_grid")


class TestThreeTierPolicy:
    def test_clean_plan_ships_as_is(self):
        request = make_request()
        plan = make_valid_plan()
        result = validate_and_ship(request, [], plan)
        assert result == plan

    def test_tiny_violation_ships_anyway_with_loud_log(self, caplog):
        request = make_request()
        plan = make_valid_plan()
        plan["total_cost_bdt"] += 1e-4  # between eps (1e-6) and judge tolerance (0.01)
        assert 1e-6 < max_violation(request, [], plan) < 0.01

        with caplog.at_level(logging.ERROR, logger="gridwise.validator"):
            result = validate_and_ship(request, [], plan)

        assert result == plan  # shipped anyway, not the trivial plan
        assert any("shipping anyway" in r.message for r in caplog.records)

    def test_large_violation_falls_back_to_trivial_plan(self):
        request = make_request()
        plan = make_valid_plan()
        plan["total_cost_bdt"] += 1.0  # >= judge tolerance (0.01)
        assert max_violation(request, [], plan) >= 0.01

        result = validate_and_ship(request, [], plan)

        assert result == build_trivial_plan(request)
        assert result["hourly_plan"][0]["battery_action"] == "idle"
        assert all(e["grid_kwh"] == DEMAND for e in result["hourly_plan"])

    def test_trivial_plan_also_invalid_raises(self):
        request = make_request()
        # A grid-cap directive below demand makes even the trivial plan
        # (grid_kwh[h] = demand[h]) violate check8/I25 for every hour.
        directives = [
            NormalizedDirective(
                note_index=0,
                directive_type="max_grid_window",
                hours=list(range(24)),
                max_grid_kwh=DEMAND - 5.0,
            )
        ]
        broken_plan = {"hourly_plan": [], "total_grid_kwh": 0.0, "total_cost_bdt": 0.0, "peak_grid_kwh": 0.0}

        with pytest.raises(ValidatorInternalError):
            validate_and_ship(request, directives, broken_plan)
