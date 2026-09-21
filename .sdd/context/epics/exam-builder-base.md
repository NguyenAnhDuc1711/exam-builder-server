---
epic: exam-builder-base
branch: epic/exam-builder-base
started: 2026-09-21T09:22:14Z
status: in-progress
---
# Epic Context: exam-builder-base

## Key Decisions
- Single-tenant v1, no `organization_id` (Product Brief, locked in plan-review NFR-3 verification).
- Clean Architecture (domain/application/infrastructure/api) per epic.md AD-1.
- Task count reduced 10→8 after plan-review RED-1 consolidation (T012=assembly+assignment, T020=submission+grading+results).
- 2 CRITICAL gaps from plan-review closed directly in task specs: T020 must wrap submit in a DB transaction (CRIT-1) and must check submission ownership before returning results (CRIT-2).

## Notes
(populated by task agents via handoff notes during epic-run)
