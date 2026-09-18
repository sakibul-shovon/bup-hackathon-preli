# GridWise — Build Progress Board

**Owner of this file: LEAD (Dev A) only.** Dev B never edits this file — she ticks boxes in
`AGENT_TASKS_DEV2.md` instead, and the lead syncs status here. This keeps the board
conflict-free.

Canonical spec: `GRIDWISE_IMPLEMENTATION_PLAN (1).md` **V4**. Where this board and the plan
disagree, the plan wins.

---

## ⏱ START HERE

| Who | You are | Open this file | First command |
|---|---|---|---|
| **Dev A** | Lead engineer | `AGENT_TASKS_LEAD.md` | Task **L0** |
| **Dev B** | Teammate | `AGENT_TASKS_DEV2.md` | Task **B0** |

Neither of you needs to read the other's task file. They are designed to never overlap.

**Opening a NEW window partway through?** Don't hunt for which task you were on — both task
files have a "🔁 Resuming in a new window" prompt near the top. Paste that instead of a
specific task number; it reads the checkboxes below (or in `AGENT_TASKS_DEV2.md` for Dev B)
and picks up the first unfinished one itself.

---

## 🔒 THE ONE RULE THAT PREVENTS ALL CONFLICTS

> **Never create or edit a file you do not own.** Not "just a small fix". Not "it was
> one line". If you need a change in someone else's file, send them a message and keep
> working on something else.

Because ownership is disjoint, `git pull --rebase` can never produce a conflict. The moment
someone edits outside their column, that guarantee is gone.

### File ownership map

| Path | Owner | Notes |
|---|---|---|
| `app/config.py` | **A** | |
| `app/schemas.py` | **A** | |
| `app/main.py` | **A** | |
| `app/directives.py` | **A** | |
| `app/optimizer.py` | **A** | build in its own agent session |
| `app/validator.py` | **A** | build in a SEPARATE agent session — zero shared code with optimizer |
| `app/llm_interpreter.py` | **A** | |
| `app/guardrails.py` | **A** | |
| `app/sanitize.py` | **B** | signatures frozen in `AGENT_TASKS_DEV2.md` — A codes against them |
| `app/summary.py` | **B** | signature frozen — A codes against it |
| `tests/test_sanitize.py` | **B** | |
| `tests/test_summary.py` | **B** | |
| `tests/data/paraphrases.json` | **B** | |
| all other `tests/*.py` | **A** | |
| `tests/data/public_cases.json` | **A** | copied from `docs/`, never hand-edited |
| `scripts/run_public_cases.py` | **A** | |
| `scripts/fuzz.py` | **A** | |
| `scripts/latency_probe.py` | **B** | |
| `Dockerfile`, `.dockerignore`, `.gitignore`, `.env.example` | **B** | |
| `requirements.txt` | **B** | content dictated by plan §4; B types it, A reviews |
| `README.md` | **B** | 10 scored points — plan §16 is the outline |
| `PROGRESS.md` | **A** | |
| `AGENT_TASKS_LEAD.md` | **A** | |
| `AGENT_TASKS_DEV2.md` | **B** | ticks her own boxes |

### Git workflow

```bash
git pull --rebase        # before every push, always
git add <only your own files>
git commit -m "<task id>: <what>"
git push
```

Small commits, one per finished task. Never `git add -A` — it picks up files you don't own.

---

## 📊 Status

Legend: ⬜ not started · 🟡 in progress · ✅ done · 🔴 blocked

### Dev A — the spine

| ID | Task | Status | Done when |
|---|---|---|---|
| L0 | Repo skeleton + `config.py` + `schemas.py` + `/health` | ✅ | `curl /health` → `{"status":"ok"}`, `pytest` collects |
| L1 | `directives.py` + `test_directives.py` | ✅ | window/factor/reserve/merge tests green |
| L2 | `optimizer.py` (own session) | ✅ | solves; 24-var LP returns status 0 |
| L3 | `validator.py` (SEPARATE session) | ✅ | negative tests catch all 10 replay checks |
| L4 | `test_public_cases.py` — **THE ANCHOR** | ✅ | **10/10 replay-clean AND cost within 0.01 of reference** |
| L5 | `llm_interpreter.py` + key rotation + deadline | ✅ | `test_provider.py` green incl. rotation + degrade |
| L6 | `guardrails.py` | ✅ | per-note violation tracking works |
| L7 | `main.py` orchestration + degrade + salvage | ✅ | full pipeline 200s end-to-end |
| L8 | `test_precision.py` + `test_api.py` + `test_adversarial.py` | ⬜ | full suite green |
| L9 | `scripts/fuzz.py` + live paraphrase holdout | ⬜ | 100% replay-valid, misses investigated |
| L10 | Deploy + external smoke test | ⬜ | public URL answers from a different network |

### Dev B — support, docs, deploy artifacts

| ID | Task | Status | Done when |
|---|---|---|---|
| B0 | Dotfiles + `requirements.txt` + `Dockerfile` | ⬜ | `docker build` succeeds |
| B1 | `app/sanitize.py` + tests | ⬜ | `pytest tests/test_sanitize.py` green |
| B2 | `app/summary.py` + tests | ⬜ | `pytest tests/test_summary.py` green |
| B3 | `tests/data/paraphrases.json` (40+ entries) | ⬜ | valid JSON, 40+ entries, no sample-pack wording |
| B4 | `README.md` | ⬜ | all 13 sections from plan §16 present |
| B5 | `scripts/latency_probe.py` | ⬜ | prints p50/p95 against a URL |
| B6 | Clean-room README replay | ⬜ | fresh venv, quickstart works verbatim |

---

## 🕐 Sync points

Stop and talk for 3 minutes at each. Do not skip these — they are where integration bugs die.

| Time | What | Who |
|---|---|---|
| **0:20** | A confirms `config.py` constants + B confirms `requirements.txt` deps match plan §4 | both |
| **1:00** | B hands over `sanitize.py` + `summary.py` signatures; A wires them in | both |
| **2:00** | A's pipeline returns real 200s; B starts README against the REAL behavior, not the plan's | both |
| **2:50** | 🚨 **HARD STOP — deploy now regardless of state.** A perfect local system scores zero. | A leads |
| **3:20** | Record the video no matter what is unfinished (tie-break #1) | both |
| **3:45** | Final checklist (plan §21), repo public after deadline | A |

---

## 🚧 Blockers

Append here, newest first. Lead clears them.

| Time | Who | Blocker | Resolved? |
|---|---|---|---|
| | | | |

---

## ✅ Pre-submission gate (plan §21 — nothing ships until all of these are true)

- [ ] `pytest -q` fully green
- [ ] 10/10 public cases: replay-clean + cost within 0.01
- [ ] Five extra-field tolerance tests green (**F3 — a 400 here is a near-zero-score bug**)
- [ ] `test_precision.py` green at 8 dp / ε=1e-6 (**F2**)
- [ ] `initial < minimum` returns 422 and the optimizer was NOT modified (**F4**)
- [ ] No key set at all → `/optimize-energy` still returns **200**, never 500 (**F1**)
- [ ] Worst mocked ladder returns inside `LLM_DEADLINE_SECONDS + 2s` (**F5**)
- [ ] Pushed image manifest says **linux/amd64** (**F9**)
- [ ] Public URL answers `/health` + one sample case from a phone hotspot
- [ ] p95 < 5 s recorded
- [ ] No secret in repo, logs, responses, or image history
- [ ] README quickstart replayed in a clean shell
- [ ] Video ≤ 3:00 and accessible
