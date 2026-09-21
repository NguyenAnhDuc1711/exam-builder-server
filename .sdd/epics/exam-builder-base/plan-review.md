---
epic: exam-builder-base
prd: exam-builder-base
mode: reduce
reviewer: claude
created: 2026-09-21T09:19:00Z
verdict: ready
critical_gaps: 0
warnings: 0
---

# Plan Review: exam-builder-base

*Mode auto-selected: REDUCE (task count = 10 > 8 threshold). Dual-voice review and git-diff-based Phase-0 auto-trigger (FR-11/FR-14) do not fire — repo has no git history yet (pre-implementation plan review, 0 changed files).*

## Step 0: Scope Challenge

**0A. Existing Code Audit:** Repo is greenfield — no existing code to reuse. No rebuild risk.

**0B. Complexity Assessment**
```
COMPLEXITY CHECK
Files touched: ~22 (>8 smell — expected for a from-scratch service scaffold)
New components: 4 (domain / application / infrastructure / api layers) (>2 smell — deliberate, justified by AD-1)
Task count: 10 / parallel: 3/10
Cross-epic conflicts: none (only epic in repo)
```

**0C. PRD Alignment**
```
PRD ALIGNMENT
MUST requirements: 7/7 mapped (100%)
NFR: 4/4 mapped (100%)
Unmapped: none
```

**0D. Implementation Alternatives:** Skipped — epic.md AD-1 already documents the flat-vs-clean-architecture tradeoff carried from office-hours/prd-rethink.

**0E. Completeness Check (Lake Score):** Reviewed 4 binary implementation choices against "full vs shortcut, <2x effort diff → prefer full": (1) normalized `Option` table vs JSON blob — chose normalized (full); (2) `ImageStoragePort` abstraction vs direct Cloudinary call — chose abstraction (full, enables NFR-2 testing); (3) hashed refresh tokens vs plaintext — chose hashed (full); (4) eager-loading for submission lists vs naive N+1 — chose eager loading (full, though untested — see WARNING-4). **Lake Score: 4/4 (100%)** — plan consistently chose the complete option where effort diff was small.

**REDUCE-mode proposal — task consolidation:** At 10 tasks (T001,T002,T003,T010,T011,T012,T020,T021,T022,T090), the plan crosses the >8 threshold. Two pairs are same-file, tightly-sequential work artificially split across task boundaries:
- T012 (Exam assembly) + T020 (Exam assignment) both edit `app/api/v1/routers/exams.py`, both admin-only, no independent value without the other.
- T021 (Submission+grading) + T022 (Results viewing) both edit `app/api/v1/routers/submissions.py`, share the same Submission/Answer entities.

Merging both pairs drops the count to 8 tasks (T001, T002, T003, T010, T011, T012'=assembly+assignment, T020'=submission+grading+results, T090), removes 2 same-file task-conflict risks, and does not reduce parallelism (both merged tasks still depend only on T003, still Phase 2/3 as before). This is the single headline REDUCE recommendation — see Unresolved Decisions.

## Section 1: Architecture Review

```
                    ┌─────────────┐
                    │   API (v1)  │ ★ new
                    │ routers/deps│
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Application │ ★ new
                    │  use_cases  │
                    │    ports    │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
       ┌──────▼──────┐            ┌─────▼──────┐
       │   Domain    │ ★ new      │Infrastructure│ ★ new
       │  entities   │◄───────────┤ db/auth/     │
       │ repo (iface)│  implements│ storage      │
       └─────────────┘            └─────┬────────┘
                                         │
                              ┌──────────┼──────────┐
                        ┌─────▼────┐          ┌─────▼─────┐
                        │PostgreSQL│          │ Cloudinary │ (external)
                        └──────────┘          └────────────┘
```

Component boundaries follow AD-1 cleanly — domain has zero SQLAlchemy/Cloudinary imports, only interfaces. Data flow (create question → assemble → assign → submit → results) traced end-to-end in Traceability Matrix, coherent. Coupling justified (repository + port pattern isolates persistence/storage). **Security smell check** (plan touches user data, credentials, external API): refresh-token hashing addressed (AD-2); however see CRIT-2 (authz on results) and WARN-3 (image upload validation) below — these ARE security-relevant gaps the plan doesn't currently close.

## Section 2: Failure Mode Analysis

**TABLE 1 — WHAT CAN FAIL**

| Codepath | What can fail | Exception/Error class |
|---|---|---|
| POST /login | Wrong credentials | InvalidCredentialsError |
| POST /refresh | Reused/expired/invalid refresh token | TokenReuseDetected |
| POST /questions (image) | Cloudinary upload timeout/error | UploadError |
| POST /exams | question_id not found in bank | QuestionNotFoundError |
| POST /exams/{id}/assign | duplicate assignment (same exam+user twice) | DuplicateAssignmentError |
| POST /submit | mid-write failure between Submission insert and Answer inserts | IntegrityError / partial write |
| POST /submit | concurrent double-submit race | IntegrityError (unique constraint) |
| GET /submissions/{id} | user requests another user's submission | — (authorization gap) |

**TABLE 2 — HOW IT'S HANDLED**

| Exception | Rescued? | Rescue Action | User sees | Test? | Severity |
|---|---|---|---|---|---|
| InvalidCredentialsError | Y | 401 | "Invalid credentials" | Not specified | WARNING |
| TokenReuseDetected | Y (AD-2) | revoke family, 401 | generic 401 | Y (SC-3) | OK |
| UploadError | Y (AD-3) | fallback, save w/o image | 201 + warning | Y (SC-4) | OK |
| QuestionNotFoundError | Not specified | — | — | Not specified | WARNING-1 |
| Partial submit write (Submission created, Answer insert fails mid-way) | **N — no transaction wrapping specified in T021** | — | Silent inconsistent state; single-attempt constraint already claimed, user can never resubmit or see a result | N | **CRITICAL-1** |
| Concurrent double-submit | Partial (DB unique constraint exists) but no explicit catch→409 in T021 | raw IntegrityError likely surfaces as 500 | Confusing 500 instead of clean "already submitted" | Not specified | WARNING-2 |
| GET /submissions/{id} cross-user access | **N — epic states intent ("chỉ bài của mình") but no task specifies the ownership check, and SC-7 only tests breakdown correctness, not the boundary** | — | Silent data leak (user sees another user's answers/score) | N | **CRITICAL-2** |

Rule check: both CRITICAL rows satisfy Rescued=N + Test=N + User-sees=Silent → correctly classified CRITICAL, not WARNING.

## Section 3: Code Quality & DRY Review

`require_role("admin")` dependency reused consistently across T010/T011/T012 routers — no DRY violation. Naming consistent (snake_case, FR-aligned). `ImageStoragePort`/`TokenServicePort` abstractions are justified, not over-engineered (single provider today, but testability requirement in NFR-2/NFR-1 directly motivates the seam). T002 touches 9 model files in one task — exceeds the ">5 files" complexity-hotspot signal, but splitting it would create circular FK-migration ordering problems (all tables must land in one Alembic revision anyway) — **flagged but accepted, no action needed.**

## Section 4: Test Strategy Review

```
TEST COVERAGE MAP
| What's new              | Happy | Failure           | Edge                  | Test type   |
|--------------------------|-------|--------------------|------------------------|-------------|
| Auth login/refresh       | Y     | Y (SC-3)           | reuse detection        | integration |
| Question + image         | Y(SC-1)| Y (SC-4)          | invalid file type — MISSING | integration |
| Exam assembly            | Y(SC-1)| question-not-found — MISSING | empty list — MISSING | integration |
| Assignment                | Y(SC-1)| duplicate assign — MISSING | —                     | integration |
| Submission + grading     | Y(SC-2)| double-submit — MISSING (WARN-2) | partial answers — MISSING | unit+integration |
| Results                  | Y(SC-7)| **cross-user access — MISSING (CRIT-2)** | —                      | integration |
```

"2AM-confidence" question: for `GET /submissions/{id}`, could you wake up at 2AM and be confident a user cannot pull another user's exam answers? **No** — this is exactly CRIT-2. A hostile QA engineer's first move on this endpoint is `GET /submissions/{someone_elses_id}` with their own token; nothing in the plan currently prevents or tests that.

## Section 5: Performance & Resource Review

Skipped in depth — PRD sets no explicit performance target beyond NFR-4 (deploy smoke test). Single-tenant, low-scale expected per Product Brief. Only carry-forward: N+1 query risk on submission-list already flagged as R-5/WARN-4.

## Section 6: PRD Traceability Audit

```
TRACEABILITY AUDIT
| PRD Req | Epic maps to      | Task(s)   | Verification | Status  |
|---------|--------------------|-----------|---------------|---------|
| FR-1    | AD-2               | T003      | SC-3          | mapped  |
| FR-2    | Technical Approach | T010      | SC-6          | mapped  |
| FR-3    | AD-3               | T011      | SC-4          | mapped  |
| FR-4    | Technical Approach | T012      | SC-1          | mapped  |
| FR-5    | Technical Approach | T020      | SC-1          | mapped  |
| FR-6    | AD-4               | T021      | SC-2          | mapped  |
| FR-7    | Technical Approach | T022      | SC-7          | mapped* |
| NFR-1   | AD-2               | T003      | SC-3          | mapped  |
| NFR-2   | AD-3               | T011      | SC-4          | mapped  |
| NFR-3   | AD-1               | T002      | schema review | mapped  |
| NFR-4   | Technical Approach | T001      | SC-5          | mapped  |
```
\* FR-7 mapped to a task and a verification method, but the verification (SC-7) does not cover the authorization boundary implied by the requirement's own wording ("chỉ bài của mình") — see CRIT-2. Traceability is structurally complete (0 unmapped); the gap is in verification depth, already captured above.

## Required Outputs

**1. Existing Code Reuse**
| Functionality | Existing code | Reused? | Recommendation |
|---|---|---|---|
| — | none (greenfield) | N/A | N/A |

**2. Not in Scope**
Deferred items match PRD Out of Scope exactly (NTH-1..NTH-5, multi-tenancy): all carried correctly into epic Traceability Matrix as "Deferred." No items deferred without reason.

**3. Failure Modes Registry**
CRITICAL GAPS: 2 (partial-write transaction on submit; missing authz check+test on results endpoint)
WARNINGS: 4 (QuestionNotFoundError unhandled; double-submit surfaces raw 500 instead of clean 409; image upload lacks file-type/size validation; N+1 mitigation in T022 has no asserting test)

**4. Unresolved Decisions**

| Issue | Section | Recommended | Risk if unresolved |
|---|---|---|---|
| RED-1: Task consolidation (T012+T020, T021+T022) | Step 0 REDUCE proposal | Merge both pairs → 8 tasks total | Two extra same-file tasks with split ownership; slightly higher coordination/conflict risk in epic-run, no functional risk |
| CRIT-1: No transaction wrapping in submit flow | Section 2 | Add explicit AC to T021 (or merged T020'): wrap Submission+Answer inserts in a single DB transaction, rollback on any failure | User can end up in unrecoverable stuck state (attempt consumed, no result) |
| CRIT-2: No ownership check / test on GET /submissions/{id} | Section 2, 4 | Add explicit AC to T022 (or merged T020'): 403 when `submission.user_id != current_user.id` for non-admin callers, plus a dedicated cross-user-access test | Silent cross-user data leak of exam answers/scores |
| WARN-1: QuestionNotFoundError unhandled in exam assembly | Section 2 | Add explicit 404 handling + validation in T012 | Confusing 500 instead of clear client error |
| WARN-2: double-submit raw 500 instead of 409 | Section 2 | Catch `IntegrityError` on unique-constraint violation, return 409 | Poor UX, but not silent — lower priority than CRIT items |
| WARN-3: image upload lacks file-type/size validation | Section 1, 3 | Add MIME-type + size-limit check before calling Cloudinary in T011 | Abuse surface (arbitrary file upload, oversized payload) |
| WARN-4: N+1 mitigation (eager loading) has no asserting test | Section 4 | Add a query-count assertion test to T022 (or merged T020') | Regression could silently reintroduce N+1 later with no test catching it |

**5. Completion Summary**

```
PLAN REVIEW — COMPLETION SUMMARY
Epic:              exam-builder-base
Mode:              REDUCE
PRD coverage:      7/7 MUST requirements mapped (100%)

Arch issues: 0 (diagram clean)     |  Failure modes: 8 traced (2 critical)
Quality: 1 flagged-but-accepted    |  Test gaps: 6 (1 tied to a critical)
Perf: 1 carried-forward (N+1)      |  PRD trace: 0 unmapped

Code reuse: N/A (greenfield)       |  Deferred: 5 (NTH-1..5, matches PRD)  |  Unresolved: 5
Lake Score: 4/4 (100%) decisions chose complete option

VERDICT:  BLOCKED
Reason:   2 CRITICAL gaps (unhandled partial-write on submit; missing authz check+test on results endpoint) must be closed in epic.md before decompose.
```

## Applied Fixes (post-review, before decompose)

User chose "Fix hết + gộp task." All items applied directly to `epic.md`:
- **RED-1:** T012+T020(old) merged → new T012 (assembly+assignment); T021+T022(old) merged → new T020 (submission+grading+results). Task count 10 → 8.
- **CRIT-1:** New T020 now specifies explicit DB transaction wrapping Submission+Answer inserts, with a dedicated rollback test.
- **CRIT-2:** New T020 now specifies explicit ownership check (`submission.user_id == current_user.id` for non-admin) plus a dedicated cross-user-access test.
- **WARN-1:** New T012 now validates question_id existence before assembly (404 on missing).
- **WARN-2:** New T020 now catches the unique-constraint `IntegrityError` on double-submit and returns 409 instead of a raw 500.
- **WARN-3:** T011 now validates image MIME-type and size before calling Cloudinary.
- **WARN-4:** New T020 now requires eager loading plus a query-count assertion test for the submission-list endpoint.

Traceability Matrix and Success Criteria (Technical) in `epic.md` updated accordingly.

NO UNRESOLVED DECISIONS
