"""Deterministic IR validation, pure functions (plan Section 8).

Signature correction (rule 3b, V4 overrides stale V3 body text): Section 8's prose
still writes `validate_ir(ir_json_text, note_count, capacity)`, but F8/Section 7.2
extended reserve_unit to a 4-value enum (kwh, percent_of_capacity, percent_of_initial,
percent_of_minimum) and explicitly assigns guardrails.py the conversion for all four.
Converting percent_of_initial/percent_of_minimum needs initial_energy_kwh and
minimum_energy_kwh, not just capacity, so this module takes the full battery object.
"""
import json
import math
from dataclasses import dataclass

from app.directives import NormalizedDirective, hours_from_windows, reserve_kwh, solar_factor

ALLOWED_DIRECTIVE_TYPES = {
    "solar_reduction", "minimum_battery_reserve", "no_charge_window",
    "no_discharge_window", "max_grid_window", "no_op",
}
ALLOWED_SOLAR_MEANINGS = {"remaining", "reduced_by"}
ALLOWED_RESERVE_UNITS = {"kwh", "percent_of_capacity", "percent_of_initial", "percent_of_minimum"}


class GuardrailError(Exception):
    """Structural failure -- no per-note recovery possible (bad JSON, wrong note
    count, duplicate/missing indices). `violations` is a list of machine-readable
    strings, fed back verbatim in the corrective re-ask.
    """

    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__("; ".join(violations))


@dataclass
class GuardrailResult:
    """Returned whenever the payload's index coverage allows per-note recovery.

    valid: note_index -> NormalizedDirective, for every note that passed all checks.
    violations: [{"note_index": int, "reason": str}, ...] for the notes that didn't --
    the terminal degrade (I5) keeps `valid` and reports the rest as no_op.
    """
    valid: dict
    violations: list


def _raise_on_constant(name: str):
    raise ValueError(f"disallowed JSON constant: {name}")


def _is_finite_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _validate_windows(windows) -> tuple[list[int], str | None]:
    if not isinstance(windows, list) or not windows:
        return [], "windows must be a non-empty list"
    parsed = []
    for w in windows:
        if not isinstance(w, dict):
            return [], "window entry is not an object"
        start = w.get("start_hour")
        end = w.get("end_hour_exclusive")
        if not isinstance(start, int) or isinstance(start, bool) or not (0 <= start <= 23):
            return [], f"start_hour out of range: {start!r}"
        if not isinstance(end, int) or isinstance(end, bool) or not (1 <= end <= 24):
            return [], f"end_hour_exclusive out of range: {end!r}"
        parsed.append((start, end))
    hours = hours_from_windows(parsed)
    if not hours or len(hours) > 24:
        return [], "expanded window union is empty or exceeds 24 hours"
    return hours, None


def _validate_note(note: dict, battery) -> tuple[NormalizedDirective | None, str | None]:
    """Returns (directive, error). error is None iff the note fully validated."""
    dtype = note.get("directive_type")
    if dtype not in ALLOWED_DIRECTIVE_TYPES:
        return None, f"directive_type not allowed: {dtype!r}"

    windows = note.get("windows")
    solar_value = note.get("solar_percent_value")
    solar_meaning = note.get("solar_percent_meaning")
    reserve_value = note.get("reserve_value")
    reserve_unit = note.get("reserve_unit")
    max_grid = note.get("max_grid_kwh")
    explanation = note.get("explanation", "")
    if not isinstance(explanation, str):
        explanation = ""
    note_index = note["note_index"]

    if dtype == "no_op":
        if any(x is not None for x in (windows, solar_value, solar_meaning, reserve_value, reserve_unit, max_grid)):
            return None, "no_op must have all parameter fields null"
        return NormalizedDirective(note_index, "no_op", explanation=explanation), None

    if dtype == "solar_reduction":
        hours, err = _validate_windows(windows)
        if err:
            return None, err
        if not _is_finite_number(solar_value) or not (0 <= solar_value <= 100):
            return None, f"solar_percent_value invalid: {solar_value!r}"
        if solar_meaning not in ALLOWED_SOLAR_MEANINGS:
            return None, f"solar_percent_meaning invalid: {solar_meaning!r}"
        if reserve_value is not None or reserve_unit is not None or max_grid is not None:
            return None, "solar_reduction must not set reserve/grid fields"
        factor = solar_factor(solar_value, solar_meaning)
        return NormalizedDirective(note_index, "solar_reduction", hours=hours,
                                    factor=factor, explanation=explanation), None

    if dtype == "minimum_battery_reserve":
        hours, err = _validate_windows(windows)
        if err:
            return None, err
        if not _is_finite_number(reserve_value) or reserve_value < 0:
            return None, f"reserve_value invalid: {reserve_value!r}"
        if reserve_unit not in ALLOWED_RESERVE_UNITS:
            return None, f"reserve_unit invalid: {reserve_unit!r}"
        if solar_value is not None or solar_meaning is not None or max_grid is not None:
            return None, "minimum_battery_reserve must not set solar/grid fields"
        computed = reserve_kwh(reserve_value, reserve_unit, battery.capacity_kwh,
                                battery.initial_energy_kwh, battery.minimum_energy_kwh)
        if computed > battery.capacity_kwh:
            return None, f"computed reserve {computed} exceeds capacity {battery.capacity_kwh}"
        return NormalizedDirective(note_index, "minimum_battery_reserve", hours=hours,
                                    minimum_energy_kwh=computed, explanation=explanation), None

    if dtype in ("no_charge_window", "no_discharge_window"):
        hours, err = _validate_windows(windows)
        if err:
            return None, err
        if any(x is not None for x in (solar_value, solar_meaning, reserve_value, reserve_unit, max_grid)):
            return None, f"{dtype} must not set any value fields"
        return NormalizedDirective(note_index, dtype, hours=hours, explanation=explanation), None

    # dtype == "max_grid_window"
    hours, err = _validate_windows(windows)
    if err:
        return None, err
    if not _is_finite_number(max_grid) or max_grid < 0:
        return None, f"max_grid_kwh invalid: {max_grid!r}"
    if solar_value is not None or solar_meaning is not None or reserve_value is not None or reserve_unit is not None:
        return None, "max_grid_window must not set solar/reserve fields"
    return NormalizedDirective(note_index, "max_grid_window", hours=hours,
                                max_grid_kwh=round(float(max_grid), 6), explanation=explanation), None


def validate_ir(ir_json_text: str, note_count: int, battery) -> GuardrailResult:
    """Section 8, checks 1-8. Raises GuardrailError only for structural failures
    where no per-note recovery is possible; otherwise returns whichever notes
    passed (partial or full) plus the per-note violations for the rest -- never
    repairs, clamps, or guesses a value (check 7).
    """
    try:
        data = json.loads(ir_json_text, parse_constant=_raise_on_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise GuardrailError([f"invalid JSON: {exc}"]) from exc

    if not isinstance(data, dict) or not isinstance(data.get("notes"), list):
        raise GuardrailError(["top-level shape must be an object with a 'notes' list"])

    notes = data["notes"]
    if len(notes) != note_count:
        raise GuardrailError([f"expected {note_count} notes, got {len(notes)}"])

    indices = [n.get("note_index") if isinstance(n, dict) else None for n in notes]
    if set(indices) != set(range(note_count)):
        raise GuardrailError([f"note_index set must be exactly 0..{note_count - 1}, got {indices}"])

    by_index = {n["note_index"]: n for n in notes}

    valid: dict = {}
    violations: list = []
    for idx in range(note_count):
        directive, err = _validate_note(by_index[idx], battery)
        if err:
            violations.append({"note_index": idx, "reason": err})
        else:
            valid[idx] = directive

    return GuardrailResult(valid=valid, violations=violations)
