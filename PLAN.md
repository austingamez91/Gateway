# PLAN.md

## Current Phase

Pre-spec environment setup.

## Strategy

Use lightweight specification-driven development:

1. Capture product truth in `SPEC.md`.
2. Choose the smallest viable architecture in this file.
3. Execute from `TODO.md`.
4. Keep `AGENTS.md` as the project operating manual.

## Initial Build Approach

- Start with one vertical slice from input to output.
- Keep persistence, auth, and integrations minimal unless the spec makes them central.
- Select libraries for speed and reliability, not novelty.
- Make the first runnable version early, then iterate.

## Architecture

TBD after specs arrive.

## Stack

TBD after specs arrive.

Known base:

- OS/runtime target: Ubuntu under WSL2.
- Python base available: Python 3.12.
- Project venv: `.venv`.

## Milestones After Specs Arrive

1. Compress incoming specs into `SPEC.md`.
2. Identify main demo path and acceptance criteria.
3. Choose stack and project structure.
4. Build runnable vertical slice.
5. Add necessary polish, validation, and tests.
6. Capture remaining gaps and demo notes.

## Risk Register

- Time pressure may force scope cuts.
- Ambiguous specs may require fast product decisions.
- External integrations may need fakes, fixtures, or narrow wrappers.

## Fallback Rules

- If scope is too broad, cut to the main demo path.
- If integration access is blocked, mock the boundary cleanly.
- If styling threatens delivery, use a simple functional UI.
- If tests threaten delivery, write focused smoke checks around the demo path.
