# AI CV Ranker (Ollama locally, vLLM in production)

Python CLI agent that reads CV files from a folder and ranks candidates from `0` to `100` against user requirements.

- `100`: best match
- `0`: no meaningful match

It uses an **OpenAI-compatible chat client** (the official `openai` SDK) so the exact same code path works against:

- **Local:** [Ollama](https://ollama.com) at `http://localhost:11434/v1` (default, model `qwen3:14b`)
- **Prod:** [vLLM](https://docs.vllm.ai)'s OpenAI-compatible server (any URL/model you configure)

## Features

- Reads CV files from one folder (`.txt`, `.md`, `.docx`, `.pdf`)
- LLM-based scoring via any OpenAI-compatible endpoint (Ollama or vLLM)
- Heuristic fallback when the LLM server is unavailable
- Structured output with score, matched/missing skills, and reasoning
- JSON or human-readable text output
- Environment-based config (`local`/`prod`) resolved from env vars, with `local` as the safe default

## Quick Start

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -e .
```

Optional PDF parser:

```bash
python3 -m pip install "pypdf>=4.0.0"
```

### Database setup

Easiest: run Postgres via Docker Compose (see [`docker/README.md`](docker/README.md)):

```bash
cd docker
docker compose up -d
```

This starts Postgres 16 with the `cvranker` database already created,
persisting data to `docker/volume/postgres` (gitignored) so it survives
container restarts. It matches the default `CV_RANKER_DB_DSN` in
`config/local.env.example`: `postgresql://postgres:postgres@localhost:5432/cvranker`.

Alternatively, use any local/existing Postgres install — just create the
database yourself:

```bash
createdb cvranker
```

Schema changes live as plain, ordered SQL files in `db/migrations/*.sql` (see
[`db/migrations/README.md`](db/migrations/README.md)). They're applied by
`CVStore.init_schema()` every time the CLI starts (idempotent, safe to
re-run) and are reused as-is by the db-layer unit tests in `tests/test_db.py`
so the schema under test always matches production/local.

## Configuration (local vs prod)

Settings are resolved by `cv_ranker.config.load_llm_settings()`, backed by
[`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

Which **environment profile** (`local` or `prod`) is picked, in order:

1. `--env` CLI flag (`local` or `prod`)
2. `CV_RANKER_ENV` environment variable
3. Defaults to `local`

Once the environment is picked, pydantic-settings resolves each field with this priority:

1. Environment variables (e.g. `CV_RANKER_MODEL`)
2. The matching `config/<env>.env` dotenv file, if present (`config/local.env` or `config/prod.env`, auto-loaded — no manual `source` needed)
3. The field defaults below

| Env var                      | Local default               | Prod default                    |
|-------------------------------|------------------------------|----------------------------------|
| `CV_RANKER_BASE_URL`          | `http://localhost:11434/v1`  | `http://localhost:8000/v1`       |
| `CV_RANKER_API_KEY`           | `ollama`                     | `EMPTY`                          |
| `CV_RANKER_MODEL`             | `qwen3:14b`                  | `Qwen/Qwen3-14B`                 |
| `CV_RANKER_TIMEOUT_SECONDS`   | `90`                          | `120`                            |
| `CV_RANKER_DB_DSN`            | `postgresql://postgres:postgres@localhost:5432/cvranker` | (same, override in `config/prod.env`) |

Example config files are provided:

- [`config/local.env.example`](config/local.env.example)
- [`config/prod.env.example`](config/prod.env.example)

Copy and source the one you need (the real `config/local.env` / `config/prod.env` files are gitignored):

```bash
cp config/prod.env.example config/prod.env
# edit config/prod.env with your real vLLM URL/key/model/DB DSN
```

CLI flags always win over environment variables: `--model`, `--base-url`, `--api-key`, `--timeout`, `--dsn`.

## Run

The CLI is split into three stages backed by the `cvs` table so you can ingest once, score independently (and retry only failures), and report at any time:

1. **`ingest`** — load CV files from a folder into Postgres as `PENDING` (deduped by content hash; safe to re-run).
2. **`process`** — claim `PENDING`/`FAILED` rows one at a time, mark them `PROCESSING`, score them (LLM or heuristic), then mark `SUCCEEDED` or `FAILED`. Re-running `process` automatically retries anything still `FAILED`.
3. **`report`** — print ranked results for all `SUCCEEDED` CVs.

There's also a **`status`** command to see counts per status.

Local (Ollama, default):

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank

# 1. Ingest CV files into the database
PYTHONPATH=src python3 -m cv_ranker ingest --cv-folder tests/fixtures/cvs

# 2. Score all PENDING/FAILED CVs
PYTHONPATH=src python3 -m cv_ranker process \
  --requirements "Minimum 5 years of experience, required skills: Java, Spring Boot, Kafka, PostgreSQL, MongoDB, Redis" \
  --mode auto

# 3. Print ranked results
PYTHONPATH=src python3 -m cv_ranker report --output text

# Check status counts
PYTHONPATH=src python3 -m cv_ranker status
```

Prod (vLLM):

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
PYTHONPATH=src python3 -m cv_ranker --env prod ingest --cv-folder tests/fixtures/cvs
PYTHONPATH=src python3 -m cv_ranker --env prod process \
  --requirements "Minimum 5 years of experience, required skills: Java, Spring Boot, Kafka, PostgreSQL, MongoDB, Redis" \
  --mode auto
PYTHONPATH=src python3 -m cv_ranker --env prod report --output text
```

If the LLM server is not running, use deterministic mode:

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
PYTHONPATH=src python3 -m cv_ranker process \
  --requirements "Minimum 5 years of experience, required skills: Java, Spring Boot, Kafka, PostgreSQL, MongoDB, Redis" \
  --mode heuristic
```

Retry only the CVs that failed scoring (e.g. after fixing the LLM server or a parsing issue):

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
PYTHONPATH=src python3 -m cv_ranker process \
  --requirements "..." \
  --only-failed
```

JSON output:

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
PYTHONPATH=src python3 -m cv_ranker report --output json
```

## Test

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
PYTHONPATH=src python3 -m unittest discover -s tests -p "test_*.py"
```

DB-layer tests (`tests/test_db.py`) automatically spin up a real, throwaway
Postgres container via [testcontainers-python](https://testcontainers-python.readthedocs.io/)
(the same pattern as Testcontainers in Java/Go) — just have Docker running,
no manual database, Docker Compose, or env vars needed for tests:

```bash
python3 -m pip install -e ".[test]"
PYTHONPATH=src python3 -m unittest tests.test_db -v
```

## Notes

- PDF extraction requires `pypdf`.
- `.docx` extraction works without extra dependencies.
- Both Ollama and vLLM are used through the same `cv_ranker.llm_client.LLMClient` (built on the `openai` SDK's `chat.completions.create`), so switching backends is a config change, not a code change.
- Reasoning models like `qwen3:14b` emit chain-of-thought tokens before the final answer, so per-candidate latency can be several seconds to ~1 minute depending on CV length; scoring many CVs in `llm`/`auto` mode runs sequentially and can take a while.
- For production use, you can improve scoring by adding weighted requirements and hard filters.




