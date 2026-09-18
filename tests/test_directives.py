import math

from app.directives import (
    NormalizedDirective,
    build_interpretation_array,
    build_structured_adjustment,
    expand,
    hours_from_windows,
    merge_charge_ub,
    merge_discharge_ub,
    merge_eff_solar,
    merge_grid_cap,
    merge_reserve,
    reserve_kwh,
    solar_factor,
)


class TestExpand:
    def test_simple_window(self):
        assert expand(13, 15) == [13, 14]

    def test_another_simple_window(self):
        assert expand(12, 14) == [12, 13]

    def test_evening_window(self):
        assert expand(18, 21) == [18, 19, 20]

    def test_single_hour(self):
        assert expand(17, 18) == [17]

    def test_midnight_wrap(self):
        assert expand(22, 1) == [0, 22, 23]

    def test_until_midnight(self):
        assert expand(18, 24) == [18, 19, 20, 21, 22, 23]

    def test_all_day(self):
        assert expand(0, 24) == list(range(24))


class TestHoursFromWindows:
    def test_union_of_windows(self):
        assert hours_from_windows([(13, 15), (20, 22)]) == [13, 14, 20, 21]

    def test_overlapping_windows_dedup(self):
        assert hours_from_windows([(13, 16), (14, 18)]) == [13, 14, 15, 16, 17]


class TestSolarFactor:
    def test_reduced_by_80(self):
        assert solar_factor(80, "reduced_by") == 0.2

    def test_remaining_20(self):
        assert solar_factor(20, "remaining") == 0.2

    def test_remaining_50(self):
        assert solar_factor(50, "remaining") == 0.5

    def test_rounding_kills_float_dust(self):
        f = solar_factor(80, "reduced_by")
        assert f == 0.2
        assert f != 0.19999999999999996
        assert round(f, 6) == f


class TestReserveKwh:
    def test_percent_of_capacity(self):
        assert reserve_kwh(50, "percent_of_capacity", capacity=200, initial=150, minimum=50) == 100.0

    def test_kwh_direct(self):
        assert reserve_kwh(120, "kwh", capacity=200, initial=150, minimum=50) == 120.0

    def test_percent_of_initial(self):
        assert reserve_kwh(100, "percent_of_initial", capacity=200, initial=150, minimum=50) == 150.0

    def test_percent_of_minimum(self):
        assert reserve_kwh(200, "percent_of_minimum", capacity=200, initial=150, minimum=50) == 100.0


class TestMergeTable:
    def test_overlapping_solar_factors_multiply(self):
        base = [100.0] * 24
        d1 = NormalizedDirective(0, "solar_reduction", hours=[10, 11], factor=0.5)
        d2 = NormalizedDirective(1, "solar_reduction", hours=[11, 12], factor=0.5)
        eff = merge_eff_solar(base, [d1, d2])
        assert eff[10] == 50.0
        assert eff[11] == 25.0
        assert eff[12] == 50.0
        assert eff[0] == 100.0

    def test_overlapping_reserves_take_max_including_base(self):
        d1 = NormalizedDirective(0, "minimum_battery_reserve", hours=[5], minimum_energy_kwh=80.0)
        d2 = NormalizedDirective(1, "minimum_battery_reserve", hours=[5], minimum_energy_kwh=60.0)
        reserve = merge_reserve(base_minimum=50.0, directives=[d1, d2])
        assert reserve[5] == 80.0
        assert reserve[6] == 50.0

    def test_overlapping_caps_take_min(self):
        d1 = NormalizedDirective(0, "max_grid_window", hours=[8], max_grid_kwh=150.0)
        d2 = NormalizedDirective(1, "max_grid_window", hours=[8], max_grid_kwh=100.0)
        cap = merge_grid_cap([d1, d2])
        assert cap[8] == 100.0
        assert math.isinf(cap[9])

    def test_charge_discharge_prohibitions_union(self):
        d1 = NormalizedDirective(0, "no_charge_window", hours=[1, 2])
        d2 = NormalizedDirective(1, "no_charge_window", hours=[2, 3])
        ub = merge_charge_ub(base_max_charge=100.0, directives=[d1, d2])
        assert ub[1] == 0.0
        assert ub[2] == 0.0
        assert ub[3] == 0.0
        assert ub[4] == 100.0

    def test_no_charge_and_no_discharge_same_hour_both_zero(self):
        d1 = NormalizedDirective(0, "no_charge_window", hours=[7])
        d2 = NormalizedDirective(1, "no_discharge_window", hours=[7])
        charge_ub = merge_charge_ub(base_max_charge=100.0, directives=[d1, d2])
        discharge_ub = merge_discharge_ub(base_max_discharge=100.0, directives=[d1, d2])
        assert charge_ub[7] == 0.0
        assert discharge_ub[7] == 0.0


class TestBuilders:
    def test_solar_reduction_shape(self):
        d = NormalizedDirective(0, "solar_reduction", hours=[13, 14], factor=0.2)
        assert build_structured_adjustment(d) == {"hours": [13, 14], "factor": 0.2}

    def test_minimum_battery_reserve_shape(self):
        d = NormalizedDirective(0, "minimum_battery_reserve", hours=[5, 6], minimum_energy_kwh=100.0)
        assert build_structured_adjustment(d) == {"hours": [5, 6], "minimum_energy_kwh": 100.0}

    def test_no_charge_window_shape(self):
        d = NormalizedDirective(0, "no_charge_window", hours=[1, 2])
        assert build_structured_adjustment(d) == {"hours": [1, 2]}

    def test_no_discharge_window_shape(self):
        d = NormalizedDirective(0, "no_discharge_window", hours=[1, 2])
        assert build_structured_adjustment(d) == {"hours": [1, 2]}

    def test_max_grid_window_shape(self):
        d = NormalizedDirective(0, "max_grid_window", hours=[19, 20], max_grid_kwh=150.0)
        assert build_structured_adjustment(d) == {"hours": [19, 20], "max_grid_kwh": 150.0}

    def test_no_op_is_none(self):
        d = NormalizedDirective(0, "no_op")
        assert build_structured_adjustment(d) is None

    def test_interpretation_entry_no_op(self):
        d = NormalizedDirective(0, "no_op", explanation="No effect on today's schedule.")
        entry = build_interpretation_array([d])[0]
        assert entry == {
            "note_index": 0,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "No effect on today's schedule.",
        }

    def test_interpretation_array_sorted_by_note_index(self):
        d1 = NormalizedDirective(1, "no_op", explanation="b")
        d0 = NormalizedDirective(0, "no_op", explanation="a")
        entries = build_interpretation_array([d1, d0])
        assert [e["note_index"] for e in entries] == [0, 1]
