---
name: cognitive-lenses
status: stable
---

# Cognitive Lenses

Fixed-order 4-lens walk for `prd-rethink` Step 0F. Each lens MUST produce ≥1 reframe candidate OR explicit "no reframe applies" line.

### Reversibility × Magnitude
Is this decision easy/hard to undo? What is the magnitude of regret if wrong?
Example: "Switch DB engines" = hard × high = veto-by-default; "rename CLI flag" = easy × low = ship.

### Inversion Reflex
What does the failure mode look like if we did the OPPOSITE? Invert to surface hidden assumptions.
Example: PRD says "add auth" → invert: "remove auth entirely" exposes which calls actually need a user.

### Focus as Subtraction
What is this PRD NOT doing? What could we cut to clarify intent (Rams "subtraction default")?
Example: brief lists 7 FRs → cut FR-4/FR-6 ("nice-to-have polish"); intent clarifies to 5-FR core.

### Blast Radius
What else does this touch? Where does damage propagate on failure (callers, data, contracts)?
Example: changing session-id format → blast radius = every analytics file + every downstream skill reading it.
