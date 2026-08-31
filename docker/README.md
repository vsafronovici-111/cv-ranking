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

