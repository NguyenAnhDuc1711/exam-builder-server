---
epic: exam-builder-base
phase: A
generated: 2026-09-21T10:13:59Z
assessment: EPIC_GAPS
quality_score: 4/5
total_issues: 4
closed_issues: 0
open_issues: 4
---

# Epic Verify — Phase A (Semantic Review): exam-builder-base

Method: documentation + code review only, per Phase A protocol (no execution). Built primarily from `.sdd/epics/exam-builder-base/verification-report.md` (T090's row-by-row static review, already thorough) plus `plan-review.md` (pre-implementation findings, to confirm the 2 CRITICAL fixes actually landed in code) and a fresh read of `git diff main..HEAD --stat`.

## Coverage Matrix

| PRD Requirement | Task(s) | Implemented | Test Coverage | Status |
|---|---|---|---|---|
| FR-1: Auth + refresh rotation | T003 | Yes | Yes (`test_auth_rotation.py`) | Pass |
| FR-2: Admin user management | T010 | Yes | Yes (`test_admin_users.py`) | Pass |
| FR-3: Question bank + image | T011 | Yes | Yes (`test_questions.py`, `test_question_upload_failure.py`) | Pass |
| FR-4: Exam assembly | T012 | Yes | Yes (`test_exam_assembly.py`) | Pass |
| FR-5: Exam assignment | T012 | Yes | Yes (`test_exam_assignment.py`) | Pass |
| FR-6: Submission + auto-grading | T020 | Yes | Yes (`test_grading.py`, `test_submit_transaction.py`) | Pass |
| FR-7: Results viewing | T020 | Yes | Yes (`test_results_authz.py`, `test_results_n_plus_1.py`) | Pass |
| NFR-1: Token rotation security | T003 | Yes | Yes | Pass |
| NFR-2: Cloudinary failure tolerance | T011 | Yes | Yes | Pass |
| NFR-3: Single-tenant | T002 | Yes | Yes (asserted against migrated schema, not just ORM) | Pass |
| NFR-4: Docker Compose deploy | T001 | Yes (as literally specified — health check only) | Yes | Pass with caveat (see Gap-1) |

**11/11 MUST FR+NFR covered and tested. 0 unmapped requirements.**

## 3D Analysis

**Dimension 1 — Architecture Integrity:** Module boundaries mostly respected (domain/application/infrastructure/api). One real deviation: use cases call SQLAlchemy models directly rather than routing through `app/domain/entities/` (Gap-4) — AD-1's isolation goal is only realized for the single-correct-option rule in `create_question.py`. No circular imports found. Config/env propagation consistent across all 5 routers (T090 cross-checked every import). No unintentional public API surface changes.

**Dimension 2 — Requirement Coverage:** Every MUST AC maps to a closed task (Coverage Matrix above). No SHOULD/NTH items were silently implemented or silently dropped — NTH-1..5 remain explicitly deferred in epic.md, unchanged. Implicit requirements: auth present on every endpoint except login/refresh (correct), error messages are structured JSON (`{"detail": "..."}`) not bare tracebacks. No orphan tasks — all 8 tasks trace to at least one FR/NFR or to CRIT/WARN fixes from plan-review.

**Dimension 3 — Code Quality:** Error paths handled per-task (409 on duplicate submit/assignment, 403 on cross-user access, 400 on invalid options/image). No hard-coded secrets — all config via `app/core/config.py` env vars. `grep -rn "TODO\|FIXME" app/` = zero matches (T090). Naming consistent (snake_case, FR-aligned file names). One quality note: `requirements.txt` pins `passlib[bcrypt]` but not `bcrypt` itself (Gap-3).

## Gap Report

**Gap-1 [Delivery Gap] — No migration-on-boot path**
- What's missing: neither `docker-compose.yml` nor `Dockerfile` runs `alembic upgrade head`. A clean `docker-compose up -d` passes the health check (SC-5, which doesn't touch the DB) but every other endpoint 500s until migration is run by hand.
- Severity: Medium (user-facing after first deploy, but has a documented workaround — run `alembic upgrade head` manually; not blocking for a dev/staging first run)
- Recommended fix: add an `entrypoint.sh` running `alembic upgrade head` before `uvicorn` in `Dockerfile`/`docker-compose.yml`, OR document the manual step in a README.

**Gap-2 [Delivery Gap] — No bootstrap-admin path**
- What's missing: `POST /users` requires an existing admin token; no public sign-up, seed script, or data migration creates the first admin. Every test works around this via direct ORM insert.
- Severity: Medium (real first-run blocker, has workaround — manual DB insert or a one-off script; explicitly out-of-scope per T010's spec, not a task defect)
- Recommended fix: a `scripts/seed_admin.py` or an Alembic data migration, run once per environment.

**Gap-3 [Quality Gap] — Unpinned `bcrypt` version under `passlib[bcrypt]`**
- What's missing: version pin for `bcrypt` itself; known passlib 1.7.x + bcrypt 4.1+ interop issue in the wider ecosystem (usually harmless, occasionally raises at import).
- Severity: Low (uncertain until `pip install` actually resolves; not confirmed to manifest)
- Recommended fix: pin `bcrypt<4.1` or `bcrypt>=4.1` explicitly and smoke-test password hashing on first real install.

**Gap-4 [Quality Gap] — `app/domain/entities/*.py` mostly unused**
- What's missing: AD-1's stated benefit ("business logic testable independent of SQLAlchemy") is only realized for `Question.has_single_answer()`; every other use case operates directly on ORM models.
- Severity: Low (no FR/NFR depends on this; architecture aspiration not fully realized but nothing is broken)
- Recommended fix: either wire the remaining use cases through domain entities in a follow-up, or update AD-1 to reflect the pragmatic scope actually implemented.

No critical or high-severity gaps found. Gap-5 from `verification-report.md` (`score` stored as raw count, not ratio) is a documented, deliberate T020 deviation with the ratio always recoverable — informational only, not listed as a gap requiring action.

### Failure Mode Summary (condensed from plan-review.md, re-confirmed against actual code by T090)

| Exception | Rescued? | Test? | Severity |
|---|---|---|---|
| TokenReuseDetected (family revoke) | Y | Y | OK — confirmed in code (T090) |
| UploadError (Cloudinary) | Y | Y | OK — confirmed in code (T090) |
| QuestionNotFoundError (assembly) | Y (WARN-1 fix) | Y | OK — confirmed, zero partial rows on 404 |
| Partial submit write (CRIT-1) | Y — single `session.begin()` transaction | Y (unexecuted) | Structurally closed; **unexecuted against real asyncpg (see Phase B Preparation)** |
| Cross-user results access (CRIT-2) | Y — ownership check before any data read | Y (unexecuted) | Structurally closed; **unexecuted against real asyncpg** |
| Double-submit (WARN-2) | Y — `IntegrityError` → 409 | Y (unexecuted) | Structurally closed; **unexecuted against real Postgres unique violation** |
| N+1 on submission list (WARN-4) | Y — eager loading | Y (unexecuted, flagged as most brittle assertion) | Structurally closed; **unexecuted** |

## Integration Risk Map

Cross-task interface consistency was checked exhaustively by T090 (7 independently-authored tasks): `require_role`/`get_current_user` signatures, `User`/`Question`/`Exam`/`Submission` field names, `ImageStoragePort` signature, `ExamQuestion.order` relationship, `submission.exam_assignment_id` UNIQUE constraint (ORM vs migration, column-by-column match), router registration order in `app/main.py`. **Zero import-path or shape mismatches found.** This is the highest-value confirmation from this review — 7 agents working from handoff notes alone produced a consistent codebase.

Remaining integration risk is entirely runtime-class, not interface-class: the `session.rollback()` immediately before `session.begin()` in `submit_exam` (SQLAlchemy autobegin interaction, T020's own #1 flagged risk) and every `selectinload`/`joinedload` path under real `asyncpg` (a missed eager-load surfaces as `MissingGreenlet`, not a clean failure — invisible to static reading).

## Quality Scorecard

**4/5.** Deducted 1 point for the 2 Delivery Gaps (migration-on-boot, bootstrap-admin) — both are real first-run friction even though neither blocks any MUST requirement and both have documented workarounds. Everything else (requirement coverage, interface consistency, CRIT/WARN closure from plan-review, absence of TODO/dead code) is clean by static review.

## Recommendations

1. Fix Gap-1 and Gap-2 before considering this "deployment-ready" (not "epic-complete" — they don't block the PRD's MUST requirements, but they block an operator's first successful run).
2. Pin `bcrypt` explicitly (Gap-3) — cheap, do it alongside Gap-1/2.
3. Leave Gap-4 (domain entities) as accepted technical debt — not worth blocking merge over an architecture aspiration with zero functional impact.
4. **Phase B cannot run in this environment** — see below.

## Phase B Preparation

Test scenarios that MUST be run first, in priority order, once Python + Docker are available:
1. `pip install -r requirements.txt` — watch for the Gap-3 bcrypt interop warning/error.
2. `docker-compose up -d` + `alembic upgrade head` (manual, since Gap-1 isn't fixed) — confirms DDL is valid (reserved-word quoting for `"user"`/`"order"` columns, constraint names).
3. `pytest tests/integration/test_e2e_flow.py -v` first, specifically — highest-value single test, exercises all 5 routers in sequence; a failure here likely indicates a cross-task integration bug that per-router test files wouldn't catch individually.
4. `pytest tests/integration/test_submit_transaction.py tests/integration/test_results_authz.py -v` — the 2 former-CRITICAL paths (CRIT-1/CRIT-2), highest business/security value.
5. `pytest tests/integration/test_results_n_plus_1.py -v` — flagged by T020 as the most brittle assertion (exact query-count equality); expect possible false failures here even if the underlying behavior is correct.
6. Full suite: `pytest tests/ -v --tb=short`.

## ENFORCEMENT: Phase A Gate

**Assessment: EPIC_GAPS** — 4 gaps found (0 critical, 0 high, 2 medium, 2 low), all with documented workarounds, 0 gaps against any MUST requirement itself. Per protocol, presenting to the user before proceeding to Phase B — **and flagging that Phase B (Tier 1-4 automated test execution) cannot physically run in this environment: no Python or Docker interpreter is available to this session.** See message to user for the gate options.
