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
| L8 | `test_precision.py` + `test_api.py` + `test_adversarial.py` | ✅ | full suite green |
| L9 | `scripts/fuzz.py` + live paraphrase holdout | ✅ | 100% replay-valid, misses investigated |
| L10 | Deploy + external smoke test | ✅ | public URL answers from a different network |

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
| earlier | A | L10 blocker (local Docker verified, push/deploy pending credentials) | Resolved -- see below |
| now | A | L10 fully deployed: user provided VPS access (165.99.219.20, root) + real GROQ keys. Confirmed the box already runs syntax-carnival-website (separate docker-compose stack, ports 80/443/5433) -- left it completely untouched. Deployed gridwise-app as an isolated container on port 8000 in /opt/gridwise/repo. Set up push-to-deploy CI/CD via GitHub Actions (deploy key for the VPS to pull, separate keypair + repo secrets for Actions to SSH in). Verified externally: `curl http://165.99.219.20:8000/health` and all 10 public cases -- 10/10 exact match to reference, replay-clean, through the real deployed URL with the real model. Still open: uptime monitor, phone-hotspot test, p95 latency logged from outside (p95=3.3s was measured against localhost during the key sanity-check, not yet re-measured against the public URL), video. | Deploy done; monitor/phone-test/video outstanding |

---

## ✅ Pre-submission gate (plan §21 — nothing ships until all of these are true)

- [x] `pytest -q` fully green (493 passed, 19 skipped -- the live tier, which itself passed 19/19 under `-m live` with the real key)
- [x] 10/10 public cases: replay-clean + cost within 0.01 (verified against the live public URL with the real GROQ key -- diff 0.0000 on all 10)
- [x] Five extra-field tolerance tests green (**F3 — a 400 here is a near-zero-score bug**)
- [x] `test_precision.py` green at 8 dp / ε=1e-6 (**F2**)
- [x] `initial < minimum` returns 422 and the optimizer was NOT modified (**F4**)
- [x] No key set at all → `/optimize-energy` still returns **200**, never 500 (**F1**)
- [x] Worst mocked ladder returns inside `LLM_DEADLINE_SECONDS + 2s` (**F5**)
- [x] Pushed image manifest says **linux/amd64** (**F9** -- confirmed both on the local build and the VPS's native build)
- [ ] Public URL answers `/health` + one sample case from a phone hotspot -- answers from this machine's network; a literal phone-hotspot check needs the user
- [x] p95 < 5 s recorded (1.2 s, measured externally against the live public URL)
- [x] No secret in repo, logs, responses, or image history (also checked VPS container logs after real-key runs -- only `key_idx=`, never a key value)
- [ ] README quickstart replayed in a clean shell -- Dev B verified an earlier version (B6); the quickstart/example-response section was rewritten after that (real bugs fixed), not yet re-replayed clean
- [ ] Video ≤ 3:00 and accessible

## 🔔 DO NOT FORGET — right after the submission deadline

The Participant Guide requires the repo to stay **private during the event,
public after the deadline**. Docker fallback image is pushed and verified
(pull + run + /health all confirmed working) at
`ghcr.io/sakibul-shovon/bup-hackathon-preli:final` (also tagged `:latest`),
but **deliberately left PRIVATE for now**, same as the repo. Right after the
deadline, do BOTH of these (GitHub blocks the second one via API — it's a
manual UI action only):

1. Make the GitHub repo public.
2. Go to https://github.com/users/sakibul-shovon/packages/container/package/bup-hackathon-preli
   → **Package settings** → **Danger Zone** → **Change package visibility** → **Public**.

Without step 2, a judge's `docker pull` will get `unauthorized` even though
the repo itself is public -- confirmed by testing: making the package
"Public" in its own settings did NOT immediately unblock an anonymous pull
in this session (GitHub may also require the linked repo to already be
public before the package visibility change takes full effect, or there is
propagation delay -- re-test with `docker pull` after doing both steps).
