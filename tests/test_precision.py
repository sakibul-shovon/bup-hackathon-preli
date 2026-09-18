"""F2 regression guard (plan Section 12.5b) -- the 10 public cases have integer
inputs, so every rounding residual there is exactly 0 and 4 dp looks perfectly
safe. This file is what actually catches it: >=300 feasible decimal-heavy
scenarios, at eps=1e-6, through the real optimizer -> canonicalize -> validator
pipeline.
"""
import random

import pytest

from app import config
from app.directives import NormalizedDirective
from app.optimizer import optimize
from app.schemas import OptimizeRequest
from app.validator import replay

NON_TERMINATING_FACTORS = [round(1 / 3, 6), round(2 / 3, 6), round(0.15, 6)]

N_SCENARIOS = 300


def _gen_scenario(seed: int):
    rng = random.Random(seed)
    dp_hourly = rng.choice([1, 2, 3, 4])
    dp_battery = rng.choice([2, 3])

    demand = [round(rng.uniform(50, 250), dp_hourly) for _ in range(24)]
    solar = [round(rng.uniform(0, 200), dp_hourly) if 6 <= h <= 18 else 0.0 for h in range(24)]
    tariff = [round(rng.uniform(4, 30), dp_hourly) for _ in range(24)]

    capacity = round(rng.uniform(300, 600), dp_battery)
    minimum = round(rng.uniform(20, 80), dp_battery)
    # initial in [minimum, capacity] -- guarantees feasibility: an all-idle
    # schedule (grid = demand - solar_used) always satisfies reserve/capacity
    # bounds and end-of-day neutrality trivially.
    initial = round(rng.uniform(minimum, capacity), dp_battery)
    max_charge = round(rng.uniform(80, 150), dp_battery)
    max_discharge = round(rng.uniform(80, 150), dp_battery)

    factor = rng.choice(NON_TERMINATING_FACTORS)
    directive = NormalizedDirective(0, "solar_reduction", hours=list(range(9, 15)), factor=factor)

    request = OptimizeRequest(
        scenario_id=f"PRECISION-{seed}",
        operator_notes=["synthetic precision-test note"],
        hours=[{"hour": h, "demand_kwh": demand[h], "solar_kwh": solar[h],
                "tariff_bdt_per_kwh": tariff[h]} for h in range(24)],
        battery={
            "capacity_kwh": capacity, "initial_energy_kwh": initial,
            "minimum_energy_kwh": minimum, "max_charge_kwh_per_hour": max_charge,
            "max_discharge_kwh_per_hour": max_discharge,
        },
    )
    return request, [directive], demand, solar, tariff, capacity, minimum, initial, max_charge, max_discharge


class TestConfigCanary:
    """I36: emission precision and replay eps are one decision. If anyone lowers
    EMIT_DP without raising REPLAY_EPS to match, this fails loudly."""

    def test_emit_dp_is_8(self):
        assert config.EMIT_DP == 8

    def test_eps_quantum_ratio_at_least_100(self):
        assert config.REPLAY_EPS / (10 ** -config.EMIT_DP) >= 100


@pytest.mark.parametrize("seed", range(N_SCENARIOS))
def test_decimal_heavy_scenario_replays_clean(seed):
    request, directives, demand, solar, tariff, capacity, minimum, initial, max_charge, max_discharge = (
        _gen_scenario(seed)
    )
    hourly_plan, totals, kept, dropped = optimize(
        directives, solar, minimum, max_charge, max_discharge, demand, tariff, initial, capacity
    )
    assert dropped == [], f"seed {seed}: feasible-by-construction scenario dropped a directive"

    plan = {"hourly_plan": hourly_plan, **totals}
    violations = replay(request, directives, plan, eps=config.REPLAY_EPS)
    assert violations == [], f"seed {seed}: replay violations {violations}"
