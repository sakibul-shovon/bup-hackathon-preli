"""FastAPI app: routes, middleware, exception handlers, orchestration (plan Section 6, 9)."""
import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app import config, llm_interpreter, optimizer, validator
from app.directives import build_interpretation_array
from app.schemas import InfeasibleError, OptimizeRequest

log = logging.getLogger("gridwise")

MAX_BODY_BYTES = 2 * 1024 * 1024


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    return JSONResponse(
                        status_code=400,
                        content={"error": "invalid_request", "detail": "body too large"},
                    )
            except ValueError:
                pass
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_request", "detail": "body too large"},
            )
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient()
    app.state.key_pool = llm_interpreter.create_key_pool()
    yield
    await app.state.http_client.aclose()


app = FastAPI(lifespan=lifespan)
app.add_middleware(BodySizeLimitMiddleware)


def summarize_field_paths(exc: RequestValidationError) -> str:
    """Safe field-path summary; never echoes input values."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        msg = err.get("msg", "invalid")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) if parts else "invalid request"


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"error": "invalid_request", "detail": summarize_field_paths(exc)},
    )


@app.exception_handler(InfeasibleError)
async def _infeasible_error_handler(request: Request, exc: InfeasibleError):
    return JSONResponse(status_code=422, content={"error": "infeasible_scenario"})


@app.exception_handler(Exception)
async def _internal_error_handler(request: Request, exc: Exception):
    log.exception("internal error")
    return JSONResponse(status_code=500, content={"error": "internal_error"})


@app.get("/health")
async def health():
    return {"status": "ok"}


def _by_hour(payload: OptimizeRequest) -> list:
    idx = {h.hour: h for h in payload.hours}
    return [idx[i] for i in range(24)]


async def _resolve_feasible_directives(directives, notes, battery, base_solar, demand, tariff,
                                        e0, cap, http_client, key_pool, deadline, corrective_used):
    """Section 6 step 7: try the current interpretation; on LP infeasibility fire
    AT MOST ONE corrective LLM re-ask (shared budget with the guardrail-triggered
    rung 4 inside interpret_notes, tracked via `corrective_used`) before ever
    falling back to salvage. Returns (directives_to_optimize, corrective_used).
    """
    res = optimizer.solve_full(directives, base_solar, battery.minimum_energy_kwh,
                                battery.max_charge_kwh_per_hour, battery.max_discharge_kwh_per_hour,
                                demand, tariff, e0, cap)
    if res.status == 0 or corrective_used or len(key_pool) == 0:
        return directives, corrective_used

    corrective_result = await llm_interpreter.corrective_reask_infeasible(
        notes, battery, http_client, key_pool, deadline)
    corrective_used = True

    res2 = optimizer.solve_full(corrective_result.directives, base_solar, battery.minimum_energy_kwh,
                                 battery.max_charge_kwh_per_hour, battery.max_discharge_kwh_per_hour,
                                 demand, tariff, e0, cap)
    if res2.status == 0:
        return corrective_result.directives, corrective_used

    orig_resolved = sum(1 for d in directives if d.directive_type != "no_op")
    corr_resolved = sum(1 for d in corrective_result.directives if d.directive_type != "no_op")
    if corr_resolved > orig_resolved:
        return corrective_result.directives, corrective_used
    return directives, corrective_used


@app.post("/optimize-energy")
async def optimize_energy(payload: OptimizeRequest, http_request: Request):
    from app.summary import build_summary  # deferred: teammate-owned module

    deadline = time.monotonic() + config.LLM_DEADLINE_SECONDS  # I35
    http_client = http_request.app.state.http_client
    key_pool = http_request.app.state.key_pool
    battery = payload.battery

    ordered = _by_hour(payload)
    solar = [float(h.solar_kwh) for h in ordered]
    demand = [float(h.demand_kwh) for h in ordered]
    tariff = [float(h.tariff_bdt_per_kwh) for h in ordered]
    e0 = battery.initial_energy_kwh
    cap = battery.capacity_kwh

    interpret_result = await llm_interpreter.interpret_notes(
        payload.operator_notes, battery, http_client, key_pool, deadline)

    directives, _ = await _resolve_feasible_directives(
        interpret_result.directives, payload.operator_notes, battery, solar, demand, tariff,
        e0, cap, http_client, key_pool, deadline, interpret_result.used_corrective_reask)

    hourly_plan, totals, kept, _dropped = optimizer.optimize(
        directives, solar, battery.minimum_energy_kwh, battery.max_charge_kwh_per_hour,
        battery.max_discharge_kwh_per_hour, demand, tariff, e0, cap)

    plan_dict = {"hourly_plan": hourly_plan, **totals}
    # Validate against `kept`, not the full `directives` list: the optimizer's own
    # salvage (Section 10.5) may have legitimately dropped a directive it could not
    # satisfy, so the shipped plan was never built to honor it. Replaying the full
    # list here would manufacture a spurious violation on a directive-by-design
    # (not a bug), push max_violation past the trivial-plan tier, and raise
    # ValidatorInternalError -> 500 even though the plan the optimizer actually
    # returned is completely valid. F6/I5a's "report the full interpretation" only
    # applies to directive_interpretation below, never to what gets validated.
    shipped = validator.validate_and_ship(payload, kept, plan_dict)

    hourly = shipped["hourly_plan"]
    peak_hour = max(range(24), key=lambda h: hourly[h]["grid_kwh"])
    charge_hours = [h["hour"] for h in hourly if h["battery_action"] == "charge"]
    discharge_hours = [h["hour"] for h in hourly if h["battery_action"] == "discharge"]
    applied_types = [d.directive_type for d in kept if d.directive_type != "no_op"]

    plan_summary = build_summary(
        total_grid_kwh=shipped["total_grid_kwh"],
        total_cost_bdt=shipped["total_cost_bdt"],
        peak_grid_kwh=shipped["peak_grid_kwh"],
        peak_hour=peak_hour,
        charge_hours=charge_hours,
        discharge_hours=discharge_hours,
        applied_types=applied_types,
    )

    return {
        "scenario_id": payload.scenario_id,
        "directive_interpretation": build_interpretation_array(directives),
        "hourly_plan": hourly,
        "total_grid_kwh": shipped["total_grid_kwh"],
        "total_cost_bdt": shipped["total_cost_bdt"],
        "peak_grid_kwh": shipped["peak_grid_kwh"],
        "plan_summary": plan_summary,
    }
