# Docker

## Postgres (local `cvranker` database)

Starts a Postgres 16 container with the `cvranker` database, persisting data
to `docker/volume/postgres` (gitignored) so it survives container restarts.

```bash
cd docker
docker compose up -d
```

Default connection (matches `config/local.env.example`'s `CV_RANKER_DB_DSN`):

```
postgresql://postgres:postgres@localhost:5432/cvranker
```

Schema is applied automatically by the CLI on startup via
[`db/migrations/`](../db/migrations) (`CVStore.init_schema()`) — no manual
`psql` step needed.

Stop / remove:

```bash
cd docker
docker compose down       # stop, keep data
docker compose down -v    # stop and wipe the named container (data on host volume is untouched)
```

To fully reset the database, stop the container and delete the contents of
`docker/volume/postgres/` (everything except `.gitkeep`).

## Qdrant (vector database for embeddings)

Starts a [Qdrant](https://qdrant.tech) container for storing/searching CV
embeddings, persisting data to `docker/volume/qdrant/qdata` (gitignored) so
it survives container restarts. Started together with Postgres via the same
`docker compose up -d` command above (both services are defined in
`docker/docker-compose.yml`).

Default endpoints:

```
REST/HTTP: http://localhost:6333
gRPC:      localhost:6334
```

Authentication: the container requires an API key (`QDRANT__SERVICE__API_KEY`
in `docker-compose.yml`), enforced identically on **both** the REST and gRPC
interfaces — matches `CV_RANKER_QDRANT_API_KEY` in `config/local.env`.
Generate your own with `openssl rand -hex 32` and keep both files in sync.

Quick health check (unauthenticated — `/healthz` is exempt from the API key):

```bash
curl http://localhost:6333/healthz
```

Quick authenticated check (should succeed with the key, `403` without it):

```bash
curl -H "api-key: <your-key>" http://localhost:6333/collections
```

To fully reset the vector store, stop the container and delete the contents
of `docker/volume/qdrant/qdata/` (everything except `.gitkeep`).

## Kafka (chat message events)

Starts a single-node [Kafka](https://kafka.apache.org) broker in KRaft mode
(no ZooKeeper), persisting data to `docker/volume/kafka` (gitignored), plus
[Kafka UI](https://github.com/provectus/kafka-ui) for browsing topics.
Started together with Postgres/Qdrant via the same `docker compose up -d`
command above.

Default endpoints:

```
Broker:   localhost:9092
Kafka UI: http://localhost:8081
```

Matches the default `CV_RANKER_KAFKA_BOOTSTRAP_SERVERS` in
`config/local.env.example`. The REST API publishes to (and
`src/consumer/chat_message_consumer.py` consumes from) the `chat-messages`
topic; topics are auto-created on first publish, no manual setup needed.

To fully reset Kafka, stop the container and delete the contents of
`docker/volume/kafka/` (everything except `.gitkeep`).

