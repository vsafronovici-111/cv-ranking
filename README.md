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
- Semantic search over ingested CVs via Qdrant embeddings (`find` command)
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
| `CV_RANKER_EMBEDDING_BASE_URL`| `http://localhost:11434/v1`  | `http://localhost:8000/v1`       |
| `CV_RANKER_EMBEDDING_API_KEY` | `ollama`                     | `EMPTY`                          |
| `CV_RANKER_EMBEDDING_MODEL`   | `qwen3-embedding:4b`         | `Qwen/Qwen3-Embedding-4B`        |
| `CV_RANKER_EMBEDDING_TIMEOUT_SECONDS` | `90`                 | `90`                             |

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

1. **`ingest`** — load CV files from a folder into Postgres as `PENDING` (deduped by content hash; safe to re-run). Unless `--no-embeddings` is passed, each new CV is also sent to the LLM to extract a structured `{summary, technologies, experience}` view (see [Structured CV chunking](#structured-cv-chunking-ingest)), and each of those three pieces is embedded and stored as its own point in Qdrant.
2. **`process`** — claim `PENDING`/`FAILED` rows one at a time, mark them `PROCESSING`, score them (LLM or heuristic), then mark `SUCCEEDED` or `FAILED`. Re-running `process` automatically retries anything still `FAILED`.
3. **`report`** — print ranked results for all `SUCCEEDED` CVs.

There's also a **`status`** command to see counts per status, and a **`find`** command to semantically search the CVs already embedded into Qdrant during `ingest` (independent of the `cvs` table/queue above).

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

# Semantic search: embed criteria text and find similar CVs in Qdrant
PYTHONPATH=src python3 -m cv_ranker find \
  --criteria "Minimum 5 years of experience, required skills: Java, Spring Boot, Kafka, PostgreSQL, MongoDB, Redis" \
  --top-k 10
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

### Structured CV chunking (`ingest`)

Rather than embedding the whole raw CV text as one vector, `ingest` first
asks the LLM (via `cv_ranker.llm_client.LLMClient.generate_tool_call`, forcing
a `record_cv_structure` tool call — see `cv_ranker.cv_structurer`) to extract:

```json
{
  "summary": "Senior level Software engineer proficient in many programming languages like Java, Go, ...",
  "technologies": ["PostgreSQL", "MongoDB", "Redis", "..."],
  "experience": "13 years"
}
```

Each of the three fields is then embedded and stored as its own point in the
`cv_embeddings` Qdrant collection, so a CV normally yields up to three points
(a section is skipped if the LLM returns it empty). Every point's payload
carries `cv_id` (the Postgres `cvs.id`), `cv_file_name`, and `chunk_type`
(`summary` | `technologies` | `experience`) so results can be traced back to
the CV — and the section — they came from.

### Semantic search (`find`)

`find` embeds a free-text criteria string with the same embedding model used
during `ingest`, then queries the `cv_embeddings` collection in Qdrant for the
closest-matching chunks by cosine similarity. It only needs Qdrant + the
OpenAI-compatible embedding server (Ollama or vLLM) reachable — it does not
touch Postgres or the `cvs` table, so it works independently of
`process`/`report`.

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
PYTHONPATH=src python3 -m cv_ranker find \
  --criteria "Minimum 5 years of experience, required skills: Java, Spring Boot, Kafka, PostgreSQL, MongoDB, Redis" \
  --top-k 10 \
  --output json
```

Each result carries the payload stored at ingestion time: `cv_id` (the
Postgres `cvs.id`), `cv_file_name`, and `chunk_type`, plus the similarity
`score`. Because each CV can contribute up to three chunks, the same CV may
appear more than once in the results (e.g. matching on both `summary` and
`technologies`).

## REST API

A minimal [FastAPI](https://fastapi.tiangolo.com) app under `src/api/rest/`
exposes conversations/messages over HTTP, backed by the same
`cv_ranker.db.CVStore` Postgres store as the CLI — migrations
(`db/migrations/*.sql`) are applied automatically on every API startup, the
same way the CLI applies them on every invocation.

Run it (requires Postgres running, see [Database setup](#database-setup)):

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
python3 -m pip install -e .
PYTHONPATH=src python3 -m uvicorn api.rest.app:app --port 8000
```

CORS is enabled for `http://localhost:3000` (the `web/` frontend's dev
server). Delete endpoints are intentionally not implemented for either
resource.

### Health check

`GET /`

```bash
curl http://localhost:8000/
```

### Conversations

`POST /conversations` — create a conversation.

```bash
curl -X POST http://localhost:8000/conversations \
  -H 'Content-Type: application/json' \
  -d '{"user_id": "user-42", "name": "First chat"}'
```

`GET /conversations?user_id=...` — list a user's conversations.

```bash
curl "http://localhost:8000/conversations?user_id=user-42"
```

`GET /conversations/{conversation_id}` — get a single conversation.

```bash
curl http://localhost:8000/conversations/1
```

`PATCH /conversations/{conversation_id}` — rename a conversation.

```bash
curl -X PATCH http://localhost:8000/conversations/1 \
  -H 'Content-Type: application/json' \
  -d '{"name": "Renamed chat"}'
```

### Messages

`POST /conversations/{conversation_id}/messages` — add a message to a conversation.

```bash
curl -X POST http://localhost:8000/conversations/1/messages \
  -H 'Content-Type: application/json' \
  -d '{"role": "user", "content": "Hello!"}'
```

`GET /conversations/{conversation_id}/messages` — list a conversation's messages.

```bash
curl http://localhost:8000/conversations/1/messages
```

`GET /messages/{message_id}` — get a single message.

```bash
curl http://localhost:8000/messages/1
```

`PATCH /messages/{message_id}` — edit a message's content.

```bash
curl -X PATCH http://localhost:8000/messages/1 \
  -H 'Content-Type: application/json' \
  -d '{"content": "Hello, edited!"}'
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
- Both Ollama and vLLM are used through the same `cv_ranker.llm_client.LLMClient` (built on the `openai` SDK's `chat.completions.create`) and `cv_ranker.embedding_client.EmbeddingClient` (built on `embeddings.create`), so switching backends is a config change, not a code change.
- Reasoning models like `qwen3:14b` emit chain-of-thought tokens before the final answer, so per-candidate latency can be several seconds to ~1 minute depending on CV length; scoring many CVs in `llm`/`auto` mode runs sequentially and can take a while.
- For production use, you can improve scoring by adding weighted requirements and hard filters.




