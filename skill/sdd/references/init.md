# Init

Bootstrap a project with SDD directory structure.

## When to Use

- First time setting up SDD on a project
- After cloning a project that uses SDD
- To verify/repair `.sdd/` structure

## Steps

### 1. Run Init Script

```bash
bash skill/sdd/scripts/init.sh
```

This creates the `.sdd/` directory tree and generates `CLAUDE.md` at project root (skipped if already present):

```
.sdd/
  prds/        # Product requirement documents
  epics/       # Epic definitions and task files
  context/     # Runtime context (progress, handoffs, sessions)
  verify/      # Verification state and reports
  config/      # Configuration files
  sessions/    # Debug journals (local-only)
  qa/          # QA scenarios and test results
  progress/    # Progress tracking
```

Each directory includes a `.gitkeep` to preserve structure in git.

`CLAUDE.md` is generated with project-specific instructions placeholder + SDD workflow blurb + Karpathy Coding Guidelines (3 principles). If `CLAUDE.md` already exists, it is not overwritten.

### 2. Verify

Confirm the structure exists:

```bash
ls -la .sdd/
```

All 8 subdirectories should be present.

### 3. Next Steps

- **New project?** Run `ctx-create` to establish project context documentation
- **Have a vague idea?** Run `office-hours` to brainstorm
- **Ready to plan?** Run `prd-rethink` to shape a product brief
- **Have a PRD?** Run `team-build` to go from PRD to executing tasks

## claude-md-refresh

Append Karpathy Coding Guidelines to an existing `CLAUDE.md`. Use this if the project already had `CLAUDE.md` before SDD was installed, or to migrate from an older SDD version.

```bash
bash skill/sdd/scripts/claude-md-refresh.sh
# or with --project-dir for a non-cwd project:
bash skill/sdd/scripts/claude-md-refresh.sh --project-dir /path/to/project
```

Idempotent — skips if marker `<!-- sdd:karpathy-section v1 -->` already present. Creates `CLAUDE.md.bak` before any modification.

## Custom Root

To use a different directory instead of `.sdd/`:

```bash
SDD_ROOT=my-custom-dir bash skill/sdd/scripts/init.sh
```

All SDD scripts respect the `SDD_ROOT` environment variable.

## Conventions

All managed files use YAML frontmatter. See [conventions.md](conventions.md) for format details.
