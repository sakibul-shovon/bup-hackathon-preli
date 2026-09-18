"""L5 stub (plan Section 12.6 writes the FULL version in L8 -- ladder-exhaustion,
degrade, salvage, and deadline-cascade cases all land there). This stub exercises
the pieces of llm_interpreter.py that don't depend on app/guardrails.py (not yet
built), so it's real coverage now rather than a placeholder.

Skips entirely until app/sanitize.py (owned by a teammate) exists, since
llm_interpreter.py imports it at module level.
"""
import asyncio
import time

import httpx
import pytest

pytest.importorskip("app.sanitize")

from app.llm_interpreter import (  # noqa: E402
    KeyPool,
    _call_pooled_rung,
    build_system_prompt,
    build_user_message,
    cache_key,
)
from app.schemas import Battery  # noqa: E402


def make_battery(**overrides):
    defaults = dict(
        capacity_kwh=500, initial_energy_kwh=200, minimum_energy_kwh=50,
        max_charge_kwh_per_hour=100, max_discharge_kwh_per_hour=100,
    )
    defaults.update(overrides)
    return Battery(**defaults)


class TestKeyPoolRotation:
    def test_round_robin_over_healthy_keys(self):
        pool = KeyPool(["k0", "k1", "k2"])
        picks = [pool.next_healthy(deadline=time.monotonic() + 10)[0] for _ in range(3)]
        assert picks == [0, 1, 2]

    def test_empty_pool_returns_none(self):
        pool = KeyPool([])
        assert pool.next_healthy(deadline=time.monotonic() + 10) is None

    def test_429_cooldown_skips_key_on_next_pick(self):
        pool = KeyPool(["k0", "k1"])
        idx0, _ = pool.next_healthy(deadline=time.monotonic() + 10)
        assert idx0 == 0
        pool.mark_429(idx0, retry_after=30)
        idx1, _ = pool.next_healthy(deadline=time.monotonic() + 10)
        assert idx1 == 1, "a different key_idx must be used after a 429"

    def test_429_cooldown_capped_at_10s_even_with_large_retry_after(self):
        pool = KeyPool(["k0"])
        pool.mark_429(0, retry_after=9999)
        assert pool._states[0].cooldown_until <= time.monotonic() + 10.0 + 1e-3

    def test_unauthorized_cools_down_for_an_hour(self):
        pool = KeyPool(["k0", "k1"])
        pool.mark_unauthorized(0)
        idx, _ = pool.next_healthy(deadline=time.monotonic() + 10)
        assert idx == 1

    def test_all_cooling_down_returns_none_when_past_deadline(self):
        pool = KeyPool(["k0"])
        pool.mark_unauthorized(0)  # cools down 1 hour
        assert pool.next_healthy(deadline=time.monotonic() + 5) is None

    def test_no_sleep_on_429(self, monkeypatch):
        import app.llm_interpreter as mod

        def _forbidden_sleep(*args, **kwargs):
            raise AssertionError("must not sleep on 429 -- hop to next key instead")

        monkeypatch.setattr("time.sleep", _forbidden_sleep)
        pool = KeyPool(["k0", "k1"])
        pool.mark_429(0, retry_after=30)
        idx, _ = pool.next_healthy(deadline=time.monotonic() + 10)
        assert idx == 1


class TestCacheKey:
    def test_deterministic(self):
        b = make_battery()
        assert cache_key(["note a"], b) == cache_key(["note a"], b)

    def test_differs_by_battery_field(self):
        b1 = make_battery()
        b2 = make_battery(initial_energy_kwh=999)
        assert cache_key(["note a"], b1) != cache_key(["note a"], b2)

    def test_differs_by_notes(self):
        b = make_battery()
        assert cache_key(["note a"], b) != cache_key(["note b"], b)


class TestPromptBuilders:
    def test_system_prompt_interpolates_battery(self):
        b = make_battery(capacity_kwh=321)
        prompt = build_system_prompt(b)
        assert "321" in prompt

    def test_user_message_has_note_tags(self):
        msg = build_user_message(["first note", "second note"])
        assert '<note index="0">' in msg
        assert '<note index="1">' in msg
        assert "first note" in msg
        assert "second note" in msg


class TestCallPooledRung:
    def test_success_returns_content(self):
        def handler(request):
            return httpx.Response(200, json={
                "choices": [{"message": {"content": '{"notes":[]}'}}]
            })

        async def run():
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                pool = KeyPool(["k0"])
                return await _call_pooled_rung(
                    client, pool, "some-model", 5.0, "sys", "user",
                    deadline=time.monotonic() + 10,
                )

        content = asyncio.run(run())
        assert content == '{"notes":[]}'

    def test_429_marks_key_and_raises_key_attributable(self):
        def handler(request):
            return httpx.Response(429, headers={"Retry-After": "5"})

        from app.llm_interpreter import _RungFailure

        async def run():
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                pool = KeyPool(["k0"])
                try:
                    await _call_pooled_rung(client, pool, "some-model", 5.0, "sys", "user",
                                             deadline=time.monotonic() + 10)
                except _RungFailure as exc:
                    return exc, pool
                raise AssertionError("expected _RungFailure")

        exc, pool = asyncio.run(run())
        assert exc.key_attributable is True
        assert pool._states[0].cooldown_until > time.monotonic()

    def test_deadline_already_breached_skips_network_call(self):
        called = False

        def handler(request):
            nonlocal called
            called = True
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

        from app.llm_interpreter import _RungFailure

        async def run():
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                pool = KeyPool(["k0"])
                await _call_pooled_rung(client, pool, "some-model", 5.0, "sys", "user",
                                         deadline=time.monotonic() + 0.1)

        with pytest.raises(_RungFailure):
            asyncio.run(run())
        assert called is False, "must not fire a network call under 1.5s of deadline budget"
