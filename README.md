# GridWise

## 1. Architecture

GridWise uses a hybrid neuro-symbolic architecture to ensure 100% hard-constraint adherence. **The LLM performs the semantic interpretation of operator notes into the structured directives used to build the optimization constraints. Deterministic code does everything else: validation, guardrails, arithmetic, LP optimization, and replay.**

### Request Flow
1. **Validation**: Strict Pydantic parsing of the incoming scenario.
2. **Cache Check**: Exact JSON hash match against previous runs.
3. **LLM Interpreter**: Single Groq call to classify and extract numerical parameters from all operator notes.
4. **Guardrails**: Deterministic checks on the LLM output.
5. **Directives**: Code combines overlapping windows and computes exact unit bounds per hour.
6. **Optimizer**: Linear Programming (`scipy.optimize.linprog` with HiGHS) solves for the exact minimum cost.
7. **Canonicalization**: Snaps dust, rebuilds SOC exactly, rounds values to 8 decimal places.
8. **Replay Validator**: Independent check ensures the final plan perfectly matches all physical constraints.
9. **Assembly**: Final response built securely, including deterministic plan summary.

## 2. Model/Provider

- **Provider**: Groq
- **Primary Model**: `openai/gpt-oss-20b`
- **Fallback Model**: `openai/gpt-oss-120b`
- **Decoding**: Strict JSON-schema structured outputs
- **Temperature**: 0 (with fixed seed for maximum determinism)

## 3. Guardrails

Our deterministic IR validation (`guardrails.py`) includes:
- `json.loads` handler that raises on NaN/Infinity (defense in depth).
- Top shape check: verifies note count and ensures unique `note_index` values without gaps.
- `directive_type` enum validation.
- Per-type field contracts (ensuring irrelevant fields are strictly null).
- Window sanity checks (start_hour 0-23, end_hour 1-24, expanded union ≤ 24 hours).
- Finite math checks (`math.isfinite`) for all numbers.
- Strict rejection without guessing or repairing values.
- Per-note violation collection, enabling selective degradation of broken notes rather than failing the whole request.

## 4. Optimizer

Linear Programming over grid, solar, and signed-battery-flow variables.
- Powered by `scipy.optimize.linprog(method="highs")`.
- Finds the exact mathematical optimum (minimum cost).
- Protected by independent replay validation before every single response.

## 5. Environment Variables

- `GROQ_API_KEYS`
- `PORT`
- `PROMPT_COMPACT`

## 6. Local Quickstart

```bash
git clone https://github.com/sakibul-shovon/bup-hackathon-preli.git
cd bup-hackathon-preli
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEYS="your_api_key_here"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 7. Verify

Check health:
```bash
curl http://localhost:8000/health
```
Expected output:
```json
{"status":"ok"}
```

Sample optimization request:
```bash
curl -X POST http://localhost:8000/optimize-energy \
-H "Content-Type: application/json" \
-d '{
  "scenario_id": "test-01",
  "operator_notes": ["Reduce solar output by 20% between 12 PM and 2 PM."],
  "battery": {
    "capacity_kwh": 500.0,
    "initial_energy_kwh": 200.0,
    "minimum_energy_kwh": 100.0,
    "max_charge_kwh_per_hour": 100.0,
    "max_discharge_kwh_per_hour": 100.0
  },
  "hours": [
    {"hour": 0, "demand_kwh": 50.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 5.0}
  ]
}'
```
*(Body truncated for brevity)*

Expected response (trimmed):
```json
{
  "scenario_id": "test-01",
  "total_grid_kwh": 1400.5,
  "total_cost_bdt": 7500.25,
  "peak_grid_kwh": 80.0,
  "plan_summary": "Purchased 1400.5 kWh from the grid for 7500.25 BDT, peaking at 80.0 kWh in hour 18. Applied operator directives: solar_reduction.",
  "hours": [
    {
      "hour": 0,
      "grid_kwh": 50.0,
      "solar_used_kwh": 0.0,
      "battery_kwh": 0.0,
      "battery_action": "idle",
      "battery_energy_after_kwh": 200.0,
      "reserve_kwh": 100.0,
      "eff_solar_kwh": 0.0
    }
  ]
}
```

## 8. Public Sample Validation

```bash
python scripts/run_public_cases.py http://localhost:8000
```
*(Expected output: 10/10 valid, 10/10 optimal within tolerance)*

## 9. Tests

Run the test suite:
```bash
pytest -q
```
*(Note: tests requiring the LLM require the `GROQ_API_KEYS` environment variable and must be run with `-m live`)*

## 10. Docker Fallback

```bash
docker pull ghcr.io/sakibul-shovon/bup-hackathon-preli:main
docker run -p 8000:8000 -e GROQ_API_KEYS="your_key_here" ghcr.io/sakibul-shovon/bup-hackathon-preli:main
```

## 11. Dependencies & Credits

| Package | Purpose |
|---|---|
| `fastapi` | API Framework |
| `uvicorn[standard]` | ASGI Server |
| `httpx` | Async HTTP Client |
| `scipy` | Optimizer (HiGHS) |
| `numpy` | Numeric structures |
| `pytest` | Testing |

Special credits as required by competition rules:
- **scipy / HiGHS**: Linear programming solver
- **FastAPI**: Backend web framework
- **Groq**: LLM infrastructure and inference
- **AI Assistants**: Built with assistance from standard AI coding tools.

## 12. Known Limitations

- System depends on Groq API availability and quota.
- **If the model provider is unavailable, the service degrades to a valid schedule with notes reported as `no_op` and still returns HTTP 200 — it never returns a 5xx.**
- Alternate optimal schedules are possible under flat tariffs (battery cycling cost-neutral).
- Overlapping-solar-directive product semantics (handled deterministically).
- Vague time expressions are mapped tightly by convention, rather than being left unanswered.

## 13. Secret Handling

- Keys are injected via environment variables only.
- Keys are never committed, logged in plaintext, or returned in API responses.
