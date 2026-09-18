"""Pydantic v2 request models (plan Section 9.1). extra='ignore' everywhere per I6a/F3."""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class InfeasibleError(Exception):
    """Raised only when the base scenario itself is infeasible (plan Section 10.5)."""


class HourEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    hour: int = Field(ge=0, le=23)
    demand_kwh: float = Field(ge=0, allow_inf_nan=False)
    solar_kwh: float = Field(ge=0, allow_inf_nan=False)
    tariff_bdt_per_kwh: float = Field(ge=0, allow_inf_nan=False)


class Battery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    capacity_kwh: float = Field(ge=0, allow_inf_nan=False)
    initial_energy_kwh: float = Field(ge=0, allow_inf_nan=False)
    minimum_energy_kwh: float = Field(ge=0, allow_inf_nan=False)
    max_charge_kwh_per_hour: float = Field(ge=0, allow_inf_nan=False)
    max_discharge_kwh_per_hour: float = Field(ge=0, allow_inf_nan=False)


class OptimizeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    scenario_id: str
    operator_notes: list[str] = Field(min_length=1, max_length=3)
    hours: list[HourEntry] = Field(min_length=24, max_length=24)
    battery: Battery

    @model_validator(mode="after")
    def _check(self):
        if sorted(h.hour for h in self.hours) != list(range(24)):
            raise ValueError("hours must contain exactly hours 0..23 with no duplicates")
        for i, n in enumerate(self.operator_notes):
            if not n.strip():
                raise ValueError(f"operator_notes[{i}] is empty")
            if len(n) > 2000:
                raise ValueError(f"operator_notes[{i}] too long")
        return self
