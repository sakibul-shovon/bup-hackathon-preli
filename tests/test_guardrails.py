import json

import pytest

from app.guardrails import GuardrailError, validate_ir
from app.schemas import Battery


def make_battery(**overrides):
    defaults = dict(
        capacity_kwh=200, initial_energy_kwh=150, minimum_energy_kwh=50,
        max_charge_kwh_per_hour=100, max_discharge_kwh_per_hour=100,
    )
    defaults.update(overrides)
    return Battery(**defaults)


def ir(notes):
    return json.dumps({"notes": notes})


def no_op_note(idx, explanation="no effect"):
    return {
        "note_index": idx, "directive_type": "no_op", "windows": None,
        "solar_percent_value": None, "solar_percent_meaning": None,
        "reserve_value": None, "reserve_unit": None, "max_grid_kwh": None,
        "explanation": explanation,
    }


def solar_note(idx, start=12, end=14, value=25, meaning="remaining"):
    return {
        "note_index": idx, "directive_type": "solar_reduction",
        "windows": [{"start_hour": start, "end_hour_exclusive": end}],
        "solar_percent_value": value, "solar_percent_meaning": meaning,
        "reserve_value": None, "reserve_unit": None, "max_grid_kwh": None,
        "explanation": "solar reduced",
    }


def reserve_note(idx, value=50, unit="percent_of_capacity", start=18, end=20):
    return {
        "note_index": idx, "directive_type": "minimum_battery_reserve",
        "windows": [{"start_hour": start, "end_hour_exclusive": end}],
        "solar_percent_value": None, "solar_percent_meaning": None,
        "reserve_value": value, "reserve_unit": unit, "max_grid_kwh": None,
        "explanation": "reserve",
    }


def window_note(idx, dtype, start=1, end=3):
    return {
        "note_index": idx, "directive_type": dtype,
        "windows": [{"start_hour": start, "end_hour_exclusive": end}],
        "solar_percent_value": None, "solar_percent_meaning": None,
        "reserve_value": None, "reserve_unit": None, "max_grid_kwh": None,
        "explanation": dtype,
    }


def grid_note(idx, value=150, start=18, end=20):
    return {
        "note_index": idx, "directive_type": "max_grid_window",
        "windows": [{"start_hour": start, "end_hour_exclusive": end}],
        "solar_percent_value": None, "solar_percent_meaning": None,
        "reserve_value": None, "reserve_unit": None, "max_grid_kwh": value,
        "explanation": "grid cap",
    }


class TestHappyPaths:
    def test_no_op(self):
        battery = make_battery()
        result = validate_ir(ir([no_op_note(0)]), 1, battery)
        assert result.violations == []
        assert result.valid[0].directive_type == "no_op"
        assert result.valid[0].hours == []

    def test_solar_reduction_reduced_by(self):
        battery = make_battery()
        result = validate_ir(ir([solar_note(0, value=80, meaning="reduced_by")]), 1, battery)
        assert result.violations == []
        assert result.valid[0].factor == 0.2
        assert result.valid[0].hours == [12, 13]

    def test_reserve_percent_of_capacity(self):
        battery = make_battery(capacity_kwh=200)
        result = validate_ir(ir([reserve_note(0, value=50, unit="percent_of_capacity")]), 1, battery)
        assert result.violations == []
        assert result.valid[0].minimum_energy_kwh == 100.0

    def test_reserve_percent_of_initial(self):
        battery = make_battery(initial_energy_kwh=150)
        result = validate_ir(ir([reserve_note(0, value=100, unit="percent_of_initial")]), 1, battery)
        assert result.valid[0].minimum_energy_kwh == 150.0

    def test_reserve_percent_of_minimum(self):
        battery = make_battery(minimum_energy_kwh=50)
        result = validate_ir(ir([reserve_note(0, value=200, unit="percent_of_minimum")]), 1, battery)
        assert result.valid[0].minimum_energy_kwh == 100.0

    def test_reserve_kwh_direct(self):
        battery = make_battery()
        result = validate_ir(ir([reserve_note(0, value=120, unit="kwh")]), 1, battery)
        assert result.valid[0].minimum_energy_kwh == 120.0

    def test_no_charge_window(self):
        battery = make_battery()
        result = validate_ir(ir([window_note(0, "no_charge_window")]), 1, battery)
        assert result.valid[0].directive_type == "no_charge_window"
        assert result.valid[0].hours == [1, 2]

    def test_no_discharge_window(self):
        battery = make_battery()
        result = validate_ir(ir([window_note(0, "no_discharge_window")]), 1, battery)
        assert result.valid[0].directive_type == "no_discharge_window"

    def test_max_grid_window(self):
        battery = make_battery()
        result = validate_ir(ir([grid_note(0, value=150)]), 1, battery)
        assert result.valid[0].max_grid_kwh == 150.0

    def test_multiple_notes_all_valid(self):
        battery = make_battery()
        result = validate_ir(ir([solar_note(0), no_op_note(1)]), 2, battery)
        assert result.violations == []
        assert len(result.valid) == 2


class TestStructuralFailuresRaise:
    def test_bad_json(self):
        battery = make_battery()
        with pytest.raises(GuardrailError):
            validate_ir("not json", 1, battery)

    def test_nan_rejected(self):
        battery = make_battery()
        with pytest.raises(GuardrailError):
            validate_ir('{"notes": [NaN]}', 1, battery)

    def test_infinity_rejected(self):
        battery = make_battery()
        with pytest.raises(GuardrailError):
            validate_ir('{"notes": [Infinity]}', 1, battery)

    def test_wrong_note_count(self):
        battery = make_battery()
        with pytest.raises(GuardrailError):
            validate_ir(ir([no_op_note(0), no_op_note(1)]), 1, battery)

    def test_duplicate_indices(self):
        battery = make_battery()
        with pytest.raises(GuardrailError):
            validate_ir(ir([no_op_note(0), no_op_note(0)]), 2, battery)

    def test_missing_notes_key(self):
        battery = make_battery()
        with pytest.raises(GuardrailError):
            validate_ir("{}", 1, battery)


class TestPerNoteRecovery:
    def test_one_bad_note_does_not_sink_the_good_one(self):
        battery = make_battery()
        bad = solar_note(1, value=150)  # out of [0,100] range
        result = validate_ir(ir([no_op_note(0), bad]), 2, battery)
        assert 0 in result.valid
        assert 1 not in result.valid
        assert result.violations == [{"note_index": 1, "reason": "solar_percent_value invalid: 150"}]

    def test_reserve_exceeding_capacity_is_a_violation(self):
        battery = make_battery(capacity_kwh=100)
        result = validate_ir(ir([reserve_note(0, value=150, unit="kwh")]), 1, battery)
        assert result.valid == {}
        assert len(result.violations) == 1

    def test_no_op_with_windows_is_a_violation(self):
        battery = make_battery()
        bad_no_op = no_op_note(0)
        bad_no_op["windows"] = [{"start_hour": 1, "end_hour_exclusive": 2}]
        result = validate_ir(ir([bad_no_op]), 1, battery)
        assert result.valid == {}
        assert len(result.violations) == 1

    def test_unknown_directive_type_is_a_violation(self):
        battery = make_battery()
        note = no_op_note(0)
        note["directive_type"] = "teleport_battery"
        result = validate_ir(ir([note]), 1, battery)
        assert result.valid == {}
        assert "not allowed" in result.violations[0]["reason"]
