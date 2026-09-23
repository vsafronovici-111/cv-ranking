# AGENTS.md

Instructions for any AI coding agent (Claude Code, Cursor, Aider, Codex, etc.)
working in this repository. Tool-specific instructions live in their own
files (e.g. `CLAUDE.md` for Claude Code) and build on top of this one.

## What this project is

A CLI (`cv-ranker`) that ingests candidate CVs, scores them against job
requirements with an LLM (or a heuristic fallback), and supports semantic
search over ingested CVs. It targets two interchangeable OpenAI-compatible
backends: **Ollama** locally, **vLLM** in production — same code path for
both chat completions and embeddings.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -e ".[test,dev,pdf]"
```

Local backing services (Postgres + Qdrant) run via Docker Compose:

```bash
cd docker && docker compose up -d
```

Ollama must be running separately on the host (`ollama serve`) with a chat
model (e.g. `qwen3:14b`) and an embedding model (e.g. `qwen3-embedding:4b`)
pulled — see the README's Quick Start for full details.

`config/local.env` holds local dev config (Qdrant/DB credentials pointing at
the local Docker stack) and is tracked directly in git — edit it in place,
there's no `.env.example` template for it. An optional `config/local.env.local`
(gitignored, not required to exist) layers on top for personal-only
overrides — any key it sets wins over the same key in `config/local.env`
(see `cv_ranker/config.py`'s `_LOCAL_ENV_FILES`). `config/prod.env` holds
real production secrets, stays gitignored, and is copied from
`config/prod.env.example`; **never edit `config/prod.env` programmatically**
— ask the developer to edit it by hand.

## Architecture map

| Module | Responsibility |
|---|---|
| `cli.py` | argparse entry point; one `_run_<command>` function per subcommand |
| `config.py` | pydantic-settings classes resolving `local`/`prod` env config |
| `db.py` | Postgres-backed durable queue (`cvs` table, PENDING/PROCESSING/SUCCEEDED/FAILED) |
| `llm_client.py` | OpenAI-SDK wrapper for chat completions, incl. forced tool-calling (`generate_tool_call`) |
| `embedding_client.py` | OpenAI-SDK wrapper for `/v1/embeddings`, same pattern as `llm_client.py` |
| `cv_structurer.py` | Uses `llm_client` to extract `{summary, technologies, experience}` from CV text via a forced `record_cv_structure` tool call |
| `qdrant_store.py` | Stores/searches CV chunk embeddings in Qdrant (`cv_embeddings` collection) |
| `ranker.py` | `CVRanker.score_candidate`: LLM scoring with heuristic fallback |
| `parsing.py` | Extracts text from `.txt`/`.md`/`.docx`/`.pdf` |

Every external-service wrapper (`llm_client`, `embedding_client`,
`qdrant_store`, `db`) defines its own `*Error` exception and a small
`*Config`/`*Settings` dataclass — follow this pattern for new integrations
rather than introducing a different error-handling style.

## Data flow (`ingest`)

1. Raw CV bytes are stored in Postgres (`cvs` table), deduped by content hash.
2. The CV text is parsed, then sent to the LLM (`cv_structurer.extract_cv_structure`)
   to get `{summary, technologies, experience}`.
3. Each non-empty field is embedded independently and stored as its own point
   in the `cv_embeddings` Qdrant collection, with payload
   `{cv_id, cv_file_name, chunk_type}` (`chunk_type` is `summary` |
   `technologies` | `experience`).
4. `find` embeds a free-text query and returns the closest chunks — so a
   single CV can appear multiple times in results (once per matching chunk).

## Commands

```bash
PYTHONPATH=src python3 -m cv_ranker ingest --cv-folder <dir>
PYTHONPATH=src python3 -m cv_ranker process --requirements "..." --mode auto
PYTHONPATH=src python3 -m cv_ranker report --output text
PYTHONPATH=src python3 -m cv_ranker status
PYTHONPATH=src python3 -m cv_ranker find --criteria "..." --top-k 10
```

See the README for the full flag reference and local/prod examples.

## Testing and linting

```bash
.venv/bin/ruff check --fix .
.venv/bin/ruff format .
PYTHONPATH=src .venv/bin/python3 -m unittest discover -s tests -p "test_*.py"
```

`tests/test_db.py` needs Docker (spins up a throwaway Postgres via
testcontainers); `tests/test_ranker.py` needs neither Docker nor a live LLM
(it exercises heuristic scoring).

Ruff is configured in `pyproject.toml` (`select = ["E","F","I","UP","B","BLE","SLF","RUF"]`).
`BLE001` (bare `except Exception`) and `SLF001` (reaching into another
module's `_private` members) are intentionally enabled — if you need to
suppress either, add a `# noqa: CODE - <reason>` comment rather than
disabling the rule, matching the existing style in `parsing.py`/`cli.py`.

## Conventions

- No comments unless they explain a non-obvious *why* (a workaround, an
  invariant, a subtle constraint) — never restate what the code already says.
- Don't add abstractions, config flags, or error handling for cases that
  can't happen; match the existing minimal style of each module.
- New env-driven settings follow the `config.py` `*SettingsBase` /
  `Local*Settings` / `Prod*Settings` pattern (see `EmbeddingSettingsBase` for
  the most recent example) — not ad hoc `os.environ.get()` calls.
- New CLI subcommands follow the existing `_run_<command>` pattern in
  `cli.py` (see the `find` command for the most recent example): a
  subparser in `build_parser()`, a dedicated `_run_*` function, and a README
  update in the same change.

## Known rough edges

- `tests/fixtures/cvs/` and `tests/fixtures/cvs2/` may carry local,
  uncommitted edits to the fixture CV text (check `git status`/`git diff`
  before assuming `tests/test_ranker.py` failures are caused by your change —
  fixture content drift has caused false failures before).
