# Dev B — Agent Task Sheet

Hi! Everything here is **self-contained** — you can finish every task without waiting for
anyone, and nothing you write can break the lead's code. Work top to bottom.

Your tasks are worth real marks, not busywork:
- **B4 (README) is worth 10 of the 100 points** — the single biggest thing either of us
  owns outside the core pipeline.
- **B0 (Dockerfile) feeds 4 more points** and is the backup the judges use if our live URL
  goes down.
- **B3 (paraphrases) feeds the 5-point "paraphrase robustness" line.**

---

## Before you start — three rules

1. **Only create or edit the files listed as yours below.** If you think another file needs
   changing, message the lead instead. This is what stops our work from colliding.
2. **Never copy wording from `docs/BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json`** into
   anything. The competition rules forbid hardcoding the public samples, and hidden test
   notes are worded differently anyway. Write fresh sentences in your own words.
3. **Never put a real API key in any file.** Only the *names* of variables, never values.
4. **When a task's Verify step passes, change that task's ⬜ to ✅ in this file, in the same
   commit as the task's files.** This file is your own progress record — if you close this
   window and open a new one later (or the lead asks "how far are you"), the ✅ marks are
   the only way anyone knows without re-asking you.

### 🔁 Resuming in a new window

Don't try to remember which task you left off on. Paste this instead:

```
Read AGENT_TASKS_DEV2.md in full. Find the FIRST task (B0-B6) that is still ⬜ (or 🔴).
Before starting it, quickly re-run the previous task's Verify command to confirm it
actually still passes — the checkbox can be stale if a commit was interrupted.
Execute that one task exactly as written, commit your files, flip its box to ✅ in the
same commit, then stop and report what you did.
```

### Your files

```
app/sanitize.py              tests/test_sanitize.py
app/summary.py               tests/test_summary.py
tests/data/paraphrases.json
scripts/latency_probe.py
Dockerfile   .dockerignore   .gitignore   .env.example
requirements.txt             README.md
AGENT_TASKS_DEV2.md          (tick your own boxes here)
```

### Git — do this every time

```bash
git pull --rebase
git add <just your files>
git commit -m "B<number>: <what you did>"
git push
```

Never use `git add -A` or `git add .` — it would pick up the lead's files.

---

## B0 — Project files   ~15 min   ✅

Create five small files. Four are nearly copy-paste from the plan.

**`requirements.txt`** — exactly the six lines in plan Section 4, nothing more:
```
fastapi
uvicorn[standard]
httpx
scipy
numpy
pytest
```

**`Dockerfile`** — copy it verbatim from plan Section 15.

**`.dockerignore`**
```
.env
.git
tests
docs
scripts
__pycache__
*.md
```

**`.gitignore`**
```
.env
__pycache__/
*.pyc
.pytest_cache/
.venv/
```

**`.env.example`** — variable **names only, no values ever**:
```
GROQ_API_KEYS=
GROQ_API_KEY=
PORT=8000
PRIMARY_MODEL=
FALLBACK_MODEL=
LLM_TIMEOUT_PRIMARY=
LLM_TIMEOUT_FALLBACK=
LLM_DEADLINE_SECONDS=
PROMPT_COMPACT=
ALT_BASE_URL=
ALT_API_KEY=
ALT_MODEL=
```

**Verify:** `docker build -t gridwise .` completes. (If Docker is not installed yet, skip
the build, tell the lead, and move to B1 — do not get stuck here.)

**Done when:** all five files exist and `.env.example` contains no actual key values.

---

## B1 — `app/sanitize.py`   ~25 min   ✅

Two small text-cleaning functions. The lead's code already calls them, so **the names and
arguments below are fixed — do not rename anything.**

```python
def sanitize_note(text: str) -> str:
    """Clean one operator note before it is shown to the language model."""

def sanitize_explanation(text: str | None, fallback: str) -> str:
    """Clean the model's explanation before it goes into our API response."""
```

### What `sanitize_note` must do, in this order

1. Unicode-normalise with `unicodedata.normalize("NFKC", text)`.
2. Remove invisible/control characters: drop any character whose
   `unicodedata.category(ch)` is `"Cf"`, and any whose category is `"Cc"` **except** `"\n"`.
   *(These hide malicious text inside an innocent-looking note.)*
3. Collapse every run of whitespace into a single space, then `.strip()`.
4. Truncate to at most **1000** characters.
5. Return the result.

### What `sanitize_explanation` must do

1. If `text` is `None` or empty after stripping → return `fallback`.
2. Remove control characters (same `Cc`/`Cf` rule).
3. Collapse whitespace and strip.
4. Truncate to at most **200** characters.
5. If nothing is left → return `fallback`.

### Agent prompt

```
Create app/sanitize.py with exactly these two functions and these exact signatures:

    def sanitize_note(text: str) -> str
    def sanitize_explanation(text: str | None, fallback: str) -> str

sanitize_note: NFKC-normalise; remove every character in Unicode category Cf and every
character in category Cc except newline; collapse whitespace runs to one space; strip;
truncate to 1000 characters.

sanitize_explanation: return the fallback if text is None or blank; remove Cc and Cf
characters; collapse whitespace; strip; truncate to 200 characters; return the fallback if
nothing remains.

Use only the standard library (re, unicodedata). No other imports. Do not create or modify
any other file.

Then create tests/test_sanitize.py covering: a normal note passes through readable; a
zero-width character (​) and a right-to-left override (‮) are both removed; a
2000-character note is cut to 1000; multiple spaces, tabs and newlines collapse; an empty
explanation returns the fallback; a 500-character explanation is cut to 200.
```

**Verify:** `pytest tests/test_sanitize.py -q`
**Done when:** tests pass and the signatures match exactly.

---

## B2 — `app/summary.py`   ~20 min   ✅

One function that writes the human-readable `plan_summary` sentence in our API response.
All inputs are plain numbers and lists — you do not need to understand the optimiser.

```python
def build_summary(
    total_grid_kwh: float,
    total_cost_bdt: float,
    peak_grid_kwh: float,
    peak_hour: int,
    charge_hours: list[int],
    discharge_hours: list[int],
    applied_types: list[str],
) -> str:
```

It returns **one or two short sentences**, built from the numbers — no randomness, no
language model, same input always gives the same output.

Example of the shape (yours does not need to match word for word):

> `Purchased 2692.5 kWh from the grid for 38365.0 BDT, peaking at 175.0 kWh in hour 10. Charged the battery in hours 2-5 and discharged in hours 18-20. Applied operator directives: solar_reduction.`

Handle these gracefully:
- empty `charge_hours` / `discharge_hours` → leave that clause out entirely
- empty `applied_types` → say something like `No operator directives affected this schedule.`
- keep the whole string under 400 characters

### Agent prompt

```
Create app/summary.py with exactly one function and this exact signature:

    def build_summary(total_grid_kwh: float, total_cost_bdt: float, peak_grid_kwh: float,
                      peak_hour: int, charge_hours: list[int], discharge_hours: list[int],
                      applied_types: list[str]) -> str

It returns one or two short deterministic sentences describing the schedule: total grid
energy and cost, the peak hour, which hours charged and discharged (collapse consecutive
hours into ranges like "2-5"), and which operator directive types were applied. Omit the
charge/discharge clause entirely when those lists are empty, and say that no operator
directives affected the schedule when applied_types is empty. Cap the result at 400
characters. Standard library only, no randomness. Do not create or modify any other file.

Then create tests/test_summary.py: a normal case contains the cost and the peak hour; empty
charge and discharge lists produce no stray punctuation; an empty applied_types list
produces the no-directives wording; the result is always under 400 characters; calling it
twice with identical arguments returns identical strings.
```

**Verify:** `pytest tests/test_summary.py -q`
**Done when:** tests pass.

---

## B3 — `tests/data/paraphrases.json`   ~35 min   ⬜   ⭐ high value

This is the **test corpus for the 5-point paraphrase-robustness score.** You are writing
fresh ways a campus operator might phrase each rule, so we can check our system understands
wording it has never seen.

**No coding — this is careful writing.** It is one of the most valuable things on either
task sheet.

### Format

```json
{
  "entries": [
    {
      "id": "solar-01",
      "note": "Rooftop output will sit at roughly a quarter of normal between 11 AM and 1 PM.",
      "expected": { "directive_type": "solar_reduction", "hours": [11, 12], "factor": 0.25 }
    },
    {
      "id": "noop-01",
      "note": "The badminton court booking system will be offline for maintenance next Tuesday.",
      "expected": { "directive_type": "no_op" }
    }
  ]
}
```

### The three conversion rules — get these right or the entry is wrong

1. **Times are start-inclusive, end-exclusive.** "1 PM to 3 PM" → `[13, 14]` (**not**
   `[13, 14, 15]`). "6 PM until 9 PM" → `[18, 19, 20]`. Noon = 12, midnight = 0.
2. **`factor` is how much solar REMAINS**, not how much is lost. "drops to 20%" → `0.2`.
   "an 80% reduction" → also `0.2`. "half of normal" → `0.5`.
3. **Every `hours` array is ascending, unique, and only contains 0-23.**

### Write at least 40 entries

| Type | How many | Cover these phrasings |
|---|---|---|
| `solar_reduction` | 8 | percent remaining, percent reduced, fractions ("a third of normal"), "cut in half", 24-hour clock ("13:00 to 15:00") |
| `minimum_battery_reserve` | 7 | absolute kWh, "% of capacity", "half the battery", "keep it at its starting level", "no less than X" |
| `no_charge_window` | 6 | "charger is isolated", "charging circuit unavailable", "do not charge", "charging is suspended" |
| `no_discharge_window` | 6 | "must not discharge", "hold all discharging", "no battery output" |
| `max_grid_window` | 7 | "must not exceed", "capped at", "at or below", "limited to X per hour" |
| `no_op` | 8 | **see the warning below** |

**Also include a few of each of these anywhere in the list:**
- "all day" / "throughout today" → `hours` 0-23
- "from 6 PM onwards" → `[18..23]`
- "before 6 AM" → `[0..5]`
- "for three hours starting at 2 PM" → `[14, 15, 16]`
- Bangladeshi/South-Asian English phrasing, e.g. "upto" for "until", "Solar will be reduced by 60% from 6 PM upto 9 PM"

### ⚠️ The `no_op` entries are the hardest and the most valuable

Half of them must be **energy-related but still `no_op`** — things that sound electrical but
are not one of our five rules. This is exactly where most teams' systems will guess wrong:

- "Please ask the library block to reduce air-conditioning this afternoon." *(energy, but not one of the five)*
- "Paperwork for the diesel generator fuel delivery must be filed today."
- "The solar vendor emailed next quarter's brochure."
- "A tariff review meeting is scheduled for Friday."
- "Battery warranty renewal is due next semester." *(mentions the battery — still no_op)*

The other half can be plainly unrelated (room bookings, exam timetables, cafeteria menus).

**Verify:** `python -c "import json;d=json.load(open('tests/data/paraphrases.json'));print(len(d['entries']))"` prints 40 or more.
**Done when:** valid JSON, 40+ entries, no wording copied from the sample pack.

---

## B4 — `README.md`   ~40 min   ⬜   ⭐ 10 points

Judges score this directly and try to run our project from it on a clean machine. Write all
13 sections from **plan Section 16**, in that order.

**Best time to start: after the 2:00 sync**, when the lead's pipeline actually returns real
responses — then you can paste real output instead of guessing.

### The three things judges actually check

1. **Copy-paste quickstart that works from nothing.** clone → create venv → install → set
   env var names → run → `curl /health`. Every command literal, no "install the usual
   dependencies", no steps only we would know.
2. **A real worked example.** An actual `curl` to `/optimize-energy` with a full request
   body and the real (trimmed) response, copied from a working run — never invented.
3. **This exact sentence, kept word for word** — it is our defence against being judged as
   not using an LLM:

   > *The LLM performs the semantic interpretation of operator notes into the structured
   > directives used to build the optimization constraints. Deterministic code does
   > everything else: validation, guardrails, arithmetic, LP optimization, and replay.*

### Also required

- Model/provider (Groq, and the model names from `config.py` — ask the lead)
- **Environment variable names only — never a key value**
- Docker `pull` and `run` commands with the exact tag/digest (ask the lead after L10)
- Dependencies table and credits (scipy/HiGHS, FastAPI, Groq, and any AI coding assistant —
  the rules require crediting these)
- Known limitations. Include this one, worded carefully:
  *if the model provider is unavailable, the service degrades to a valid schedule with notes
  reported as `no_op` and still returns HTTP 200 — it never returns a 5xx.*
- How to run the tests: `pytest -q`

**Done when:** every one of the 13 sections exists and B6 passes.

---

## B5 — `scripts/latency_probe.py`   ~15 min   ⬜

A small script that measures how fast our deployed API responds. We need **p95 under 5
seconds** for full marks.

```
python scripts/latency_probe.py http://localhost:8000 20
```

### Agent prompt

```
Create scripts/latency_probe.py. It takes a base URL as the first command-line argument and
an optional request count as the second (default 20). It POSTs a scenario to
<base_url>/optimize-energy that many times, timing each request with time.perf_counter().

Vary the operator note text slightly on each request so the server-side cache cannot hide
the real latency.

Print the count, how many succeeded, how many failed, and p50, p95 and max latency in
seconds, plus a clear PASS or FAIL line for whether p95 is under 5 seconds.

Use only the standard library plus httpx. Handle connection errors without crashing — count
them as failures and keep going. Do not create or modify any other file.
```

**Verify:** run it against the lead's local server once it is up.
**Done when:** it prints a p50/p95 table.

---

## B6 — Clean-room README test   ~15 min   ⬜   (do this last, near 3:30)

Prove a judge can actually run our project. Open a **brand-new terminal** and follow your
own README **exactly as written** — no shortcuts, no knowledge from having built it.

```bash
cd /tmp && git clone <our repo> gridwise-test && cd gridwise-test
# now follow README step by step, literally
```

Every time you have to think "well obviously you also need to…", that is a **missing step**
— add it to the README. That instinct is exactly what earns the 10 points.

**Done when:** a fresh clone starts, `/health` returns `{"status":"ok"}`, and one sample
request succeeds — with zero undocumented steps.

---

## If you finish everything early

Tell the lead, then pick up (in this order):
1. More `paraphrases.json` entries — especially trickier `no_op` near-misses
2. Proofread the README aloud; fix anything ambiguous
3. Help rehearse the 3-minute video script (it is tie-break #1)

## If you get stuck for more than 10 minutes

Message the lead and move to the next task. **Do not sit blocked** — every task here is
independent, so skipping one never blocks another.
