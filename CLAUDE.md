# CLAUDE.md

@AGENTS.md

The above is the tool-agnostic project primer (setup, architecture,
commands, conventions) — read it first. Everything below is specific to
working in this repo with Claude Code.

## Automation already in place

- **`.claude/settings.json`** (committed, shared) configures two hooks:
  - A `PostToolUse` hook runs `ruff check --fix` + `ruff format` on every
    `.py` file after `Write`/`Edit`/`MultiEdit`. You generally don't need to
    run ruff manually after an edit — it already happened. Still run it
    yourself before declaring a task done, since the hook is best-effort
    (non-blocking) and won't surface findings it can't auto-fix
    (e.g. `BLE001`/`SLF001` need a `# noqa` comment, not a formatter).
  - A `PreToolUse` hook blocks `Write`/`Edit`/`MultiEdit` on
    `config/local.env` and `config/prod.env` (real, gitignored secrets). If
    you need one of these changed, ask the developer to edit it — don't try
    to work around the block.
- `.claude/settings.local.json` is per-developer and gitignored; don't move
  shared config into it.

## Custom slash commands (`.claude/commands/`)

- `/check` — runs the full lint + test loop (`ruff check`, `ruff format
  --check`, `unittest`). Run this before considering any code change done.
- `/stack-up` / `/stack-down` — bring the local Postgres+Qdrant Docker stack
  up or down (see `docker/docker-compose.yml`).

## Skills (`.claude/skills/`)

- `add-cli-command` — the established pattern for adding a new `cv-ranker`
  subcommand (subparser, `_run_*` handler, config wiring, README update).
  Use this whenever asked to add a new CLI command rather than improvising a
  different structure.
- `local-stack-smoke-test` — how to safely exercise a change against the
  real local Ollama/Qdrant/Postgres stack and clean up any test data
  afterward, without polluting the persistent local dataset.

## House rules for this repo specifically

- This is a solo-developer local project with no CI yet — there is no
  server-side check that will catch a skipped lint/test pass, so actually
  run `/check` (or the equivalent commands) rather than assuming the hook
  covered it.
- Prefer extending an existing `*Client`/`*Store`/`*Settings` class family
  over introducing a new pattern; see `AGENTS.md`'s architecture map.
- When a task involves the LLM (scoring or CV structuring), test against the
  real local Ollama instance when it's running rather than only unit-testing
  the heuristic fallback — several real bugs in this codebase (a crash on
  LLM-fallback error handling, tool-calling not being wired up) were only
  visible when actually exercising the LLM path.
