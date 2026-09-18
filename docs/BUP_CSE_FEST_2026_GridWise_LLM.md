# BUP CSE FEST 2026 HACKATHON
### *In association with Poridhi.io*

**BANGLADESH UNIVERSITY OF PROFESSIONALS**  
Mirpur Cantonment, Dhaka - 1216

---

# Participant Guide & Evaluation Rubric
### Online Preliminary Round

| Field | Details |
|---|---|
| **Round** | Online Preliminary |
| **Round Window** | 7:00 PM - 11:00 PM (4 hours) |
| **Required Service** | Deployed Public HTTP API |
| **Health Endpoint** | GET /health |
| **Primary Endpoint** | POST /optimize-energy |
| **LLM Requirement** | Mandatory for operator_notes interpretation |

> **PURPOSE:** Use this guide for participation, deployment, submission, and evaluation rules. The separate Problem Statement defines the GridWise challenge behavior, operator-note directives, schemas, and optimization rules.

---

## 01. About This Guide & Document Pack

This document explains how to participate, deploy, submit, and understand the evaluation for the LLM-assisted GridWise preliminary. It does not redefine the challenge itself.

The online preliminary round runs from 7:00 PM to 11:00 PM (4 hours).

> **IMPORTANT:** For operator_notes, supported directive types, structured adjustments, guardrails, request/response fields, battery rules, and exact challenge behavior, read the separate Problem Statement.

### Participant document pack

| Document | Purpose |
|---|---|
| Problem Statement | Defines the scenario, operator-note interpretation, supported directives, API schema, optimization rules, guardrails, and required outputs. |
| Participant Guide & Evaluation Rubric | Defines execution, deployment, repository policy, submission, scoring, penalties, and tie-break rules. |
| Public Sample Cases JSON | Provides worked input/output examples for local validation. Public cases are references, not the hidden judge set. |

### Inside this guide

| Section | Contents |
|---|---|
| 02 | Required Deliverables |
| 03 | Technical & Deployment Rules |
| 04 | LLM, Technology, Security & Repository Policy |
| 05 | Testing & Submission Checklist |
| 06 | Evaluation Model |
| 07 | Scoring Rubric |
| 08 | LLM & API Quality Metrics |
| 09 | Critical Violations & Penalties |
| 10 | Hidden Tests & Tie-Breakers |
| 11 | Final Quick Reference |

---

## 02. Required Deliverables

Submit one complete solution that the judging harness can evaluate without asking your team for setup help.

| Required item | Requirement | Notes |
|---|---|---|
| API service | Deploy one HTTP API service exposing both required endpoints. | Submit one service, not separate deployments. |
| GET /health | Readiness endpoint for the judging harness. | Must return the readiness response defined in the Problem Statement. |
| POST /optimize-energy | Main LLM interpretation + 24-hour optimization endpoint. | Must follow the exact request/response contract in the Problem Statement. |
| directive_interpretation | Return exactly one machine-checkable interpretation entry for every operator note, in note_index order. | Applicable notes use applies = true. Irrelevant notes use applies = false, directive_type = no_op, and structured_adjustment = null. |
| hourly_plan | Return the final 24-hour schedule after applying all valid directives. | The judge independently replays the schedule. |
| Source repository | Provide all source code and dependency/configuration files. | Repository timing and visibility must follow the official rulebook. |
| README.md | Provide an excellent, self-contained README that lets organizers run and test the solution locally without team assistance. | Include source setup, environment-variable names, model/provider, LLM role, guardrails, optimizer/solver, exact run command, health/API curl examples, public-sample test command, dependencies, and known limitations. Do not include secret values. |
| Docker fallback image | Submit a tested container image as a fallback execution path for organizers. | Provide a pullable registry reference with an exact tag or digest. The image must expose the documented service port, bind to 0.0.0.0, and must not contain baked-in secrets. |
| 3-minute solution video | Submit a maximum 3-minute video explaining the problem, architecture overview, and your solution approach. | Focus on technical clarity: problem understanding, LLM-to-guardrail-to-optimizer architecture, key implementation choices, and how the solution is run/tested. Production-quality editing is not required. |

### Submission package

| Item | Required submission | What to provide |
|---|---|---|
| 1 | Working public endpoint | Base URL reachable by the judge for GET /health and POST /optimize-energy. |
| 2 | GitHub repository | Repository created after question reveal; keep private during the event and make public after the submission deadline for evaluation. |
| 3 | README & configuration | Setup/run instructions, model/provider or local model identifier, required environment-variable names, solver/library usage, and sample request/response. |
| 4 | Docker fallback image (Public API URL Recommended) | Registry image reference (Docker Hub, GHCR, or equivalent) with exact tag/digest, required environment-variable names, exposed port, and one verified docker run command. Image must remain pullable during evaluation. |
| 5 | 3-minute architecture / solution video | MP4 upload or organizer-accessible link. Maximum 3 minutes. Explain the problem, architecture overview, and solution flow; show enough implementation detail for judges to understand how the LLM, guardrails, and optimizer work together. |

---

## 03. Technical & Deployment Rules

Keep the judging path exact, reachable, reproducible, and practical for repeated LLM-assisted hidden tests.

### Required judge access

- The judge must be able to call GET /health and POST /optimize-energy from the submitted base URL.
- No login, dashboard access, manual approval, VPN, or private-network access may be required for the judging endpoint.
- The service must accept JSON and return JSON using the exact endpoint names and fields defined in the Problem Statement.
- The submitted service must remain reachable throughout the evaluation window, including repeated LLM-backed requests.
- Test both endpoints from outside your development environment before submitting.

### Deployment & reproducibility rules

| Rule | Requirement |
|---|---|
| Platform choice | Teams may deploy on any reachable platform. Judging is based on behavior, accessibility, and reproducibility, not provider choice. |
| LLM availability | The language model used for operator_notes must be available during judging. Teams are responsible for keys, quota, rate limits, and provider availability. |
| Runtime training | Do not require long training or fine-tuning jobs during evaluation. |
| Deterministic validation | LLM output must pass the exact deterministic guardrails in the Problem Statement before it is applied to the optimizer, including directive type, note mapping, hours, applies semantics, and numeric ranges. |
| Local reproduction | The README must provide a copy-paste local quickstart from a clean environment: clone/pull, configure environment-variable names, install or pull image, start service, call /health, and run at least one public sample against /optimize-energy. |

---

## 04. LLM, Technology, Security & Repository Policy

LLM use for operator_notes is mandatory. Other implementation choices are open as long as the submitted system is valid, secure, reproducible, and compliant with the Problem Statement.

### Implementation policy

| Approach | Policy |
|---|---|
| Language-capable generative model | Required for interpreting operator_notes. Its structured interpretation must be part of the path that produces the optimization constraints. |
| Deterministic preprocessing / postprocessing | Allowed for normalization, JSON validation, guardrails, and applying structured directives. It may not replace the required language-model interpretation step. |
| Optimization libraries / solvers | Allowed, including linear programming, dynamic programming, constraint solving, or other practical optimization methods. |
| External model API or local model | Allowed. Teams may choose the provider/model, but must meet reliability and latency requirements and document the model/provider or local identifier used. |
| Hard-coded phrase matching as the sole interpreter | Not compliant. Hidden notes may paraphrase the same directive, and the language model must be part of the interpretation path. |
| AI used only for plan_summary or documentation | Does not satisfy the LLM requirement. The model must interpret operator_notes into directive_interpretation used by the optimizer. |

> **CANONICAL CONTRACT:** If this guide and the Problem Statement appear to disagree about operator-note directives, schemas, guardrails, battery behavior, or optimization validity, the Problem Statement is the canonical source.

### Security & repository requirements

- Do not commit API keys, tokens, .env files, passwords, or other secrets to the repository.
- Do not expose secrets, tokens, raw prompts containing secrets, stack traces, or sensitive values in logs or API responses.
- Use only the synthetic challenge data supplied by the harness; do not use live campus, utility, billing, or personal data.
- Create a new GitHub repository after the question is revealed and develop the round solution there. Keep it private during the event and make it public after the submission deadline for evaluation.
- AI coding assistants and public libraries/frameworks/APIs/SDKs are permitted under the official rulebook, but core architecture and logic should be the team's own work. Credit all external tools and dependencies in README.md.

> **EXTERNAL MODEL RESPONSIBILITY:** If your solution depends on a hosted model/API, your team is responsible for valid credentials, quota, cost, rate limits, and availability. Judges are not expected to repair an unavailable dependency. A local or backup model is allowed if it still satisfies the Problem Statement.

---

## 05. Testing & Submission Checklist

Run these checks before submitting. They combine operator-note interpretation, guardrails, directive application, optimization, deployment, and repository requirements.

| Check | What to verify |
|---|---|
| API | /health responds; /optimize-energy accepts the exact request schema and returns the exact response schema. |
| LLM interpretation | Every operator note produces exactly one directive_interpretation entry in note_index order with applies, directive_type, structured_adjustment, and explanation. |
| Guardrails & directives | Only supported directive types are emitted; no_op uses applies = false and null adjustment; all other directives use applies = true; hours are unique integers 0-23 in ascending order; numeric values are valid; relevant directives are applied before optimization. |
| Optimization | The 24-hour plan is valid first, then minimizes recalculated grid electricity cost after all organizer-ground-truth directives are applied. |
| Energy constraints | Demand, effective solar, battery bounds, rate limits, state transitions, directive-specific limits, and end-of-day neutrality are all respected. |
| Robustness | Malformed JSON, invalid structured input, LLM/provider errors, repeated requests, and unexpected valid numeric combinations do not crash the service. |
| Deployment | Both endpoints work from outside the development environment and remain reachable during evaluation. |
| Submission | Endpoint, public-after-deadline repository, excellent README/local quickstart, model/provider, environment-variable names, optimizer/solver, credited libraries, sample request/response, fallback Docker image, and 3-minute video are included. |
| Local reproduction | From a clean machine/environment, follow the README exactly and verify that the service starts, /health returns {"status":"ok"}, and at least one Public Sample Cases request succeeds without undocumented steps. |
| 3-minute video | Video is accessible to judges, is no longer than 3 minutes, and clearly explains the problem, architecture overview, solution approach, LLM/guardrail/optimizer flow, and how the system is executed/tested. |

> **REPOSITORY ACCESS:** Follow the official rulebook: create a new repository after question reveal, keep it private during the event, and make it public after the submission deadline for evaluation.

> **FINAL SUBMISSION CHECK:** Do not submit secret values in public fields or README.

---

## 06. Evaluation Model

The preliminary uses automated testing as the primary evaluation mechanism. The submitted video is not part of the base 100-point score and is reviewed only when teams finish with the same total score and a tie must be resolved.

> **PRIMARY EVALUATION - 100 POINTS:** Automated judge tests are used to score the core API behavior, LLM directive interpretation, directive application, optimization quality, schema correctness, performance, and reliability. Deployment/Docker and documentation are checked against fixed reproducibility criteria using the submitted artifacts. The 3-minute video does not contribute base points.

> **VIDEO TIE-BREAK REVIEW - NO BASE POINTS:** The 3-minute architecture/solution video is reviewed only when two or more teams finish with the same total score and a tie must be resolved, especially at a qualification or ranking boundary. Reviewers compare problem understanding, architecture clarity, the LLM -> deterministic guardrails -> optimizer flow, and run/testing explanation. If the tie still remains, the technical sub-score tie-break order in Section 10 is applied.

### Seven scoring categories

| # | Category | Points |
|---|---|---|
| 1 | LLM Directive Interpretation | 25 |
| 2 | Directive Application & Constraint Correctness | 25 |
| 3 | Optimization Quality | 10 |
| 4 | API Contract & Schema | 10 |
| 5 | Performance & Reliability | 10 |
| 6 | Deployment & Docker Fallback | 10 |
| 7 | Documentation & Local Reproducibility | 10 |
| | **TOTAL** | **100** |

> **IMPORTANT:** LLM interpretation and downstream application are scored separately. Correct extraction is not enough if the returned schedule does not obey the directive. Optimization credit is considered only after the affected hidden case is valid under organizer ground-truth directives and normal GridWise rules. The 3-minute video carries no base marks and is used only to resolve tied total scores.

---

## 07. Scoring Rubric

Detailed criteria for the seven-category, 100-point GridWise preliminary evaluation model.

| Category / Score / Stage | What it measures |
|---|---|
| **LLM Directive Interpretation** 25 pts · Automated | 25 = 5 relevance/no_op + 5 directive_type + 5 affected hours + 5 numeric values/required structured_adjustment shape + 5 paraphrase robustness across related hidden notes. Free-text explanation wording is not matched byte-for-byte. |
| **Directive Application & Constraint Correctness** 25 pts · Automated | 25 = 10 organizer-ground-truth directive application + 5 hourly energy balance/effective-solar validity + 5 battery transitions/bounds/rate limits + 5 action consistency/end-of-day neutrality/non-negative values. |
| **Optimization Quality** 10 pts · Automated | 10 = cost-quality score over optimization hidden cases. Invalid cases receive zero optimization credit. Valid cases are scored from organizer optimal cost versus recalculated team cost; see formula below. |
| **API Contract & Schema** 10 pts · Automated | 10 = 2 endpoints/status behavior + 2 request validation + 3 directive_interpretation schema/order/types + 3 hourly_plan/top-level response schema and scenario_id echo. |
| **Performance & Reliability** 10 pts · Automated | 10 = 2 health readiness + 3 p95 latency + 3 valid-request stability/failure rate + 2 controlled malformed/model-provider failure handling and secret safety. |
| **Deployment & Docker Fallback** 10 pts · Automated + Artifact Check | 10 = 3 live endpoint reachability + 4 working pullable Docker fallback image that reaches /health using the documented command + 2 clean startup/reproducibility from submitted instructions + 1 no judge debugging/manual code changes required. |
| **Documentation & Local Reproducibility** 10 pts · Structured Reproducibility Check | 10 = 3 clean local quickstart from a fresh environment + 2 environment/configuration/model-provider documentation + 2 public-sample test procedure and expected result + 1 LLM/guardrail/optimizer architecture explanation + 1 Docker pull/run fallback instructions + 1 dependencies, limitations, and secret-handling guidance. |

> **SCORING PRINCIPLE:** The system is judged as a pipeline: understand the note, validate the structured directive, apply it to the optimization, return a valid schedule, and then optimize cost. A cheap schedule built on a wrong or ignored directive does not score as a correct solution.

---

## 08. LLM & API Quality Metrics

These machine-checkable interpretation, operational, and API thresholds are used by the judge harness and reproducibility checks.

| Metric | Expected standard | Meaning |
|---|---|---|
| Interpretation coverage | Exactly one directive_interpretation entry for every operator_notes item, returned in note_index order 0..N-1. | Missing, duplicate, or out-of-order mappings are schema/interpretation failures. |
| Directive accuracy | applies, directive_type, required structured_adjustment shape, hours, and directive numeric values must match organizer ground truth within tolerance. | no_op must use applies = false and null adjustment; every other directive must use applies = true. |
| Paraphrase robustness | Equivalent hidden phrasings of the same rule should resolve to the same underlying directive. Time ranges use the Problem Statement whole-hour convention. | Paraphrase robustness is measured across related hidden cases; it is not a separate response field. |
| Downstream application | The final hourly_plan must satisfy every applicable organizer-ground-truth directive, including solar_reduction, minimum_battery_reserve, no_charge_window, no_discharge_window, and max_grid_window. | Correct extraction without correct scheduling is insufficient. |
| Health readiness | GET /health returns {"status":"ok"} within 60 seconds of service start. | Shows the service is ready before hidden tests begin. |
| Per-request timeout | POST /optimize-energy must complete within 30 seconds. | Responses beyond the timeout are treated as failures. |
| p95 latency | p95 <= 5s: 3/3 latency points; >5s to 15s: 2/3; >15s to 30s: 1/3; >30s: 0/3 and timed-out requests are failures. | Repeated LLM/API slowness reduces the Performance & Reliability score. |
| Failure rate | Valid requests should not return 5xx, invalid JSON, or no response. | The service must remain stable across repeated hidden cases. |
| Malformed input | Return a controlled error or safe failure; do not crash or invent an unsupported directive. | Bad input or bad model output should not take down the service. |
| Secret handling | No API keys, tokens, raw secret values, or sensitive stack traces in repo, logs, or responses. | Never leak credentials or sensitive configuration. |
| Time & factor normalization | hours must be unique integers 0-23 in ascending order. A window from 1 PM to 3 PM maps to [13,14]. For solar_reduction, factor is the usable fraction remaining: an 80% reduction means factor = 0.2. | These rules make hidden semantic extraction machine-checkable. |
| Numeric tolerance | Use absolute tolerance of 0.01 kWh or 0.01 BDT unless the official judge package specifies a stricter value. | Matches the canonical Problem Statement tolerance for floating-point comparisons. |
| Documentation & local reproducibility | README is self-contained and judges can reproduce the service locally from a clean environment using only the submitted repository and documented environment-variable names, including /health and at least one public-sample request. | Scored through fixed reproducibility criteria; undocumented setup steps, missing commands, or team intervention reduce credit. |
| Docker fallback image | Submitted image can be pulled and started with the documented command and reaches /health. Image contains no baked-in credentials. | Used as a fallback path if the hosted endpoint is unavailable or for reproducibility verification. |
| 3-minute video | Accessible, <= 3:00, and clearly explains the problem, architecture overview, solution approach, LLM -> deterministic guardrails -> optimizer flow, and how the submission is run/tested. | Tie-break only. The video is not part of the base 100-point score and is reviewed only when teams have the same total score. |

> **OPTIMIZATION SCORE:** min(1, organizer_optimal_cost / recalculated_team_cost). Optimization Quality = 10 x the average quality_ratio across all optimization hidden cases. If organizer_optimal_cost and recalculated_team_cost are both within numeric tolerance of 0, quality_ratio = 1. If organizer_optimal_cost is within tolerance of 0 but team cost is above tolerance, quality_ratio = 0.

> **MACHINE-CHECKED INTERPRETATION:** Hidden operator notes have organizer ground truth for relevance, directive type, affected hours, and required numeric values. Free-text explanation wording is not judged byte-for-byte.

---

## 09. Critical Violations & Penalties

A low-cost schedule is not acceptable if it misunderstands or violates an applicable operator directive, or if it breaks the underlying GridWise energy rules.

| Violation | Penalty | Explanation |
|---|---|---|
| Required LLM absent from operator-note interpretation path, or AI used only for plan_summary/documentation | Fails the mandatory challenge requirement; not eligible for the final preliminary shortlist | Automated and artifact verification may inspect the repository/architecture to confirm that a language-capable generative model directly produces the structured operator-note interpretation used by the optimizer. |
| Relevant note interpreted incorrectly or marked no_op | Interpretation credit lost for the affected note/case | The judge compares the structured interpretation against organizer ground truth. The schedule is still checked separately against the true directive. |
| Applicable ground-truth directive not reflected in hourly_plan | Affected hidden case invalid for directive-application scoring; no optimization credit for that case | The judge replays the plan using the true hidden directive, not only the team-reported interpretation. |
| Energy-balance failure or unmet hourly demand | Affected hidden case treated as invalid; no optimization credit | Every hour must satisfy the Problem Statement energy-balance equation within tolerance. |
| Battery bound, transition, charge-rate, or discharge-rate violation | Affected hidden case treated as invalid; no optimization credit | The judge independently replays battery state hour by hour. |
| Effective-solar overuse or impossible/negative energy values | Affected hidden case treated as invalid; no optimization credit | solar_reduction changes available solar before the schedule is checked. |
| no_charge_window, no_discharge_window, minimum reserve, or max_grid_window violation | Affected hidden case treated as invalid; no optimization credit | Applicable directive constraints are hard operational rules. |
| End-of-day battery energy does not return to initial level | Affected hidden case treated as invalid; no optimization credit | Battery neutrality prevents using starting energy as a free one-time source. |
| Reported totals disagree with hourly_plan or repeated critical invalidity | Recalculation / scoring deduction; repeated failures may block qualification eligibility | hourly_plan is the source of truth for totals and validity. |

> **GROUND TRUTH BEFORE COST:** The judge first checks the organizer ground-truth directive, its downstream application, and the normal GridWise constraints. Only then is optimization quality scored for that hidden case.

---

## 10. Hidden Tests & Tie-Breakers

Public examples teach the contract. Hidden tests determine whether the full LLM-to-optimizer pipeline generalizes across unseen language and energy conditions.

### Hidden tests

- The exact hidden case list, wording, distribution, and expected answers will not be published.
- Each valid hidden scenario follows the Problem Statement and contains 1-3 synthetic operator notes. Each note maps to exactly one supported directive type or no_op; hidden scoring notes do not require unpublished directive types.
- The same underlying directive may be paraphrased with different wording, whole-hour time expressions, percentages, or equivalent numeric descriptions. Teams should not hard-code public phrases.
- Hidden cases also vary demand, solar, tariff, battery state, reserve/rate limits, and directive combinations. Organizer valid scoring scenarios are feasible and do not require mutually contradictory hard directives. Equivalent valid optimal schedules are accepted; judging is based on interpretation ground truth, directive application, validity, and recalculated cost.

### Tie-break order

| Priority | Tie-breaker | Why it matters |
|---|---|---|
| 1 | 3-minute Architecture & Solution Video | Used only after teams have the same total score. Reviewers compare problem understanding, architecture clarity, solution flow, and run/testing explanation. |
| 2 | Directive Application & Constraint Correctness | If the video does not separate the tie, stronger correctness against ground-truth directives and GridWise constraints ranks higher. |
| 3 | LLM Directive Interpretation | Better semantic extraction across paraphrases separates systems that genuinely understand unseen notes. |
| 4 | Optimization Quality | Among otherwise tied valid solutions, stronger cost quality separates teams. |
| 5 | API/schema validity | Exact machine-checkable contracts make evaluation reliable and reproducible. |
| 6 | Reliability and deployment stability | A strong pipeline must remain reachable and respond within judging limits. |
| 7 | Documentation & local reproducibility | Clear copy-paste setup, public-sample validation, model/solver disclosure, and Docker fallback instructions matter at the cutoff. |
| 8 | Exceptional engineering / verification | Robust guardrails, fallbacks, caching, testing, and implementation quality may be considered if a tie still remains. |

---

## 11. Final Quick Reference

Recommended priority order and final pre-submit checklist for the LLM-assisted GridWise preliminary.

### Recommended priority

| Priority | Focus |
|---|---|
| 1 | Exact API & JSON Contract |
| 2 | LLM Operator-Note Interpretation |
| 3 | Deterministic Guardrails |
| 4 | Directive Application & Energy Correctness |
| 5 | Optimization Quality |
| 6 | Reliability, Deployment & Docker Fallback |
| 7 | Documentation & Local Reproducibility |
| 8 | 3-minute Video (Tie-break Readiness Only) |

### Final pre-submit checklist

- [ ] GET /health is reachable and returns the expected readiness response.
- [ ] POST /optimize-energy is reachable externally and accepts 1-3 operator_notes with the exact Problem Statement schema.
- [ ] Every operator note produces exactly one directive_interpretation entry in note_index order; no_op uses applies = false + null adjustment, and all other directives use applies = true with the exact required structured_adjustment shape.
- [ ] LLM output is deterministically guardrailed before optimization; directive hours are unique integers 0-23 in ascending order, numeric values are valid, and invalid model output cannot silently invent constraints.
- [ ] hourly_plan obeys the organizer-ground-truth directives plus energy balance, effective-solar, battery, rate-limit, grid-cap, and end-of-day rules.
- [ ] total_grid_kwh, total_cost_bdt, and peak_grid_kwh match values recalculated from hourly_plan.
- [ ] README is self-contained and has a clean local quickstart: setup, required environment-variable names, model/provider or local model, LLM role, guardrails, optimizer/solver, dependencies, exact run command, /health test, /optimize-energy curl/sample test, known limitations, and no committed secrets.
- [ ] Repository was created after question reveal, remains private during the event, is made public after the deadline, the submitted endpoint remains reachable for evaluation, and all required fallback/video links remain accessible through the judging window.
- [ ] Fallback Docker image is submitted with an exact pullable tag/digest; documented docker pull/run commands work, /health becomes ready, the documented port is exposed, and no secrets are baked into the image.
- [ ] Required 3-minute video is accessible and explains the problem, architecture overview, solution approach, LLM -> deterministic guardrails -> optimizer pipeline, and how organizers can run/test the submission. The video is used only as a tie-break when teams have the same total score.
