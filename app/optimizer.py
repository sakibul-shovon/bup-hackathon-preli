"""Exact LP construction, solve, canonicalization, feasibility salvage (plan Section 10).

Must not import app/validator.py (validator is an independent replay oracle, Section 11).
"""
import itertools

import numpy as np
from scipy.optimize import linprog

from app.config import EMIT_DP
from app.directives import (
    NormalizedDirective,
    merge_charge_ub,
    merge_discharge_ub,
    merge_eff_solar,
    merge_grid_cap,
    merge_reserve,
)
from app.schemas import InfeasibleError

SNAP_TOL = 1e-9


def solve_lp(demand, eff_solar, tariff, e0, cap, reserve, grid_cap, charge_ub, discharge_ub):
    """Reference LP (plan Section 10.2), ported verbatim. Signed battery flow, order g|s|b."""
    n = 24
    c = np.concatenate([tariff, np.zeros(n), np.zeros(n)])
    bounds = [(0.0, None if not np.isfinite(grid_cap[h]) else float(grid_cap[h])) for h in range(n)]
    bounds += [(0.0, float(eff_solar[h])) for h in range(n)]
    bounds += [(-float(discharge_ub[h]), float(charge_ub[h])) for h in range(n)]

    A_eq = np.zeros((n + 1, 3 * n))
    b_eq = np.zeros(n + 1)
    for h in range(n):
        A_eq[h, h] = 1.0
        A_eq[h, n + h] = 1.0
        A_eq[h, 2 * n + h] = -1.0
        b_eq[h] = demand[h]
    A_eq[n, 2 * n:] = 1.0

    A_ub = np.zeros((2 * n, 3 * n))
    b_ub = np.zeros(2 * n)
    for h in range(n):
        A_ub[h, 2 * n:2 * n + h + 1] = 1.0
        b_ub[h] = cap - e0
        A_ub[n + h, 2 * n:2 * n + h + 1] = -1.0
        b_ub[n + h] = e0 - reserve[h]

    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    return res


def _snap(x: float) -> float:
    return 0.0 if abs(x) < SNAP_TOL else float(x)


def canonicalize(res, demand, tariff, e0):
    """Section 10.4: snap dust, kill -0.0, rebuild SOC cumulatively, round to EMIT_DP."""
    n = 24
    g = [_snap(v) for v in res.x[:n]]
    s = [_snap(v) for v in res.x[n:2 * n]]
    b = [_snap(v) for v in res.x[2 * n:3 * n]]

    hourly_plan = []
    e = float(e0)
    for h in range(n):
        bh = b[h]
        if bh > SNAP_TOL:
            action = "charge"
            kwh = bh
            e = e + kwh
        elif bh < -SNAP_TOL:
            action = "discharge"
            kwh = -bh
            e = e - kwh
        else:
            action = "idle"
            kwh = 0.0

        hourly_plan.append({
            "hour": h,
            "grid_kwh": round(g[h], EMIT_DP) + 0.0,
            "solar_used_kwh": round(s[h], EMIT_DP) + 0.0,
            "battery_action": action,
            "battery_kwh": round(kwh, EMIT_DP) + 0.0,
            "battery_energy_after_kwh": round(e, EMIT_DP) + 0.0,
        })

    for p in hourly_plan:
        assert p["grid_kwh"] >= 0
        assert p["solar_used_kwh"] >= 0
        assert p["battery_kwh"] >= 0

    total_grid_kwh = round(sum(p["grid_kwh"] for p in hourly_plan), EMIT_DP) + 0.0
    total_cost_bdt = round(
        sum(p["grid_kwh"] * tariff[h] for h, p in enumerate(hourly_plan)), EMIT_DP
    ) + 0.0
    peak_grid_kwh = max(p["grid_kwh"] for p in hourly_plan) + 0.0

    totals = {
        "total_grid_kwh": total_grid_kwh,
        "total_cost_bdt": total_cost_bdt,
        "peak_grid_kwh": peak_grid_kwh,
    }
    return hourly_plan, totals


def _solve_subset(subset, base_solar, base_minimum, base_max_charge, base_max_discharge,
                   demand, tariff, e0, cap):
    eff_solar = merge_eff_solar(base_solar, subset)
    reserve = merge_reserve(base_minimum, subset)
    grid_cap = merge_grid_cap(subset)
    charge_ub = merge_charge_ub(base_max_charge, subset)
    discharge_ub = merge_discharge_ub(base_max_discharge, subset)
    return solve_lp(demand, eff_solar, tariff, e0, cap, reserve, grid_cap, charge_ub, discharge_ub)


def optimize(directives: list[NormalizedDirective], base_solar, base_minimum, base_max_charge,
             base_max_discharge, demand, tariff, e0, cap):
    """Solve with all applicable directives; on infeasibility, salvage per Section 10.5.

    Returns (hourly_plan, totals, kept_directives, dropped_note_indices).
    Raises InfeasibleError only when even the empty-directive base scenario is infeasible.
    """
    applicable = [d for d in directives if d.directive_type != "no_op"]

    res = _solve_subset(applicable, base_solar, base_minimum, base_max_charge,
                         base_max_discharge, demand, tariff, e0, cap)
    if res.status == 0:
        plan, totals = canonicalize(res, demand, tariff, e0)
        return plan, totals, applicable, []
    if res.status != 2:
        raise RuntimeError(f"unexpected LP status {res.status}")

    best = None
    for size in range(len(applicable) - 1, -1, -1):
        candidates = []
        for subset_tuple in itertools.combinations(applicable, size):
            subset = list(subset_tuple)
            sub_res = _solve_subset(subset, base_solar, base_minimum, base_max_charge,
                                     base_max_discharge, demand, tariff, e0, cap)
            if sub_res.status == 0:
                candidates.append((sub_res.fun, subset, sub_res))
        if candidates:
            candidates.sort(key=lambda t: t[0])
            _, kept, best_res = candidates[0]
            best = (kept, best_res)
            break

    if best is None:
        raise InfeasibleError()

    kept, res = best
    plan, totals = canonicalize(res, demand, tariff, e0)
    kept_indices = {d.note_index for d in kept}
    dropped_indices = [d.note_index for d in applicable if d.note_index not in kept_indices]
    return plan, totals, kept, dropped_indices
