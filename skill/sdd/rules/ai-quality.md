# AI Quality

Checklist for detecting AI-generated design anti-patterns. Apply when reviewing or implementing UI features.

## Anti-Patterns

Flag these in UI code and designs:

- **Purple/blue gradient backgrounds** — default AI palette. Use project's actual brand colors.
- **3-column feature grid** — the "SaaS landing page starter kit." Vary layout by content type.
- **Centered everything** — centered headlines, centered text, centered buttons. Use left-alignment for readability.
- **Generic hero section** — large heading + subtitle + CTA button. Design for the specific user journey.
- **Uniform border-radius** — same rounded corners on every element. Vary by component purpose.
- **"Built for X" / "Designed for Y" copy** — generic value props. Use specific, evidence-based claims.
- **Stock photo aesthetics** — perfect people, perfect lighting, no context. Use real screenshots or illustrations.
- **Excessive whitespace symmetry** — everything equidistant. Use intentional spacing hierarchy.
- **Card-based everything** — every piece of content in a card with shadow. Use cards sparingly for grouped content.

## When to Apply

- During `/pm:epic-verify` Phase A review of UI tasks
- During `/pm:epic-run` when implementing frontend features
- When reviewing PR diffs that touch UI components

## What to Do Instead

- Reference the project's design system if one exists
- Look at the actual product context — who uses this, in what environment?
- Prefer functional over decorative
- When in doubt, simpler is better
