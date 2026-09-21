# Design Pipeline

Generate design system, visual mockups, and implementation specs from a PRD.

See [conventions.md](conventions.md) for shared rules (frontmatter, paths, git, GitHub ops).

## Usage
```
sdd prd-design <feature_name> [--screen <screen_name>]
```

## Preflight (silent — do not show progress to user)

1. **Parse arguments:**
   - Split `$ARGUMENTS` into `feature_name` and optional `--screen <screen_name>`.
   - Extract: `FEATURE` = first argument (kebab-case name), `TARGET_SCREEN` = value after `--screen` (or empty).
   - If `$ARGUMENTS` is empty → `Missing feature name. Usage: sdd prd-design <feature_name> [--screen <screen_name>]` and stop.
   - `FEATURE` MUST match `^[a-z0-9][a-z0-9-]*[a-z0-9]$`. If invalid → `Feature name must be kebab-case. Got: '$FEATURE'` and stop.

2. **Locate PRD:**
   - If `.sdd/prds/$FEATURE.md` doesn't exist → `PRD not found: .sdd/prds/$FEATURE.md. Run: sdd prd-new $FEATURE` and stop.

3. **Check lifecycle config:**
   - Read `.sdd/config/lifecycle.json`. If `design_phase.enabled` is `false` → `Design phase is disabled in .sdd/config/lifecycle.json. Enable it or run prd-parse $FEATURE directly.` and stop.

4. **Detect tools — determine operation mode:**
   ```bash
   uupm_available=false; stitch_available=false
   skill/sdd/scripts/detect-uupm.sh >/dev/null 2>&1 && uupm_available=true
   skill/sdd/scripts/detect-stitch.sh >/dev/null 2>&1 && stitch_available=true
   ```
   Determine MODE:
   - `FULL` — both UUPM and Stitch available
   - `DESIGN_ONLY` — UUPM available, Stitch not available
   - `MOCKUP_ONLY` — Stitch available, UUPM not available
   - `TEXT_ONLY` — neither available

   Display: `Operating in {MODE} mode`

5. **Handle --screen flag (targeted iteration):**
   - If `TARGET_SCREEN` is set:
     - Verify `.sdd/designs/$FEATURE/` exists → if not: `No existing designs for '$FEATURE'. Run prd-design $FEATURE first (without --screen).` and stop.
     - Verify `TARGET_SCREEN` appears in `.sdd/designs/$FEATURE/screen-inventory.md` → if not: `Screen '$TARGET_SCREEN' not found in inventory. Available screens:` then list screens from inventory and stop.
     - Skip Phase 1. Run Phase 2 only for `TARGET_SCREEN`, then Phase 3 only for `TARGET_SCREEN`.
     - Jump to **Phase 2** instructions.

6. **Check existing designs (re-run menu):**
   - If `.sdd/designs/$FEATURE/` exists and `TARGET_SCREEN` is empty:
     - Ask user:
       ```
       Designs already exist for '$FEATURE'. Choose an action:
       1. Regenerate all (delete existing, run full pipeline)
       2. Regenerate specific screen (enter screen name, run Phase 2+3 for that screen)
       3. Update design system only (re-run Phase 1, keep existing screens/specs)
       ```
     - Option 1: `rm -rf .sdd/designs/$FEATURE` then continue with full pipeline.
     - Option 2: Ask for screen name → set `TARGET_SCREEN` → skip Phase 1, run Phase 2+3 for that screen only.
     - Option 3: Run Phase 1 only, then display summary and stop.

7. **Create directory structure:**
   ```bash
   mkdir -p .sdd/designs/$FEATURE/{prompts,screens,specs}
   ```

## Role & Mindset

You are a senior UI/UX architect who translates product specifications into cohesive design systems and implementation-ready specs. Your designs are known for:
- Visual consistency through strict token-based design systems
- Practical component hierarchies that map cleanly to frontend frameworks
- Accessibility-aware color palettes with sufficient contrast ratios
- Responsive layouts that degrade gracefully across breakpoints

Your approach — apply all four lenses:
- **User:** What does the persona need to see, do, and feel on each screen?
- **Consistency:** Does every element reference the design system? Zero ad-hoc values.
- **Developer:** Can an engineer build this screen from the spec alone, without guessing?
- **Pragmatism:** Is this the simplest visual design that meets the product goals?

## Instructions

### Phase 1: PRD Analysis + Design System Generation

**1a. Read and analyze the PRD:**

Load `.sdd/prds/$FEATURE.md` and extract:
- **Product type:** SaaS dashboard, mobile app, internal tool, CLI, landing page, etc. — infer from Executive Summary and Problem Statement.
- **Target personas:** From Target Users section — note their technical sophistication, usage context (desktop/mobile/both), and frequency of use.
- **Screen inventory (preliminary):** Scan User Stories for stories that involve UI interaction. Each UI-related user story maps to at least one screen. List screen candidates with source user story IDs.
- **Mood/tone keywords:** From Executive Summary and Problem Statement — extract adjectives and context clues (e.g., "enterprise", "fast", "simple", "data-heavy", "consumer-friendly").
- **Brand/style hints:** Any existing color, font, or style mentions in the PRD or project context files.

**1b. Check for UI context:**

If the PRD has zero UI-related user stories (all backend/API/infrastructure):
- Display: `PRD '$FEATURE' has no UI-related user stories. Design pipeline works best with UI requirements.`
- Ask user: `Continue with minimal design system (useful for API documentation styling)? Or skip? (continue/skip)`
- If skip → stop with message: `Skipped. Run prd-parse $FEATURE to proceed without design.`

If PRD has >10 screens identified:
- Display: `Found {count} potential screens. Recommend prioritizing top 5 for initial design pass.`
- Ask user to confirm screen list or trim.

**1c. Generate design system:**

Generate `.sdd/designs/$FEATURE/design-system.md` with the following sections:

**Schema** (`design-system.md`):

| name | type | required | example |
|------|------|----------|---------|
| feature | string | yes | "task-manager" |
| style-recommendation | string | yes | "Modern minimal — clean whitespace, muted neutrals, single accent; suits productivity SaaS personas who scan data quickly" |
| color-primary | hex | yes | "#2563EB" |
| color-secondary | hex | yes | "#64748B" |
| color-accent | hex | yes | "#F59E0B" |
| color-background | hex | yes | "#F8FAFC" |
| color-surface | hex | yes | "#FFFFFF" |
| color-text | hex | yes | "#0F172A" |
| color-text-muted | hex | yes | "#64748B" |
| color-border | hex | yes | "#E2E8F0" |
| color-success | hex | yes | "#16A34A" |
| color-warning | hex | yes | "#D97706" |
| color-error | hex | yes | "#DC2626" |
| accessibility-notes | string | no | "text(#0F172A) on background(#F8FAFC) = 17.5:1 ✓; primary(#2563EB) on surface(#FFFFFF) = 5.1:1 ✓" |
| typography-h1 | font/size/weight/lh | yes | "Inter, 2.25rem, 700, 1.2" |
| typography-h2 | font/size/weight/lh | yes | "Inter, 1.5rem, 600, 1.3" |
| typography-h3 | font/size/weight/lh | yes | "Inter, 1.25rem, 600, 1.3" |
| typography-body | font/size/weight/lh | yes | "Inter, 1rem, 400, 1.5" |
| typography-caption | font/size/weight/lh | yes | "Inter, 0.75rem, 400, 1.4" |
| typography-label | font/size/weight/lh | yes | "Inter, 0.875rem, 500, 1.4" |
| font-pairing-rationale | string | no | "Inter single-family for readability; weight variation (400/500/600/700) provides hierarchy without visual noise" |
| spacing-base-unit | number | yes | "4" |
| spacing-xs | px | yes | "4px" |
| spacing-sm | px | yes | "8px" |
| spacing-md | px | yes | "16px" |
| spacing-lg | px | yes | "24px" |
| spacing-xl | px | yes | "32px" |
| spacing-2xl | px | yes | "48px" |
| spacing-3xl | px | yes | "64px" |
| component-buttons | string | yes | "border-radius:6px; padding: spacing/sm spacing/md; variants: primary, secondary, ghost, destructive" |
| component-inputs | string | yes | "border: 1px color-border; focus-ring: 2px color-primary; error-border: color-error" |
| component-cards | string | yes | "padding: spacing/md; border-radius:8px; shadow: 0 1px 3px rgba(0,0,0,0.1); hover: shadow-md" |
| component-navigation | string | yes | "top-nav height:56px; active-indicator: color-primary border-bottom; responsive: hamburger < 768px" |
| component-tables | string | no | "row-height:44px; header-bg: color-surface; stripe: color-background; responsive: horizontal scroll" |
| anti-patterns | string | no | "No raw hex values in specs; no font-sizes outside typography scale; no spacing outside spacing scale" |

**Required fields:** feature, style-recommendation, color-primary, color-secondary, color-accent, color-background, color-surface, color-text, color-text-muted, color-border, color-success, color-warning, color-error, typography-h1, typography-h2, typography-h3, typography-body, typography-caption, typography-label, spacing-base-unit, spacing-xs, spacing-sm, spacing-md, spacing-lg, spacing-xl, spacing-2xl, spacing-3xl, component-buttons, component-inputs, component-cards, component-navigation

**Mode branching for generation:**
- **FULL or DESIGN_ONLY:** Invoke the UUPM skill to provide design intelligence. Use its recommendations as the foundation for the design system. Prompt UUPM with: product type, personas, mood keywords, and any brand constraints. Incorporate its output into the design system structure above. If UUPM invocation fails → fall back to Claude native reasoning (same as TEXT_ONLY path).
- **MOCKUP_ONLY or TEXT_ONLY:** Use Claude's native reasoning to generate the design system. Base decisions on: product type conventions, persona needs, mood keywords, and established design principles.

Write output to `.sdd/designs/$FEATURE/design-system.md`.

Display: `Phase 1 complete: design-system.md generated`

---

### Phase 2: Screen Inventory + Mockup Generation

**2a. Generate screen inventory:**

Create `.sdd/designs/$FEATURE/screen-inventory.md`:

```markdown
# Screen Inventory: {FEATURE}

| Priority | Screen Name       | Source User Story | Description                    | Key Components              |
|----------|-------------------|-------------------|--------------------------------|-----------------------------|
| 1        | {screen-name}     | US-N              | [1-sentence description]       | [nav, form, table, etc.]    |
| 2        | {screen-name}     | US-N              | [1-sentence description]       | [components]                |
| ...      | ...               | ...               | ...                            | ...                         |
```

Rules:
- Priority order follows user flow (e.g., onboarding → dashboard → detail → settings).
- Screen names are kebab-case (used as filenames).
- Every UI-related user story must map to at least one screen.
- Group closely related stories into one screen where natural.

**2b. Generate Stitch prompts:**

For each screen, create `.sdd/designs/$FEATURE/prompts/{screen-name}.txt`:

```
Design a {screen-name} screen for a {product-type} application.

Target user: {persona name} — {persona context}
Screen purpose: {description from inventory}

Design System References:
- Colors: Use primary (#hex) for CTAs, secondary (#hex) for secondary actions, background (#hex) for page bg
- Typography: {h1 font} at {h1 size} for headings, {body font} at {body size} for body text
- Spacing: Base unit {N}px, use {md}px for component padding, {lg}px for section gaps
- Border radius: {value} for cards, {value} for buttons
- Shadows: {card shadow value}

Key Components:
{list of components from inventory with layout hints}

Layout:
- {mobile-first or desktop-first based on persona} responsive design
- {specific layout guidance: sidebar + main, single column, grid, etc.}

{If not the first screen: "Reuse components from: {list of prior screen names} where applicable."}

Constraints:
- Single HTML file with inline CSS
- Semantic HTML5 elements
- WCAG AA compliant contrast
- No JavaScript required (static mockup)
```

**2c. Mode branching for mockup generation:**

- **FULL or MOCKUP_ONLY:** For each screen (in priority order):
  1. Read the prompt file for the screen.
  2. Invoke Stitch MCP tool with the prompt content.
  3. Save returned HTML to `.sdd/designs/$FEATURE/screens/{screen-name}.html`.
  4. On Stitch error: retry up to 3 times with exponential backoff (2s, 4s, 8s). On persistent failure: log `Stitch failed for '{screen-name}' — prompt saved for manual use`, continue with remaining screens.
  5. After all screens: display count of successful HTML generations.

- **DESIGN_ONLY or TEXT_ONLY:**
  - Display: `Stitch MCP not available — prompts saved for manual use at .sdd/designs/$FEATURE/prompts/`
  - Display: `Tip: Paste prompts into stitch.withgoogle.com and save HTML to .sdd/designs/$FEATURE/screens/`
  - Skip HTML generation entirely.

Display: `Phase 2 complete: {N} screens inventoried, {M} mockups generated`

---

### Phase 3: Implementation Spec Generation

For each screen in the inventory (in priority order):

**3a. Determine spec source:**
- If `.sdd/designs/$FEATURE/screens/{screen-name}.html` exists → parse HTML for component extraction.
- If no HTML → generate text-based spec from design system + screen description.

**3b. Generate spec:**

Write `.sdd/designs/$FEATURE/specs/{screen-name}-spec.md`:

**Schema** (`{screen-name}-spec.md`):

| name | type | required | example |
|------|------|----------|---------|
| screen-name | string | yes | "dashboard" |
| source | string | yes | "screens/dashboard.html" |
| component-tree | string | yes | "Page > Header(Logo, Navigation, UserMenu) > Main(spacing/lg) > SectionTitle(typography/h2) > ContentArea(surface) > ComponentA(spacing/md), ComponentB > Footer" |
| layout-container | string | yes | "max-width:1280px, centered; section spacing: spacing/xl between major sections" |
| layout-grid | string | yes | "12-col grid, gap: spacing/md; sidebar 3-col + main 9-col on desktop; stacks on mobile" |
| color-usage | table | yes | "element=Page background, token=background, context=Base layer; element=Primary CTA, token=primary, context=Main action buttons; element=Body text, token=text, context=Paragraphs" |
| typography-usage | table | yes | "element=Page title, token=h1, context=Main heading; element=Body text, token=body, context=Content paragraphs; element=Form labels, token=label, context=Input labels" |
| interactive-states | table | yes | "component=Button-primary: default=primary+white-text, hover=primary-10%, active=primary-20%, disabled=50%-opacity, loading=spinner; component=Input: hover=border-primary, disabled=surface-muted" |
| breakpoint-mobile | string | yes | "< 640px: stack columns, hide sidebar, hamburger nav" |
| breakpoint-tablet | string | yes | "640-1024px: 2-col layout, condensed nav" |
| breakpoint-desktop | string | yes | "> 1024px: default layout as designed" |
| component-reuse-map | table | no | "component=Navigation, used-in=all screens, shared=same nav items + design tokens; component=Button-primary, used-in=dashboard+settings, shared=same design tokens" |

**Required fields:** screen-name, source, component-tree, layout-container, layout-grid, color-usage, typography-usage, interactive-states, breakpoint-mobile, breakpoint-tablet, breakpoint-desktop

**Spec rules:**
- Every color value MUST reference a `design-system` token name — never a raw hex.
- Every spacing value MUST reference a `spacing/{token}` — never a raw pixel value.
- Every typography element MUST reference a `typography/{role}` — never a raw font-size.
- Component tree uses indentation to show hierarchy.
- If parsing HTML: extract actual component structure. If text-based: generate reasonable structure from screen description and component list.

Display after each spec: `specs/{screen-name}-spec.md`

Display: `Phase 3 complete: {N} implementation specs generated`

---

### Post-execution

Display summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Design Pipeline Complete: {FEATURE}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Mode: {MODE}
Design System: .sdd/designs/{FEATURE}/design-system.md
Screens: {count} screens in inventory
Mockups: {count} HTML files generated (or "prompts saved for manual use")
Specs: {count} implementation specs generated

Next actions:
→ Parse to epic:      sdd prd-parse {FEATURE}
→ Iterate a screen:   sdd prd-design {FEATURE} --screen {first_screen_name}
→ View design system: Read .sdd/designs/{FEATURE}/design-system.md
→ View screen spec:   Read .sdd/designs/{FEATURE}/specs/{first_screen_name}-spec.md
```

## Important

- The design system is the **single source of truth** for all visual decisions. Specs MUST reference it — never hardcode values.
- Design system file persists on filesystem — it is reused across re-runs and by downstream commands (`prd-parse`, `epic-decompose`).
- In TEXT_ONLY mode, the pipeline MUST still produce usable artifacts: `design-system.md`, `screen-inventory.md`, prompt files, and text-based specs.
- Screen names are kebab-case and used as filenames throughout — consistency is critical.
- When iterating a single screen (`--screen`), preserve the existing design system and other screen artifacts.
- Prompts in `prompts/` directory are useful even without Stitch — users can paste them into any design tool.
- Keep specs under 200 lines per screen. Be precise, not verbose.

## Model Tier

Requires opus — creative design thinking, visual system generation, implementation spec authoring.

## Workflow

After design, proceed to [doc.md](doc.md) for the conversion pipeline (prd-parse through epic setup).
