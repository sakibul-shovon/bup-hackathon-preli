"""Full provider ladder test suite (plan Section 12.6), replacing the L5 stub.

Two spots where this file deliberately does NOT follow 12.6's literal wording,
per standing rule 3b (V4 overrides stale V3 body text still present in the plan):

1. "429 with Retry-After -> sleep capped at 4s" describes V3's behavior, which
   F7/7.3b explicitly replaces with "hop to the next key immediately, do NOT
   sleep." Tested as zero-sleep hop-to-next-key here, matching 7.3b and the
   V4 change table (F7).
2. The plain "salvage" bullet says a salvage-dropped directive is reported as
   no_op; the F6-labeled bullet two lines below it says the opposite (keeps its
   real interpretation, applies=true) and F6 is explicitly a V4 fix in the
   change table. Tested per F6/I5a here.

"timeout -> attempt 2 model used": timeout is NOT in 7.3's key-attributable
list (429/401/403/5xx only), so a rung-1 timeout skips rung 2 and the second
HTTP call actually made uses FALLBACK_MODEL -- tested that way below.
"""
import asyncio
import json
import logging
import time

import httpx

from app import config
from app.llm_interpreter import KeyPool, interpret_notes
from app.schemas import Battery


def make_battery(**overrides):
    defaults = dict(
        capacity_kwh=200, initial_energy_kwh=150, minimum_energy_kwh=50,
        max_charge_kwh_per_hour=100, max_discharge_kwh_per_hour=100,
    )
    defaults.update(overrides)
    return Battery(**defaults)


def ir_response(notes: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"notes": notes})}}]})


def no_op(idx, explanation="n/a"):
    return {
        "note_index": idx, "directive_type": "no_op", "windows": None,
        "solar_percent_value": None, "solar_percent_meaning": None,
        "reserve_value": None, "reserve_unit": None, "max_grid_kwh": None,
        "explanation": explanation,
    }


def solar(idx, start=12, end=14, value=25, meaning="remaining"):
    return {
        "note_index": idx, "directive_type": "solar_reduction",
        "windows": [{"start_hour": start, "end_hour_exclusive": end}],
        "solar_percent_value": value, "solar_percent_meaning": meaning,
        "reserve_value": None, "reserve_unit": None, "max_grid_kwh": None,
        "explanation": "solar reduced",
    }


def reserve(idx, value, unit="kwh", start=18, end=20):
    return {
        "note_index": idx, "directive_type": "minimum_battery_reserve",
        "windows": [{"start_hour": start, "end_hour_exclusive": end}],
        "solar_percent_value": None, "solar_percent_meaning": None,
        "reserve_value": value, "reserve_unit": unit, "max_grid_kwh": None,
        "explanation": "reserve",
    }


def no_charge(idx, start=0, end=24):
    return {
        "note_index": idx, "directive_type": "no_charge_window",
        "windows": [{"start_hour": start, "end_hour_exclusive": end}],
        "solar_percent_value": None, "solar_percent_meaning": None,
        "reserve_value": None, "reserve_unit": None, "max_grid_kwh": None,
        "explanation": "no charge",
    }


def run(coro):
    return asyncio.run(coro)


def client_with(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# Basic ladder mechanics
# ---------------------------------------------------------------------------
class TestLadderMechanics:
    def test_timeout_on_rung1_skips_to_fallback_model_not_rung2(self):
        """Timeout is not key-attributable (7.3's list is 429/401/403/5xx only),
        so the second HTTP call actually made must use FALLBACK_MODEL."""
        models_seen = []

        def handler(request):
            body = json.loads(request.content)
            models_seen.append(body["model"])
            if len(models_seen) == 1:
                raise httpx.ReadTimeout("simulated timeout")
            return ir_response([no_op(0)])

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool(["k0"])
                return await interpret_notes(
                    ["timeout test note"], make_battery(), client, pool,
                    deadline=time.monotonic() + 20)

        result = run(go())
        assert not result.degraded
        assert models_seen == [config.PRIMARY_MODEL, config.FALLBACK_MODEL]

    def test_429_hops_to_next_key_with_zero_sleep(self, monkeypatch):
        """F7 overrides V3's 'sleep up to 4s' -- must hop immediately."""
        keys_used = []

        def handler(request):
            auth = request.headers["authorization"]
            keys_used.append(auth)
            if len(keys_used) == 1:
                return httpx.Response(429, headers={"Retry-After": "30"})
            return ir_response([no_op(0)])

        def _forbidden_sleep(*a, **k):
            raise AssertionError("must not call time.sleep")

        monkeypatch.setattr("time.sleep", _forbidden_sleep)

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool(["key-A", "key-B"])
                return await interpret_notes(
                    ["429 hop test note"], make_battery(), client, pool,
                    deadline=time.monotonic() + 20)

        start = time.monotonic()
        result = run(go())
        elapsed = time.monotonic() - start
        assert not result.degraded
        assert keys_used == ["Bearer key-A", "Bearer key-B"]
        assert elapsed < 0.5

    def test_500_from_provider_is_key_attributable_uses_rung2(self):
        models_and_keys = []

        def handler(request):
            body = json.loads(request.content)
            models_and_keys.append((body["model"], request.headers["authorization"]))
            if len(models_and_keys) == 1:
                return httpx.Response(500)
            return ir_response([no_op(0)])

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool(["key-A", "key-B"])
                return await interpret_notes(
                    ["500 test note"], make_battery(), client, pool,
                    deadline=time.monotonic() + 20)

        result = run(go())
        assert not result.degraded
        assert [m for m, _ in models_and_keys] == [config.PRIMARY_MODEL, config.PRIMARY_MODEL]
        assert models_and_keys[0][1] != models_and_keys[1][1]

    def test_free_form_text_instead_of_json_is_a_parse_failure_advances_ladder(self):
        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(200, json={"choices": [{"message": {"content": "sure, here you go!"}}]})
            return ir_response([no_op(0)])

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool(["k0"])
                return await interpret_notes(
                    ["free-form text regression note"], make_battery(), client, pool,
                    deadline=time.monotonic() + 20)

        result = run(go())
        assert not result.degraded
        assert len(calls) == 2

    def test_semantically_invalid_ir_triggers_corrective_reask_with_violations(self):
        """reserve>capacity (a per-note guardrail violation, not key-attributable)
        on rung 1 -> rung 2 skipped -> rung 3 also bad -> rung 4 corrective re-ask
        (the 3rd actual HTTP call) finally returns a guardrail-clean response."""
        attempts = []

        def handler(request):
            attempts.append(1)
            n = len(attempts)
            if n <= 2:
                # reserve_value 999 with unit kwh vastly exceeds capacity=200 -> per-note violation
                return ir_response([reserve(0, value=999, unit="kwh")])
            # rung 4 (corrective, the 3rd actual call): the corrective prompt was sent
            user_msg = json.loads(request.content)["messages"][1]["content"]
            assert "problems" in user_msg
            return ir_response([no_op(0)])

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool(["k0"])
                return await interpret_notes(
                    ["reserve too large note"], make_battery(capacity_kwh=200), client, pool,
                    deadline=time.monotonic() + 20)

        result = run(go())
        assert result.used_corrective_reask is True
        assert not result.degraded
        assert len(attempts) == 3

    def test_all_attempts_fail_degrades_to_200_not_5xx(self):
        def handler(request):
            return httpx.Response(500)

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool(["k0", "k1"])
                return await interpret_notes(
                    ["everything fails note"], make_battery(), client, pool,
                    deadline=time.monotonic() + 20)

        result = run(go())
        assert result.degraded
        assert all(d.directive_type == "no_op" for d in result.directives)

    def test_partial_failure_one_note_persistently_invalid(self):
        def handler(request):
            body = json.loads(request.content)
            n_notes = len(body["messages"][1]["content"].split("<note index="))  # rough note count probe
            return ir_response([
                no_op(0),
                solar(1, value=30, meaning="remaining"),
                reserve(2, value=99999, unit="kwh"),  # persistently exceeds capacity
            ])

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool(["k0"])
                return await interpret_notes(
                    ["note a", "note b", "note c"], make_battery(capacity_kwh=200), client, pool,
                    deadline=time.monotonic() + 20)

        result = run(go())
        assert result.degraded
        assert result.directives[0].directive_type == "no_op"
        assert result.directives[1].directive_type == "solar_reduction"
        assert result.directives[2].directive_type == "no_op"

    def test_cache_hit_exactly_one_provider_call(self):
        calls = []

        def handler(request):
            calls.append(1)
            return ir_response([no_op(0)])

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool(["k0"])
                battery = make_battery()
                r1 = await interpret_notes(["cache test note unique"], battery, client, pool,
                                            deadline=time.monotonic() + 20)
                r2 = await interpret_notes(["cache test note unique"], battery, client, pool,
                                            deadline=time.monotonic() + 20)
                return r1, r2

        r1, r2 = run(go())
        assert len(calls) == 1
        assert r1.directives[0].directive_type == r2.directives[0].directive_type


# ---------------------------------------------------------------------------
# F6 -- salvage-dropped directive keeps its real interpretation
# ---------------------------------------------------------------------------
class TestF6SalvageKeepsInterpretation:
    def test_infeasible_directive_reported_not_no_op(self):
        """Guardrails-clean interpretation that makes the LP infeasible: after
        optimizer.optimize()'s salvage, the response must still report the
        dropped directive with its real type/hours/values, applies=true --
        never no_op (F6/I5a)."""
        from app.directives import NormalizedDirective
        from app.optimizer import optimize

        battery = make_battery(initial_energy_kwh=100, capacity_kwh=200)
        no_charge_d = NormalizedDirective(0, "no_charge_window", hours=list(range(24)))
        reserve_d = NormalizedDirective(1, "minimum_battery_reserve", hours=[12], minimum_energy_kwh=180.0)
        directives = [no_charge_d, reserve_d]

        demand = [50.0] * 24
        solarr = [0.0] * 24
        tariff = [10.0] * 24
        plan, totals, kept, dropped = optimize(
            directives, solarr, battery.minimum_energy_kwh, battery.max_charge_kwh_per_hour,
            battery.max_discharge_kwh_per_hour, demand, tariff, battery.initial_energy_kwh,
            battery.capacity_kwh,
        )
        assert len(dropped) == 1
        dropped_idx = dropped[0]

        from app.directives import build_interpretation_array
        entries = build_interpretation_array(directives)  # F6: report ALL, not just kept
        dropped_entry = entries[dropped_idx]
        assert dropped_entry["applies"] is True
        assert dropped_entry["directive_type"] != "no_op"


# ---------------------------------------------------------------------------
# V4 additions: F1 (no key / invalid key), F7 (rotation, deadline), key leakage
# ---------------------------------------------------------------------------
class TestF1NoOrInvalidKey:
    def test_no_key_configured_degrades_to_200_never_500(self):
        called = False

        def handler(request):
            nonlocal called
            called = True
            return ir_response([no_op(0)])

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool([])  # GROQ_API_KEYS and GROQ_API_KEY both unset
                return await interpret_notes(
                    ["no key configured note"], make_battery(), client, pool,
                    deadline=time.monotonic() + 20)

        result = run(go())
        assert result.degraded
        assert called is False

    def test_invalid_key_401_marks_dead_then_degrades_when_no_healthy_left(self):
        def handler(request):
            return httpx.Response(401)

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool(["only-key"])
                return await interpret_notes(
                    ["401 test note"], make_battery(), client, pool,
                    deadline=time.monotonic() + 20)

        result = run(go())
        assert result.degraded


class TestF7KeyRotationAndDeadline:
    def test_429_then_skipped_on_next_request_while_cooling_down(self):
        pool = KeyPool(["key-0", "key-1", "key-2"])
        call_log = []

        def handler(request):
            call_log.append(request.headers["authorization"])
            if len(call_log) == 1:
                return httpx.Response(429, headers={"Retry-After": "30"})
            return ir_response([no_op(0)])

        async def first_request():
            async with client_with(handler) as client:
                return await interpret_notes(["rotation note one"], make_battery(), client, pool,
                                              deadline=time.monotonic() + 20)

        run(first_request())
        assert call_log[0] == "Bearer key-0"
        assert call_log[1] == "Bearer key-1"

        call_log.clear()

        def handler2(request):
            call_log.append(request.headers["authorization"])
            return ir_response([no_op(0)])

        async def second_request():
            async with client_with(handler2) as client:
                return await interpret_notes(["rotation note two, different cache key"], make_battery(),
                                              client, pool, deadline=time.monotonic() + 20)

        run(second_request())
        assert call_log[0] != "Bearer key-0", "key-0 should still be cooling down from the 429"

    def test_all_keys_429_degrades_within_deadline(self):
        def handler(request):
            return httpx.Response(429, headers={"Retry-After": "30"})

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool(["k0", "k1", "k2"])
                return await interpret_notes(
                    ["all 429 note"], make_battery(), client, pool,
                    deadline=time.monotonic() + 20)

        start = time.monotonic()
        result = run(go())
        elapsed = time.monotonic() - start
        assert result.degraded
        assert elapsed < 1.0

    def test_deadline_stops_ladder_early_and_never_exceeds_budget_plus_2s(self):
        calls = []

        def handler(request):
            calls.append(1)
            raise httpx.ReadTimeout("simulated hang")

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool(["k0"])
                # small deadline: after rung 1's (near-instant, mocked) failure,
                # remaining budget must drop under 1.5s and stop the ladder.
                return await interpret_notes(
                    ["deadline test note"], make_battery(), client, pool,
                    deadline=time.monotonic() + 1.0)

        start = time.monotonic()
        result = run(go())
        elapsed = time.monotonic() - start
        assert result.degraded
        assert elapsed < config.LLM_DEADLINE_SECONDS + 2.0
        assert len(calls) < 5, "must not dial every rung once the deadline is nearly exhausted"


class TestKeyMaterialNeverLeaks:
    def test_key_values_never_in_logs_but_key_idx_does(self, caplog):
        def handler(request):
            return httpx.Response(429, headers={"Retry-After": "30"})

        secret_keys = ["sk-super-secret-AAA", "sk-super-secret-BBB"]

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool(secret_keys)
                return await interpret_notes(
                    ["log leakage test note"], make_battery(), client, pool,
                    deadline=time.monotonic() + 20)

        with caplog.at_level(logging.DEBUG):
            run(go())

        log_text = caplog.text
        for key in secret_keys:
            assert key not in log_text
        assert "key_idx=" in log_text


class TestCrossProviderRung:
    def test_alt_rung_called_when_configured_and_groq_exhausted(self, monkeypatch):
        monkeypatch.setattr(config, "ALT_BASE_URL", "https://alt.example.com/v1")
        monkeypatch.setattr(config, "ALT_API_KEY", "alt-key")
        monkeypatch.setattr(config, "ALT_MODEL", "alt-model")

        hosts_called = []

        def handler(request):
            hosts_called.append(str(request.url))
            if "alt.example.com" in str(request.url):
                return ir_response([no_op(0)])
            return httpx.Response(500)

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool(["k0"])
                return await interpret_notes(
                    ["alt rung note"], make_battery(), client, pool,
                    deadline=time.monotonic() + 20)

        result = run(go())
        assert any("alt.example.com" in h for h in hosts_called)
        assert not result.degraded

    def test_alt_rung_never_dialled_when_unconfigured(self, monkeypatch):
        monkeypatch.setattr(config, "ALT_BASE_URL", None)
        monkeypatch.setattr(config, "ALT_API_KEY", None)
        monkeypatch.setattr(config, "ALT_MODEL", None)

        def handler(request):
            assert "alt" not in str(request.url).lower()
            return httpx.Response(500)

        async def go():
            async with client_with(handler) as client:
                pool = KeyPool(["k0"])
                return await interpret_notes(
                    ["no alt rung note"], make_battery(), client, pool,
                    deadline=time.monotonic() + 20)

        result = run(go())
        assert result.degraded


# ---------------------------------------------------------------------------
# Base-infeasible request -> 422 (through the real HTTP pipeline)
# ---------------------------------------------------------------------------
class TestBaseInfeasibleRequest:
    def test_minimum_greater_than_capacity_is_422(self):
        from fastapi.testclient import TestClient

        from app.main import app

        payload = {
            "scenario_id": "PROVIDER-BASE-INFEASIBLE",
            "operator_notes": ["no directive"],
            "hours": [{"hour": h, "demand_kwh": 50.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 10.0}
                      for h in range(24)],
            "battery": {
                "capacity_kwh": 100.0, "initial_energy_kwh": 100.0, "minimum_energy_kwh": 150.0,
                "max_charge_kwh_per_hour": 50.0, "max_discharge_kwh_per_hour": 50.0,
            },
        }
        with TestClient(app) as client:
            r = client.post("/optimize-energy", json=payload)
        assert r.status_code == 422
        assert r.json() == {"error": "infeasible_scenario"}
