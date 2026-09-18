"""Independent replay validator (plan Section 11).

Hard rule: this module shares ZERO code with app/optimizer.py. It is written
without reading optimizer.py, and every derived per-hour array used below
(effective solar, active reserve, grid cap, charge/discharge bounds) is
recomputed here from scratch, from the original request and the final
normalized directives -- never trusted from anything the optimizer passed
along. The only things imported from the rest of the app are the request
model shape (app/schemas.py), the directive dataclass shape for typing
(app/directives.py's NormalizedDirective -- its fields only, never its
merge_* helper functions), and two constants from app/config.py.
"""
import logging
import math

from app.config import EMIT_DP, REPLAY_EPS
from app.directives import NormalizedDirective  # dataclass shape only, for typing
from app.schemas import OptimizeRequest

logger = logging.getLogger("gridwise.validator")


class ValidatorInternalError(RuntimeError):
    """Raised when even the trivial-plan floor fails replay.

    The caller (main.py) should catch this and return the controlled
    500 {"error":"internal_error"} response per plan Section 11's runtime
    policy ("trivial plan also invalid -> 500").
    """


# --------------------------------------------------------------------------
# Independent recomputation of per-hour derived arrays (from the ORIGINAL
# request + final normalized directives only -- never from the plan/optimizer).
# --------------------------------------------------------------------------

def _by_hour(request: OptimizeRequest) -> list:
    """Request hour entries reindexed 0..23 by their .hour field."""
    idx = {h.hour: h for h in request.hours}
    return [idx[i] for i in range(24)]


def _eff_solar(request: OptimizeRequest, directives: list) -> list[float]:
    ordered = _by_hour(request)
    eff = [float(ordered[h].solar_kwh) for h in range(24)]
    for d in directives:
        if d.directive_type == "solar_reduction" and d.factor is not None:
            for h in d.hours:
                if 0 <= h < 24:
                    eff[h] *= d.factor
    return eff


def _active_reserve(request: OptimizeRequest, directives: list) -> list[float]:
    base = float(request.battery.minimum_energy_kwh)
    reserve = [base] * 24
    for d in directives:
        if d.directive_type == "minimum_battery_reserve" and d.minimum_energy_kwh is not None:
            for h in d.hours:
                if 0 <= h < 24 and d.minimum_energy_kwh > reserve[h]:
                    reserve[h] = float(d.minimum_energy_kwh)
    return reserve


def _grid_cap(directives: list) -> list[float]:
    cap = [math.inf] * 24
    for d in directives:
        if d.directive_type == "max_grid_window" and d.max_grid_kwh is not None:
            for h in d.hours:
                if 0 <= h < 24 and d.max_grid_kwh < cap[h]:
                    cap[h] = float(d.max_grid_kwh)
    return cap


def _charge_ub(request: OptimizeRequest, directives: list) -> list[float]:
    ub = [float(request.battery.max_charge_kwh_per_hour)] * 24
    for d in directives:
        if d.directive_type == "no_charge_window":
            for h in d.hours:
                if 0 <= h < 24:
                    ub[h] = 0.0
    return ub


def _discharge_ub(request: OptimizeRequest, directives: list) -> list[float]:
    ub = [float(request.battery.max_discharge_kwh_per_hour)] * 24
    for d in directives:
        if d.directive_type == "no_discharge_window":
            for h in d.hours:
                if 0 <= h < 24:
                    ub[h] = 0.0
    return ub


def _num(value):
    """Return value if it's a real finite number (not bool), else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


# --------------------------------------------------------------------------
# The 10 numbered checks from plan Section 11, each producing zero or more
# (label, magnitude) residuals. magnitude == 0 means satisfied exactly;
# magnitude == math.inf marks a structural/enum failure with no numeric
# residual; otherwise magnitude is the numeric amount the check was violated
# by (before applying eps -- eps is applied by the callers below).
# --------------------------------------------------------------------------

def _residuals(request: OptimizeRequest, directives: list, plan: dict) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []

    hourly = plan.get("hourly_plan") if isinstance(plan, dict) else None
    if not isinstance(hourly, list):
        return [("check1_entries: hourly_plan missing or not a list", math.inf)]

    # --- Check 1: exactly 24 entries, hours 0..23 in order ---
    seen_hours = [e.get("hour") if isinstance(e, dict) else None for e in hourly]
    if len(hourly) != 24 or seen_hours != list(range(24)):
        out.append((f"check1_entries: expected hours 0..23 in order, got {seen_hours}", math.inf))

    n = min(len(hourly), 24)

    def entry(i: int) -> dict:
        e = hourly[i] if i < len(hourly) else {}
        return e if isinstance(e, dict) else {}

    # --- Check 2: every numeric field finite; grid/solar_used/battery_kwh >= 0 ---
    for i in range(n):
        e = entry(i)
        for field in ("grid_kwh", "solar_used_kwh", "battery_kwh", "battery_energy_after_kwh"):
            raw = e.get(field)
            v = _num(raw)
            if v is None:
                out.append((f"check2_finite: hour {i} field {field} not finite ({raw!r})", math.inf))
            elif field != "battery_energy_after_kwh" and v < 0:
                out.append((f"check2_nonneg: hour {i} field {field} is negative ({v})", abs(v)))

    # --- Check 3: battery_action enum; idle => battery_kwh == 0 ---
    for i in range(n):
        e = entry(i)
        action = e.get("battery_action")
        if action not in ("charge", "discharge", "idle"):
            out.append((f"check3_action_enum: hour {i} battery_action invalid ({action!r})", math.inf))
        elif action == "idle":
            v = _num(e.get("battery_kwh"))
            if v is None:
                out.append((f"check3_idle_zero: hour {i} idle battery_kwh not finite ({e.get('battery_kwh')!r})", math.inf))
            elif v != 0:
                out.append((f"check3_idle_zero: hour {i} idle but battery_kwh={v}", abs(v)))

    # --- Check 4: recomputed effective solar bound ---
    eff_solar = _eff_solar(request, directives)
    for i in range(n):
        e = entry(i)
        su = _num(e.get("solar_used_kwh"))
        if su is not None:
            excess = su - eff_solar[i]
            if excess > 0:
                out.append((f"check4_solar_bound: hour {i} solar_used {su} exceeds recomputed eff_solar {eff_solar[i]}", excess))

    # --- Check 5: recomputed SOC trajectory + reserve/capacity bounds ---
    reserve = _active_reserve(request, directives)
    capacity = float(request.battery.capacity_kwh)
    e_soc = float(request.battery.initial_energy_kwh)
    for i in range(n):
        e = entry(i)
        action = e.get("battery_action")
        bk = _num(e.get("battery_kwh")) or 0.0
        if action == "charge":
            e_soc = e_soc + bk
        elif action == "discharge":
            e_soc = e_soc - bk
        # idle: unchanged

        reported = _num(e.get("battery_energy_after_kwh"))
        if reported is not None:
            diff = abs(reported - e_soc)
            if diff > 0:
                out.append((f"check5_soc_recompute: hour {i} reported E_after {reported} != recomputed {e_soc} (diff {diff})", diff))

        lo = reserve[i]
        if e_soc < lo:
            out.append((f"check5_reserve_floor: hour {i} recomputed SOC {e_soc} below active reserve {lo}", lo - e_soc))
        if e_soc > capacity:
            out.append((f"check5_capacity_ceiling: hour {i} recomputed SOC {e_soc} above capacity {capacity}", e_soc - capacity))

    # --- Check 6: charge/discharge upper bounds (respecting prohibition windows) ---
    charge_ub = _charge_ub(request, directives)
    discharge_ub = _discharge_ub(request, directives)
    for i in range(n):
        e = entry(i)
        action = e.get("battery_action")
        bk = _num(e.get("battery_kwh")) or 0.0
        if action == "charge":
            excess = bk - charge_ub[i]
            if excess > 0:
                out.append((f"check6_charge_ub: hour {i} charge {bk} exceeds bound {charge_ub[i]}", excess))
        elif action == "discharge":
            excess = bk - discharge_ub[i]
            if excess > 0:
                out.append((f"check6_discharge_ub: hour {i} discharge {bk} exceeds bound {discharge_ub[i]}", excess))

    # --- Check 7: energy balance equation ---
    ordered = _by_hour(request)
    for i in range(n):
        e = entry(i)
        grid = _num(e.get("grid_kwh")) or 0.0
        su = _num(e.get("solar_used_kwh")) or 0.0
        bk = _num(e.get("battery_kwh")) or 0.0
        action = e.get("battery_action")
        charge_part = bk if action == "charge" else 0.0
        discharge_part = bk if action == "discharge" else 0.0
        demand = float(ordered[i].demand_kwh)
        residual = abs(grid + su + discharge_part - demand - charge_part)
        if residual > 0:
            out.append((f"check7_energy_balance: hour {i} residual {residual}", residual))

    # --- Check 8: grid cap ---
    grid_cap = _grid_cap(directives)
    for i in range(n):
        e = entry(i)
        grid = _num(e.get("grid_kwh"))
        if grid is not None:
            excess = grid - grid_cap[i]
            if excess > 0:
                out.append((f"check8_grid_cap: hour {i} grid {grid} exceeds cap {grid_cap[i]}", excess))

    # --- Check 9: end-of-day neutrality ---
    initial = float(request.battery.initial_energy_kwh)
    diff9 = abs(e_soc - initial)
    if diff9 > 0:
        out.append((f"check9_neutrality: recomputed final SOC {e_soc} != initial_energy_kwh {initial} (diff {diff9})", diff9))

    # --- Check 10: totals self-consistency, using the RETURNED per-hour values ---
    grid_values = []
    cost = 0.0
    for i in range(n):
        e = entry(i)
        g = _num(e.get("grid_kwh")) or 0.0
        grid_values.append(g)
        cost += g * float(ordered[i].tariff_bdt_per_kwh)
    sum_grid = sum(grid_values)
    peak_expected = max(grid_values) if grid_values else 0.0

    total_grid = _num(plan.get("total_grid_kwh")) if isinstance(plan, dict) else None
    total_cost = _num(plan.get("total_cost_bdt")) if isinstance(plan, dict) else None
    peak_grid = _num(plan.get("peak_grid_kwh")) if isinstance(plan, dict) else None

    if total_grid is None:
        out.append(("check10_total_grid: total_grid_kwh missing or not finite", math.inf))
    else:
        d = abs(sum_grid - total_grid)
        if d > 0:
            out.append((f"check10_total_grid: sum(grid)={sum_grid} != total_grid_kwh={total_grid} (diff {d})", d))

    if total_cost is None:
        out.append(("check10_total_cost: total_cost_bdt missing or not finite", math.inf))
    else:
        d = abs(cost - total_cost)
        if d > 0:
            out.append((f"check10_total_cost: sum(grid*tariff)={cost} != total_cost_bdt={total_cost} (diff {d})", d))

    if peak_grid is None:
        out.append(("check10_peak_grid: peak_grid_kwh missing or not finite", math.inf))
    else:
        d = abs(peak_expected - peak_grid)
        if d > 0:
            out.append((f"check10_peak_grid: max(grid)={peak_expected} != peak_grid_kwh={peak_grid} (diff {d})", d))

    return out


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def replay(request: OptimizeRequest, directives: list[NormalizedDirective], plan: dict,
           eps: float = REPLAY_EPS) -> list[str]:
    """Run all 10 checks from plan Section 11. Empty list == valid.

    `plan` is a dict shaped like the response contract's schedule fields:
    {"hourly_plan": [24 dicts with hour/grid_kwh/solar_used_kwh/battery_action/
    battery_kwh/battery_energy_after_kwh], "total_grid_kwh": ..., "total_cost_bdt": ...,
    "peak_grid_kwh": ...}. `directives` is the final list of NormalizedDirective
    (or any objects with the same .directive_type/.hours/.factor/.minimum_energy_kwh/
    .max_grid_kwh attributes).
    """
    return [label for label, magnitude in _residuals(request, directives, plan) if magnitude > eps]


def max_violation(request: OptimizeRequest, directives: list[NormalizedDirective], plan: dict) -> float:
    """The largest residual magnitude across all 10 checks (0.0 if the plan is exact).

    Structural/enum failures (wrong entry count, bad enum value, non-finite field)
    report math.inf. This is the quantity the three-tier runtime policy below acts on.
    """
    residuals = _residuals(request, directives, plan)
    if not residuals:
        return 0.0
    return max(magnitude for _, magnitude in residuals)


def build_trivial_plan(request: OptimizeRequest) -> dict:
    """The always-available floor plan (plan Section 11, "Trivial plan" paragraph).

    grid_kwh[h] = demand[h], solar_used_kwh = 0, battery idle all 24 hours,
    battery_energy_after_kwh flat at initial_energy_kwh. Totals computed from
    those same values.
    """
    ordered = _by_hour(request)
    initial = round(float(request.battery.initial_energy_kwh), EMIT_DP)
    hourly = []
    total_grid = 0.0
    total_cost = 0.0
    peak = 0.0
    for h in range(24):
        demand = round(float(ordered[h].demand_kwh), EMIT_DP)
        tariff = float(ordered[h].tariff_bdt_per_kwh)
        hourly.append({
            "hour": h,
            "grid_kwh": demand,
            "solar_used_kwh": 0.0,
            "battery_action": "idle",
            "battery_kwh": 0.0,
            "battery_energy_after_kwh": initial,
        })
        total_grid += demand
        total_cost += demand * tariff
        peak = max(peak, demand)
    return {
        "hourly_plan": hourly,
        "total_grid_kwh": round(total_grid, EMIT_DP),
        "total_cost_bdt": round(total_cost, EMIT_DP),
        "peak_grid_kwh": round(peak, EMIT_DP),
    }


def validate_and_ship(request: OptimizeRequest, directives: list[NormalizedDirective], plan: dict,
                       eps: float = REPLAY_EPS, judge_tolerance: float = 0.01) -> dict:
    """The V4 three-tier runtime policy (plan Section 11, "Runtime policy").

        max_violation <= eps                    -> ship `plan` as-is
        eps < max_violation < judge_tolerance    -> log loudly, ship `plan` anyway
        max_violation >= judge_tolerance         -> build+replay the trivial plan,
                                                     ship IT if clean
        trivial plan also invalid                -> raise ValidatorInternalError
                                                     (caller returns 500)

    Returns the plan dict that should be shipped. Raises ValidatorInternalError
    only when even the trivial floor fails replay -- that is the sole path to a
    controlled 500 for this module.
    """
    mv = max_violation(request, directives, plan)

    if mv <= eps:
        return plan

    if mv < judge_tolerance:
        logger.error(
            "replay: residual %.3e exceeds internal eps %.3e but is within judge "
            "tolerance %.3g -- I36 precision assumption may be broken; shipping anyway. "
            "violations=%s",
            mv, eps, judge_tolerance, replay(request, directives, plan, eps=eps),
        )
        return plan

    logger.error(
        "replay: residual %.3e >= judge tolerance %.3g -- plan rejected, falling back "
        "to the trivial plan. violations=%s",
        mv, judge_tolerance, replay(request, directives, plan, eps=eps),
    )
    trivial = build_trivial_plan(request)
    trivial_mv = max_violation(request, directives, trivial)
    if trivial_mv < judge_tolerance:
        return trivial

    trivial_violations = replay(request, directives, trivial, eps=eps)
    logger.error(
        "replay: trivial plan ALSO invalid (residual %.3e). violations=%s",
        trivial_mv, trivial_violations,
    )
    raise ValidatorInternalError(
        f"trivial plan failed replay: max_violation={trivial_mv}, violations={trivial_violations}"
    )
