#!/usr/bin/env python
"""Hidden-test simulator (plan Section 12.8) -- the 10 public samples are the
one thing every competing team will pass; generalization is the differentiator.

Two halves:
  1. Scenario fuzz (mocked interpretations, no network): 150+ synthetic cases
     through the REAL pipeline (FastAPI -> schemas -> llm_interpreter's ladder
     -> guardrails -> directives -> optimizer -> validator -> response
     assembly), asserting every case returns a replay-valid 200 or a 422 ONLY
     when the base scenario was deliberately constructed to be infeasible
     (I7a). If the trivial-plan fallback is ever reached, that's a P0 bug --
     printed loudly, not swallowed as "the safety net worked."
  2. Paraphrase holdout (live Groq): scores extraction accuracy against
     tests/data/paraphrases.json's ground truth. Skipped gracefully (not a
     failure) when no GROQ_API_KEYS/GROQ_API_KEY is configured.

Run in Phase 3; re-run after any prompt change.
"""
import asyncio
import json
import logging
import random
import sys
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.directives import reserve_kwh  # noqa: E402
from app.llm_interpreter import create_key_pool, interpret_notes  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import Battery  # noqa: E402

REFERENCE_BATTERY = Battery(capacity_kwh=400, initial_energy_kwh=200, minimum_energy_kwh=50,
                             max_charge_kwh_per_hour=100, max_discharge_kwh_per_hour=100)

DIRECTIVE_TYPES = ["solar_reduction", "minimum_battery_reserve", "no_charge_window",
                    "no_discharge_window", "max_grid_window", "no_op"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def percentile(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def print_latency_summary(label, latencies):
    if not latencies:
        print(f"{label}: no timed requests")
        return
    p50, p95 = percentile(latencies, 0.5), percentile(latencies, 0.95)
    print(f"{label} latency: p50={p50 * 1000:.1f}ms p95={p95 * 1000:.1f}ms n={len(latencies)}")


class _RecordingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


# ---------------------------------------------------------------------------
# 1. scenario fuzz (mocked interpretations, real pipeline)
# ---------------------------------------------------------------------------
def _random_window(rng: random.Random):
    """Occasionally forces windows touching hour 0 or hour 23 (per spec)."""
    r = rng.random()
    if r < 0.15:
        return 0, rng.randint(1, 6)
    if r < 0.3:
        return rng.randint(18, 22), 24
    start = rng.randint(0, 22)
    end = min(24, start + rng.randint(1, 6))
    return start, end


def _random_ir_note(rng: random.Random, idx: int, battery: dict) -> dict:
    dtype = rng.choice(DIRECTIVE_TYPES)
    base = {
        "note_index": idx, "directive_type": dtype, "windows": None,
        "solar_percent_value": None, "solar_percent_meaning": None,
        "reserve_value": None, "reserve_unit": None, "max_grid_kwh": None,
        "explanation": f"synthetic {dtype}",
    }
    if dtype == "no_op":
        return base

    start, end = _random_window(rng)
    base["windows"] = [{"start_hour": start, "end_hour_exclusive": end}]

    if dtype == "solar_reduction":
        base["solar_percent_meaning"] = rng.choice(["remaining", "reduced_by"])
        base["solar_percent_value"] = round(rng.uniform(0, 100), 1)
    elif dtype == "minimum_battery_reserve":
        unit = rng.choice(["kwh", "percent_of_capacity", "percent_of_initial", "percent_of_minimum"])
        base["reserve_unit"] = unit
        # a reserve deliberately above current energy, forcing pre-charging (per spec)
        base["reserve_value"] = (
            round(rng.uniform(0, battery["capacity_kwh"]), 1) if unit == "kwh"
            else round(rng.uniform(20, 100), 1)
        )
    elif dtype == "max_grid_window":
        # occasionally tight enough to force discharge (per spec)
        base["max_grid_kwh"] = round(rng.uniform(5, 300), 1)
    # no_charge_window / no_discharge_window need only windows, already set
    return base


def _random_battery(rng: random.Random) -> dict:
    mode = rng.choice(["normal", "normal", "normal", "initial_eq_min", "initial_eq_cap", "tiny_capacity"])
    if mode == "tiny_capacity":
        capacity = round(rng.uniform(1, 20), 2)
    else:
        capacity = round(rng.uniform(50, 800), 1)
    minimum = round(rng.uniform(0, capacity * 0.3), 2)
    if mode == "initial_eq_min":
        initial = minimum
    elif mode == "initial_eq_cap":
        initial = capacity
    else:
        initial = round(rng.uniform(minimum, capacity), 2)
    return dict(
        capacity_kwh=capacity, initial_energy_kwh=initial, minimum_energy_kwh=minimum,
        max_charge_kwh_per_hour=round(rng.uniform(10, 200), 1),
        max_discharge_kwh_per_hour=round(rng.uniform(10, 200), 1),
    )


def _random_scenario(rng: random.Random, idx: int):
    battery = _random_battery(rng)
    force_infeasible = rng.random() < 0.08
    if force_infeasible:
        # I7a: unconditionally infeasible, and the only base-infeasible case
        # this fuzzer deliberately constructs.
        battery["initial_energy_kwh"] = max(0.0, battery["minimum_energy_kwh"] - round(rng.uniform(1, 20), 1))

    n_notes = rng.randint(1, 3)
    notes_ir = [_random_ir_note(rng, i, battery) for i in range(n_notes)]

    demand = [round(rng.uniform(20, 300), rng.choice([0, 1, 2])) for _ in range(24)]
    solar = [round(rng.uniform(0, 250), rng.choice([0, 1, 2])) if 5 <= h <= 19 else 0.0 for h in range(24)]
    tariff = [round(rng.uniform(2, 35), rng.choice([0, 1, 2])) for _ in range(24)]

    payload = {
        "scenario_id": f"FUZZ-{idx}",
        "operator_notes": [f"synthetic fuzz note {i}" for i in range(n_notes)],
        "hours": [{"hour": h, "demand_kwh": demand[h], "solar_kwh": solar[h],
                   "tariff_bdt_per_kwh": tariff[h]} for h in range(24)],
        "battery": battery,
    }
    return payload, notes_ir, force_infeasible


def _mock_handler(notes_ir):
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"notes": notes_ir})}}]})
    return handler


def run_scenario_fuzz(n: int, seed: int = 20260918):
    rng = random.Random(seed)
    latencies = []
    counts = {"200": 0, "422": 0, "other": 0}
    failures = []
    trivial_hits = []

    validator_log = _RecordingHandler()
    logging.getLogger("gridwise.validator").addHandler(validator_log)
    logging.getLogger("gridwise.validator").setLevel(logging.WARNING)

    with TestClient(app) as client:
        for i in range(n):
            payload, notes_ir, force_infeasible = _random_scenario(rng, i)
            client.app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(_mock_handler(notes_ir)))

            before_log_count = len(validator_log.messages)
            start = time.monotonic()
            try:
                r = client.post("/optimize-energy", json=payload)
            except Exception as exc:  # pragma: no cover -- would itself be the P0 bug
                failures.append((i, f"unhandled exception escaped the pipeline: {exc!r}"))
                continue
            latencies.append(time.monotonic() - start)

            new_messages = validator_log.messages[before_log_count:]
            if any("trivial plan" in m for m in new_messages):
                trivial_hits.append(i)

            if r.status_code == 200:
                counts["200"] += 1
                body = r.json()
                hp = body["hourly_plan"]
                recomputed_grid = sum(h["grid_kwh"] for h in hp)
                recomputed_peak = max(h["grid_kwh"] for h in hp)
                if abs(recomputed_grid - body["total_grid_kwh"]) > 1e-3:
                    failures.append((i, f"total_grid_kwh mismatch: {body['total_grid_kwh']} vs recomputed {recomputed_grid}"))
                if abs(recomputed_peak - body["peak_grid_kwh"]) > 1e-3:
                    failures.append((i, f"peak_grid_kwh mismatch: {body['peak_grid_kwh']} vs recomputed {recomputed_peak}"))
            elif r.status_code == 422:
                counts["422"] += 1
                if not force_infeasible:
                    failures.append((i, "422 on a scenario that was NOT constructed to be base-infeasible"))
            else:
                counts["other"] += 1
                failures.append((i, f"unexpected status {r.status_code}: {r.text[:200]}"))

    return counts, latencies, failures, trivial_hits


# ---------------------------------------------------------------------------
# 2. paraphrase holdout (live Groq; skipped gracefully with no key)
# ---------------------------------------------------------------------------
def _score_entry(directive, expected: dict):
    if directive.directive_type != expected["directive_type"]:
        return False, f"type: got {directive.directive_type}, expected {expected['directive_type']}"

    if "hours" in expected and set(directive.hours) != set(expected["hours"]):
        return False, f"hours: got {directive.hours}, expected {expected['hours']}"

    if expected["directive_type"] == "solar_reduction":
        if directive.factor is None or abs(directive.factor - expected["factor"]) > 0.03:
            return False, f"factor: got {directive.factor}, expected {expected['factor']}"

    elif expected["directive_type"] == "minimum_battery_reserve":
        if "minimum_energy_kwh" in expected:
            target = expected["minimum_energy_kwh"]
        else:
            target = reserve_kwh(expected["reserve_value"], expected["reserve_unit"],
                                  REFERENCE_BATTERY.capacity_kwh, REFERENCE_BATTERY.initial_energy_kwh,
                                  REFERENCE_BATTERY.minimum_energy_kwh)
        if directive.minimum_energy_kwh is None or abs(directive.minimum_energy_kwh - target) > max(1.0, 0.03 * target):
            return False, f"reserve: got {directive.minimum_energy_kwh}, expected {target}"

    elif expected["directive_type"] == "max_grid_window":
        if directive.max_grid_kwh is None or abs(directive.max_grid_kwh - expected["max_grid_kwh"]) > 1.0:
            return False, f"max_grid: got {directive.max_grid_kwh}, expected {expected['max_grid_kwh']}"

    return True, "ok"


async def run_paraphrase_holdout():
    if not config.GROQ_API_KEYS:
        print("No GROQ_API_KEYS/GROQ_API_KEY configured -- skipping live paraphrase holdout.")
        return None

    entries = json.loads((ROOT / "tests" / "data" / "paraphrases.json").read_text(encoding="utf-8"))["entries"]

    latencies = []
    misses = []
    async with httpx.AsyncClient() as client:
        pool = create_key_pool()
        for entry in entries:
            deadline = time.monotonic() + config.LLM_DEADLINE_SECONDS
            start = time.monotonic()
            result = await interpret_notes([entry["note"]], REFERENCE_BATTERY, client, pool, deadline)
            latencies.append(time.monotonic() - start)
            ok, reason = _score_entry(result.directives[0], entry["expected"])
            if not ok:
                misses.append((entry["id"], entry["note"], reason))
                print(f"MISS  {entry['id']:14s} {reason}")

    hits = len(entries) - len(misses)
    print(f"\nParaphrase holdout: {hits}/{len(entries)} correct ({100 * hits / len(entries):.1f}%)")
    print_latency_summary("paraphrase holdout", latencies)
    return misses


# ---------------------------------------------------------------------------
def main():
    n = 150
    print(f"=== Scenario fuzz: {n} synthetic cases through the real pipeline (mocked LLM) ===")
    counts, latencies, failures, trivial_hits = run_scenario_fuzz(n)
    print(f"200: {counts['200']}  422: {counts['422']}  other: {counts['other']}")
    print_latency_summary("scenario fuzz", latencies)

    if trivial_hits:
        print(f"\n*** P0: trivial-plan fallback reached on {len(trivial_hits)} scenario(s): "
              f"{trivial_hits[:10]}{'...' if len(trivial_hits) > 10 else ''} ***")

    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for idx, reason in failures[:25]:
            print(f"  scenario {idx}: {reason}")
    else:
        print("\n100% replay-valid: every case returned a self-consistent 200, "
              "or 422 only for a deliberately base-infeasible scenario.")

    print("\n=== Paraphrase holdout (live Groq) ===")
    asyncio.run(run_paraphrase_holdout())

    if failures or trivial_hits:
        sys.exit(1)


if __name__ == "__main__":
    main()
