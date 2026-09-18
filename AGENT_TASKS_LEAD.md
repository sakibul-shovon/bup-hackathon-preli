# Dev A (Lead) — Agent Task Sheet

**You own the spine.** Every task below is a ready-to-paste prompt for an agentic coding
tool. Paste **one task at a time**, let it finish, run the verify command, commit, move on.

**Canonical spec:** `GRIDWISE_IMPLEMENTATION_PLAN (1).md` **V4**. Every prompt tells the agent
to read the relevant sections. Do not let it improvise past them.

**Files you own:** `app/{config,schemas,main,directives,optimizer,validator,llm_interpreter,guardrails}.py`,
all `tests/*.py` except `test_sanitize.py` / `test_summary.py`, `tests/data/public_cases.json`,
`scripts/{run_public_cases,fuzz}.py`, `PROGRESS.md`.

**Files you must NOT create or edit** (Dev B owns them): `app/sanitize.py`, `app/summary.py`,
`Dockerfile`, `requirements.txt`, `README.md`, `.env.example`, `.gitignore`, `.dockerignore`,
`scripts/latency_probe.py`, `tests/data/paraphrases.json`, `tests/test_sanitize.py`,
`tests/test_summary.py`. If one is missing when you need it, import it and keep going — do
not create her file.

---

## Standing preamble — paste this at the TOP of every task prompt

```
Read `GRIDWISE_IMPLEMENTATION_PLAN (1).md` sections 0 and 2 before writing any code, and
treat them as binding. This is V4 of the plan; where older V3 text survives in the body and
contradicts the V4 change table at the top of the file, V4 wins.

Hard rules for this task:
- Implement exactly what the plan specifies. Where it is silent, pick the simplest option
  that preserves every Section 2 invariant.
- Do not add any dependency beyond Section 4.
- Do not hardcode public sample note wording, scenario IDs, or reference numbers anywhere
  under app/.
- Do not create or modify these files (another developer owns them): app/sanitize.py,
  app/summary.py, Dockerfile, requirements.txt, README.md, .env.example, .gitignore,
  .dockerignore, scripts/latency_probe.py, tests/data/paraphrases.json,
  tests/test_sanitize.py, tests/test_summary.py.
- If a test contradicts a mathematical proof, the proof wins and you change the test — but
  write the proof in the commit message and never delete the test (standing rule 3a).
- Never relax energy balance (I24), battery transitions (I20), reserve/capacity bounds
  (I21), or end-of-day neutrality (I26). If they cannot be satisfied, the answer is 422.
```

---

## L0 — Skeleton, config, schemas, /health   ~20 min

```
[standing preamble]

Create the repo skeleton from plan Section 3 (only the files I own). Then implement:

1. app/config.py — read every environment variable in plan Section 4 with the stated
   defaults. GROQ_API_KEYS is a comma-separated list, whitespace-stripped, blanks dropped;
   fall back to GROQ_API_KEY only when GROQ_API_KEYS is unset or empty. Missing keys is NOT
   an error at import time or at startup — the service must boot fine without any key.
   Export EMIT_DP = 8 and REPLAY_EPS = 1e-6 as module constants (invariant I36).

2. app/schemas.py — the Pydantic v2 request models from plan Section 9.1, with I6a applied:
   model_config = ConfigDict(extra="ignore") on ALL THREE models. Unknown extra fields must
   be silently dropped, never rejected. Everything else stays strict: allow_inf_nan=False,
   ge=0 bounds, exactly 24 hours whose `hour` values are exactly the set 0..23, 1-3 notes
   each non-empty after strip and at most 2000 chars.

3. app/main.py — FastAPI app, GET /health returning exactly {"status":"ok"}, the 2 MB body
   middleware, and all exception handlers from Section 9.2 (RequestValidationError -> 400,
   InfeasibleError -> 422, catch-all -> opaque 500). POST /optimize-energy may be a stub
   that raises NotImplementedError for now.

Verify: uvicorn starts, curl localhost:8000/health returns exactly {"status":"ok"}, and
pytest collects with no errors.
```

**Verify:** `uvicorn app.main:app --port 8000` then `curl -s localhost:8000/health`
**Commit:** `L0: skeleton, config, schemas, health`

---

## L1 — directives.py   ~25 min

```
[standing preamble]

Implement app/directives.py per plan Section 6.1 and Section 8's NormalizedDirectives output,
plus tests/test_directives.py per plan Section 12.2.

- expand(start_hour, end_hour_exclusive) including the midnight wrap, returning sorted
  unique hours.
- Factor arithmetic: (80, "reduced_by") -> exactly 0.2; (20, "remaining") -> 0.2. Round to
  6 dp so 0.19999999999999996 can never reach the response.
- Reserve unit conversion for ALL FOUR units in the V4 enum: kwh, percent_of_capacity,
  percent_of_initial, percent_of_minimum (plan Section 7.2, F8).
- The per-hour merge table exactly as written: solar factors MULTIPLY, reserves take MAX
  (including the base minimum), grid caps take MIN, charge/discharge prohibitions UNION.
- The structured_adjustment builders, byte-exact shapes per type, no_op -> None.

Tests must cover every row of Section 12.2 including the merge table and the wrap case.
```

**Verify:** `pytest tests/test_directives.py -q`
**Commit:** `L1: directives + merge semantics`

---

## L2 — optimizer.py   ~25 min   (own agent session)

```
[standing preamble]

Implement app/optimizer.py from plan Section 10. Port Section 10.2's reference LP code
faithfully — it has been independently verified to reproduce all 10 official reference costs
to the exact BDT, so do not restructure it.

Include:
- solve_lp() exactly as in 10.2 (signed battery flow; 3*24 variables ordered g | s | b).
- Canonicalization per 10.4, with ONE correction that overrides the V3 text: round emitted
  plan values to 8 decimal places, NOT 4. See invariant I36 — at 4 dp the service rejects
  its own valid output on 105 of 477 decimal-heavy scenarios. Use config.EMIT_DP; never
  write a literal 4 here.
- Rebuild the SOC trajectory cumulatively from initial_energy_kwh using the snapped flows;
  never emit raw solver SOC.
- Kill -0.0. Totals computed FROM the final emitted values.
- Feasibility salvage per 10.5 WITH the F6 correction: directives dropped by the salvage
  keep their reported interpretation (applies stays true) and are dropped only from the
  optimizer. Return which directives were dropped so the caller can log it.

This module must not import app/validator.py.
```

**Verify:** small script solving one hand-built scenario returns status 0
**Commit:** `L2: exact LP + 8dp canonicalization + salvage`

---

## L3 — validator.py   ~25 min   ** START A FRESH AGENT SESSION **

> The plan requires `validator.py` to share **zero** code with `optimizer.py`. Start a new
> session so the agent cannot copy from it. Do not paste optimizer code into this session.

```
[standing preamble]

Implement app/validator.py from plan Section 11 as an INDEPENDENT replay of a finished
schedule. It may import only stdlib and the request dataclasses. It must NOT import
app/optimizer.py, and you must not consult that file while writing this one.

replay(request, directives, plan, eps=1e-6) -> list[str], empty list meaning valid.
Implement all 10 numbered checks. Recompute effective solar and the active reserve from
scratch from the original request — never trust a value the optimizer passed along.

Then implement the V4 three-tier runtime policy from Section 11 (this REPLACES V3's flat
"violations -> 500"):
  max_violation <= 1e-6        -> ship
  1e-6 < max_violation < 0.01  -> log loudly, SHIP ANYWAY (the judge accepts it at 0.01;
                                  a 500 here turns full credit into zero)
  max_violation >= 0.01        -> build the TRIVIAL PLAN (grid=demand, solar_used=0,
                                  battery idle all 24 h, SOC flat at initial), re-replay
                                  that, and ship it if clean
  trivial plan also invalid    -> 500

Also write tests/test_validator.py: hand-build a plan that violates each of the 10 checks
one at a time, and assert each violation is caught AND named.
```

**Verify:** `pytest tests/test_validator.py -q`
**Commit:** `L3: independent replay validator + 3-tier ship policy`

---

## L4 — THE ANCHOR: 10/10 public cases   ~20 min   ** this is the submittable core **

```
[standing preamble]

Copy docs/BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json to tests/data/public_cases.json
(copy it, never hand-edit it). Write tests/test_public_cases.py per plan Section 12.1.

For each of the 10 cases: mock the LLM to return that case's ground-truth interpretation in
IR form, then run the full deterministic pipeline (guardrails -> directives -> optimizer ->
canonicalize -> replay -> response assembly). Assert:
  - response schema exactly matches Section 5.2 (top-level keys, interpretation entries in
    note_index order with exact structured_adjustment shapes, 24 plan entries)
  - replay returns zero violations
  - totals are self-consistent with the returned plan
  - abs(total_cost_bdt - reference cost) <= 0.01

Reference costs, for your own sanity check — all ten have been independently verified as
achievable exactly by this LP formulation:
  SAMPLE-01 38365 · 02 42885 · 03 35480 · 04 40495 · 05 33950
  SAMPLE-06 34090 · 07 38550 · 08 37665 · 09 34873 · 10 41620
A cost ABOVE reference means a suboptimal bug; BELOW means a constraint bug. Both fail.
```

**Verify:** `pytest tests/test_public_cases.py -q` → 10 passed
**Commit:** `L4: 10/10 public cases green`
**You now have a submittable core. Update PROGRESS.md and tell Dev B.**

---

## L5 — llm_interpreter.py + key rotation + deadline   ~35 min

```
[standing preamble]

Implement app/llm_interpreter.py from plan Sections 7.1-7.8. Pay particular attention to
V4 sections 7.3 and 7.3b, which replace V3's ladder entirely.

Required:
- ONE Groq call interprets ALL notes. A single shared httpx.AsyncClient, created at startup.
- The IR JSON schema from 7.4 verbatim, including the four-value reserve_unit enum.
- System prompt from 7.5 INCLUDING the V4 window-phrasing rules (all day / open-ended start
  / open-ended end / duration / vague time words) and all five battery fields interpolated.
- max_completion_tokens 1500, temperature 0, seed 7, reasoning_effort low.
- The deadline-bounded ladder from 7.3: every rung gets timeout = min(rung_timeout,
  deadline - now); no rung starts with under 1.5 s left; a deadline breach degrades
  immediately. Rung 2 is taken ONLY on a key-attributable failure (429/401/403/5xx), not on
  a schema or guardrail failure. The corrective re-ask fires AT MOST ONCE per request.
- The multi-key pool from 7.3b: round-robin over healthy keys, per-key cooldown_until.
  On 429 -> cooldown and IMMEDIATELY hop to the next key, DO NOT SLEEP. On 401/403 ->
  cooldown 1 hour. On 5xx/transport -> cooldown 2 s.
- Keys appear in logs ONLY as key_idx=N. Never the value, prefix, suffix, or length.
- Optional ALT provider rung, skipped entirely when ALT_BASE_URL is unset.
- LRU cache (256) keyed on sha256 of {"notes": [...], "battery": {all five fields}}.
  Never cache a degraded or partially-degraded interpretation.

app/sanitize.py is owned by another developer. Import it and code against exactly these
signatures without creating the file:
    sanitize_note(text: str) -> str
    sanitize_explanation(text: str | None, fallback: str) -> str
```

**Verify:** `pytest tests/test_provider.py -q` (written in L8 — stub it for now)
**Commit:** `L5: interpreter, deadline-bounded ladder, key rotation`

---

## L6 — guardrails.py   ~20 min

```
[standing preamble]

Implement app/guardrails.py from plan Section 8 as pure functions.

validate_ir(ir_json_text, note_count, battery) -> NormalizedDirectives, raising
GuardrailError(violations) on failure.

All 8 numbered checks, in order. Specifically:
- json.loads with a parse_constant that RAISES on NaN/Infinity.
- Exactly note_count entries whose note_index set is exactly {0..N-1}.
- The per-type field contract, including reserve_unit conversion for all four units and the
  rule that a computed reserve must not exceed capacity.
- Never repair, clamp, or guess a VALUE. Reject instead.
- Violations collected PER NOTE so the terminal degrade can keep the valid notes and no_op
  only the broken ones.
```

**Verify:** `pytest tests/test_directives.py tests/test_public_cases.py -q` still green
**Commit:** `L6: deterministic guardrails`

---

## L7 — main.py orchestration   ~25 min

```
[standing preamble]

Wire the full flow in app/main.py per plan Section 6, steps 0-10.

Critical V4 behaviors that must be exactly right:
- Step 0 starts the I35 deadline clock.
- I5: provider failure of ANY kind -> degraded 200. This includes NO KEY CONFIGURED AT ALL.
  There is no code path from a provider, key, quota, timeout, or guardrail problem to a 5xx.
  A 500 means only that our own code has a bug.
- I5a / F6: a note that WAS interpreted successfully keeps its real interpretation in the
  response even when the optimizer could not apply it. Only genuinely uninterpreted notes
  become no_op. Interpretation and Application are scored in separate categories, and the
  rubric has no self-consistency check between them.
- Step 9 uses the validator's three-tier ship policy, not a flat 500.
- The response is assembled as plain dicts (not nested response models) so the field set is
  exactly Section 5.2 and structured_adjustment serializes as JSON null.
- Totals computed FROM the final returned hourly values.

app/summary.py is owned by another developer. Import it and code against exactly:
    build_summary(total_grid_kwh: float, total_cost_bdt: float, peak_grid_kwh: float,
                  peak_hour: int, charge_hours: list[int], discharge_hours: list[int],
                  applied_types: list[str]) -> str
Compute those seven values yourself and pass them in. Do not create her file.
```

**Verify:** a real POST of a sample case returns a valid 200
**Commit:** `L7: full pipeline orchestration`

---

## L8 — the defect-guard test files   ~30 min

```
[standing preamble]

Write these three test files. Each guards a defect that was live in V3 of the plan, so treat
a red test here as a real bug, not a flaky test.

1. tests/test_precision.py per plan Section 12.5b (guards F2). Generate at least 300
   feasible scenarios with 1-4 decimal places in demand/solar/tariff and 2-3 in the battery
   fields, plus non-terminating factors (1/3, 2/3, 0.15). Assert zero replay violations at
   eps=1e-6, assert EMIT_DP == 8, and assert EPS / 10**-EMIT_DP >= 100.
   NOTE: the 10 public cases have integer inputs, so they CANNOT detect this class of bug.
   Passing them is not evidence this is fixed.

2. tests/test_api.py per plan Section 12.4. The five extra-field tolerance cases must return
   200, not 400 — they guard the highest-expected-loss failure mode in the whole submission
   (C11 / I6a). Also assert that no response body at any status contains a key value, a
   provider hostname, a stack frame, or an echoed input number.

3. tests/test_provider.py per plan Section 12.6 including every V4 addition: no key
   configured -> 200; invalid key -> hop then degrade; 3 keys with one 429 -> a different
   key_idx is used and NO sleep longer than 0.1 s occurs; all keys 429 -> degraded 200
   inside the deadline; every rung hangs 10 s -> the handler returns within
   LLM_DEADLINE_SECONDS + 2 s; key values never appear in captured logs; F6 salvage keeps
   the real interpretation; the ALT rung is called only when configured.

Also add the edge scenarios from Section 12.3 to tests/test_optimizer.py. Note that
initial_energy_kwh < minimum_energy_kwh must be ACCEPTED by the API layer and then return
422 — it is provably infeasible because neutrality forces E_after[23] = initial while the
reserve floor forces E_after[23] >= minimum. Do NOT modify the optimizer to make it
feasible; that would invalidate every hidden case.
```

**Verify:** `pytest -q` fully green
**Commit:** `L8: precision, api-tolerance, provider tests`

---

## L9 — fuzz.py   ~20 min (compress if behind, but keep the paraphrase half)

```
[standing preamble]

Implement scripts/fuzz.py per plan Section 12.8.

Scenario fuzz with mocked interpretations: 100+ synthetic cases through the REAL pipeline.
Assert every case returns a replay-valid 200, or a 422 only when the base scenario is
provably infeasible. Log latency.

Paraphrase holdout with the live LLM: read tests/data/paraphrases.json (another developer
owns that file — read it, never edit it) and score extraction accuracy against the expected
field in each entry. Print a summary table plus p50/p95.

If the scenario fuzz ever reaches the trivial-plan fallback, that is a P0 bug, not a safety
net working as intended — print it loudly.
```

**Verify:** `python scripts/fuzz.py` → 100% replay-valid
**Commit:** `L9: hidden-test simulator`

---

## L10 — Deploy   ** HARD START BY 2:50 REGARDLESS OF STATE **

Follow plan Section 15 exactly. Build `--platform linux/amd64` (F9) — an arm64 image is
unrunnable by the judge precisely when the fallback matters most.

```bash
docker buildx build --platform linux/amd64 -t gridwise --load .
docker run -d -p 8000:8000 -e GROQ_API_KEYS="$GROQ_API_KEYS" gridwise
curl -s localhost:8000/health
python scripts/run_public_cases.py http://localhost:8000

# F1 check — no key configured must still return 200, never 500:
docker run -d -p 8001:8000 gridwise
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8001/optimize-energy \
     -H 'content-type: application/json' -d @tests/data/one_case.json

docker push <registry>/gridwise:final
docker buildx imagetools inspect <registry>/gridwise:final | grep -i arch   # must say amd64
```

Then deploy to an always-on host (no cold sleep), point an uptime monitor at `/health`, and
smoke-test the public URL from a phone hotspot.

**Commit:** `L10: deployed`

---

## If you fall behind — drop in this order

1. `scripts/fuzz.py` scenario-fuzz case count (keep the paraphrase holdout — it targets 5
   directly scored points)
2. `test_adversarial.py` beyond the two injection cases
3. The ALT-provider rung
4. Alternate-optima polish (already a non-feature)

**Never drop:** L4 (the anchor), the five extra-field tests, `test_precision.py`, L10, or
the video.
