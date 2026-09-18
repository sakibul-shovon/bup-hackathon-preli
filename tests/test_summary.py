from app.summary import build_summary

def test_summary_normal():
    res = build_summary(
        total_grid_kwh=2692.5,
        total_cost_bdt=38365.0,
        peak_grid_kwh=175.0,
        peak_hour=10,
        charge_hours=[2, 3, 4, 5],
        discharge_hours=[18, 19, 20],
        applied_types=["solar_reduction"]
    )
    assert "38365.0 BDT" in res
    assert "hour 10" in res
    assert "2-5" in res
    assert "18-20" in res
    assert "solar_reduction" in res
    assert len(res) <= 400

def test_summary_empty_charge_discharge():
    res = build_summary(
        total_grid_kwh=100.0,
        total_cost_bdt=1000.0,
        peak_grid_kwh=50.0,
        peak_hour=1,
        charge_hours=[],
        discharge_hours=[],
        applied_types=["solar_reduction"]
    )
    assert "charge" not in res.lower()
    assert "discharge" not in res.lower()
    assert "  " not in res  # no stray punctuation or extra spaces

def test_summary_empty_directives():
    res = build_summary(
        total_grid_kwh=100.0,
        total_cost_bdt=1000.0,
        peak_grid_kwh=50.0,
        peak_hour=1,
        charge_hours=[1],
        discharge_hours=[],
        applied_types=[]
    )
    assert "No operator directives affected this schedule." in res

def test_summary_length_limit():
    res = build_summary(
        total_grid_kwh=100.0,
        total_cost_bdt=1000.0,
        peak_grid_kwh=50.0,
        peak_hour=1,
        charge_hours=list(range(24)),
        discharge_hours=[],
        applied_types=["long_directive_name"] * 50
    )
    assert len(res) <= 400

def test_summary_deterministic():
    args = {
        "total_grid_kwh": 100.0,
        "total_cost_bdt": 1000.0,
        "peak_grid_kwh": 50.0,
        "peak_hour": 1,
        "charge_hours": [1, 2],
        "discharge_hours": [3, 4],
        "applied_types": ["solar_reduction"]
    }
    assert build_summary(**args) == build_summary(**args)
