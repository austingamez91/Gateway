# AGENTS.md

## Mission

Build GatewayKit, a lightweight config-driven API gateway, under a short time box. Favor a correct, testable core over broad but brittle feature coverage.

## Operating Principles

- Core requirements come before tertiary config features.
- Keep architecture boring and legible.
- Prefer one end-to-end happy path before expanding surface area.
- Make product assumptions explicit in `SPEC.md`.
- Track engineering decisions in `PLAN.md`.
- Track execution state in `TODO.md`.
- Record evaluator-facing trade-offs in `DECISIONS.md`.
- Avoid speculative abstractions until they remove immediate complexity.
- Treat time as the primary constraint.

## Project Location

- WSL distro: `Ubuntu`
- Project directory: `/home/austin/Projects/gateway`
- Windows entry command: `wsl -d Ubuntu`
- Git remote: `git@github.com:austingamez91/Gateway.git`

## Python Environment

- Python: `3.12`
- Virtual environment: `.venv`
- Activate with:

```bash
source .venv/bin/activate
```

## Stack

- FastAPI.
- Uvicorn.
- httpx.
- PyYAML.
- pytest.
- pytest-asyncio.
- Ruff.

## Expected Commands

Install dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run gateway:

```bash
python -m gatewaykit gateway.yaml
```

Run tests:

```bash
./scripts/test
```

Lint:

```bash
ruff check .
```

## Prototype Priorities

- First: config loading, health, route matching, method filtering, proxying, and tests.
- Second: `strip_prefix`, timeouts, header hygiene, and clean errors.
- Third: rate limiting, API key auth, retry, and load balancing.
- Last: body transforms, circuit breaker, and active health checks.

## Accepted Shortcuts

- In-memory state is acceptable.
- Focused validation is acceptable.
- Manual smoke checks may supplement tests, but core behavior needs automated coverage.
- Partial features are acceptable only when clearly documented.

## Do Not Spend Time On

- Existing gateway/proxy frameworks.
- Premature plugin systems, generic frameworks, or broad refactors.
- Exhaustive test suites before the core flow exists.
- Documentation beyond what directly helps setup, evaluation, or walkthrough.
- Multi-environment deployment.

## Definition Of Done For The Sprint

- Gateway starts from documented commands.
- Core requirements in `SPEC.md` work.
- Tests run with a single command.
- `README.md` and `DECISIONS.md` are accurate.
- Known gaps and shortcuts are captured.
