"""Window expansion, unit arithmetic, per-hour merge, response builders (plan Section 6.1, 8)."""
import math
from dataclasses import dataclass, field


@dataclass
class NormalizedDirective:
    note_index: int
    directive_type: str
    hours: list[int] = field(default_factory=list)
    factor: float | None = None
    minimum_energy_kwh: float | None = None
    max_grid_kwh: float | None = None
    explanation: str = ""


def expand(start_hour: int, end_hour_exclusive: int) -> list[int]:
    if end_hour_exclusive > start_hour:
        hours = list(range(start_hour, end_hour_exclusive))
    else:
        # midnight wrap, e.g. "10 PM until 1 AM" -> start 22, end 1
        hours = list(range(start_hour, 24)) + list(range(0, end_hour_exclusive))
    return sorted(set(hours))


def hours_from_windows(windows: list[tuple[int, int]]) -> list[int]:
    hours: set[int] = set()
    for start, end in windows:
        hours.update(expand(start, end))
    return sorted(hours)


def solar_factor(value: float, meaning: str) -> float:
    if meaning == "remaining":
        f = value / 100
    elif meaning == "reduced_by":
        f = 1 - value / 100
    else:
        raise ValueError(f"unknown solar_percent_meaning: {meaning}")
    return round(f, 6)


def reserve_kwh(value: float, unit: str, capacity: float, initial: float, minimum: float) -> float:
    if unit == "kwh":
        v = value
    elif unit == "percent_of_capacity":
        v = value / 100 * capacity
    elif unit == "percent_of_initial":
        v = value / 100 * initial
    elif unit == "percent_of_minimum":
        v = value / 100 * minimum
    else:
        raise ValueError(f"unknown reserve_unit: {unit}")
    return round(v, 6)


def merge_eff_solar(base_solar: list[float], directives: list[NormalizedDirective]) -> list[float]:
    eff = list(base_solar)
    for d in directives:
        if d.directive_type == "solar_reduction":
            for h in d.hours:
                eff[h] *= d.factor
    return eff


def merge_reserve(base_minimum: float, directives: list[NormalizedDirective]) -> list[float]:
    reserve = [base_minimum] * 24
    for d in directives:
        if d.directive_type == "minimum_battery_reserve":
            for h in d.hours:
                reserve[h] = max(reserve[h], d.minimum_energy_kwh)
    return reserve


def merge_grid_cap(directives: list[NormalizedDirective]) -> list[float]:
    cap = [math.inf] * 24
    for d in directives:
        if d.directive_type == "max_grid_window":
            for h in d.hours:
                cap[h] = min(cap[h], d.max_grid_kwh)
    return cap


def merge_charge_ub(base_max_charge: float, directives: list[NormalizedDirective]) -> list[float]:
    ub = [base_max_charge] * 24
    for d in directives:
        if d.directive_type == "no_charge_window":
            for h in d.hours:
                ub[h] = 0.0
    return ub


def merge_discharge_ub(base_max_discharge: float, directives: list[NormalizedDirective]) -> list[float]:
    ub = [base_max_discharge] * 24
    for d in directives:
        if d.directive_type == "no_discharge_window":
            for h in d.hours:
                ub[h] = 0.0
    return ub


def build_structured_adjustment(d: NormalizedDirective) -> dict | None:
    if d.directive_type == "no_op":
        return None
    if d.directive_type == "solar_reduction":
        return {"hours": d.hours, "factor": d.factor}
    if d.directive_type == "minimum_battery_reserve":
        return {"hours": d.hours, "minimum_energy_kwh": d.minimum_energy_kwh}
    if d.directive_type == "no_charge_window":
        return {"hours": d.hours}
    if d.directive_type == "no_discharge_window":
        return {"hours": d.hours}
    if d.directive_type == "max_grid_window":
        return {"hours": d.hours, "max_grid_kwh": d.max_grid_kwh}
    raise ValueError(f"unknown directive_type: {d.directive_type}")


def build_interpretation_entry(d: NormalizedDirective) -> dict:
    return {
        "note_index": d.note_index,
        "applies": d.directive_type != "no_op",
        "directive_type": d.directive_type,
        "structured_adjustment": build_structured_adjustment(d),
        "explanation": d.explanation,
    }


def build_interpretation_array(directives: list[NormalizedDirective]) -> list[dict]:
    return [build_interpretation_entry(d) for d in sorted(directives, key=lambda d: d.note_index)]
