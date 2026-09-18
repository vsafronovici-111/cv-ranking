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

### Kafka setup

The REST API publishes a Kafka event every time a chat message is created.
`docker compose up -d` (same compose file as Postgres/Qdrant) also starts a
single-node Kafka broker (KRaft mode, no ZooKeeper) on `localhost:9092`, plus
[Kafka UI](https://github.com/provectus/kafka-ui) on
[http://localhost:8081](http://localhost:8081) for browsing topics/messages.
It matches the default `CV_RANKER_KAFKA_BOOTSTRAP_SERVERS` in
`config/local.env.example`.

### Redis setup

The consumer publishes an `ai-model-response` pub/sub event every time an
assistant reply is persisted (see
[Chat message events (Kafka)](#chat-message-events-kafka)). `docker compose
up -d` (same compose file as Postgres/Qdrant/Kafka) also starts Redis on
`localhost:6379`, plus
[Redis Commander](https://github.com/joeferner/redis-commander) on
[http://localhost:8082](http://localhost:8082) for browsing keys/channels.
It matches the default `CV_RANKER_REDIS_URL` in `config/local.env.example`.

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
| `CV_RANKER_LOG_LEVEL`         | `DEBUG`                      | `INFO`                           |
| `CV_RANKER_KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092`       | (override in `config/prod.env`)  |

Example config files are provided:

- [`config/local.env.example`](config/local.env.example)
- [`config/prod.env.example`](config/prod.env.example)

Copy and source the one you need (the real `config/local.env` / `config/prod.env` files are gitignored):

```bash
cp config/prod.env.example config/prod.env
# edit config/prod.env with your real vLLM URL/key/model/DB DSN
```

CLI flags always win over environment variables: `--model`, `--base-url`, `--api-key`, `--timeout`, `--dsn`.

### Logging

`cv_ranker.logging_config.configure_logging()` configures the root logger's
level from `load_logging_settings()` — resolved the same way as the other
settings (`CV_RANKER_LOG_LEVEL` env var, or `config/<env>.env`), defaulting
to `DEBUG` locally and `INFO` in prod. Both the CLI (`main()`) and the REST
API (its startup `lifespan`) call it once at process startup. It currently
just logs to stderr via `logging.basicConfig`; the intent is to swap in
centralized log shipping (e.g. a log aggregator) later by changing only
this one function, not every call site.

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
same way the CLI applies them on every invocation. Creating a message also
publishes it to Kafka — see [Chat message events (Kafka)](#chat-message-events-kafka).

Run it (requires Postgres and Kafka running, see [Database setup](#database-setup)
and [Kafka setup](#kafka-setup)):

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

### Chat message events (Kafka)

Every `POST /conversations/{conversation_id}/messages` call also publishes
the created message as a JSON event to the `chat-messages` Kafka topic, via
`kafka.producer.chat_message_producer.ChatMessageProducer` (an `aiokafka`
producer, started once at API startup and stopped at shutdown — see
`src/api/rest/app.py`'s `lifespan`). Requires the Kafka broker running (see
[Kafka setup](#kafka-setup)).

`kafka.consumer.chat_message_consumer.ChatMessageConsumer` subscribes to `chat-messages`:

- On a `role: "user"` event, it loads that conversation's earlier messages,
  calls the LLM for a reply (idempotently, tracked via the `message_responses`
  table keyed by `message.id`), and publishes the reply back to
  `chat-messages` as a `role: "assistant"` event.
- On a `role: "assistant"` event, it persists it as a new row in `messages`.

Both of the above retry up to 3 total attempts (1-second backoff between
each) before giving up. On the 3rd failure, the original event is published
to `chat-messages-dlt` (wrapped with `error`/`attempts`/`failed_at` context)
and the offset is committed as normal — a permanently-broken event no longer
blocks the topic, it just stops being retried. There's no consumer reading
`chat-messages-dlt` yet; inspect it via Kafka UI (see
[Kafka setup](#kafka-setup)) for now.

The API's `lifespan` starts it automatically — as an `asyncio` task sharing
the API's event loop — alongside the producer, and stops it cleanly on
shutdown, so it needs no separate process for local dev. Its DB/LLM calls
are synchronous, so each is offloaded via `asyncio.to_thread` to avoid
blocking that event loop while one message is being processed.

It can still be run as its own standalone process (e.g. to scale consumption
independently of the API in a real deployment):

```bash
PYTHONPATH=src python3 -m kafka
```

Don't run the standalone process *and* the API at the same time against the
same Kafka broker unless you also give it a distinct `group_id` (hardcoded
as `"chat-message-consumer"` in `kafka/consumer/chat_message_consumer.py`) —
the `chat-messages` topic has a single partition, so two consumers sharing
one group id will silently split it: only one of them will ever receive
messages, and the other will sit idle.

### AI model response notifications (Redis pub/sub)

After `ChatMessageConsumer._on_ai_model_response` successfully persists an
assistant reply, it publishes that same payload to the `ai-model-response`
Redis channel via
`redis_pubsub.producer.redis_pubsub_producer.RedisPubSubProducer`. This is a
plain fire-and-forget pub/sub notification (no retry/DLT, no idempotency
tracking, no durability once published) — it's a lightweight hook for
anything that wants to react to a finished assistant reply in real time,
separate from the durable `messages` row Postgres already holds.

`redis_pubsub.consumer.redis_pubsub_consumer.RedisPubSubConsumer` subscribes
to that channel and logs each message it receives. Like the Kafka consumer,
the API's `lifespan` starts and stops it automatically as an `asyncio` task
sharing the API's event loop, so it needs no separate process for local dev.
Requires Redis running (see [Redis setup](#redis-setup)).

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




