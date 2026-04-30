# AGENTS.md

## Mission

Build a working prototype quickly once the incoming specs arrive. Favor a running vertical slice over broad completeness.

## Operating Principles

- Keep architecture boring and legible.
- Prefer one end-to-end happy path before expanding surface area.
- Make product assumptions explicit in `SPEC.md`.
- Track engineering decisions in `PLAN.md`.
- Track execution state in `TODO.md`.
- Avoid speculative abstractions until they remove immediate complexity.
- Treat time as the primary constraint.

## Project Location

- WSL distro: `Ubuntu`
- Project directory: `/home/austin/Projects/gateway`
- Windows entry command: `wsl -d Ubuntu`

## Python Environment

- Use the project-local virtual environment at `.venv`.
- Activate with:

```bash
source .venv/bin/activate
```

## Run And Test Commands

TBD after stack and app shape are selected from the incoming specs.

## Prototype Priorities

- First: make the main user flow work end to end.
- Second: make the experience understandable and demoable.
- Third: add resilience, polish, and tests where they reduce real risk.

## Accepted Shortcuts

- Fake or seed data is acceptable if the spec does not require live integrations.
- Minimal styling is acceptable until the core flow works.
- Manual verification is acceptable for low-risk paths during the time box.

## Do Not Spend Time On

- Premature plugin systems, generic frameworks, or broad refactors.
- Exhaustive test suites before the core flow exists.
- Documentation beyond what directly speeds implementation.
- Multi-environment deployment unless the spec requires it.

## Definition Of Done For The Sprint

- App or service starts from documented commands.
- Main flow from `SPEC.md` works.
- Known gaps and shortcuts are captured in `TODO.md`.
- Demo path is clear.
