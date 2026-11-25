# AlphaProject — PBI backlog

This is the delivery backlog for the lab. Entries are ordered by readiness; status is current for
this workspace, not for earlier experiment workspaces.

## Index

| PBI | Title | Status | Depends on |
|---|---|---|---|
| 0 | Isolated test-database runner | **complete** | — |
| 1 | Add priority to demo items | ready | 0 |
| 2 | Add Conversation storage and CRUD API | ready | 0 |
| 3 | Add synchronous conversation triage | ready after 2 | 2 |
| 4 | Add the Conversations UI | ready after 3 | 2, 3 |
| 5 | Content-free triage usage accounting | deferred | provider boundary |
| 6 | Asynchronous triage | deferred | measured need |
| 7 | Owner-scoped conversation search and pagination | candidate | 2 |
| 8 | Export an owned conversation | candidate | 2 |
| 9 | Structured feedback on triage results | candidate | 2, 3 |
| 10 | Deterministic delivery-plan preflight validator | not applicable here | AgenticLab-side scope |

## Conventions for every PBI

- Before implementation, list the main Python/framework concepts in plain language and identify the
  existing files that demonstrate them.
- Keep each approved slice to one major new concept at a time; explain the
  request → validation → persistence → response path before adding abstractions.
- Run backend tests only with `bash backend/scripts/test-isolated.sh`. Never use
  `backend/scripts/test.sh` against the application database.
- End each PBI with a short learning review: what changed, how the data/request flows through it,
  what the tests prove, what remains uncertain, and what you want to practise next.
- Distinguish application source changes from local DB state, generated output, and AgenticLab
  workspace state. Only source/docs intended for the app repository become application commits.

No entry below is implementation authorization. Approve a bounded `/plan` before each PBI.

---



---

## PBI 0 — Isolated test-database runner

**Status:** complete — see the run record in this section.

### Learning outcomes

- How PostgreSQL databases and roles differ from schemas, and why a separate database — not a
  separate schema — is the simplest reliable isolation for this stack.
- How configuration flows: `.env` → `pydantic-settings` `Settings` → `create_engine` → the `engine`
  that `conftest.py` imports at module load, and why a process-level environment override is what
  actually redirects it.
- Why pytest's `session`-scoped autouse fixture in `backend/tests/conftest.py` makes the target
  database a safety-critical choice rather than a detail.
- How Alembic treats migrations as the schema source of truth for a freshly created database.
- Shell hygiene for destructive scripts: `set -euo pipefail`, `trap` cleanup, and refusing rather
  than guessing.

### Problem

`backend/tests/conftest.py` imports `engine` from `app.core.db`, which is built from
`settings.DATABASE_URL`. The session-scoped fixture calls `init_db(session)` and then deletes all
`Item` and `User` rows. `backend/scripts/test.sh` runs pytest with no database override, so running
the suite writes to and then empties whatever database `DATABASE_URL` names — on this workspace, the
lab application database.

The upstream template ships no isolated runner. Every later PBI that adds tests inherits this
hazard, so it is fixed first.

### User story

As the developer of this lab, I want the backend test suite to run against a disposable database, so
that running tests can never modify the application data in my local stack.

### Acceptance criteria

1. `backend/scripts/test-isolated.sh` exists, is executable, and runs the full backend suite.
2. It creates a database whose name contains `test` with a per-run suffix, applies
   `alembic upgrade head` to it, runs `pytest tests/`, and exits with pytest's status.
3. **Guard:** it refuses to run, with a clear message and non-zero exit, when the resolved target
   database name does not contain `test`, or when it equals the database named by the application
   `DATABASE_URL`. It must never fall back to the application database.
4. **Cleanup:** the disposable database is dropped on success, on failure, and on interrupt
   (`trap`), verified by the script itself reporting the drop or by the caller checking that no
   `app_test_*` database remains.
5. **Non-destructiveness:** running the suite leaves the application database unchanged. Verified by
   recording `users`/`items` row counts before and after.
6. No new third-party dependency is added; the script uses `psql` from the running compose `db`
   service (or `uv run` with psycopg already present) and the existing `uv`/`alembic` tooling.
7. The script never prints a password or the full `DATABASE_URL`; failures name the problem without
   echoing secret values.
8. A short usage note is added to the repository documentation where test commands are described.

### Proposed scope

- `backend/scripts/test-isolated.sh` (new)
- `backend/README.md` (one usage paragraph, if that is where test commands are documented)

Explicitly out of scope: changing application code, altering `conftest.py`'s fixtures, adding a
pytest plugin, containerising the test run, or adding CI. If the script cannot work without touching
`conftest.py`, stop and report the reason instead of changing it.

### Verification plan

- `bash backend/scripts/test-isolated.sh` → suite passes, exit 0.
- Before/after: `select count(*) from "user"` and `from item` on the application database are
  identical.
- Guard: run with `DATABASE_URL` pointing at the application database → script refuses, exit
  non-zero, message names the rule.
- Cleanup: after a normal run and after a forced failure, no `app_test_*` database remains.
- `docker compose exec db psql -l` shows no leftover disposable database.

### Risks and stop conditions

- Dropping the wrong database would be destructive. The guard is the mitigation; if the target name
  cannot be parsed with certainty, the script must exit rather than proceed.
- Local Postgres already holds the lab application data; the verification step above is a
  pre-condition, not a formality.
- Stop if the compose database service is not healthy, or if creating a database requires
  credentials the workspace does not hold.

### Run record — 2026-11-25

- **Status:** complete. Committed as `49649b1` (`backend/scripts/test-isolated.sh` + `backend/README.md`).
- **Result:** 58 backend tests passed on a disposable database; application database remained
  `users=2, items=0`; both guards refused with exit 1; no `app_test_*` database remained after the run.
- **Measured session (corrected with declared windows):** 3,205 s window, 84 tool calls, 7 retrieval
  calls (2 applicable, 5 no_match), 3.96M tokens; free model so cost was unavailable. Four
  action-scope blocks (`chmod +x` attempts outside approved scope) and one knowledge-shell block
  occurred; none broke the task. Earlier figures used whole-session aggregates and were superseded.
- **Knowledge:** two handoff candidates were staged and promoted with explicit user approval:
  `env-override-redirects-pytest-and-alembic` and `no-xtrace-with-database-url`.
- **Workflow finding (see also `AgenticLab-v5/DEV-LOG.md` and `C04.2`):** checkpoint disposition B
  was chosen before the implementation log was written. Deleting the checkpoint removed the gate's
  authorization source, so the log write was correctly refused. The operator wrote the 55-line log
  from verified evidence instead. The complementary failure was observed earlier: keeping the
  checkpoint leaves the gate armed with a stale scope and blocks unrelated default work until a
  restart. **Proposed, not applied:** in `prompts/delivery/implement.md`, write the implementation
  log *before* asking A/B, so A/B only controls transient checkpoint retention. No payload change
  was made during this PBI.

---


PBI 1–10 below are adapted from the archived exp4 backlog; the full inherited text is kept in `Archive/PBIs-exp4-inherited-full.md`.

---

## PBI 1 — Add priority to demo items

**Status:** ready. Not implemented in this repository (inherited from exp4 as a reference implementation).

### Learning outcomes
- Trace a Python `StrEnum` and SQLModel field through request/response schemas and a database migration.
- Understand how OpenAPI generation produces the frontend TypeScript client types.
- Follow a value through the React form, API request, persistence, and table display.

### User story
As a user, I want to assign a priority to an item, so that I can distinguish items that need attention sooner from those that can wait.

### Implemented contract
Use `low`, `normal`, and `high`, with `normal` as the default. Unknown values are rejected by the request schema.

### Acceptance criteria
- Persist the priority on the SQLModel `Item` table with a migration; existing items receive the agreed default.
- Validate priority on create and update; reject unknown values rather than silently coercing them.
- Return priority in the item API schemas while preserving current owner scoping and superuser behavior.
- Regenerate the OpenAPI frontend client after the API schema changes.
- Add priority selection to the item create/edit flow and display it in the item list.
- Cover defaulting, valid values, invalid values, persistence, and UI behavior with focused backend and frontend tests.
- Database tests use an isolated disposable test database; never a shared development or production database.
- Do not change unrelated authentication, item ownership, or deployment behavior.

### Run record — 2026-11-25

- **Status:** complete. Code changes are in the application working tree, ready to commit.
- **Result:** backend suite 63/63 on the isolated runner, 5 focused priority tests, single Alembic
  head `7b3d9e2f1a4c`, client regenerated with the `ItemPriority` union, `bun run build` passed,
  Playwright items suite 11/11 on a disposable database at ports 8100/5273, and an Orca browser
  accessibility snapshot showed High/Low/Normal priority values.
- **Review correction:** the migration was first written as
  `<new-revision>_add_item_priority.py`, because the approved checkpoint used that literal
  placeholder path. Review renamed it to `7b3d9e2f1a4c_add_item_priority.py` to match the Alembic
  convention used by every existing migration. Alembic reads the revision id inside the module, so
  history and the applied database state were unchanged. This is a naming-governance finding for
  plan generation, not an application defect.
- **Browser limitation:** `screenshot` failed in the browser runtime; the interactive snapshot was
  used as visual evidence. Recorded, not repaired.
- **Incident:** the first e2e attempt collided with the lab servers on ports 8000/5173 and wrote test
  rows into the application database (`users` 2 → 10, `items` 0 → 3). The agent stopped rather than
  deleting rows or processes. After explicit authorization, it stopped the lab servers, reran on
  alternate ports, dropped the disposable DB, and left the application rows as evidence.
- **Recovery:** the lab servers were restarted afterwards; backend :8000 and frontend :5173 both
  returned HTTP 200 and the application database was healthy. Do not treat the absence of the UI
  during that interval as a database failure.
- **Measured session (corrected with declared windows):** 29,608 s window (includes a long blocked
  interval), 120 tool calls, 10 retrieval calls (4 applicable, 6 no_match), 15.5M tokens; free model
  so cost was unavailable. Gate blocks: 2 action-scope, 2 knowledge-shell; none broke the task.
  Earlier whole-session figures were superseded.
- **Knowledge:** both checkpoint handoffs were staged and promoted with explicit user approval:
  `client-generation-script-side-effects` and `playwright-compose-targets-app-database`.
- **Workflow finding:** following the lab instruction, the implementation log was written **before**
  checkpoint disposition, so choosing B caused no gate conflict. This is the second data point for
  the deferred prompt-ordering fix in `AgenticLab-v5` `C04.2` (first: PBI 0's failure when B preceded
  the log). **Fix remains proposed, not applied.**
- **Post-run application-state finding:** after the servers were restarted, the UI failed with what
  Axios displayed as a CORS error. The real cause was in `/tmp/alpha-backend.log`:
  `psycopg.errors.UndefinedColumn: column item.priority does not exist`. The application database was
  still at Alembic revision `fe56fa70289e`; PBI 1's e2e run had migrated only its disposable database.
  Applying `alembic upgrade head` to the lab database (`fe56fa70289e` → `7b3d9e2f1a4c`) fixed it.
  Verified: `item.priority` exists with default `normal`, authenticated `GET /api/v1/items/` returns
  HTTP 200 with priority values, and a GET with `Origin: http://localhost:5173` succeeds with CORS.
  **Lesson:** a PBI that changes schema must explicitly migrate the running lab database after the
  isolated/e2e validation, or the browser will test stale application state. No code defect; this is
  workspace-state hygiene.
- **Next safe action:** commit the application changes; start PBI 2 only after that.

---

## PBI 2 — Add Conversation storage and CRUD API

**Status:** ready. Not implemented in this repository.

### Recommended learning slices
1. **Model and migration:** define a minimal owned Conversation model, its SQLModel/Pydantic schemas, and a migration; add model/schema tests.
2. **Basic API:** implement create and list/get endpoints using the existing FastAPI dependency/session patterns; test response schemas and authentication.
3. **Ownership and lifecycle:** add update/delete, owner-isolation tests, transcript limits, and the agreed behavior when an owner is deleted. Keep privacy/retention decisions explicit.

Review and understand each slice before proceeding to the next; avoid adding transcript workflows or triage to PBI2.

### Learning outcomes
- Learn SQLModel tables/relationships, Alembic migrations, Pydantic schemas, FastAPI dependencies, and session-based CRUD.
- Understand authenticated owner scoping and test it with two distinct users.

### User story
As a signed-in user, I want to create and manage conversations that I own, so that I can use them in later triage workflows.

### Acceptance criteria
- Add a `Conversation` model with a required owner, title, transcript text, and created/updated timestamps.
- Define and enforce a documented maximum size for title and transcript before implementation; do not accept unbounded transcript input.
- Provide authenticated create, list, get, update, and delete endpoints using the project's established API patterns.
- Scope list and item operations to the authenticated owner. Cross-user access is denied; do not assume that superuser status grants access to private transcripts without an explicit product decision.
- Decide and document what happens to a user's conversations when that user is deleted; implement the approved retention/deletion behavior.
- Add an Alembic migration and focused API/service tests for CRUD, validation, ownership isolation, and deletion behavior.
- Use an isolated disposable test database. Do not read `.env`, inspect an existing database, or run migrations against a shared database.
- Do not log transcript text or include it in error messages.

### Run record — 2026-11-25

- **Status:** complete. Code changes are in the application working tree, ready to commit.
- **Result:** single Alembic head `8c1f4a2d6b70`; 18 conversation-focused tests and 81 full isolated
  backend tests passed; client regenerated (`ConversationsService`) and `bun run build` passed;
  Playwright items regression 11/11 on a disposable stack at ports 8100/5273.
- **Lab database:** migrated additively from `7b3d9e2f1a4c` to `8c1f4a2d6b70`; `conversation`
  table created with `title VARCHAR(255)`, `transcript VARCHAR(20000)`, cascade FK. Existing rows
  preserved (`users=10, items=4` at review).
- **Behaviour:** owner-only CRUD; superusers denied cross-user access; 404 for missing resources;
  oversized transcript rejected with fixed 422 and no transcript echo; conversation rows cascade
  with owner deletion.
- **Measured session:** 445 s, 68 tool calls, 7 retrieval calls (1 applicable, 6 no_match),
  11.0M tokens, $0.0868, model `deepseek-v4.1-flash` (first paid-model lab PBI). Gate blocks: 2
  action-scope, 1 knowledge-shell, 1 sensitive-path; none broke the task.
- **Knowledge:** one handoff promoted after explicit approval:
  `fastapi-422-echoes-submitted-input`. Pending queue empty. Retrieval of that record was relevant to
  the no-transcript-echo requirement and is the strongest knowledge-use signal so far in the lab.
- **Workflow:** implementation log written before checkpoint disposition; B then deleted the
  checkpoint without a gate conflict. The prompt-ordering fix remains proposed, not applied.
- **Naming:** the migration was created with the correct Alembic filename
  `8c1f4a2d6b70_add_conversation.py`; the PBI 1 placeholder lesson was applied.
- **Next safe action:** commit the application changes; start PBI 3 only after that.

---

## PBI 3 — Add synchronous conversation triage

**Status:** depends on PBI 2. Not implemented in this repository; live provider integration remains excluded.

### Recommended learning slices
1. **Contract and fake client:** define the triage result schema and a deterministic fake-client interface; test valid and invalid results without an API route or provider.
2. **Service behavior:** implement validation, bounded retry/error handling, and persistence rules against fake responses.
3. **Endpoint integration:** add the authorized route for an owned conversation and test owner isolation and stored results. Keep this synchronous; do not add queues or live provider calls.

### Learning outcomes
- Learn Python interfaces/protocols and dependency injection by comparing the fake client with the service boundary.
- Practice Pydantic validation, error handling, and testing failure cases without external services.

### User story
As a signed-in user, I want to request a structured triage of a conversation I own, so that I can understand its main intent and a suggested next action.

### Acceptance criteria
- Add `POST /conversations/{id}/triage`; authorize access using the conversation owner rules from PBI 2.
- Put triage behind a small injectable client/interface. The initial implementation and tests use a deterministic fake client; no external LLM call, provider credential, or paid request is made.
- Validate the result with a Pydantic schema containing `summary`, `intent`, `sentiment`, and `next_action`; define allowed values and size limits before implementation.
- Persist the validated result and a triage timestamp on the owned conversation; define whether a later request replaces or versions the prior result.
- Handle malformed JSON, missing fields, invalid enum values, timeout, and provider errors. Any retry policy must be bounded (at most one retry) and tested; after that, return a safe error without storing an invalid result.
- Tests use fake responses and verify owner isolation, validation failures, retry limits, and persistence without a live provider.
- Never log transcripts, prompts, model output, secrets, or credentials. A live provider integration requires a separate PBI and explicit provider/privacy/cost approval.

### Run record — 2026-11-25

- **Status:** complete. Code changes are in the application working tree, ready to commit.
- **Result:** single Alembic head `4a7c2b9d1e63`; triage helper tests and full isolated backend suite
  passed; client regenerated; build passed. Lab database migrated additively with nullable triage
  columns on `conversation`, no row loss.
- **Behaviour:** owner-only triage (403 for non-owner and superuser, 404 for unknown conversation);
  bounded one retry/two attempts across malformed JSON, missing fields, invalid enums, timeout, and
  provider errors; 504 for repeated timeouts and 502 otherwise; invalid results never stored; prior
  results preserved on failure; transcript never logged or echoed.
- **Measured session:** 459 s, 60 tool calls, 5 retrieval calls (2 applicable, 3 no_match), 14.4M
  tokens, $0.0700, model `deepseek-v4.1-flash`. Gate blocks: 2 action-scope; none broke the task.
- **Knowledge:** one new verified handoff was staged and promoted with explicit user approval:
  `triage-client-injected-via-fastapi-dependency`. Pending queue empty. Retrieval and promotion
  happened as part of implementation, with no workflow ceremony.
- **Workflow:** implementation log written before checkpoint disposition; B then deleted the
  checkpoint without a gate conflict. The prompt-ordering fix remains proposed, not applied.
- **User judgement (recorded as such, not as a measurement):** the user reported a measurable
  qualitative difference from earlier prototype phases — less friction, more organic knowledge
  retrieval and promotion, and faster progress from `/plan` to `/implement`. This aligns with the
  retrieval, promotion, and gate-block data but has no same-task plain-Pi baseline.
- **Next safe action:** commit the application changes; start PBI 4 only after that.

---

## PBI 4 — Add the Conversations UI

**Status:** depends on PBI 3. Not implemented in this repository.

### Learning outcomes
- This is primarily a TypeScript/React learning slice; connect UI actions to the generated API client and existing TanStack Query patterns.
- Keep frontend acceptance separate from backend/API correctness so failures are easier to locate.

### User story
As a signed-in user, I want to create, find, and review my conversations and their triage results in the web interface, so that I can use the workflow without calling the API manually.

### Acceptance criteria
- Add a Conversations route with a list and a detail view, scoped to the signed-in user through the API.
- Provide a form to create a conversation and validate the agreed title/transcript limits before submission.
- Provide clear loading, empty, success, and error states for list, create, detail, and delete/update operations that are included in the approved scope.
- Add a “Run triage” action for an owned conversation; show pending/loading and failure states, then display the validated summary, intent, sentiment, and next action.
- Use the generated API client and TanStack Query patterns; regenerate the client when the backend OpenAPI schema changes.
- Add focused frontend tests for form validation, the main list/detail flow, and triage loading/error/result states without starting the application or requiring a live model provider.
- Do not expose another user's conversation in routes, caches, or UI state.

### Run record — 2026-11-25

- **Status:** complete. Code changes are in the application working tree, ready to commit.
- **Result:** `bun run build` and lint passed; Playwright `conversations.spec.ts` + `items.spec.ts`
  **18/18** on a disposable stack at ports 8100/5273. The first run failed 3 tests because the list
  route had no `<Outlet />` for nested detail; fixed and reran clean. One unrelated items
  “Page crashed” flake in that first run passed on rerun.
- **Scope discipline:** frontend-only; no backend, client, auth-handler, dependency, or database
  migration change. No leftover disposable databases; app rows unchanged (`users=10, items=4,
  conversations=0`).
- **Privacy:** a second user opening another user's conversation URL lands on `/login` via the
  global 403→logout behaviour; no title or transcript rendered. This is existing global behaviour,
  documented as a finding, not changed.
- **Measured session:** 316 s, 54 tool calls, 5 retrieval calls (2 applicable, 3 no_match), 14.4M
  tokens, $0.0687, model `deepseek-v4.1-flash`. No gate blocks.
- **Knowledge:** one handoff staged and promoted with explicit user approval:
  `ui-treats-403-as-logout`. Pending queue empty.
- **Workflow:** implementation log written before checkpoint disposition; B then deleted the
  checkpoint without a gate conflict. The prompt-ordering fix remains proposed, not applied.
- **Next safe action:** commit the application changes; start PBI 5 only after that.

---

## PBI 5 — Add content-free triage usage accounting

**Status:** deferred — needs an approved provider boundary.

### User story
As an administrator, I want to review aggregate triage usage and latency without seeing conversation content, so that I can monitor cost and performance.

### Acceptance criteria
- Define the recorded fields before implementation: timestamp, provider/model identifier, outcome/status, latency, and input/output token counts when supplied by the client.
- Record unknown token counts as unavailable; do not estimate them silently.
- Never store transcripts, prompts, model output, credentials, or other raw content in usage records.
- Keep usage access admin-only and separate from user conversation access.
- Add tests proving usage records contain metadata only, access is authorized, and failures do not block or corrupt conversation data.
- Start with fake client metadata in tests. Live-provider accounting and any provider-specific billing semantics require a separately approved integration decision.
- Defer an admin usage UI until the persisted usage contract and access rules are validated.

---

## PBI 6 — Consider asynchronous triage

**Status:** deferred — needs a measured latency or reliability need.

### User story
As a user, I want long-running triage to complete reliably in the background, so that I can continue using the application while it runs.

### Acceptance criteria
- First measure the synchronous flow and document why a background job is needed; do not add queue infrastructure speculatively.
- Select and approve the job mechanism, persistence model, retry limits, idempotency behavior, and failure/recovery semantics before implementation.
- Represent triage state as `pending`, `done`, or `failed`, scoped to an authorized conversation owner.
- The UI polls or refreshes status without duplicate submissions, unbounded requests, or leaking another user's status.
- Tests cover successful completion, terminal failure, retry bounds, duplicate requests, and owner isolation.
- Any new service/dependency or deployment change requires a separate scope and validation plan.

---

## PBI 7 — Add owner-scoped conversation search and pagination

**Status:** candidate — not approved for implementation.

**C03 evaluation marker for its first plan/implement run:** `C03-EVAL-ID: EXP4-C03-PBI7-001`. Include this exact marker in the explicit `/plan` task context to opt into one sanitized evaluation card under the approved plan scope; the marker does not authorize implementing this PBI.

### User story
As a signed-in user with many conversations, I want to search and navigate my conversation list, so that I can find a specific conversation without loading an unbounded list.

### Candidate acceptance criteria
- Add bounded, owner-scoped title search; transcript full-text search is out of scope unless separately approved.
- Use the existing `skip`/`limit` API contract or propose a bounded cursor alternative; define maximum page size and deterministic ordering before implementation.
- Ensure both the filtered result count and page results are scoped to the authenticated owner.
- Update the Conversations list UI with search, pagination, loading, empty, and error states; reset pagination when the query changes.
- Add backend tests for filtering, pagination boundaries, stable ordering, and cross-owner isolation, plus focused UI tests.
- Do not log raw search text or return another user's conversations.

---

## PBI 8 — Export an owned conversation

**Status:** candidate — not approved for implementation.

### User story
As a signed-in user, I want to download a copy of a conversation I own, so that I can keep or move my data outside the application.

### Candidate acceptance criteria
- Export one conversation at a time in a documented JSON format, including only explicitly selected conversation fields and current triage metadata.
- Require ownership authorization; cross-user access follows the existing 403/404 policy.
- Bound export size and use a safe download filename/content type; never log transcript or triage content.
- Provide a UI action and clear loading/error behavior.
- Add tests for format, size limits, ownership isolation, and absence of database mutation.
- Bulk export, import, external storage, and scheduled retention are out of scope.

---

## PBI 9 — Capture structured feedback on triage results

**Status:** candidate — not approved for implementation.

### User story
As a signed-in user, I want to mark whether a conversation's current triage was useful, so that I can distinguish reviewed results from unreviewed ones and inform later product decisions.

### Candidate acceptance criteria
- Allow feedback only for the current triage result on a conversation owned by the caller; start with controlled values such as `helpful` and `not_helpful`, not free text.
- Define how feedback relates to the triage result timestamp/version and whether transcript edits or re-triage clear prior feedback before implementation.
- Display and update the feedback in the conversation detail UI without implying a live model or changing the triage result.
- Test ownership, missing/stale triage, feedback replacement/clearing behavior, and UI states.
- Do not send feedback or conversation content to an external provider; any aggregate usage reporting remains under the separate PBI 5.

---

## PBI 10 — Add deterministic delivery-plan preflight validator

**Status:** candidate — not approved for implementation.

**C03 evaluation marker for its first plan/implement run:** `C03-EVAL-ID: EXP4-C03-PBI10-001`. Include this exact marker in the explicit `/plan` task context to opt into one sanitized evaluation card under the approved plan scope; the marker does not authorize implementing this PBI.

### User story
As a developer using the delivery workflows, I want a lightweight plan preflight before plan presentation to catch missing opt-in markers, scope/outcome conflicts, unverified validation targets, and inconsistent open-decision statements, so that a normal PBI plus an optional C03-EVAL-ID produces an accurate, reviewable plan in one pass.

### Candidate acceptance criteria
- Add a preflight check in the `/plan` flow that runs before final plan presentation.
- If a PBI reference is supplied, resolve any `C03-EVAL-ID` marker from the PBI entry and carry it into the plan and checkpoint.
- Verify plan outcome, scope, and exclusions are mutually consistent; planning-session no-change/no-test restrictions must not be misread as future-implementation prohibitions.
- Verify referenced source paths and validation commands against actual repository files before finalizing the plan.
- Verify open design decisions are labeled open rather than closed; do not emit a "None" outcome while decisions remain open.
- Include the scoped C03 evaluation-card append in `/implement` scope when a marker is present; do not present a marker-less plan for a marked task.
- If any preflight check fails, withhold the plan and present only the identified gaps.
- Add regression tests for the preflight behavior without adding synthetic PBI stages.
- Out of scope: permanent telemetry, automatic plan rewriting, or broad workflow re-architecture.

### Implementation notes (not acceptance criteria)
- **Test runner:** use the existing Node test runner, run from the exp4 repo root:
  `node --test AgenticLab/adapters/pi/tests/*.test.mjs`
- **New file:** `AgenticLab/adapters/pi/plan-preflight.mjs` — a standalone, deterministic preflight module with no synthetic PBI stages.
- **Registration point:** Register the preflight through the existing delivery-workflow entry point (`context-policy-gate.mjs`, which registers `registerPlanShellGuard`). During `/implement`, wire the preflight alongside the shell guard in the same extension entry (`knowledge-write-gate.ts` loads both). Do not register via `knowledge-capture-tools.mjs` — that file owns knowledge-capture tools only.
- **Preflight checks (minimum):** marker carried from PBI entry; outcome/scope/exclusions consistent; referenced source paths exist; referenced validation commands verified against package/config files; open decisions labeled open; C03 card append in `/implement` scope when marker present.
- **Do not** add new test infrastructure, dev servers, or environment setup; reuse the existing Node test runner and existing test files only.

## Future Project 2 — Document retrieval / embeddings discovery

**Status:** future discovery — not part of the current lab sequence.

### Proposed discovery questions
- Which document types and access boundaries must be supported?
- Which embedding provider/model is acceptable, and what content may be sent to it?
- Does the actual PostgreSQL image and deployment environment support `pgvector`? Verify the selected image/version and extension installation before choosing a schema or committing to it.
- What are the retention, re-indexing, deletion, and tenant/owner-isolation requirements?
- What search-quality evaluation set and success criteria will be used?

Do not add `pgvector`, embed documents, or send project content to an external provider until these questions and the data boundary are explicitly approved.
